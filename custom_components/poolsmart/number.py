"""Values the user changes day to day."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature
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
        [
            PoolSmartTargetTemperature(coordinator),
            PoolSmartMaxPrice(coordinator),
            PoolSmartSolarThreshold(coordinator),
            PoolSmartPowerLimit(coordinator),
        ]
    )


class PoolSmartTargetTemperature(PoolSmartEntity, NumberEntity):
    _entity_domain = "number"
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
    _entity_domain = "number"
    """Upper price limit for heating, ignored in BOOST."""

    _attr_native_step = 0.01
    _attr_native_min_value = 0.0
    _attr_native_max_value = 2.0
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PoolSmartCoordinator) -> None:
        super().__init__(coordinator, "max_price")

    @property
    def native_value(self) -> float | None:
        """The configured limit, or the default if none was ever set.

        Leaving this blank made the entity render as unknown, which broke any
        dashboard template doing arithmetic on it and gave no hint what a
        sensible value looks like.
        """
        configured = self.coordinator.pool_config.energy.max_price
        return configured if configured is not None else c.DEFAULT_MAX_PRICE

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_max_price(value)


class PoolSmartSolarThreshold(PoolSmartEntity, NumberEntity):
    """Solar surplus above which heating is treated as free.

    Adjustable here rather than only in the options flow, because this is a
    number people want to tune while watching the sun, not while reading a
    settings page.
    """

    _entity_domain = "number"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_step = 50
    _attr_native_min_value = 0
    _attr_native_max_value = 20000
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PoolSmartCoordinator) -> None:
        super().__init__(coordinator, "solar_threshold")

    @property
    def native_value(self) -> float:
        return self.coordinator.pool_config.energy.solar_threshold_w

    @property
    def extra_state_attributes(self) -> dict:
        config = self.coordinator.pool_config
        draw = (config.heat_pump.input_kw + config.pump.power_kw) * 1000
        return {
            "equipment_draw_w": round(draw),
            "suggested_minimum_w": round(draw + 200),
        }

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_solar_threshold(value)


class PoolSmartPowerLimit(PoolSmartEntity, NumberEntity):
    """House-power cap above which heating pauses.

    Unlike the solar threshold, there is no sensible computed default here --
    a cap is either something the household's contract/breaker actually
    needs, or it is absent, and 0 W would misleadingly read as "never heat".
    Left unset, ``native_value`` reports unknown rather than a number that
    is not really a limit. See issue #13.
    """

    _entity_domain = "number"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_step = 50
    _attr_native_min_value = 0
    _attr_native_max_value = 30000
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PoolSmartCoordinator) -> None:
        super().__init__(coordinator, "power_limit")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.pool_config.energy.power_limit_w

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_power_limit(value)
