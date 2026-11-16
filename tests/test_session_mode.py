"""Exercise configuration loading and real BIRD parsing without network changes."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "ip-anycast-service"
MANAGER = PACKAGE / "usr/sbin/ip-anycast-manager"
CONFIG = PACKAGE / "etc/ip-anycast/ip-anycast.conf"
TEMPLATE = PACKAGE / "etc/ip-anycast/bird.template"


class SessionModeTest(unittest.TestCase):
    def setUp(self):
        if os.geteuid() != 0:
            self.skipTest("Run as root to exercise the config ownership check")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config = self.directory / "config"
        self.template = self.directory / "template"
        self.output = self.directory / "bird.conf"
        self.marker = self.directory / "network-touched"
        self.template.write_text(TEMPLATE.read_text())
        script = MANAGER.read_text().replace(
            'CONFIG_FILE="/etc/ip-anycast/ip-anycast.conf"',
            f'CONFIG_FILE="{self.config}"',
        ).replace(
            'TEMPLATE_FILE="/etc/ip-anycast/bird.template"',
            f'TEMPLATE_FILE="{self.template}"',
        )
        self.manager = self.directory / "manager"
        self.manager.write_text(script)
        self.library = self.directory / "functions"
        self.library.write_text(script.split("# --- Main Execution Logic ---")[0])
        fakebin = self.directory / "bin"
        fakebin.mkdir()
        fake_ip = fakebin / "ip"
        fake_ip.write_text(f'#!/bin/sh\ntouch "{self.marker}"\nexit 1\n')
        fake_ip.chmod(0o755)
        self.env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}")

    def configure(self, mode=None):
        config = re.sub(r"^BGP_SESSION_MODE=.*\n", "", CONFIG.read_text(), flags=re.M)
        if mode is not None:
            config += f'\nBGP_SESSION_MODE="{mode}"\n'
        self.config.write_text(config)
        self.config.chmod(0o644)

    def generate(self):
        return subprocess.run(
            ["bash", "-c", 'source "$1"; BIRD_CONF="$2"; generate_bird_config',
             "test", str(self.library), str(self.output)],
            capture_output=True, text=True, env=self.env,
        )

    def assert_valid(self, mode):
        self.configure(mode)
        result = self.generate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIsNotNone(shutil.which("bird"), "Install BIRD to validate generated configs")
        subprocess.run(["bird", "-p", "-c", str(self.output)], check=True)
        text = self.output.read_text()
        self.assertNotRegex(text, r"__[A-Z_]+__")
        self.assertIn("neighbor 10.0.0.1 as 64512", text)
        self.assertIn("neighbor 10.0.0.2 as 64512", text)
        self.assertIn("interval 200 ms;", text)
        self.assertIn("multiplier 3;", text)
        self.assertFalse(self.marker.exists())
        return text

    def test_unset_keeps_multihop(self):
        text = self.assert_valid(None)
        self.assertIn("    multihop;", text)
        self.assertIn("    multihop {", text)

    def test_explicit_multihop(self):
        text = self.assert_valid("multihop")
        self.assertIn("    multihop;", text)
        self.assertIn("    multihop {", text)

    def test_singlehop_aligns_bgp_and_bfd(self):
        text = self.assert_valid("singlehop")
        self.assertIn("    direct;", text)
        self.assertIn('    interface "*" {', text)
        self.assertNotIn("multihop", text)

    def test_invalid_mode_fails_before_network_changes(self):
        self.configure("invalid")
        result = subprocess.run(["bash", str(self.manager)], capture_output=True,
                                text=True, env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BGP_SESSION_MODE must be singlehop or multihop", result.stderr)
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.output.exists())

    def test_legacy_template_still_supports_default_mode(self):
        self.template.write_text(TEMPLATE.read_text().replace(
            "__BGP_SESSION_DIRECTIVE__", "multihop").replace("__BFD_SESSION_SCOPE__", "multihop"))
        self.assert_valid(None)

    def test_singlehop_rejects_each_missing_template_placeholder(self):
        self.configure("singlehop")
        for placeholder, legacy in [("__BGP_SESSION_DIRECTIVE__", "multihop"),
                                    ("__BFD_SESSION_SCOPE__", "multihop")]:
            with self.subTest(placeholder=placeholder):
                self.template.write_text(TEMPLATE.read_text().replace(placeholder, legacy))
                self.output.write_text("existing configuration\n")
                result = self.generate()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("update the BIRD template", result.stderr)
                self.assertEqual(self.output.read_text(), "existing configuration\n")
                self.assertFalse(self.marker.exists())
                self.assertFalse(Path(str(self.output) + ".tmp").exists())


if __name__ == "__main__":
    unittest.main()
