"""Unit tests for the irrigation tap MQTT<->GPIO bridge.

Run from the role directory (or anywhere) with:

    pytest infrastructure/ansible/roles/irrigation-tap-bridge/tests/

Needs: pytest, paho-mqtt. No broker and no GPIO hardware are required — the
MQTT client is faked and the lgpio backend is monkeypatched, so these run on a
laptop/CI. They cover the safety-critical behaviour: command handling, the
max-on watchdog, the disconnect fail-safe, and the active-high/-low GPIO level
mapping (so a booting pin leaves the valve closed).
"""
import importlib.util
import pathlib
import sys
import types

import pytest

MODULE_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "files" / "irrigation_tap_bridge.py"
)
_spec = importlib.util.spec_from_file_location("irrigation_tap_bridge", MODULE_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class FakeClient:
    """Records publish/subscribe instead of talking to a broker."""

    def __init__(self):
        self.published = []   # list of (topic, payload, retain)
        self.subscribed = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, retain))

    def subscribe(self, topic, qos=0):
        self.subscribed.append(topic)

    def last(self, topic):
        for t, p, r in reversed(self.published):
            if t == topic:
                return p, r
        return None


def msg(topic, payload):
    return types.SimpleNamespace(topic=topic, payload=payload.encode())


@pytest.fixture
def make_bridge(monkeypatch):
    """Factory: build a Bridge with a given env and a fake MQTT client."""

    def factory(**env):
        env.setdefault("GPIO_BACKEND", "stub")
        for key, value in env.items():
            monkeypatch.setenv(key, str(value))
        bridge = mod.Bridge()
        bridge.client = FakeClient()
        return bridge

    return factory


@pytest.fixture
def bridge(make_bridge):
    return make_bridge()


# --- topics ---------------------------------------------------------------
def test_topics_from_base(make_bridge):
    b = make_bridge(TOPIC_BASE="garden/valve1")
    assert b.t_set == "garden/valve1/set"
    assert b.t_state == "garden/valve1/state"
    assert b.t_avail == "garden/valve1/availability"


def test_topic_base_trailing_slash(make_bridge):
    b = make_bridge(TOPIC_BASE="irrigation/tap/")
    assert b.t_set == "irrigation/tap/set"


# --- command handling -----------------------------------------------------
@pytest.mark.parametrize("payload", ["ON", "on", "1", "true", "OPEN"])
def test_on_opens_and_publishes_retained_state(bridge, payload):
    bridge._on_message(None, None, msg(bridge.t_set, payload))
    assert bridge.is_open is True
    assert bridge.client.last(bridge.t_state) == ("ON", True)


@pytest.mark.parametrize("payload", ["OFF", "off", "0", "false", "CLOSE"])
def test_off_closes_and_publishes_retained_state(bridge, payload):
    bridge._on_message(None, None, msg(bridge.t_set, "ON"))
    bridge._on_message(None, None, msg(bridge.t_set, payload))
    assert bridge.is_open is False
    assert bridge.client.last(bridge.t_state) == ("OFF", True)


def test_unknown_command_is_ignored(bridge):
    bridge._on_message(None, None, msg(bridge.t_set, "ON"))
    before = list(bridge.client.published)
    bridge._on_message(None, None, msg(bridge.t_set, "GARBAGE"))
    assert bridge.is_open is True          # unchanged
    assert bridge.client.published == before  # nothing published


# --- connect handshake ----------------------------------------------------
def test_on_connect_announces_online_state_and_subscribes(bridge):
    bridge._on_connect(bridge.client, None, None, 0)
    assert bridge.client.last(bridge.t_avail) == ("online", True)
    assert bridge.client.last(bridge.t_state) == ("OFF", True)
    assert bridge.t_set in bridge.client.subscribed


def test_on_connect_failure_does_nothing(bridge):
    bridge._on_connect(bridge.client, None, None, 5)  # non-zero rc
    assert bridge.client.published == []
    assert bridge.client.subscribed == []


# --- watchdog -------------------------------------------------------------
class FakeTimer:
    instances = []

    def __init__(self, interval, fn):
        self.interval = interval
        self.fn = fn
        self.started = False
        self.cancelled = False
        FakeTimer.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


