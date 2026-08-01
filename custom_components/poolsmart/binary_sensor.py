"""Binary sensors reflecting the current decision and the operating envelope."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PoolSmartCoordinator
from .entity import PoolSmartEntity


@dataclass(frozen=True, kw_only=True)
class PoolBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[PoolSmartCoordinator], bool | None]
    attributes_fn: Callable[[PoolSmartCoordinator], dict] | None = None


BINARY_SENSORS: tuple[PoolBinaryDescription, ...] = (
    PoolBinaryDescription(
        key="heating",
        value_fn=lambda c: c.decision.heat_pump if c.decision else None,
    ),
    PoolBinaryDescription(
        key="circulating",
        value_fn=lambda c: c.decision.pump if c.decision else None,
    ),
    PoolBinaryDescription(
        key="heat_pump_available",
        value_fn=lambda c: c.heat_pump_available,
        attributes_fn=lambda c: {"reason": c.heat_pump_gate_reason},
    ),
    PoolBinaryDescription(
        key="fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda c: bool(c.faults),
        attributes_fn=lambda c: {
            "codes": c.fault_codes(),
            "messages": [f.message for f in c.faults],
        },
    ),
    PoolBinaryDescription(
        key="filter_service_needed",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda c: any(f.code == "filter_service_needed" for f in c.faults),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolSmartCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(PoolSmartBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class PoolSmartBinarySensor(PoolSmartEntity, BinarySensorEntity):
    _entity_domain = "binary_sensor"
    entity_description: PoolBinaryDescription

    def __init__(self, coordinator, description: PoolBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict:
        if self.entity_description.attributes_fn is None:
            return {}
        return self.entity_description.attributes_fn(self.coordinator)
