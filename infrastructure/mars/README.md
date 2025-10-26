# Mars Server Setup Guide

This document outlines the physical and initial software setup for the Mars Raspberry Pi 5 server.

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