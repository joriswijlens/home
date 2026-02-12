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
- Grafana, Loki, Prometheus (monitoring stack)

## Network Configuration

### Ethernet Setup (Ubuntu 24.04)

**Issue**: When imaging Ubuntu Server 24.04 with Raspberry Pi Imager and configuring WiFi during the imaging process, the resulting cloud-init configuration only includes WiFi - eth0 is not configured for DHCP and won't get an IPv4 address.

**Symptoms**:
- eth0 shows as UP but has no IPv4 address (only IPv6)
- System connects via WiFi instead of ethernet
- `ip addr show eth0` shows no `inet` line

**Root Cause**: Raspberry Pi Imager's cloud-init configuration only includes the WiFi network configured during imaging. Ethernet must be manually added to netplan afterwards.

**Solution Applied**:
- Netplan configured with both eth0 (primary, metric 100) and wlan0 (fallback, metric 600)
- eth0 and wlan0 MAC addresses configured for stable interface naming
- Configuration file: `/etc/netplan/01-netcfg.yaml`
- Cloud-init network management disabled: `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg`

**Current Status**:
- Primary connection via ethernet (eth0)
- WiFi configured as automatic failover
- All traffic routes through eth0 (lower metric = higher priority)

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

## Monitoring Stack

Grafana + Loki + Prometheus for centralized logging and metrics. Remote nodes (EC2) push data over WireGuard.

| Service | Port | Purpose |
|---------|------|---------|
| Grafana | 3000 | Dashboard UI |
| Loki | 3100 | Log aggregation (push API) |
| Prometheus | 9090 | Metrics (remote-write receiver) |

### Deploy Configuration

```bash
cd infrastructure/jupiter/ansible/
ansible-playbook -i inventory.ini copy-config.yml
```

### Start Stack

```bash
docker context use jupiter
cd infrastructure/jupiter/
docker compose up -d
docker context use default
```

### Endpoints

- Grafana: `http://jupiter.local:3000`
- Loki push API: `http://<jupiter-wireguard-ip>:3100/loki/api/v1/push`
- Prometheus remote-write: `http://<jupiter-wireguard-ip>:9090/api/v1/write`

### Retention

- Loki: 6 months (4320h)
- Prometheus: 6 months / 50GB max

### Configuration Files

- `docker-compose.yml` - service definitions
- `loki-config/loki.yml` - Loki storage and retention config
- `prometheus-config/prometheus.yml` - Prometheus config
- `grafana-config/grafana.ini` - Grafana settings
- `grafana-config/provisioning/datasources/datasources.yml` - auto-provisioned data sources

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