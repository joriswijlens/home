# Relays

## Context
Smart bulbs vs smart switches.

## Decision
Switching to smart switches is a better option for us. We will use Zigbee relays to control the lights. The concept is
to introduce a zigbee connection on every current control point, because it will be transparent to the user.

## Consequences
- Better user experience: Users can continue using their existing wall switches without any changes.
- Cost-effective: Zigbee relays last long and we can reuse existing wiring and switches.
