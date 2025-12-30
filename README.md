# ip-anycast-service

A lightweight service manager that controls an IP Anycast interface and dynamically updates BIRD BGP configuration based on application health checks.

## Overview

This service ensures that your Anycast IP address is only advertised to the network when the underlying application service is healthy. It manages a dummy network interface and generates BIRD configuration files to announce or withdraw routes.

## Features

- **Health Monitoring**: Built-in health checks for common services (HTTP, HTTPS, NTP, DNS, LDAP) and support for custom check commands.
- **Dynamic BGP Announcement**: Automatically reconfigures BIRD to advertise the Anycast IP when healthy and withdraw it when unhealthy.
- **Interface Management**: Automatically creates and manages a dummy interface for the Anycast IP.
- **BFD Support**: Configurable BFD (Bidirectional Forwarding Detection) settings for fast failure detection.

## Installation

### RHEL / Rocky Linux (RPM)

```bash
sudo dnf install ./ip-anycast-service-*.rpm
```

### Debian / Ubuntu (DEB)

```bash
sudo dpkg -i ./ip-anycast-service_*.deb
sudo apt-get install -f  # Install missing dependencies
```

## Configuration

The main configuration file is located at `/etc/ip-anycast/ip-anycast.conf`.

### Basic Settings

| Parameter | Description | Example |
|-----------|-------------|---------|
| `APP_TYPE` | Type of application to monitor (`http`, `https`, `ntp`, `dns`, `ldap`, `custom`) | `ntp` |
| `ANYCAST_CIDR` | The Anycast IP address with CIDR prefix | `192.168.10.1/32` |
| `INTERFACE_NAME` | Name of the dummy interface to create | `anycast0` |

### BGP Settings

| Parameter | Description | Example |
|-----------|-------------|---------|
| `ROUTER_ID` | BGP Router ID (usually the host's physical IP) | `10.0.0.5` |
| `LOCAL_AS` | Local Autonomous System number | `65001` |
| `SOURCE_IP` | Source IP for BGP sessions | `10.0.0.5` |
| `NEIGHBORS` | Space-separated list of upstream neighbors (`IP:AS`) | `10.0.0.1:64512 10.0.0.2:64512` |

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

- `bird` (BIRD Internet Routing Daemon)
- `bash`
- `iproute2`
- `systemd`
- Service-specific tools: `bind-utils` (DNS), `nmap-ncat` (LDAP), `chrony` (NTP), `curl` (HTTP/HTTPS)

## License

MIT
