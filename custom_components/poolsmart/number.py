"""Values the user changes day to day."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
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
    async_add_entities(
        [PoolSmartTargetTemperature(coordinator), PoolSmartMaxPrice(coordinator)]
    )


class PoolSmartTargetTemperature(PoolSmartEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PoolSmartCoordinator) -> None:
        super().__init__(coordinator, "target_temperature")

    @property
    def native_min_value(self) -> float:
        return 10.0

    @property
    def native_max_value(self) -> float:
        return float(self.coordinator.pool_config.comfort.max_temp)

    @property
    def native_value(self) -> float:
        return self.coordinator.target_temp

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_target(value)


class PoolSmartMaxPrice(PoolSmartEntity, NumberEntity):
    """Upper price limit for heating, ignored in BOOST."""

    _attr_native_step = 0.01
    _attr_native_min_value = 0.0
    _attr_native_max_value = 2.0
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PoolSmartCoordinator) -> None:
        super().__init__(coordinator, "max_price")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.pool_config.energy.max_price

    async def async_set_native_value(self, value: float) -> None:
        options = dict(self.coordinator.entry.options)
        options[c.CONF_MAX_PRICE] = value
        self.hass.config_entries.async_update_entry(
            self.coordinator.entry, options=options
        )
