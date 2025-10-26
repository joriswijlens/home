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

This playbook creates a compressed backup of the entire `volumes_dir` (`/opt/smartworkx`) on the `mars` host. It also manages old backups, keeping only the last 7 by default.

**Usage:**

```bash
ansible-playbook -i inventory.ini backup_remote_data.yml
```

### `restore_remote_data.yml`

This playbook restores a backup of the `volumes_dir` on the `mars` host. It stops the Docker Compose services, removes the current `volumes_dir`, unarchives the specified backup file (or the latest one if not specified), and then restarts the Docker Compose services.

**Usage:**

To restore the latest backup:

```bash
ansible-playbook -i inventory.ini restore_remote_data.yml
```

To restore a specific backup (e.g., `smartworkx-backup-20251026T141300.tgz`):

```bash
ansible-playbook -i inventory.ini restore_remote_data.yml --extra-vars "backup_file=/opt/backups/smartworkx/smartworkx-backup-20251026T141300.tgz"
```

### `setup-ha-host-playbook.yml`

This playbook is used to set up the Home Assistant host.

**Usage:**

```bash
ansible-playbook -i inventory.ini setup-ha-host-playbook.yml
```

## General Usage

To run any playbook, use the following command:

```bash
ansible-playbook -i inventory.ini <playbook_name>.yml
```