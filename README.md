# ip-anycast-service

A lightweight service manager that controls an IP Anycast interface and dynamically updates BIRD or FRRouting (FRR) BGP configuration based on application health checks.

## Overview

This service ensures that your Anycast IP address is only advertised to the network when the underlying application service is healthy. It manages a dummy network interface and generates BIRD or FRR configuration files to announce or withdraw routes.

## Features

- **Health Monitoring**: Built-in health checks for common services (HTTP, HTTPS, NTP, DNS, LDAP) and support for custom check commands.
- **Dynamic BGP Announcement**: Automatically reconfigures BIRD or FRR to advertise the Anycast IP when healthy and withdraw it when unhealthy.
- **Selectable Routing Daemon**: Choose BIRD (default) or FRR with `ROUTING_DAEMON`.
- **Interface Management**: Automatically creates and manages a dummy interface for the Anycast IP.
- **BFD Support**: Configurable BFD (Bidirectional Forwarding Detection) settings for fast failure detection.

## Installation

### RHEL / Rocky Linux (RPM)

```bash
# BIRD
sudo dnf install -y epel-release  # Provides BIRD on RHEL/Rocky
sudo dnf install bird ./ip-anycast-service-*.rpm

# FRR (from the base repositories)
sudo dnf install frr ./ip-anycast-service-*.rpm
```

### Debian / Ubuntu (DEB)

```bash
# BIRD
sudo apt-get install ./ip-anycast-service_*.deb

# FRR
sudo apt-get install frr ./ip-anycast-service_*.deb
```

## Configuration

The main configuration file is located at `/etc/ip-anycast/ip-anycast.conf`.

### Basic Settings

| Parameter | Description | Example |
|-----------|-------------|---------|
| `APP_TYPE` | Type of application to monitor (`http`, `https`, `ntp`, `dns`, `ldap`, `custom`) | `ntp` |
| `ANYCAST_CIDR` | The Anycast IP address with CIDR prefix | `192.168.10.1/32` |
| `INTERFACE_NAME` | Name of the dummy interface to create | `anycast0` |

### Routing Daemon

| Parameter | Description | Example |
|-----------|-------------|---------|
| `ROUTING_DAEMON` | Routing daemon to configure (`bird` or `frr`). Defaults to `bird` when unset. | `frr` |

The BGP, BFD, and `BGP_SESSION_MODE` settings below apply to both daemons unless noted.
When switching daemons, stop and disable the one you no longer use so that only one daemon speaks BGP.

### BGP Settings

