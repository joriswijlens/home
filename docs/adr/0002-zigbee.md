# Initial Architecture

## Context
We are building a home automation system with Home Assistant. 
We want it to be maintainable, cost effective, reliable, and support smart devices easily.

## Decision
We will use Zigbee for our smart devices. Zigbee is a low-power, wireless mesh network standard that is widely supported by many smart home devices. 
We will use a Zigbee coordinator (like a USB dongle) connected to our Home Assistant server to manage the Zigbee network.

## Consequences
- Wide availability of Zigbee devices.
- Using a mesh network for better coverage.
