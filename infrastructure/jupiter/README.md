# Jupiter

## Hardware
- Raspberry Pi 5 Model B Rev 1.1
- 16GB RAM
- 1TB SSD

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