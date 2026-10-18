from minion.sources.grafana import grafana_mapper


def alert(fingerprint="abc123", status="firing", **labels):
    return {
        "status": status,
        "fingerprint": fingerprint,
        "labels": {
            "alertname": "depot-errors",
            "minion_event": "depot_error_detected",
            "error_type": "ServletException",
            **labels,
        },
        "annotations": {},
        "startsAt": "2026-10-14T08:00:00Z",
        "valueString": "[ var='B0' value=3 ]",
    }


def test_the_alert_rule_names_the_fact():
    [event] = grafana_mapper({"alerts": [alert("a1")]})

    assert event.type == "depot_error_detected"
    assert event.payload["task_id"] == "depot_error_detected-a1"
    assert event.payload["labels"]["error_type"] == "ServletException"
    assert event.payload["value"] == "[ var='B0' value=3 ]"
    assert event.payload["fingerprint"] == "a1"


def test_each_firing_alert_in_a_group_is_one_fact():
    events = grafana_mapper({"alerts": [alert("a1"), alert("a2", error_type="NPE")]})

    assert [e.payload["task_id"] for e in events] == [
        "depot_error_detected-a1",
        "depot_error_detected-a2",
    ]


def test_resolved_alerts_are_ignored():
    events = grafana_mapper({"alerts": [alert("a1"), alert("a2", status="resolved")]})

    assert [e.payload["fingerprint"] for e in events] == ["a1"]


def test_an_alert_that_names_no_fact_is_ignored():
    """Without the label, minion would have to guess what the alert means."""
    unnamed = alert("a1")
    del unnamed["labels"]["minion_event"]

    assert grafana_mapper({"alerts": [unnamed]}) is None


def test_an_alert_whose_fact_name_is_not_a_plain_token_is_ignored():
    assert grafana_mapper({"alerts": [alert("a1", minion_event="depot.>")]}) is None


def test_a_payload_with_nothing_firing_maps_to_nothing():
    assert grafana_mapper({"alerts": [alert(status="resolved")]}) is None
    assert grafana_mapper({"something": "else"}) is None
