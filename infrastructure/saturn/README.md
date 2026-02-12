# Saturn - WireGuard VPN Server

## Hardware
- Raspberry Pi 3 Model B Rev 1.2
- 1GB RAM

## Operating System
- Debian Bookworm

## Services
- **wg-easy v15.1**: WireGuard VPN with web UI management
  - Web UI: http://saturn:51821 (HTTP only, `INSECURE=true` for LAN access)
  - VPN Port: UDP 51820
- **dnsmasq 2.90**: Lightweight DNS server for VPN clients
  - Listens on: 10.8.0.1:53 (WireGuard interface)
  - Resolves local hostnames for infrastructure servers

## Setup Summary

Successfully deployed wg-easy v15.1 on Saturn with the following:
- ✅ Docker Compose setup with proper IPv6 sysctls
- ✅ Kernel modules mounted (`/lib/modules`) for ip6_tables support
- ✅ HTTP access enabled for local network management
- ✅ WireGuard interface `wg0` running
- ✅ Docker context created for remote deployment via SSH
- ✅ VPN clients configured and tested

**Note**: v15 moved from environment variable configuration to web-based setup wizard

## Initial Setup

1. **Deploy to Saturn** (using Docker context):
   ```bash
   # One-time: Create Docker context (already created)
   docker context create saturn --docker "host=ssh://joris@saturn"

   # Deploy
   docker context use saturn
   cd infrastructure/saturn
   docker compose up -d

   # View logs
   docker compose logs -f

   # Switch back to local context
   docker context use default
   ```

2. **Access web UI for first-time setup**:
   - URL: `http://saturn:51821`
   - Complete the setup wizard in the web UI:
     - Set your public IP/domain
     - Configure admin password
     - Add VPN clients

## Firewall Configuration

Ensure your router/firewall forwards these ports to Saturn:
- **UDP 51820**: WireGuard VPN traffic
- **TCP 51821**: Web UI (optional, only if accessing remotely)

## Client Setup

**Mobile (iOS/Android):**
1. Install WireGuard app from App Store/Play Store
2. In wg-easy web UI, create a new client
3. Scan the QR code with the app

**Desktop (Ubuntu/Linux):**
```bash
sudo apt install wireguard
sudo mv ~/Downloads/your-config.conf /etc/wireguard/wg0.conf
sudo chmod 600 /etc/wireguard/wg0.conf
sudo wg-quick up wg0
```

## Management

**View logs**:
```bash
docker context use saturn
docker compose logs -f wg-easy
docker context use default
```

**Restart service**:
```bash
docker context use saturn
docker compose restart
docker context use default
```

**Reset configuration** (deletes all clients and settings):
```bash
ssh joris@saturn "sudo rm -rf ~/workspaces/smartworkx/home/infrastructure/saturn/data/*"
docker context use saturn
docker compose restart
docker context use default
```

## DNS Configuration

### Local Hostname Resolution

A **dnsmasq** service runs alongside wg-easy to provide DNS resolution for local infrastructure hostnames to VPN clients.

**How it works:**
- dnsmasq listens on the WireGuard interface at `10.8.0.1`
- Forwards DNS queries to KPN router (192.168.2.254) for local hostname resolution
- Falls back to Cloudflare DNS (1.1.1.1, 1.0.0.1) for public domains
- Automatically appends `.home` domain to short hostnames (e.g., `mars` → `mars.home`)
- Router resolves all local hostnames: `mars`, `jupiter`, `venus`, `saturn`

**Setup:**

DNS is automatically configured via `WG_DEFAULT_DNS=10.8.0.1` in docker-compose.yml. All new VPN clients will automatically use dnsmasq for DNS resolution.

1. **Deploy both services** (using Docker context):
   ```bash
   docker context use saturn
   cd infrastructure/saturn
   docker compose up -d
   docker compose logs -f
   docker context use default
   ```

2. **For existing VPN clients** - update to use new DNS:
   - Option A: In wg-easy web UI (`http://saturn:51821`), edit each client and change DNS to `10.8.0.1`
   - Option B: Delete and recreate clients (they'll automatically get `10.8.0.1` DNS)

3. **Test DNS resolution** (from VPN client):
   ```bash
   # Should resolve to local IPs via KPN router:
   nslookup mars 10.8.0.1
   nslookup jupiter 10.8.0.1
   nslookup saturn 10.8.0.1

   # Should resolve via Cloudflare:
   nslookup google.com 10.8.0.1
   ```

   **Note**: Use short hostnames (`mars`, `jupiter`) without the `.local` suffix. The `.local` domain uses mDNS which doesn't work over traditional DNS forwarding.

**Configuration:**
- `dnsmasq-config/dnsmasq.conf` - Main dnsmasq configuration
  - Forwards to KPN router (192.168.2.254) for local hostnames
  - No manual IP mapping needed - router handles it automatically

**Logging:**
Query logging is enabled by default for debugging. To disable, comment out `log-queries` in `dnsmasq.conf`.

## Related Infrastructure Changes

- **Venus**: Added `network-config` Ansible role to enable eth0 interface with DHCP