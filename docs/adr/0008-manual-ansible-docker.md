# Relays

## Context
We are building a home automation system.
We want it to be maintainable, cost effective, reliable, customizable and support smart devices easily.
We need to install a lot of devices to control the lights in our house.

## Decision
Do as little as possible manually. Only do what is absolutely necessary manually to bootstrap the system and configure
devices. Then do as little as possible on the RPI host itself. Use Ansible to configure the host and Docker to run.
Use as much as possible Dokcer Compose and Docker containers to run services. 


## Consequences
- Self-documenting infrastructure as code.
- Easy to replicate and recover from failures.
- More complex initial setup.
- Leverage existing knowledge of Ansible and Docker.