@pytest.fixture
def fake_timer(monkeypatch):
    FakeTimer.instances.clear()
    monkeypatch.setattr(mod.threading, "Timer", FakeTimer)
    return FakeTimer


def test_watchdog_armed_on_open_with_configured_timeout(make_bridge, fake_timer):
    b = make_bridge(MAX_ON_SECONDS=2400)
    b._on_message(None, None, msg(b.t_set, "ON"))
    assert len(fake_timer.instances) == 1
    t = fake_timer.instances[-1]
    assert t.interval == 2400 and t.started is True


def test_watchdog_cancelled_on_close(make_bridge, fake_timer):
    b = make_bridge(MAX_ON_SECONDS=2400)
    b._on_message(None, None, msg(b.t_set, "ON"))
    t = fake_timer.instances[-1]
    b._on_message(None, None, msg(b.t_set, "OFF"))
    assert t.cancelled is True


def test_watchdog_firing_closes_valve(make_bridge, fake_timer):
    b = make_bridge(MAX_ON_SECONDS=2400)
    b._on_message(None, None, msg(b.t_set, "ON"))
    assert b.is_open is True
    fake_timer.instances[-1].fn()   # simulate timeout expiry
    assert b.is_open is False
    assert b.client.last(b.t_state) == ("OFF", True)


def test_watchdog_disabled_when_zero(make_bridge, fake_timer):
    b = make_bridge(MAX_ON_SECONDS=0)
    b._on_message(None, None, msg(b.t_set, "ON"))
    assert b.is_open is True
    assert fake_timer.instances == []   # no timer armed


# --- disconnect fail-safe -------------------------------------------------
def test_disconnect_closes_valve(bridge):
    bridge._on_message(None, None, msg(bridge.t_set, "ON"))
    assert bridge.is_open is True
    bridge._on_disconnect()
    assert bridge.is_open is False


def test_disconnect_during_shutdown_is_suppressed(bridge):
    bridge._on_message(None, None, msg(bridge.t_set, "ON"))
    bridge.stopping = True
    bridge._on_disconnect()
    assert bridge.is_open is True   # left untouched; shutdown() handles it


# --- helpers --------------------------------------------------------------
@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", "On"])
def test_env_bool_true(monkeypatch, value):
    monkeypatch.setenv("X", value)
    assert mod.env_bool("X", False) is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "garbage"])
def test_env_bool_false(monkeypatch, value):
    monkeypatch.setenv("X", value)
    assert mod.env_bool("X", True) is False


def test_stub_valve_does_not_raise():
    v = mod.StubValve()
    v.open()
    v.close()
    v.cleanup()


# --- RealValve GPIO level mapping (fake lgpio) ----------------------------
def _fake_lgpio(calls):
    return types.SimpleNamespace(
        gpiochip_open=lambda chip: ("handle", chip),
        gpio_claim_output=lambda h, pin, level: calls.append(("claim", pin, level)),
        gpio_write=lambda h, pin, level: calls.append(("write", pin, level)),
        gpiochip_close=lambda h: calls.append(("close",)),
    )


def test_real_valve_active_high_fails_safe_closed(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "lgpio", _fake_lgpio(calls))
    v = mod.RealValve(chip=0, pin=17, active_high=True)
    assert ("claim", 17, 0) in calls   # starts at inactive=0 => valve CLOSED
    v.open()
    assert calls[-1] == ("write", 17, 1)   # energise relay
    v.close()
    assert calls[-1] == ("write", 17, 0)


def test_real_valve_active_low_inverts_levels(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "lgpio", _fake_lgpio(calls))
    v = mod.RealValve(chip=0, pin=17, active_high=False)
    assert ("claim", 17, 1) in calls   # inactive=1 for active-low board
    v.open()
    assert calls[-1] == ("write", 17, 0)
    v.close()
    assert calls[-1] == ("write", 17, 1)


def test_real_valve_cleanup_closes_and_releases(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "lgpio", _fake_lgpio(calls))
    v = mod.RealValve(chip=0, pin=17, active_high=True)
    v.cleanup()
    assert ("write", 17, 0) in calls   # closed during cleanup
    assert ("close",) in calls
