"""Switches for manual takeover and learning."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import const as c
from .const import DOMAIN
from .coordinator import PoolSmartCoordinator
from .entity import PoolSmartEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolSmartCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PoolSmartManualOverride(coordinator), PoolSmartLearning(coordinator)])


class PoolSmartManualOverride(PoolSmartEntity, SwitchEntity):
    _entity_domain = "switch"
    """Force circulation, overriding everything except safety."""

    def __init__(self, coordinator: PoolSmartCoordinator) -> None:
        super().__init__(coordinator, "manual_override")

    @property
    def is_on(self) -> bool:
        return self.coordinator._manual_pump_request

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_manual_pump(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_manual_pump(False)


class PoolSmartLearning(PoolSmartEntity, SwitchEntity):
    _entity_domain = "switch"
    """Enable or disable self-learning."""

    def __init__(self, coordinator: PoolSmartCoordinator) -> None:
        super().__init__(coordinator, "learning_enabled")

    @property
    def is_on(self) -> bool:
        return self.coordinator.pool_config.learning.enabled

    async def _set(self, enabled: bool) -> None:
        options = dict(self.coordinator.entry.options)
        options[c.CONF_LEARNING_ENABLED] = enabled
        self.hass.config_entries.async_update_entry(
            self.coordinator.entry, options=options
        )

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
