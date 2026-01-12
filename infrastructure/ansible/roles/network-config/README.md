# Network Config Role

Ansible role to fix ethernet connectivity on Ubuntu 24.04 Server when imaged with Raspberry Pi Imager.

## Problem

When using Raspberry Pi Imager to create an Ubuntu Server 24.04 image and configuring WiFi during the imaging process, the resulting cloud-init configuration only includes WiFi. The ethernet interface (eth0) is not configured for DHCP and won't get an IPv4 address.

## Solution

This role:
1. Reads existing WiFi configuration from cloud-init
2. Adds eth0 configuration with DHCP
3. Preserves WiFi as automatic failover
4. Disables cloud-init network management
5. Creates stable interface naming with udev rules

## Usage

### In a playbook

```yaml
---
- hosts: raspberrypi
  become: true
  roles:
    - network-config
```

### Standalone playbook

Create a playbook like `fix-network.yml`:

```yaml
---
- hosts: all
  become: true
  roles:
    - network-config
```

Run it:

```bash
ansible-playbook -i ../mars/ansible/inventory.ini fix-network.yml
ansible-playbook -i ../jupiter/ansible/inventory.ini fix-network.yml
```

## Result

- eth0: Primary interface with DHCP (metric 100)
- wlan0: Fallback interface (metric 600)
- All traffic routes through ethernet
- WiFi automatically takes over if ethernet fails

## Variables

No variables required - the role automatically:
- Detects eth0 MAC address
- Preserves existing WiFi configuration
- Works on any Ubuntu 24.04 Server installation

## Files Created/Modified

- `/etc/netplan/01-netcfg.yaml` - New netplan config with eth0 + WiFi
- `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg` - Disables cloud-init networking
- `/etc/udev/rules.d/70-persistent-net.rules` - Stable interface naming
- `/etc/netplan/backup/` - Backup of original configs

## Tested On

- Ubuntu Server 24.04 LTS
- Raspberry Pi 4 Model B (Mars)
- Raspberry Pi 5 Model B (Jupiter)
