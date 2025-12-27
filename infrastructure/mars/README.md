# Mars Server Setup Guide

## Initial Setup

For the initial Raspberry Pi setup, follow the instructions in [rpi-setup.md](../rpi-setup.md), using `mars` as the hostname.

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