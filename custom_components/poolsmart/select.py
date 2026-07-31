"""Mode selection.

A mode does not carry its own logic. It enables or disables branches of the one
decision ladder, which is what keeps the decision logic in a single place.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .core.models import Mode
from .coordinator import PoolSmartCoordinator
from .entity import PoolSmartEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: PoolSmartCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PoolSmartModeSelect(coordinator)])


class PoolSmartModeSelect(PoolSmartEntity, SelectEntity):
    _attr_options = [m.value for m in Mode]

    def __init__(self, coordinator: PoolSmartCoordinator) -> None:
        super().__init__(coordinator, "mode")

    @property
    def current_option(self) -> str:
        return self.coordinator.mode.value

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_mode(option)
