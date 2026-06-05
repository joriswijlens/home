# Balcony Served From Garden Pump

**Status:** proposed

## Context

The balcony has ~20 potted plants and needs irrigation. It has **no
mains outlet**, so any electronics there would require a self-contained
solar+battery power system. Initial designs went down that path: own
solar panel, LiFePO4 battery, DC switch board, DC pump, balcony
reservoir.

The garden also gets a pump (for its own zones) sourced from the
barrel bank (see [Water Source ADR](2026-05-18-water-source-strategy.md)).
A modest 230 V garden pump easily handles the head to reach the balcony.

Cost and comfort matter alongside the technical fit:
- Independent balcony stack (solar + battery + DC pump + reservoir +
  DIY switch board) is ~€400 and a meaningful build effort.
- A tube up the facade + the existing garden pump is ~€20 of extra PE
  tubing.
- Independent balcony stack means a second system to maintain: refill
  reservoir, monitor battery, manage two HA schedules. Garden-fed
  means one system, one dashboard, one refill discipline.

## Decision

The balcony is **served from the garden irrigation system**, not an
independent system. A tube runs from the garden's drip mainline up the
facade to a drip line on the balcony. The garden pump and barrel bank
supply both garden and balcony; the balcony waters whenever the garden
mainline is pressurised.

No electronics, no pump, no reservoir, no solar+battery on the
balcony.

## Consequences

- **Cost**: ~€20 of PE tubing vs ~€400 for an independent balcony
  stack. ~€380 saved.
- **No manual reservoir filling on the balcony**: the original design
  had the user carrying a hose up to a 300 L balcony reservoir. Garden-
  fed eliminates this chore entirely — rainwater capture is automatic
  via the downpipes into the garden bank.
- **Comfort**: one system to maintain instead of two — one dashboard,
  one refill discipline, no battery or DIY firmware to babysit.
- Eliminates a whole parallel sub-system (solar, battery, DC pump,
  reservoir, DIY switch board) — fewer parts, less to fail.
- Single rainwater source (the garden barrel bank) serves both garden
  and balcony.
- The balcony loses independence: if the garden pump or controller is
  down, the balcony loses water too. Accepted for simplicity.
- A PE tube runs visibly along the facade. Aesthetic trade-off; can be
  clipped alongside an existing downpipe.
- The garden pump must be sized for worst-case head + flow including
  the balcony route (typically a small premium — most garden pumps
  handle 15-30 m head, balcony is ~3-6 m).
- Balcony and garden water on the same schedule. If per-plant timing
  becomes a problem, the upgrade path is per-zone control (separate
  decision).
