"""Exercise FRR config generation and preflight checks without network changes."""
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
TEMPLATE = PACKAGE / "etc/ip-anycast/frr.template"


class FrrTest(unittest.TestCase):
    def setUp(self):
        if os.geteuid() != 0:
            self.skipTest("Run as root to exercise the config ownership check")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.config = self.directory / "config"
        self.template = self.directory / "template"
        self.daemons = self.directory / "daemons"
        self.vtysh_conf = self.directory / "vtysh.conf"
        self.output = self.directory / "frr.conf"
        self.marker = self.directory / "network-touched"
        self.template.write_text(TEMPLATE.read_text())
        self.daemons.write_text("zebra=yes\nbgpd=yes\nbfdd=yes\n")
        self.vtysh_conf.write_text("service integrated-vtysh-config\n")
        script = MANAGER.read_text()
        for name, path in [("CONFIG_FILE", self.config),
                           ("FRR_TEMPLATE_FILE", self.template),
                           ("FRR_DAEMONS_FILE", self.daemons),
                           ("FRR_VTYSH_CONF", self.vtysh_conf)]:
            script, count = re.subn(rf'^{name}=".*"$', f'{name}="{path}"', script, flags=re.M)
            self.assertEqual(count, 1, name)
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

    def configure(self, **settings):
        config = CONFIG.read_text()
        settings.setdefault("ROUTING_DAEMON", "frr")
        for name, value in settings.items():
            config = re.sub(rf"^{name}=.*\n", "", config, flags=re.M)
            if value is not None:
                config += f'\n{name}="{value}"\n'
        self.config.write_text(config)
        self.config.chmod(0o644)

    def run_function(self, function):
        return subprocess.run(
            ["bash", "-c", 'source "$1"; FRR_CONF="$2"; ' + function,
             "test", str(self.library), str(self.output)],
            capture_output=True, text=True, env=self.env,
        )

    def assert_valid(self, **settings):
        self.configure(**settings)
        result = self.run_function("generate_frr_config")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = self.output.read_text()
        self.assertNotRegex(text, r"__[A-Z_]+__")
        self.assertIn("router bgp 65001\n", text)
        self.assertIn(" bgp router-id 10.0.0.5\n", text)
        self.assertIn(" neighbor UPSTREAM update-source 10.0.0.5\n", text)
        self.assertIn(" neighbor 10.0.0.1 remote-as 64512\n neighbor 10.0.0.1 peer-group UPSTREAM\n", text)
        self.assertIn(" neighbor 10.0.0.2 remote-as 64512\n neighbor 10.0.0.2 peer-group UPSTREAM\n", text)
        self.assertIn("ip prefix-list ANYCAST_EXPORT seq 10 permit 192.168.10.1/32\n", text)
        self.assertIn("  network 192.168.10.1/32\n", text)
        self.assertIn("  detect-multiplier 3\n", text)
        self.assertFalse(self.marker.exists())
        self.assertFalse(Path(str(self.output) + ".tmp").exists())
        if shutil.which("vtysh"):
            subprocess.run(["vtysh", "--dryrun", "--inputfile", str(self.output)],
                           check=True, capture_output=True)
        return text

    def test_unset_keeps_multihop(self):
        text = self.assert_valid(BGP_SESSION_MODE=None)
        self.assertIn(" neighbor UPSTREAM ebgp-multihop 255\n", text)
        self.assertIn("  receive-interval 200\n  transmit-interval 200\n", text)

    def test_singlehop_omits_multihop(self):
        text = self.assert_valid(BGP_SESSION_MODE="singlehop")
        self.assertNotIn("multihop", text)

    def test_bfd_interval_units(self):
        for value, expected in [("1 s", "1000"), ("50ms", "50"), ("300000 us", "300")]:
            with self.subTest(value=value):
                text = self.assert_valid(BFD_INTERVAL=value)
                self.assertIn(f"  receive-interval {expected}\n", text)

    def test_bfd_idle_tx_not_required(self):
        self.assert_valid(BFD_IDLE_TX=None)

    def test_invalid_bfd_interval_rejected(self):
        for value in ["200", "0.5 s", "1500 us"]:
            with self.subTest(value=value):
                self.configure(BFD_INTERVAL=value)
                result = self.run_function("generate_frr_config")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("BFD_INTERVAL must be a whole number of milliseconds", result.stderr)
                self.assertFalse(self.output.exists())

    def test_singlehop_rejects_ibgp_neighbor(self):
        self.configure(BGP_SESSION_MODE="singlehop", NEIGHBORS="10.0.0.1:65001")
        self.output.write_text("existing configuration\n")
        result = self.run_function("generate_frr_config")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("singlehop with FRR requires eBGP neighbors", result.stderr)
        self.assertEqual(self.output.read_text(), "existing configuration\n")

    def test_preserves_existing_mode(self):
        self.configure()
        self.output.write_text("existing configuration\n")
        self.output.chmod(0o640)
        result = self.run_function("generate_frr_config")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o640)

    def test_invalid_routing_daemon_fails_before_network_changes(self):
        self.configure(ROUTING_DAEMON="quagga")
        result = subprocess.run(["bash", str(self.manager)], capture_output=True,
                                text=True, env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ROUTING_DAEMON must be bird or frr", result.stderr)
        self.assertFalse(self.marker.exists())

    def test_custom_frr_conf_requires_custom_service(self):
        self.configure(FRR_CONF="/tmp/frr-custom.conf")
        result = subprocess.run(["bash", str(self.manager)], capture_output=True,
                                text=True, env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FRR_CONF is set to '/tmp/frr-custom.conf' but FRR_SERVICE is still 'frr'",
                      result.stderr)
        self.assertFalse(self.marker.exists())

    def test_setup_check(self):
        self.configure()
        self.assertEqual(self.run_function("check_frr_setup").returncode, 0)
        for daemons, vtysh, message in [
            ("bgpd=no\nbfdd=yes\n", "service integrated-vtysh-config\n", "bgpd is not enabled"),
            ("bgpd=yes\nbfdd=no\n", "service integrated-vtysh-config\n", "bfdd is not enabled"),
            ("bgpd=yes\nbfdd=yes\n", "no service integrated-vtysh-config\n", "disables the integrated config"),
        ]:
            with self.subTest(message=message):
                self.daemons.write_text(daemons)
                self.vtysh_conf.write_text(vtysh)
                result = self.run_function("check_frr_setup")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_setup_check_failure_stops_before_network_changes(self):
        self.configure()
        self.daemons.write_text("bgpd=no\nbfdd=yes\n")
        script = self.manager.read_text().replace("/etc/frr/frr.conf", str(self.output))
        self.manager.write_text(script)
        result = subprocess.run(["bash", str(self.manager)], capture_output=True,
                                text=True, env=self.env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bgpd is not enabled", result.stderr)
        self.assertFalse(self.marker.exists())


if __name__ == "__main__":
    unittest.main()
