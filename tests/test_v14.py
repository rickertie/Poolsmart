"""Tests for the 1.11.0 batch: the notify action-buttons fix (#19), the swim
time dashboard tile (#17), the weather_entity air-temp fallback (#16), the
demand/power limiter (#13), and the AI feedback loop (#10).
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

import ha_stubs  # noqa: E402


# ---------------------------------------------------------------------------
# Issue #19 -- notify.send_message must forward data.actions/tag
# ---------------------------------------------------------------------------


class _FakeServices:
    def __init__(self):
        self.calls = []

    def has_service(self, domain, service):
        return False

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


class _FakeHass:
    def __init__(self, entity_state):
        self.services = _FakeServices()
        self.states = types.SimpleNamespace(get=lambda entity_id: entity_state)

    def async_create_task(self, coro):
        asyncio.run(coro)


def test_send_message_path_forwards_action_buttons():
    notify_module = ha_stubs.load("notify", "notify.py")
    hass = _FakeHass(entity_state=object())
    manager = notify_module.NotificationManager(hass=hass, coordinator=None)
    payload = {
        "title": "Heating postponed",
        "message": "Waiting for a cheaper slot.",
        "data": {
            "actions": [{"action": "POOLSMART_BOOST", "title": "Heat now"}],
            "tag": "poolsmart_heating_postponed",
        },
    }

    manager._send_one("notify.mobile_app_phone", payload, "heating_postponed")

    assert len(hass.services.calls) == 1
    domain, service, data = hass.services.calls[0]
    assert domain == "notify"
    assert service == "send_message"
    assert data["entity_id"] == "notify.mobile_app_phone"
    assert data["data"] == payload["data"]


def test_send_message_path_omits_data_key_when_there_are_no_actions():
    notify_module = ha_stubs.load("notify", "notify.py")
    hass = _FakeHass(entity_state=object())
    manager = notify_module.NotificationManager(hass=hass, coordinator=None)
    payload = {"title": "Target reached", "message": "Pool is at temperature."}

    manager._send_one("notify.mobile_app_phone", payload, "heating_started")

    assert len(hass.services.calls) == 1
    _domain, _service, data = hass.services.calls[0]
    assert "data" not in data
