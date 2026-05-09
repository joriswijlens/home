# Paperclip on Jupiter, on a Shared Postgres

## Context
We want an AI agent orchestration control plane for the home infrastructure
(Companies → Agents → Tasks → Heartbeats → Budgets → Approvals). Paperclip is
the chosen tool. It needs Node 20+ and a Postgres database. It is the first
service on Jupiter that needs a relational database — Opencloud, Radicale,
Vaultwarden, and the monitoring stack do not.

Where to host:
- **Mars** is the home automation hub and is already at a comfortable load;
  we do not want to mix general-purpose container workloads onto it.
- **Venus** (Pi 3, 1GB RAM) is too small for a Node app + Postgres.
- **Old laptop** that previously ran Minion is dead.
- **Jupiter** (Pi 5, 16GB RAM, 1TB SSD) has the headroom and is on UPS-grade
  always-on power.

How to provision the database:
- Per-service Postgres containers are simple to start with but quickly
  multiply on-disk footprint, backup surface, and tuning work.
- A single shared Postgres with one DB + role per service trades a tiny bit
  of blast-radius coupling for far less operational overhead, and matches
  how every traditional self-hosted setup with multiple Rails/Node/etc apps
  works.

How to back it up:
- Copying the live `postgres-data` Docker volume to S3 with rclone is unsafe:
  files change under the syncer and the resulting snapshot is unrestorable.
- `pg_dump -Fc` produces a consistent, compressed, restorable artifact.

## Decision
- Run **Paperclip** on **Jupiter** as a Docker container with `network_mode:
  host`, reachable on both the LAN interface and the Saturn WireGuard
  interface. Pull the multi-arch image from
  `ghcr.io/paperclipai/paperclip:latest` (the upstream OSS repo, not the
  `paperclipinc/paperclip` managed-hosting fork). Run in `authenticated`
  deployment mode with a generated `BETTER_AUTH_SECRET`, and register
  `PAPERCLIP_PUBLIC_URL` + `PAPERCLIP_ALLOWED_HOSTNAMES` so better-auth
  trusts requests from `jupiter`, `jupiter.local`, and via the WireGuard
  hostname.
- Run a **single shared Postgres 16 container** on Jupiter, listening on
  `127.0.0.1:5432` only. Each future Jupiter service that needs an RDB
  creates **its own database and its own login role** on this shared
  instance, with privileges scoped to that database (no cross-DB grants, no
  superuser). Provisioning is done via `postgres-init/NN-<service>.sh`
  scripts.
- Back up Postgres via a **`pg_dump` job** that runs every 4 hours, 5
  minutes before the existing `opencloud-backup.timer`. Compressed dumps
  land in `/var/lib/postgres-dumps/`, which the existing rclone job then
  ships to Scaleway. The live `postgres-data` Docker volume is **not**
  rclone'd.

## Out of scope (to revisit)
- The `claude-local` adapter expects to shell out to a logged-in `claude`
  CLI. The upstream Dockerfile does not currently install that CLI, so the
  Claude Max subscription path requires a custom image layer. Until that
  lands, configure agents with `ANTHROPIC_API_KEY` (via the Secrets API).
  Tracked separately from the install task.

## Consequences
- One Postgres to monitor, tune, upgrade, and back up — instead of N.
- Lower disk footprint than per-service Postgres containers.
- A bad query in one service's role can't reach another service's data, but
  CPU/IO contention and major-version upgrades are now shared concerns.
- Major Postgres upgrades require coordinating all dependent services at
  once. Acceptable at the current scale (1–3 services).
- Backups are point-in-time-consistent (per dump) and restorable into any
  Postgres 16 container, on or off Jupiter.
- Worst-case data loss between dumps is up to 4 hours. Acceptable for this
  workload; if it ever isn't, switch the affected DB to WAL archiving.
- Paperclip is reachable over WireGuard from outside the LAN, which is
  required for remote operation but means Paperclip's own auth must hold up.
