# Initial Architecture

## Context
We are building a home automation system with Home Assistant and Raspberry Pi. 
We want it to be maintainable, cost effective, reliable, customizable and support smart devices easily.

## Decision
We will use Zigbee2MQTT to manage our Zigbee devices. 
Zigbee2MQTT will run in a Docker container on the same Raspberry Pi as Home Assistant. 
We will use a compatible Zigbee USB adapter (e.g., CC2531, CC2652) to connect Zigbee devices to the Raspberry Pi.
No ZHA is required.

## Consequences
- We benefit from a large community and lots of integrations.
- We rely on the stability of the Raspberry Pi and Home Assistant updates.
