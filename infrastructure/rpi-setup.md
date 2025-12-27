# Setup Steps

- Physically mounted SSD on the Raspberry Pi
- Prepared SD card with rpi os (rpi os has rpi-imager installed). I want to use rpi-imager ui to set server image on ssd
  https://www.raspberrypi.com/documentation/computers/getting-started.html#raspberry-pi-imager
- Boot rpi with the SD card, with the monitor, mouse, and keyboard connected
- Use the rpi-imager to install ubuntu server LTS on the SSD
- Remove the SD card and boot the Raspberry Pi
- Ubuntu server will boot from the SSD
- Name the rpi `mars` and set a user (e.g., `joris`)
- Connect with <username>@mars.local or <username>@<ip-address> via SSH
- If you are using a Mac, you can use the terminal to connect via SSH:
    - `ssh joris@mars.local`
- You can disconnect the monitor, mouse, and keyboard now, as everything can be done via SSH.
- Get your SSH key and add it to the authorized keys on the Raspberry Pi
    - `ssh-copy-id joris@mars.local`
- Prepare the rpi for Ansible
    - Copy the setup script to the rpi:
      ```bash
      scp infrastructure/scripts/setup-ansible-user.sh joris@<server-name>.local:~/
      ```
    - Log in to rpi `ssh joris@mars.local`
    - Execute the setup script:
      ```bash
      ./setup-ansible-user.sh
      ```
    - exit the SSH session
    - Test the ansible user connection:
      ```bash
      ssh ansibleuser@mars.local
      ```
    - You can now log in as `ansibleuser` via SSH without a password.
    - exit the SSH session

- Use Ansible to set up the Raspberry Pi server (install Docker, etc.):
    - Navigate to the ansible directory:
      ```bash
      cd ./ansible/
      ```
    - Run the setup host playbook "once":
      ```bash
      ansible-playbook -i inventory.ini setup-ha-host-playbook.yml
      ```
