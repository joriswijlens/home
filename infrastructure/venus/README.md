# Mars Server Setup Guide

This document outlines the physical and initial software setup for the Venus Raspberry Pi 5 server.

My mars server is my family cloud server. It will run:
- Opencloud - file sharing
- Radicale - calendar and contacts
- Vaultwarden - secrets

## Setup

### Requirements
- Raspberry Pi 5 (rpi) with 16GB RAM
- Raspberry Pi SSD with 256GB storage
- SD card
- Computer which can write to the SD card
- Micro HDMI cable or converter micro HDMI to HDMI.
- Usb mouse and keyboard

### Setup Steps
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
    - Log in to rpi `ssh joris@mars.local`
    - `sudo useradd -m ansibleuser`
    - `sudo usermod -aG sudo ansibleuser`
    - `sudo mkdir /home/ansibleuser/.ssh`
    - `sudo cp ~/.ssh/authorized_keys /home/ansibleuser/.ssh/`
    - `sudo chmod 700 /home/ansibleuser/.ssh`
    - `sudo chmod 600 /home/ansibleuser/.ssh/authorized_keys`
    - `sudo chown -R ansibleuser:ansibleuser /home/ansibleuser/.ssh`
    - exit the SSH session
    - `ssh ansibleuser@hmars.local`
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

Removed modem manager:

```bash
sudo systemctl disable ModemManager
```

## References

- https://docs.opencloud.eu/docs/admin/getting-started/container/docker-compose/docker-compose-base
- 