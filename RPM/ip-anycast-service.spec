Name:           ip-anycast-service
Version:        1.0.0
Release:        1%{?dist}
Summary:        BIRD Anycast Manager based on health checks
License:        MIT
URL:            https://ark-networks.net/ip-anycast-service
Source0:        %{name}-%{version}.tar.gz
# Assumes the source code (tar.gz) contains files in the following structure
# ./etc/ip-anycast/ip-anycast.conf
# ./etc/ip-anycast/bird.template
# ./usr/sbin/ip-anycast-manager
# ./usr/lib/systemd/system/ip-anycast.service

BuildArch:      noarch
BuildRequires:  systemd-rpm-macros

# Dependencies for RHEL/CentOS
# Assumes bird is installed from EPEL repository or similar
Requires:       bird
Requires:       bash
Requires:       iproute
Requires:       nmap-ncat
Requires:       bind-utils
Requires:       chrony
Requires:       curl
Requires:       systemd

%description
Manages IP Anycast interface (dummy) and generates BIRD configuration
dynamically based on application health checks.

%prep
%setup -q

%install
# Create directories
mkdir -p %{buildroot}/etc/ip-anycast
mkdir -p %{buildroot}/usr/sbin
mkdir -p %{buildroot}/usr/lib/systemd/system

# Install files (copy contents of tar.gz to buildroot)
install -m 644 etc/ip-anycast/ip-anycast.conf %{buildroot}/etc/ip-anycast/ip-anycast.conf
install -m 644 etc/ip-anycast/bird.template %{buildroot}/etc/ip-anycast/bird.template
install -m 755 usr/sbin/ip-anycast-manager %{buildroot}/usr/sbin/ip-anycast-manager
install -m 644 usr/lib/systemd/system/ip-anycast.service %{buildroot}/usr/lib/systemd/system/ip-anycast.service

%files
# Configuration files are not overwritten on update; .rpmnew files are created instead
%config(noreplace) /etc/ip-anycast/ip-anycast.conf
%dir /etc/ip-anycast
/etc/ip-anycast/bird.template
/usr/sbin/ip-anycast-manager
/usr/lib/systemd/system/ip-anycast.service

%post
%systemd_post ip-anycast.service

%preun
%systemd_preun ip-anycast.service

%postun
%systemd_postun_with_restart ip-anycast.service

%changelog
* Sun Dec 7 2025 akamio <kamio_akira@ark-networks.net> - 1.0.0-1
- Initial release
