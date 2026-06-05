# Water Source Strategy

**Status:** proposed

## Context

Two possible sources for irrigation:
- **Rainwater**: free, captured from downpipes, requires storage.
- **Tap**: mains, unlimited, treated drinking water, no storage required.

Storage hardware (above-ground barrels vs underground tank vs none) is
a separate decision. This ADR is about **source selection logic**,
independent of how (or whether) storage is realised.

## Decision

When both are available, prefer rainwater; fall back to tap
automatically:

```
source = tap if (force_tap OR rainwater_unavailable) else rainwater
```

`rainwater_unavailable` means either no storage installed, or
installed storage below a configurable level threshold. Switchback to
rainwater uses hysteresis (e.g. fall below 15 %, restore above 25 %).

Plumbing realisation: tap and rainwater outlets join via a tee; the
tap branch has a check valve to prevent back-feed. A Zigbee-switched
solenoid on the tap branch is HA-controlled.

Manual overrides: `input_boolean.irrigation_force_tap`,
`input_boolean.irrigation_pause_all`.

## Consequences

- Source selection is automatic — no operator vigilance.
- The logic also covers the "no storage yet" case: with no storage,
  `rainwater_unavailable` is permanently true and tap is the sole
  source. Adding storage later does not change this ADR.
- Tap fallback prevents pump dry-running once a pump is installed.
- Specific storage product, dimensions, and inlet hardware live in a
  separate ADR + `docs/design/irrigation.md`.
