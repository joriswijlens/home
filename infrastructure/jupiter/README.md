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
- Postgres (shared instance, see [Shared Postgres](#shared-postgres))
- Paperclip (AI agent orchestrator, see [Paperclip](#paperclip))

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

## Shared Postgres

Jupiter runs a single shared `postgres` container (Postgres 16). **Each future
service that needs a relational database creates its own database and role on
this shared instance** — do NOT add a per-service Postgres container.

Conventions:
- One database per service, named after the service (`paperclip`, `foo`, …).
- One login role per service, with the same name, owning that database and
  with privileges scoped to that database only (no cross-database `GRANT`s,
  no superuser).
- Provisioning happens via `postgres-init/NN-<service>.sh` scripts mounted
  into `/docker-entrypoint-initdb.d`. These run **once** on the first
  container start. To apply a new init script to an existing instance, exec
  it manually inside the running container.
- Passwords come from the `.env` file next to `docker-compose.yml`. The
  `paperclip` role's password is `PAPERCLIP_DB_PASSWORD`.

Postgres only listens on `127.0.0.1:5432` — services on the host (or in other
host-networked containers) reach it via loopback. It is **not** exposed on
the LAN or via WireGuard.

### Setup

1. Copy `.env.example` to `.env` and fill in secrets:
   ```bash
   cp .env.example .env
   # generate strong values, e.g.:
   #   openssl rand -base64 32   # POSTGRES_PASSWORD, PAPERCLIP_DB_PASSWORD
   #   openssl rand -base64 48   # BETTER_AUTH_SECRET
   ```
2. Sync to Jupiter (also copies `.env`):
   ```bash
   cd ansible/
   ansible-playbook -i inventory.ini copy-config.yml
   ```
3. On Jupiter, bring services up — bind mounts must resolve on jupiter, so
   run `docker compose` from there (not via `DOCKER_CONTEXT` on the laptop):
   ```bash
   ssh joris@jupiter
   cd ~/workspaces/smartworkx/home/infrastructure/jupiter
   docker compose up -d postgres   # first start runs postgres-init/*.sh
   docker compose up -d paperclip  # applies Drizzle migrations on first start
   ```

## Paperclip

[Paperclip](https://github.com/paperclipai/paperclip) is an AI agent
orchestration control plane. On Jupiter it runs as a Docker container with
`network_mode: host`, so it is reachable on both the LAN interface (eth0)
and the Saturn WireGuard interface (wg0) without per-IP binds.

| Item | Value |
|------|-------|
| Default port | `4280` (override with `PAPERCLIP_PORT` in `.env`; Paperclip's docs default is `3100`, which collides with Loki on Jupiter) |
| Image | `ghcr.io/paperclipai/paperclip:latest` (multi-arch, pulled by Jupiter; override via `PAPERCLIP_IMAGE`) |
| Deployment mode | `authenticated` (production auth via better-auth) |
| Database | `paperclip` on the shared `postgres` instance (the embedded Postgres in `/paperclip` is **not** used) |
| Persistent volume | `paperclip-data` mounted at `/paperclip` |
| Public URL / trusted origins | `PAPERCLIP_PUBLIC_URL=http://jupiter:4280` plus `jupiter.local`, `jupiter.home`, `localhost` via `PAPERCLIP_ALLOWED_HOSTNAMES` |
| Claude credentials | host `/home/joris/.claude` mounted at `/root/.claude` (only useful once the `claude` CLI ships in Paperclip's image — see Adapter note below) |

> Adapter note: the upstream Dockerfile does **not** install the `claude`
> CLI inside the image. The `claude-local` adapter therefore can't shell
> out to a logged-in CLI from inside the container without a custom
> Dockerfile layer. Until that's added, configure agents to use
> `ANTHROPIC_API_KEY` (set via Paperclip's Secrets API, not as a plain env
> var). Bootstrapping companies/agents is tracked separately.

### Verify reachability

```bash
# From the LAN:
curl -fsS http://jupiter:4280/api/health

# From outside the LAN, with the WireGuard tunnel up (dnsmasq on Saturn at
# 10.8.0.1 resolves `jupiter` to its LAN IP):
curl -fsS http://jupiter:4280/api/health
```

A healthy response:
```json
{"status":"ok","deploymentMode":"authenticated","bootstrapStatus":"bootstrap_pending"}
```

`bootstrap_pending` is expected on a fresh install — see the separate issue
for company/agent bootstrap.

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
  - `/var/lib/vaultwarden/data`
  - `/var/lib/postgres-dumps` (compressed `pg_dump` artifacts)

> The live `postgres-data` Docker volume is **not** synced — copying it under
> concurrent writes produces a torn snapshot. Postgres is backed up via
> `pg_dump` instead (see [Postgres dumps](#postgres-dumps)).

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
        ├── radicale/
        ├── vaultwarden/data/
        └── postgres-dumps/
```

## Postgres dumps

A separate `postgres-dump.timer` runs **every 4 hours, 5 minutes before**
`opencloud-backup.timer`, so a fresh set of dumps lands in
`/var/lib/postgres-dumps/` before the rclone sync ships them off to Scaleway.

The script (`postgres-dump.sh`):
- enumerates every non-template database in the running `postgres` container,
- runs `pg_dump -Fc` (custom/compressed format) inside the container,
- writes `<db>-<UTC-timestamp>.dump` files to `/var/lib/postgres-dumps/`,
- keeps the last 12 dumps per database (~2 days at 4h cadence).

### Manual dump

```bash
sudo /usr/local/bin/postgres-dump.sh
ls -lh /var/lib/postgres-dumps/
```

### Check timer status

```bash
systemctl status postgres-dump.timer
systemctl list-timers postgres-dump.timer opencloud-backup.timer
sudo tail -f /var/log/postgres-dump.log
```

### Restore procedure

To restore one database (e.g. `paperclip`) from a Scaleway dump into a fresh
`postgres` container:

```bash
# 1. Pick the dump to restore from Scaleway and pull it down.
rclone lsf scaleway:jupiter-backup/var/lib/postgres-dumps/ | sort | tail
rclone copy scaleway:jupiter-backup/var/lib/postgres-dumps/paperclip-<TS>.dump /tmp/

# 2. Spin up a scratch Postgres on the host (separate volume!).
docker run -d --name pg-restore \
    -e POSTGRES_PASSWORD=temp \
    -p 127.0.0.1:55432:5432 \
    postgres:16-alpine

# 3. Wait for it to be ready, then create the target DB+role and restore.
docker exec pg-restore psql -U postgres -c "CREATE ROLE paperclip LOGIN PASSWORD 'temp';"
docker exec pg-restore psql -U postgres -c "CREATE DATABASE paperclip OWNER paperclip;"
docker cp /tmp/paperclip-<TS>.dump pg-restore:/tmp/paperclip.dump
docker exec pg-restore pg_restore -U postgres -d paperclip /tmp/paperclip.dump

# 4. Verify, then either point Paperclip at this scratch instance, or
#    pg_dump it back out and load into the production container.
docker exec pg-restore psql -U paperclip -d paperclip -c "\dt"

# 5. Tear down when done.
docker rm -f pg-restore
```

For a real disaster-recovery restore into the production `postgres`, stop the
service consumers (`paperclip`, …), drop and recreate the target DB inside
the production container, then `pg_restore` the dump there:

```bash
docker compose stop paperclip
docker exec -i postgres psql -U postgres -c "DROP DATABASE paperclip;"
docker exec -i postgres psql -U postgres -c "CREATE DATABASE paperclip OWNER paperclip;"
docker exec -i postgres pg_restore -U postgres -d paperclip < /var/lib/postgres-dumps/paperclip-<TS>.dump
docker compose start paperclip
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
- `ansible/files/postgres-dump.sh` - postgres dump script
- `ansible/files/postgres-dump.service` - systemd service
- `ansible/files/postgres-dump.timer` - systemd timer (4h, fires 5m before opencloud-backup)