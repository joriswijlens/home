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

## Known Issues & Future Improvements

### Local Hostname Resolution

**Issue**: VPN clients cannot resolve local hostnames (e.g., `saturn`, `mars.local`) by default.

**Current Workaround**: Add entries to `/etc/hosts` on client devices:
```bash
# On Linux/Mac clients:
sudo nano /etc/hosts

# Add:
192.168.2.79    saturn
192.168.2.37    venus
# etc...
```

**Permanent Solution** (TODO): Deploy dnsmasq or Pi-hole as a Docker Compose service on Saturn to provide DNS for VPN clients:
1. Create `services/dnsmasq/` or use Pi-hole
2. Configure it to:
   - Listen on WireGuard interface (wg0, 10.8.0.1)
   - Resolve local hostnames for all infrastructure servers
   - Forward other queries to public DNS (1.1.1.1, 1.0.0.1)
3. Update wg-easy DNS settings to point clients to `10.8.0.1`
4. Recreate VPN client configs with new DNS setting

This would allow all VPN clients to automatically resolve local hostnames without manual configuration.

## Related Infrastructure Changes

- **Venus**: Added `network-config` Ansible role to enable eth0 interface with DHCP