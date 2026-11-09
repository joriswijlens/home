---
name: deye-monitoring-best-practices
description: Advise developers on optimizing DeyeCloud OpenAPI call patterns — polling frequency, matching hardware refresh rates, selective endpoints, eliminating redundant calls, staying within QPM rate limits, client-side caching, and device command concurrency. Use when a developer asks how to reduce API calls, avoid HTTP 429 rate limiting, optimize polling intervals, avoid wasting quota, follow DeyeCloud API best practices, prepare for the upcoming usage-metering / quota / rate-limit adjustment, or audit an existing DeyeCloud OpenAPI integration for efficiency.
version: v261109
author: DeyeCloud Portal
---

# DeyeCloud OpenAPI — Monitoring & Call Optimization Best Practices

Optimize a DeyeCloud OpenAPI integration to reduce unnecessary calls and stay within the service's rate limits. Source of truth: the developer portal's "API Usage Best Practices" page.

## Why Optimize

Redundant high-frequency polling consumes shared infrastructure and degrades stability for all developers. Usage metering, quota, and rate-limit controls are being introduced. Most developers are covered by a base quota; optimize to stay safely within it.

Preliminary key figures (subject to change; final rules prevail):
- Base quota: ~100,000 calls/month.
- Rate limit: ~60 QPM (requests per minute).
- Recommended polling interval: 1–2 minutes.

Core principle: reduce unnecessary polling, adopt event-driven responses.

## Right-Size Polling Frequency

Over-polling — fetching data faster than it changes — is the #1 waste source. Inverter/logger data rarely changes by the second.

| Scenario | Recommended interval | Rationale |
|---|---|---|
| Real-time dashboard (live view open) | 1–2 min | User is watching; data still looks fresh |
| Background monitoring (dashboard closed) | 5 min | No one watching; periodic health check |
| Historical daily/weekly reports | Once/day | Historical data doesn't change retroactively |
| Alarm/fault detection | 1–5 min | Catch faults without flooding the API |

Polling every 1–5 seconds for extended periods is the top waste cause. If an integration polls faster than 1 minute, fix that first.

## Match Polling to Hardware Refresh Rates

DeyeCloud loggers upload at fixed hardware-determined intervals. Polling faster than the upload is pure waste (repeated identical data).

- Logger upload interval: real-time data every 1 min or 5 min depending on type/config.
- Historical data: server-side aggregated; fetch once per reporting period.
- Plant-level summaries: cached server-side, refreshed at most every 5 min.

Rule of thumb: set polling interval to the logger's upload interval (or slower). If unsure, 1–2 minutes is safe.

## Fetch Only What You Need

- Cache the plant/device list at startup or login; refresh only on device add/remove.
- Poll device-level data directly by SN instead of the full plant hierarchy each time.
- Query only the time range needed: specify precise start/end for historical data instead of pulling a broad range and filtering client-side.

## Eliminate Redundant Calls

- Parallel requests for the same data: fetch once and share across widgets — don't let each widget call independently.
- Retry storms: on 429 / 5xx, use exponential backoff; never tight-loop retry (it worsens the rate limit).
- Re-fetching on page navigation: cache the last response with a timestamp; if fetched within the polling interval, serve cached.

## Manage QPM

Each application (API key) is subject to a per-minute rate limit. Exceeding it returns HTTP 429 with no valid data. Current limit is visible via API response headers.

- Distribute calls across time: for 100 devices at QPM 60, poll ~1 device/second rather than 100 at once.
- Use a request queue with a rate limiter that spaces requests evenly.
- Batch where possible: prefer batch endpoints (multiple device SNs in one call) over individual calls.

Example: 50 inverters polled every 30 s = 100 QPM (exceeds limit, burns quota). Optimized = stagger 50 calls across 2 min = 25 QPM — same freshness, within limit.

## Client-Side Caching (TTL)

- Real-time data: cache 1–2 min.
- Plant/device list: cache 1 hour or until explicitly invalidated.
- Historical data: cache 24 hours (yesterday won't change).
- Static config (inverter models, firmware info): cache indefinitely until version changes.

## Device Command Concurrency

- A device executes one command at a time. If a second command is sent while the previous is still running, the server rejects it with `2104004 command concurrent running`.

- One command per device at a time: a second command sent while the previous executes is rejected with `2104004 command concurrent running`. (If commands are spaced far enough apart, both succeed because the lock window has closed.)
- Control permission is per-device, not per-station. Not all devices under a station are writable — some return `2101027` (permission denied). Check device-level write access before issuing control commands.
- Queue and retry: implement a client-side queue; confirm the previous command completed before sending the next.
- Check command status via the command-result query endpoint (`GET /v1.0/order/{orderId}`) before issuing the next.

Rapid-fire commands without waiting for confirmation → `2104004` rejection and lost operations.

## Quick Optimization Checklist

- Polling interval ≥ 1 min (1–2 min recommended).
- Cache plant/device list; query by SN, not full hierarchy.
- Stagger device calls across the minute to stay within QPM.
- Use exponential backoff on 429/5xx (no tight-loop retries).
- Apply TTL caching per data type.
- Wait for command confirmation before sending the next command to the same device.

