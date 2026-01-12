# Session Summary: 2026-01-10 - Ethernet Configuration & Monitoring Setup

## Overview
This session focused on two main objectives:
1. Setting up Uptime Kuma monitoring with Signal notifications
2. Diagnosing and fixing ethernet connectivity issues on Ubuntu 24.04 Raspberry Pi servers

## Part 1: Uptime Kuma & Signal API Setup

### Services Added
- **Uptime Kuma**: Self-hosted monitoring tool (port 3001)
- **Signal CLI REST API**: Signal notification service (port 8081, changed from default 8080 due to conflict)

### Implementation
- Added both services to `services/docker-compose.yml`
- Used `network_mode: host` pattern consistent with existing infrastructure
- Created service directories with `service.yml` configuration files
- Added development overrides to `docker-compose.dev.yml`

### Deployment Process
Standard deployment workflow:
1. Backup with Ansible playbook
2. Deploy configuration with `copy-config.yml`
3. Start services via Docker Compose
4. Link Signal account via QR code at API endpoint
5. Configure Uptime Kuma to use Signal API for notifications

## Part 2: Ethernet Connectivity Issues

### Problem Discovery
Both Raspberry Pi 5 servers running Ubuntu Server 24.04 had ethernet interfaces (eth0) that were UP but without IPv4 addresses. Systems were connecting via WiFi instead of ethernet.

**Symptoms:**
- eth0 showed UP but only IPv6 addresses
- No IPv4 address assigned to eth0
- System routing all traffic through WiFi (wlan0)
- Docker virtual ethernet interfaces (veth*) visible in logs, initially suspected as cause

### Root Cause Analysis
After investigation, discovered the actual issue was **not Docker-related**:

**Real Cause:** Raspberry Pi Imager's cloud-init configuration
- When configuring WiFi during imaging with RPi Imager, it creates a cloud-init netplan with **only WiFi configured**
- No eth0 configuration included in `/etc/netplan/50-cloud-init.yaml`
- Docker's virtual interfaces were just noise - not interfering with eth0

**Key Insight:** Both servers had identical issue because they were imaged with the same WiFi-only cloud-init setup.

### Solution Implemented

#### Manual Fix Process (tested on Jupiter first)
1. Backed up existing netplan configs
2. Read existing WiFi configuration from cloud-init
3. Created new netplan config (`/etc/netplan/01-netcfg.yaml`) with:
   - eth0 configured with DHCP and MAC address matching
   - Existing WiFi configuration preserved
   - Proper metric priorities (eth0: 100, wlan0: 600)
4. Disabled cloud-init network management
5. Created udev rules for stable interface naming
6. Removed old systemd network configs causing parse errors
7. Applied netplan changes and restarted systemd-networkd

#### Verification
- Rebooted server to test persistence
- Confirmed eth0 obtained IPv4 via DHCP
- Verified routing table prioritized eth0 (metric 100) over wlan0 (metric 600)
- WiFi remained as automatic failover

#### Results
- Network performance improvement immediately noticeable
- Sub-millisecond local latency vs 5-20ms on WiFi
- SSH connections instant with no lag
- WiFi preserved as automatic failover if cable unplugged

### Automation: Shared Ansible Role

Created reusable Ansible role at `infrastructure/ansible/roles/network-config/`:

**Features:**
- Automatically detects eth0 MAC address
- Reads and preserves existing WiFi configuration from cloud-init
- No hardcoded credentials
- Merges WiFi config with new eth0 configuration
- Sets proper metric priorities
- Creates stable interface naming with udev rules
- Handles edge cases (missing WiFi config, cable unplugged, etc.)

**Integration:**
- Added role to both server setup playbooks
- Runs before docker-host role
- Future server deployments automatically get proper ethernet config

**Testing:**
- Successfully applied to second server
- One server had physical cable issue (NO-CARRIER) - resolved by reseating cable
- Role correctly detected link, applied config, and prioritized eth0

## Documentation Updates

Updated server README files with:
- Description of the issue and root cause
- Symptoms to watch for
- Solution applied (specific to Jupiter)
- Reference to Ansible role (for others)
- Clarification that Docker virtual interfaces are not the cause

## Technical Details

### Network Metric Priorities
- **metric 100**: Primary interface (eth0) - all traffic routes here
- **metric 600**: Fallback interface (wlan0) - only used if primary fails
- Lower metric = higher priority in Linux routing

### Files Created/Modified
- `/etc/netplan/01-netcfg.yaml` - New unified network config
- `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg` - Disables cloud-init networking
- `/etc/udev/rules.d/70-persistent-net.rules` - Stable interface naming
- `infrastructure/ansible/roles/network-config/` - Reusable role
- Server-specific documentation files

### Key Commands Used
```bash
# Check interface status
ip addr show eth0
ip link show eth0

# Check link detection
ethtool eth0 | grep "Link detected"

# Verify routing
ip route show
ip route get 1.1.1.1

# Check network state
networkctl status eth0
```

## Lessons Learned

1. **RPi Imager WiFi config creates WiFi-only setup** - Always check netplan after imaging if WiFi was configured during the process

2. **Docker virtual interfaces are normal** - The veth* interfaces and bridge networks are expected Docker behavior and don't interfere with physical interfaces

3. **Physical layer matters** - Always verify cable connectivity (LED lights, ethtool) before diving into configuration

4. **Preserve existing configs** - Reading and merging existing WiFi config instead of hardcoding is more maintainable and reusable

5. **Infrastructure as Code** - Creating a shared Ansible role ensures consistency and makes future deployments easier

## Outcome

Both servers now running optimally:
- Primary connectivity via Gigabit ethernet
- WiFi configured as automatic failover
- Monitoring infrastructure ready for deployment
- Reusable automation for future servers
- Improved network performance and reliability
