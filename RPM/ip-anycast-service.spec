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
# ./lib/systemd/system/ip-anycast.service
# ./LICENSE

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
mkdir -p %{buildroot}%{_unitdir}

# Install files (copy contents of tar.gz to buildroot)
install -m 644 etc/ip-anycast/ip-anycast.conf %{buildroot}/etc/ip-anycast/ip-anycast.conf
install -m 644 etc/ip-anycast/bird.template %{buildroot}/etc/ip-anycast/bird.template
install -m 755 usr/sbin/ip-anycast-manager %{buildroot}/usr/sbin/ip-anycast-manager
install -m 644 lib/systemd/system/ip-anycast.service %{buildroot}%{_unitdir}/ip-anycast.service

# EPEL's BIRD package uses /etc/bird.conf with the default bird.service.
sed -i 's|^BIRD_CONF=.*|BIRD_CONF="/etc/bird.conf"|' %{buildroot}/etc/ip-anycast/ip-anycast.conf

%files
# Configuration files are not overwritten on update; .rpmnew files are created instead
%license LICENSE
%config(noreplace) /etc/ip-anycast/ip-anycast.conf
%dir /etc/ip-anycast
/etc/ip-anycast/bird.template
/usr/sbin/ip-anycast-manager
%{_unitdir}/ip-anycast.service

%post
if [ -f /etc/ip-anycast/ip-anycast.conf ] && grep -qx 'BIRD_CONF="/etc/bird/bird.conf"' /etc/ip-anycast/ip-anycast.conf; then
    sed -i 's|^BIRD_CONF="/etc/bird/bird.conf"$|BIRD_CONF="/etc/bird.conf"|' /etc/ip-anycast/ip-anycast.conf
fi
%systemd_post ip-anycast.service

%preun
%systemd_preun ip-anycast.service

%postun
%systemd_postun_with_restart ip-anycast.service

%changelog
* Sun Dec 7 2025 akamio <kamio_akira@ark-networks.net> - 1.0.0-1
- Initial release
