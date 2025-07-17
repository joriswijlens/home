# Home assistant 

This document outlines the setup and deployment of the Home Assistant application.

## Setup

For initial server setup (OS installation, SSH, Ansible user, Docker, etc.), please refer to the [Mars Server Setup Guide](../../infrastructure/mars/README.md).

### Deployment Steps

- Use Ansible to deploy Home Assistant:
  - Navigate to the `apps/home-assistant/ansible/` directory:
    ```bash
    cd apps/home-assistant/ansible/
    ```
  - Run the playbook, referencing the centralized inventory:
    ```bash
    ansible-playbook -i ../../../infrastructure/mars/ansible/inventory.ini playbook.yml
    ```

### Resources
- [Installing Zigbee2MQTT with Home Assistant](https://www.youtube.com/watch?v=sFSqgiOoPMs)