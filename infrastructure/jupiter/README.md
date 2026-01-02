# Jupiter

## Hardware
- Raspberry Pi 5 Model B Rev 1.1
- 16GB RAM
- 1TB SSD

## Software
- OS Ubuntu Server 24.04 LTS
- Docker & Docker Compose
- Node.js & npm
- Vim
- Claude CLI
- rclone
- Opencloud

## Ansible Deployment

- Use Ansible to set up the Raspberry Pi server (install Docker, Node.js, Vim, Claude CLI, etc.):
    - Navigate to the ansible directory:
      ```bash
      cd ./ansible/
      ```
    - Run the setup host playbook "once":
      ```bash
      ansible-playbook -i inventory.ini setup-host-playbook.yml
      ```

## Opencloud Configuration

Opencloud is managed using Docker Compose, but the configuration is done **directly on the host** rather than remotely. This approach is used because remote configuration deployment failed.

**Workflow**:
1. SSH into Jupiter:
   ```bash
   ssh joris@jupiter
   ```

2. Clone/checkout this repository on the host:
   ```bash
   git clone <repository-url>
   ```

3. Make configuration changes directly on the host

4. Run Docker Compose on the host:
   ```bash
   docker compose up -d
   ```

## Backup Configuration

Jupiter is configured with automated backups to Scaleway Object Storage using rclone.

### Backup Details

- **Storage Provider**: Scaleway Object Storage
- **Region**: Paris (fr-par)
- **Bucket**: `jupiter-backup`
- **Method**: Incremental sync (only changed files are transferred)
- **Schedule**: Every 4 hours via systemd timer
- **Backed up directories**:
  - `/etc/opencloud`
  - `/var/lib/opencloud`
  - `/var/lib/radicale`

### Setup Credentials

1. SSH into Jupiter:
   ```bash
   ssh joris@jupiter
   ```

2. Create the credentials file:
   ```bash
   sudo nano /root/.scaleway-credentials
   ```

3. Add your Scaleway API credentials:
   ```bash
   export AWS_ACCESS_KEY_ID="your-scaleway-access-key"
   export AWS_SECRET_ACCESS_KEY="your-scaleway-secret-key"
   ```

4. Secure the file:
   ```bash
   sudo chmod 600 /root/.scaleway-credentials
   ```

### Manual Backup

To run a backup manually:
```bash
sudo /usr/local/bin/opencloud-backup.sh
```

### Check Backup Status

View backup timer status:
```bash
systemctl status opencloud-backup.timer
```

View next scheduled backup:
```bash
systemctl list-timers opencloud-backup.timer
```

View backup logs:
```bash
sudo tail -f /var/log/opencloud-backup.log
```

### Bucket Structure

The Scaleway bucket maintains the directory structure:
```
jupiter-backup/
├── etc/
│   └── opencloud/
└── var/
    └── lib/
        ├── opencloud/
        └── radicale/
```

### Restore from Backup

To restore data from Scaleway:
```bash
# Restore specific directory
rclone sync scaleway:jupiter-backup/var/lib/opencloud /var/lib/opencloud

# Or restore all directories
rclone sync scaleway:jupiter-backup/etc/opencloud /etc/opencloud
rclone sync scaleway:jupiter-backup/var/lib/opencloud /var/lib/opencloud
rclone sync scaleway:jupiter-backup/var/lib/radicale /var/lib/radicale
```

### Configuration Files

All backup configuration files are located in:
- `ansible/files/rclone.conf` - rclone configuration
- `ansible/files/opencloud-backup.sh` - backup script
- `ansible/files/opencloud-backup.service` - systemd service
- `ansible/files/opencloud-backup.timer` - systemd timer