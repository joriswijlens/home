# Infrastructure Management

This directory contains Ansible playbooks for managing the `mars` host infrastructure.

## Playbooks

### `copy-config.yml`

This playbook copies service configurations from the local machine (control host) to the `mars` host. It dynamically discovers service directories, reads their `service.yml` files to determine the `config_dir`, and then synchronizes the configurations. After copying, it restarts the Docker Compose services on the control host to apply the new configurations.

**Usage:**

```bash
ansible-playbook -i inventory.ini copy-config.yml
```

### `backup_remote_data.yml`

This playbook creates a compressed backup of `/opt/smartworkx/volumes` in `/opt/smartworkx/backups` on the `mars` host. It also manages old backups, keeping only the last 7 by default.

**Usage:**

```bash
ansible-playbook -i inventory.ini backup_remote_data.yml
```

### `restore_remote_data.yml`

This playbook restores a backup of `/opt/smartworkx/volumes` on the `mars` host. It stops the Docker Compose services, moves the current volumes aside to `volumes.pre-restore-<timestamp>`, unarchives the specified backup file (or the latest one if not specified), and then starts the services again.

**Usage:**

To restore the latest backup:

```bash
ansible-playbook -i inventory.ini restore_remote_data.yml
```

To restore a specific backup (e.g., `backup-20261101T203520.tgz`):

```bash
ansible-playbook -i inventory.ini restore_remote_data.yml --extra-vars "backup_file=/opt/smartworkx/backups/backup-20261101T203520.tgz"
```

### Scaleway backup script

`files/mars-backup.sh` runs every 6 hours. To deploy only a script change:

```bash
ansible-playbook -i inventory.ini setup-host-playbook.yml --tags backup-script
```

### `setup-ha-host-playbook.yml`

This playbook is used to set up the Home Assistant host.

**Usage:**

```bash
ansible-playbook -i inventory.ini setup-host-playbook.yml
```

## General Usage

To run any playbook, use the following command:

```bash
ansible-playbook -i inventory.ini <playbook_name>.yml
```