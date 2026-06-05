#!/usr/bin/env python3
"""MQTT <-> GPIO bridge for the Phase 1 tap irrigation valve (Venus).

The valve is a dumb on/off switch: HA holds all watering policy and just
publishes ON/OFF. This bridge subscribes to the command topic and drives one
GPIO pin (relay -> 24VAC -> Rain Bird XCZ solenoid). It publishes state and an
availability topic (LWT) so HA can see when the bridge is offline.

Fail-safe by design -- the valve is closed:
  * at startup,
  * on SIGTERM / SIGINT,
  * on MQTT disconnect (we can no longer receive an OFF),
  * automatically after MAX_ON_SECONDS (watchdog) so a missed OFF or a crashed
    scheduler can never flood the garden.

Config via environment variables (see the Ansible role defaults):
  MQTT_HOST       broker host             (default: mars.local)
  MQTT_PORT       broker port             (default: 1883)
  TOPIC_BASE      topic prefix            (default: irrigation/tap)
  GPIO_BACKEND    real | stub             (default: stub)
  GPIO_CHIP       gpiochip number         (default: 0 -> /dev/gpiochip0)
  GPIO_PIN        BCM pin number          (default: 17)
  ACTIVE_HIGH     true | false            (default: true)
  MAX_ON_SECONDS  watchdog timeout, 0=off (default: 2400)

The 'stub' backend touches no hardware (just logs), so the whole MQTT/watchdog/
fail-safe logic can be developed and tested on a laptop against the real broker
with `mosquitto_pub`/`mosquitto_sub`. Switch to 'real' on Venus.
"""
import logging
import os
import signal
import sys
import threading

import paho.mqtt.client as mqtt

log = logging.getLogger("irrigation-tap")


def env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in (
        "1", "true", "yes", "on",
    )


class Valve:
    """Abstract on/off valve. open() = water flows, close() = shut."""

    def open(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def cleanup(self):
        pass


class StubValve(Valve):
    """No hardware -- just logs. For laptop development."""

    def open(self):
        log.info("VALVE OPEN  (stub)")

    def close(self):
        log.info("VALVE CLOSED (stub)")


class RealValve(Valve):
    """Drives a relay via the lgpio character-device interface."""

    def __init__(self, chip, pin, active_high):
        import lgpio

        self._lgpio = lgpio
        self.pin = pin
        self.active = 1 if active_high else 0
        self.inactive = 0 if active_high else 1
        self.handle = lgpio.gpiochip_open(chip)
        # Claim as output and start in the inactive (valve-closed) level.
        lgpio.gpio_claim_output(self.handle, pin, self.inactive)
        log.info(
            "GPIO chip %d pin %d claimed (active_high=%s); started CLOSED",
            chip, pin, active_high,
        )

    def open(self):
        self._lgpio.gpio_write(self.handle, self.pin, self.active)
        log.info("VALVE OPEN  (gpio pin %d -> %d)", self.pin, self.active)

    def close(self):
        self._lgpio.gpio_write(self.handle, self.pin, self.inactive)
        log.info("VALVE CLOSED (gpio pin %d -> %d)", self.pin, self.inactive)

    def cleanup(self):
        try:
            self.close()
            self._lgpio.gpiochip_close(self.handle)
        except Exception:  # noqa: BLE001 - best effort on shutdown
            pass


def make_valve():
    backend = os.environ.get("GPIO_BACKEND", "stub").strip().lower()
    if backend == "real":
        chip = int(os.environ.get("GPIO_CHIP", "0"))
        pin = int(os.environ.get("GPIO_PIN", "17"))
        return RealValve(chip, pin, env_bool("ACTIVE_HIGH", True))
    log.info("Using STUB valve backend (no hardware)")
    return StubValve()


class Bridge:
    def __init__(self):
        self.host = os.environ.get("MQTT_HOST", "mars.local")
        self.port = int(os.environ.get("MQTT_PORT", "1883"))
        base = os.environ.get("TOPIC_BASE", "irrigation/tap").rstrip("/")
        self.t_set = f"{base}/set"
        self.t_state = f"{base}/state"
        self.t_avail = f"{base}/availability"
        self.max_on = float(os.environ.get("MAX_ON_SECONDS", "2400"))

        self.valve = make_valve()
        self.lock = threading.RLock()
        self.is_open = False
        self.timer = None
        self.stopping = False

        try:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1,
                client_id="irrigation-tap-bridge",
            )
        except (AttributeError, TypeError):
            # paho-mqtt < 2.0 has no CallbackAPIVersion.
            self.client = mqtt.Client(client_id="irrigation-tap-bridge")
        self.client.will_set(self.t_avail, "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    # --- valve control + watchdog -------------------------------------
    def _cancel_timer(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None

    def _open(self):
        with self.lock:
            self.valve.open()
            self.is_open = True
            self._cancel_timer()
            if self.max_on > 0:
                self.timer = threading.Timer(self.max_on, self._watchdog)
                self.timer.daemon = True
                self.timer.start()
            self._publish_state()

    def _close(self, reason=""):
        with self.lock:
            self.valve.close()
            self.is_open = False
            self._cancel_timer()
            self._publish_state()
            if reason:
                log.info("Valve closed: %s", reason)

    def _watchdog(self):
        log.warning(
            "WATCHDOG: max-on %.0fs reached, forcing valve closed", self.max_on
        )
        self._close("watchdog timeout")

    def _publish_state(self):
        payload = "ON" if self.is_open else "OFF"
        self.client.publish(self.t_state, payload, qos=1, retain=True)

    # --- mqtt callbacks ------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc, *args):
        if rc != 0:
            log.error("MQTT connect failed rc=%s", rc)
            return
        log.info("Connected to %s:%d", self.host, self.port)
        client.publish(self.t_avail, "online", qos=1, retain=True)
        self._publish_state()
        client.subscribe(self.t_set, qos=1)

    def _on_message(self, client, userdata, msg):
        cmd = msg.payload.decode(errors="ignore").strip().upper()
        log.info("CMD %s = %s", msg.topic, cmd)
        if cmd in ("ON", "1", "TRUE", "OPEN"):
            self._open()
        elif cmd in ("OFF", "0", "FALSE", "CLOSE"):
            self._close("command OFF")
        else:
            log.warning("Ignoring unknown command: %r", cmd)

    def _on_disconnect(self, *args):
        if self.stopping:
            return
        # Fail-safe: we can no longer receive an OFF, so close the valve.
        # paho's loop will keep trying to reconnect in the background.
        log.warning("MQTT disconnected; closing valve fail-safe")
        with self.lock:
            self.valve.close()
            self.is_open = False
            self._cancel_timer()

    # --- lifecycle -----------------------------------------------------
    def run(self):
        # Ensure the valve is physically closed before we touch the network.
        with self.lock:
            self.valve.close()
            self.is_open = False
        self.client.connect_async(self.host, self.port, keepalive=30)
        self.client.loop_start()
        signal.pause()

    def shutdown(self, *args):
        log.info("Shutting down")
        self.stopping = True
        try:
            self.client.publish(self.t_avail, "offline", qos=1, retain=True)
        except Exception:  # noqa: BLE001
            pass
        self._close("shutdown")
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        self.valve.cleanup()
        sys.exit(0)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    bridge = Bridge()
    signal.signal(signal.SIGTERM, bridge.shutdown)
    signal.signal(signal.SIGINT, bridge.shutdown)
    bridge.run()


if __name__ == "__main__":
    main()
