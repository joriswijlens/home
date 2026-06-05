# Irrigation Control Strategy

**Status:** proposed

## Context

Two ways to decide *when and how long* to water:
1. **ET-based** — weather-driven model of soil water loss (Smart
   Irrigation HACS).
2. **Soil moisture-based** — per-zone sensors, water when dry.

Off-the-shelf Zigbee soil sensors are all battery-powered (against
ADR 0007), and DIY mains-powered nodes were rejected for this
iteration. A barrel level sensor (single battery sensor) is in scope —
see [Water Source ADR](2026-05-18-water-source-strategy.md) — but
per-zone soil-moisture sensors are not.

## Decision

**ET-only** via Smart Irrigation HACS. Smart Irrigation drives
scheduling and duration for the single drip system as one logical
zone. Rain skip uses the `weather.home` forecast.

If per-zone control is later added, each physical zone gets its own
Smart Irrigation zone configured the same way — the strategy itself
doesn't change.

Soil-moisture feedback is **not in scope**. If observed performance
shows persistent over- or under-watering across a season, raise a new
ADR proposing sensor-based feedback at that time.

## Consequences

- No wet-skip gate or saturation cut-off — Smart Irrigation duration
  is authoritative.
- Manual override remains via dashboard inputs.
- ET-only has watered conventional gardens reliably for decades; the
  risk is bounded.
- Smart Irrigation models deficit cumulatively, so under-watering one
  day is compensated the next.
