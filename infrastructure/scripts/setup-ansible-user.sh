#!/bin/bash

# Script to set up ansible user on the Raspberry Pi
# This script should be run on the target machine (mars) as a user with sudo privileges
# Usage: ./setup-ansible-user.sh

set -e  # Exit on error

echo "Setting up ansible user on this machine..."

# Check if script is run with sudo privileges
if [ "$EUID" -ne 0 ]; then
    echo "This script needs sudo privileges. Running with sudo..."
    exec sudo "$0" "$@"
fi

# Get the original user who invoked sudo
ORIGINAL_USER="${SUDO_USER:-$USER}"

echo "Creating ansibleuser..."
if id "ansibleuser" &>/dev/null; then
    echo "User 'ansibleuser' already exists, skipping user creation."
else
    useradd -m ansibleuser
    echo "User 'ansibleuser' created."
fi

echo "Adding ansibleuser to sudo group..."
usermod -aG sudo ansibleuser

echo "Creating .ssh directory for ansibleuser..."
mkdir -p /home/ansibleuser/.ssh

echo "Copying authorized_keys from $ORIGINAL_USER to ansibleuser..."
if [ -f "/home/$ORIGINAL_USER/.ssh/authorized_keys" ]; then
    cp /home/$ORIGINAL_USER/.ssh/authorized_keys /home/ansibleuser/.ssh/
    echo "Authorized keys copied successfully."
else
    echo "Warning: /home/$ORIGINAL_USER/.ssh/authorized_keys not found!"
    echo "You will need to manually add SSH keys to /home/ansibleuser/.ssh/authorized_keys"
fi

echo "Setting correct permissions..."
chmod 700 /home/ansibleuser/.ssh
chmod 600 /home/ansibleuser/.ssh/authorized_keys 2>/dev/null || true
chown -R ansibleuser:ansibleuser /home/ansibleuser/.ssh

echo "Configuring passwordless sudo for ansibleuser..."
echo "ansibleuser ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ansibleuser
chmod 440 /etc/sudoers.d/ansibleuser
echo "Passwordless sudo configured."

echo ""
echo "✓ Ansible user setup complete!"
echo ""
echo "You can now test SSH login with:"
echo "  ssh ansibleuser@$(hostname).local"
echo ""
echo "Or if using IP address:"
echo "  ssh ansibleuser@$(hostname -I | awk '{print $1}')"
