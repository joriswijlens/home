# irrigation-tap-bridge

Ansible role that installs the **Phase 1 garden-irrigation tap bridge** on Venus
as a systemd service. The bridge is a small Python program that subscribes to an
MQTT command topic and drives one GPIO pin (relay → 24 VAC → Rain Bird XCZ
solenoid). Home Assistant on Mars holds all watering policy and just publishes
`ON`/`OFF`; the valve is a dumb on/off switch.

Full plan and rationale: **GitHub issue #4**.

## What it deploys

| Path on Venus | Purpose |
|---|---|
| `/opt/smartworkx/irrigation-tap/irrigation_tap_bridge.py` | the bridge |
| `/etc/systemd/system/irrigation-tap-bridge.service` | systemd unit (auto-restart, env config) |

apt deps: `python3-paho-mqtt`, `python3-lgpio`.

## MQTT contract (Mars Mosquitto, anonymous, :1883)

| Topic | Direction | Payload |
|---|---|---|
| `irrigation/tap/set` | HA → bridge | `ON` / `OFF` |
| `irrigation/tap/state` | bridge → HA | `ON` / `OFF` (retained) |
| `irrigation/tap/availability` | bridge → HA | `online` / `offline` (LWT, retained) |

## Safety (fail-safe closed)

The valve is closed at startup, on `SIGTERM`/`SIGINT`, on MQTT disconnect (the
bridge can no longer receive an `OFF`), and automatically after
`MAX_ON_SECONDS` (watchdog). Pair this with an **active-high** relay board so an
undriven/booting pin leaves the valve shut — the watchdog is the backstop, not
the only line of defence. If HA dies mid-run, the watchdog still closes the tap.

## Variables (`defaults/main.yml`)

| Variable | Default | Notes |
|---|---|---|
| `irrigation_tap_mqtt_host` | `mars.local` | broker |
| `irrigation_tap_mqtt_port` | `1883` | |
| `irrigation_tap_topic_base` | `irrigation/tap` | topic prefix |
| `irrigation_tap_gpio_backend` | `real` | `real` = lgpio; `stub` = log only (dry run) |
| `irrigation_tap_gpio_chip` | `0` | `/dev/gpiochip0` on a Pi 3 |
| `irrigation_tap_gpio_pin` | `17` | BCM pin to the relay IN |
| `irrigation_tap_active_high` | `true` | use an active-high relay board |
| `irrigation_tap_max_on_seconds` | `2400` | watchdog; must exceed the longest HA run (Phase 1 max 30 min) |

## Deploy

```bash
cd infrastructure/venus/ansible/
ansible-playbook -i inventory.ini irrigation-tap-playbook.yml

# Dry run with no relay wired (logs valve open/close, touches no GPIO):
ansible-playbook -i inventory.ini irrigation-tap-playbook.yml \
  -e irrigation_tap_gpio_backend=stub

# Pick the wired pin:
ansible-playbook -i inventory.ini irrigation-tap-playbook.yml \
  -e irrigation_tap_gpio_pin=27
```

Check / follow logs on Venus:

```bash
systemctl status irrigation-tap-bridge
journalctl -u irrigation-tap-bridge -f
```

## Local development (no hardware, no deploy)

The `stub` backend touches no GPIO, so the whole MQTT/watchdog/fail-safe logic
runs on a laptop against the real broker:

```bash
GPIO_BACKEND=stub MQTT_HOST=mars.local \
  python3 files/irrigation_tap_bridge.py

# another terminal:
mosquitto_sub -h mars.local -t 'irrigation/#' -v
mosquitto_pub -h mars.local -t irrigation/tap/set -m ON
mosquitto_pub -h mars.local -t irrigation/tap/set -m OFF
```

Only the final relay/valve bring-up has to happen on Venus (`GPIO_BACKEND=real`);
the bridge/HA config is identical when you swap the breadboard bulb for the
solenoid.

## Tests

No broker or GPIO needed — the MQTT client is faked and lgpio is monkeypatched:

```bash
pytest tests/        # from this role dir, or pass the full path from the repo root
```

Covers command handling, the watchdog (armed/cancelled/fires/disabled), the
disconnect fail-safe, and the active-high/-low GPIO level mapping.

## paho-mqtt version note

The bridge uses the **v1 callback API** because Venus (Ubuntu 24.04) ships
`python3-paho-mqtt` 1.6, which only has v1. On paho ≥ 2.0 (e.g. a dev laptop) it
selects `CallbackAPIVersion.VERSION1` and you'll see a harmless deprecation
warning. Both work.
