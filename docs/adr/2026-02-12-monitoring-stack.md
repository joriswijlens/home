# Monitoring Stack

## Context
We need centralized logging and metrics collection for our infrastructure, including EC2 instances in the depot project. The monitoring stack should run on our own hardware to maintain privacy and zero-cost operation, receiving logs and metrics pushed from remote nodes over WireGuard.

## Decision
We deploy Grafana + Loki + Prometheus on Jupiter (Pi 5, 16GB RAM, 1TB SSD) as a push-based monitoring stack:

- **Loki** receives logs via its push API (`/loki/api/v1/push`)
- **Prometheus** receives metrics via remote-write (`/api/v1/write`)
- **Grafana** provides the dashboard UI with both data sources auto-provisioned
- **Grafana Alloy** on remote nodes (EC2) pushes data over WireGuard

This avoids exposing services to the internet — all traffic flows through the WireGuard VPN.

## Consequences
- All logs and metrics are stored on our own hardware (privacy, no SaaS costs)
- 6-month retention for both logs and metrics (estimated 50-140GB total)
- Jupiter needs sufficient disk space shared with OpenCloud on the 1TB SSD
- Remote nodes need WireGuard connectivity to push data
- No pull-based scraping needed — simplifies firewall rules
