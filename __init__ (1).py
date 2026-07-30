"""One-shot actions."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    async_add_entities(
        [
            PoolSmartBoostNow(coordinator),
            PoolSmartForceFiltration(coordinator),
            PoolSmartStartChemistry(coordinator),
            PoolSmartResetLearning(coordinator),
        ]
    )


class PoolSmartBoostNow(PoolSmartEntity, ButtonEntity):
    _attr_icon = "mdi:rocket-launch"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "boost_now")

    async def async_press(self) -> None:
        await self.coordinator.async_set_mode(Mode.BOOST.value)


class PoolSmartForceFiltration(PoolSmartEntity, ButtonEntity):
    _attr_icon = "mdi:filter-plus"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "force_filtration")

    async def async_press(self) -> None:
        await self.coordinator.async_force_filtration()


class PoolSmartStartChemistry(PoolSmartEntity, ButtonEntity):
    """Circulate for a chemical treatment.

    The hardware for automated dosing does not exist yet; this button makes the
    branch useful in the meantime.
    """

    _attr_icon = "mdi:flask"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "start_chemistry_cycle")

    async def async_press(self) -> None:
        await self.coordinator.async_start_chemistry()


class PoolSmartResetLearning(PoolSmartEntity, ButtonEntity):
    _attr_icon = "mdi:restore"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reset_learning")

    async def async_press(self) -> None:
        await self.coordinator.async_reset_learning()