| Parameter | Description | Example |
|-----------|-------------|---------|
| `ROUTER_ID` | BGP Router ID (usually the host's physical IP) | `10.0.0.5` |
| `LOCAL_AS` | Local Autonomous System number | `65001` |
| `SOURCE_IP` | Source IP for BGP sessions | `10.0.0.5` |
| `NEIGHBORS` | Space-separated list of upstream neighbors (`IP:AS`) | `10.0.0.1:64512 10.0.0.2:64512` |
| `BIRD_CONF` | Path to the generated BIRD configuration file | Debian/Ubuntu: `/etc/bird/bird.conf`; RHEL/Rocky: `/etc/bird.conf` |
| `BIRD_SERVICE` | systemd service name used to start/reload BIRD | `bird` |
| `BIRD_CONTROL_SOCKET` | Optional BIRD control socket for `birdc`; required when `BIRD_SERVICE` is not `bird` | `/run/bird/bird.ctl` |

The `BIRD_*` settings are used only with `ROUTING_DAEMON="bird"`.
If `BIRD_CONF` is set to a non-default path, `BIRD_SERVICE` must point to a dedicated systemd unit that starts BIRD with that same config file. The default `bird` service supports `/etc/bird/bird.conf` on Debian/Ubuntu and `/etc/bird.conf` on RHEL/Rocky. When `BIRD_SERVICE` is not `bird`, set `BIRD_CONTROL_SOCKET` to that daemon's control socket.

### FRR Settings

| Parameter | Description | Example |
|-----------|-------------|---------|
| `FRR_CONF` | Path to the generated FRR integrated configuration file | `/etc/frr/frr.conf` |
| `FRR_SERVICE` | systemd service name used to start/reload FRR | `frr` |

With `ROUTING_DAEMON="frr"`, the manager renders `/etc/ip-anycast/frr.template`, validates it with
`vtysh --dryrun`, replaces the whole `FRR_CONF`, and applies it with `systemctl reload` (which runs
`frr-reload.py`) or starts the service. Keep any other FRR configuration in the template.
The Anycast prefix is announced with a BGP `network` statement, so it is withdrawn when the
service brings the dummy interface down.

Before starting the service with the default `frr` unit:

- Enable `bgpd=yes` and `bfdd=yes` in `/etc/frr/daemons`, then restart `frr`.
- Use the integrated config. On RHEL/Rocky 8, replace `no service integrated-vtysh-config` with
  `service integrated-vtysh-config` in `/etc/frr/vtysh.conf`.

The manager checks both and exits before touching the interface if either is missing.
If `FRR_CONF` is not `/etc/frr/frr.conf`, `FRR_SERVICE` must point to a dedicated unit that loads that file.

Differences from BIRD:

- `BFD_INTERVAL` must convert to whole milliseconds (for example `200 ms` or `1 s`); it sets both the
  receive and transmit intervals.
- `BFD_IDLE_TX` is ignored because FRR has no idle TX interval.
- `BGP_SESSION_MODE="singlehop"` requires eBGP neighbors, because FRR always treats iBGP sessions and
  their BFD as multihop. iBGP neighbors in single-hop mode are rejected.

Tested with FRR 7.5 (RHEL/Rocky 8), 8.5 (RHEL/Rocky 9), 8.1 (Ubuntu 22.04), and 8.4 (Ubuntu 24.04).

### Single-hop and Multihop BGP/BFD

Set `BGP_SESSION_MODE` to select the hop mode for all entries in `NEIGHBORS`:

| Value | BGP | BFD |
| --- | --- | --- |
| `multihop` (default) | `multihop;` | `multihop { ... }` |
| `singlehop` | `direct;` | `interface "*" { ... }` |

With FRR, `multihop` adds `neighbor UPSTREAM ebgp-multihop 255` and BFD follows the BGP hop mode.

For directly connected peers, use:

```sh
BGP_SESSION_MODE="singlehop"
BFD_INTERVAL="200 ms"
BFD_MULTIPLIER="3"
```

Configure the peers for the same BFD hop mode and compatible timers. The existing
`BFD_INTERVAL`, `BFD_IDLE_TX`, and `BFD_MULTIPLIER` settings apply to either mode.
Leaving `BGP_SESSION_MODE` unset preserves the previous multihop behavior. Other
values are rejected before the service changes the interface or BIRD configuration.
A manager instance uses one hop mode for all its neighbors; mixed modes are not supported.

If you maintain a custom `bird.template`, replace the BGP `multihop` keyword with
`__BGP_SESSION_DIRECTIVE__` and the BFD `multihop` block selector with
`__BFD_SESSION_SCOPE__`. Single-hop mode rejects templates missing either placeholder.
Legacy templates remain usable with the default multihop mode.

### Custom Health Check

If `APP_TYPE` is set to `custom`, define your check command:

```bash
CUSTOM_CHECK_CMD="/usr/local/bin/my_check_script.sh"
```
The command should be an executable file path and return exit code `0` for healthy and non-zero for unhealthy.

### Health Check Timing (Optional)

```bash
HEALTHCHECK_TIMEOUT_SECONDS="2"
HEALTHCHECK_INTERVAL_SECONDS="5"
HEALTHCHECK_SUCCESS_THRESHOLD="2"
HEALTHCHECK_FAILURE_THRESHOLD="2"
```

## Usage

Start and enable the service:

```bash
sudo systemctl enable --now ip-anycast
```

Check the status:

```bash
sudo systemctl status ip-anycast
```

View logs:

```bash
journalctl -u ip-anycast -f
```

## Dependencies

- `bird` (BIRD Internet Routing Daemon) or `frr` (FRRouting)
- `bash`
- `iproute2`
- `systemd`
- Service-specific tools: `bind-utils` (DNS), `nmap-ncat` (LDAP), `chrony` (NTP), `curl` (HTTP/HTTPS)

## License

MIT. See [LICENSE](LICENSE).
