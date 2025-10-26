# Girier

## Notes

- Is an end device only, so no router
- Cheap only 6 euros
- No neutral wire needed

## Installation

The device was really simple to pair, just put it in pairing mode and it was discovered by zigbee2mqtt.
The problem seemed to be in the syncing of the physical switch and the state in Home Assistant. After each
toggle in home assistant I needed to toggle the physical switch twice to get the state change.

I think the problem is that the wire from the switch to s1 was not properly connected. After reconnecting it, the
problem was solved.