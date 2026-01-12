# Mars Server Setup Guide

## Initial Setup

For the initial Raspberry Pi setup, follow the instructions in [rpi-setup.md](../rpi-setup.md), using `mars` as the hostname.

## Network Configuration

### Ethernet Setup (Ubuntu 24.04)

**Issue**: When imaging Ubuntu Server 24.04 with Raspberry Pi Imager and configuring WiFi during the imaging process, the resulting cloud-init configuration only includes WiFi - eth0 is not configured for DHCP and won't get an IPv4 address.

**Symptoms**:
- eth0 shows as UP but has no IPv4 address (only IPv6)
- System connects via WiFi instead of ethernet
- `ip addr show eth0` shows no `inet` line

**Root Cause**: Raspberry Pi Imager's cloud-init configuration only includes the WiFi network configured during imaging. Ethernet must be manually added to netplan afterwards. Docker's virtual ethernet interfaces (veth*) may appear in logs but are not the cause of the issue.

**Solution**:
Run the Ansible playbook to fix ethernet configuration:
```bash
cd infrastructure/ansible
ansible-playbook -i ../mars/ansible/inventory.ini fix-ethernet-ubuntu2404.yml
```

This playbook will:
- Configure eth0 with DHCP and MAC address matching
- Keep WiFi as automatic failover (or disable it if desired)
- Disable cloud-init network management
- Create stable interface naming with udev rules

**Expected Result**:
- Primary connection via ethernet (eth0)
- WiFi configured as automatic failover (metric 600)
- All traffic routes through eth0 (metric 100)

## Ansible Deployment

- Use Ansible to set up the Raspberry Pi server (install Docker, etc.):
  - Navigate to the ansible directory:
    ```bash
    cd ./ansible/
    ```
  - Run the setup host playbook "once":
    ```bash
    ansible-playbook -i inventory.ini setup-host-playbook.yml
    ```

## Optional Configuration

Removed modem manager:
```bash
sudo systemctl disable ModemManager
```
#### Pre-Deployment Backup 

Before deploying, it's highly recommended to create a backup of your critical service data directly on the remote host. This ensures that if anything goes wrong during deployment, you have a recent snapshot of your configurations and data.

To perform a remote backup using Ansible, navigate to the `infrastructure/mars/ansible` directory and run the `backup_remote_data.yml` playbook:

```bash
ansible-playbook -i inventory.ini backup_remote_data.yml
```

This Ansible playbook will connect to your remote host, create a timestamped backup of your service data directories, and store it in a `backups/` folder within your `services` directory on the remote host.

#### Restoring from Backup

In case of data loss or corruption, you can restore your critical service data from a previous backup using an Ansible playbook.

To restore, navigate to the `infrastructure/mars/ansible` directory and run the `restore_remote_data.yml` playbook, providing the `backup_timestamp` as a variable:

```bash
ansible-playbook -i inventory.ini restore_remote_data.yml -e "backup_timestamp=YYYYMMDD_HHMMSS"
```