# Mars Ansible Playbooks

This repository contains Ansible playbooks for managing the Mars environment.

## `backup_remote_data.yml`

This playbook backs up critical service data on a remote host.

### Usage

To run the playbook, use the following command:

```bash
ansible-playbook -i inventory.ini backup_remote_data.yml
```

### Variables

*   `user`: The user to own the backup files. Defaults to `joris`.

To override the default user, use the `--extra-vars` flag:

```bash
ansible-playbook -i inventory.ini backup_remote_data.yml --extra-vars "user=another_user"
```
