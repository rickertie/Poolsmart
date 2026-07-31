"""Config and options flow.

The installation wizard is deliberately short: it asks only what is needed to
calculate and to switch. Filtration duration, heating time and the energy budget
are derived from volume and flow rather than entered as hours, which is what makes
the integration work for a 1000 litre pool and a 10000 litre pool alike.

Every optional entity may be left blank. The matching capability is then switched
off and reported, because inventing a value would be worse than not having one.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import const as c
from .const import DEFAULT_NAME, DOMAIN

TEMP_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
)
ANY_SENSOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
POWER_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
SWITCH = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
)
WEATHER = selector.EntitySelector(selector.EntitySelectorConfig(domain="weather"))


def _positive(minimum: float, maximum: float, step: float = 0.01):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=step, mode=selector.NumberSelectorMode.BOX
        )
    )


STEP_POOL = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(c.CONF_VOLUME_L): _positive(100, 500000, 1),
        vol.Required(c.CONF_SURFACE_M2): _positive(1, 500, 0.1),
        vol.Required(c.CONF_DEPTH_M): _positive(0.1, 5, 0.01),
        vol.Required(c.CONF_TARGET_TEMP, default=28.0): _positive(10, 40, 0.5),
        vol.Required(c.CONF_MAX_TEMP, default=32.0): _positive(10, 40, 0.5),
    }
)

STEP_PUMP = vol.Schema(
    {
        vol.Required(c.CONF_PUMP_FLOW_M3H): _positive(0.1, 100, 0.001),
        vol.Required(c.CONF_PUMP_FLOW_MEASURED, default=False): bool,
        vol.Required(c.CONF_PUMP_POWER_KW, default=0.1): _positive(0.01, 10, 0.01),
    }
)

STEP_HEAT_PUMP = vol.Schema(
    {
        vol.Required(c.CONF_HP_INPUT_KW): _positive(0.05, 50, 0.01),
        vol.Required(c.CONF_HP_THERMAL_KW): _positive(0.1, 200, 0.1),
        vol.Required(c.CONF_HP_COP_REF_TEMP, default=26.0): _positive(-10, 45, 0.5),
        vol.Optional(c.CONF_HP_COP_LOW): _positive(1, 15, 0.01),
        vol.Optional(c.CONF_HP_COP_LOW_TEMP, default=15.0): _positive(-10, 45, 0.5),
        vol.Required(c.CONF_HP_AIR_TEMP_MIN, default=11.0): _positive(-20, 30, 0.5),
        vol.Required(c.CONF_HP_AIR_TEMP_MAX, default=43.0): _positive(20, 60, 0.5),
        vol.Required(c.CONF_HP_FLOW_MIN_M3H, default=2.0): _positive(0, 50, 0.1),
    }
)

STEP_REQUIRED_ENTITIES = vol.Schema(
    {
        vol.Required(c.CONF_PUMP_SWITCH): SWITCH,
        vol.Required(c.CONF_HP_SWITCH): SWITCH,
        vol.Required(c.CONF_WATER_TEMP_SENSOR): TEMP_SENSOR,
    }
)

STEP_OPTIONAL_ENTITIES = vol.Schema(
    {
        vol.Optional(c.CONF_AIR_TEMP_SENSOR): TEMP_SENSOR,
        vol.Optional(c.CONF_HP_INLET_SENSOR): TEMP_SENSOR,
        vol.Optional(c.CONF_HP_OUTLET_SENSOR): TEMP_SENSOR,
        vol.Optional(c.CONF_FLOW_SENSOR): ANY_SENSOR,
        vol.Optional(c.CONF_PUMP_POWER_SENSOR): POWER_SENSOR,
        vol.Optional(c.CONF_HP_POWER_SENSOR): POWER_SENSOR,
        vol.Optional(c.CONF_PRICE_SENSOR): ANY_SENSOR,
        vol.Optional(c.CONF_SOLAR_POWER_SENSOR): POWER_SENSOR,
        vol.Optional(c.CONF_SOLAR_FORECAST_SENSOR): ANY_SENSOR,
        vol.Optional(c.CONF_WEATHER_ENTITY): WEATHER,
        vol.Optional(c.CONF_COVER_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["cover", "binary_sensor", "input_boolean"])
        ),
    }
)


class PoolSmartConfigFlow(ConfigFlow, domain=DOMAIN):
    """Guide the user through the five setup steps."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_pump()
        return self.async_show_form(step_id="user", data_schema=STEP_POOL)

    async def async_step_pump(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_heat_pump()

        return self.async_show_form(
            step_id="pump",
            data_schema=STEP_PUMP,
            description_placeholders={
                "derate": f"{int(100 * 0.7)}",
            },
        )

    async def async_step_heat_pump(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # Derive the reference COP from thermal output over electrical input.
            input_kw = float(user_input[c.CONF_HP_INPUT_KW])
            thermal_kw = float(user_input[c.CONF_HP_THERMAL_KW])
            cop_ref = thermal_kw / input_kw if input_kw else 5.0
            user_input[c.CONF_HP_COP_REF] = round(cop_ref, 3)
            if c.CONF_HP_COP_LOW not in user_input:
                # No second reference point: assume a flat curve.
                user_input[c.CONF_HP_COP_LOW] = round(cop_ref, 3)
                user_input[c.CONF_HP_COP_LOW_TEMP] = user_input[c.CONF_HP_COP_REF_TEMP]
            self._data.update(user_input)
            return await self.async_step_entities()

        recommended = float(self._data.get(c.CONF_MAX_TEMP, 32.0)) + 2.0
        return self.async_show_form(
            step_id="heat_pump",
            data_schema=STEP_HEAT_PUMP,
            description_placeholders={"recommended_setpoint": f"{recommended:.0f}"},
        )

    async def async_step_entities(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_optional()
        return self.async_show_form(step_id="entities", data_schema=STEP_REQUIRED_ENTITIES)

    async def async_step_optional(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update({k: v for k, v in user_input.items() if v})
            title = self._data.pop(CONF_NAME, DEFAULT_NAME)
            return self.async_create_entry(title=title, data=self._data)

        volume = float(self._data.get(c.CONF_VOLUME_L, 0))
        flow = float(self._data.get(c.CONF_PUMP_FLOW_M3H, 1))
        measured = bool(self._data.get(c.CONF_PUMP_FLOW_MEASURED, False))
        effective = flow if measured else flow * 0.7
        daily_h = (volume * 2.0) / (effective * 1000) if effective else 0

        return self.async_show_form(
            step_id="optional",
            data_schema=STEP_OPTIONAL_ENTITIES,
            description_placeholders={
                "daily_hours": f"{daily_h:.1f}",
                "block_minutes": f"{daily_h / 3 * 60:.0f}",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> PoolSmartOptionsFlow:
        return PoolSmartOptionsFlow()


WEEKDAYS = [
    {"value": "0", "label": "Monday"},
    {"value": "1", "label": "Tuesday"},
    {"value": "2", "label": "Wednesday"},
    {"value": "3", "label": "Thursday"},
    {"value": "4", "label": "Friday"},
    {"value": "5", "label": "Saturday"},
    {"value": "6", "label": "Sunday"},
]


class PoolSmartOptionsFlow(OptionsFlow):
    """Everything that is not needed to get started lives here."""

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "swimming", "notifications"],
        )

    async def async_step_swimming(self, user_input: dict | None = None) -> ConfigFlowResult:
        """When the pool should be at temperature.

        One window per weekday covers nearly every household. A second is offered
        for the exceptions and costs almost nothing, because the planner works
        from a list of deadlines either way.
        """
        if user_input is not None:
            options = {**self.config_entry.options, **user_input}
            return self.async_create_entry(data=options)

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Optional(
                    c.CONF_SWIM_TIME, default=current.get(c.CONF_SWIM_TIME, "17:00")
                ): str,
                vol.Optional(
                    c.CONF_SWIM_TIME_2, default=current.get(c.CONF_SWIM_TIME_2, "")
                ): str,
                vol.Optional(
                    c.CONF_SWIM_DAYS,
                    default=current.get(c.CONF_SWIM_DAYS, ["0", "1", "2", "3", "4", "5", "6"]),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=WEEKDAYS, multiple=True, mode=selector.SelectSelectorMode.LIST
                    )
                ),
            }
        )
        return self.async_show_form(step_id="swimming", data_schema=schema)

    async def async_step_notifications(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Route each kind of message to its own destination.

        Faults can go to one phone and "the pool is warm" to everyone.
        """
        if user_input is not None:
            targets = {k: v for k, v in user_input.items() if v}
            options = {**self.config_entry.options, c.CONF_NOTIFY_TARGETS: targets}
            return self.async_create_entry(data=options)

        current = (self.config_entry.options.get(c.CONF_NOTIFY_TARGETS) or {})
        notify_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="notify")
        )
        fields = {vol.Optional("default", default=current.get("default", "")): notify_selector}
        for event in c.NOTIFY_EVENTS:
            fields[vol.Optional(event, default=current.get(event, ""))] = notify_selector
        return self.async_show_form(
            step_id="notifications", data_schema=vol.Schema(fields)
        )

    async def async_step_general(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            options = {**self.config_entry.options, **user_input}
            return self.async_create_entry(data=options)

        current = {**self.config_entry.data, **self.config_entry.options}

        schema = vol.Schema(
            {
                vol.Optional(
                    c.CONF_TURNOVER_FACTOR,
                    default=current.get(c.CONF_TURNOVER_FACTOR, 2.0),
                ): _positive(0.5, 4.0, 0.1),
                vol.Optional(
                    c.CONF_MIN_BLOCK_MINUTES,
                    default=current.get(c.CONF_MIN_BLOCK_MINUTES, 20),
                ): _positive(5, 240, 1),
                vol.Optional(
                    c.CONF_NIGHT_START, default=current.get(c.CONF_NIGHT_START, "22:00")
                ): str,
                vol.Optional(
                    c.CONF_NIGHT_END, default=current.get(c.CONF_NIGHT_END, "07:00")
                ): str,
                vol.Optional(
                    c.CONF_MIN_ON_MINUTES,
                    default=current.get(c.CONF_MIN_ON_MINUTES, 15),
                ): _positive(1, 120, 1),
                vol.Optional(
                    c.CONF_MIN_OFF_MINUTES,
                    default=current.get(c.CONF_MIN_OFF_MINUTES, 10),
                ): _positive(1, 120, 1),
                vol.Optional(
                    c.CONF_PUMP_RUNDOWN_MINUTES,
                    default=current.get(c.CONF_PUMP_RUNDOWN_MINUTES, 5),
                ): _positive(0, 60, 1),
                vol.Optional(
                    c.CONF_TEMP_HYSTERESIS,
                    default=current.get(c.CONF_TEMP_HYSTERESIS, 0.3),
                ): _positive(0.1, 3.0, 0.1),
                vol.Optional(
                    c.CONF_MIN_WATER_TEMP,
                    default=current.get(c.CONF_MIN_WATER_TEMP, 10.0),
                ): _positive(0, 25, 0.5),
                vol.Optional(
                    c.CONF_FROST_AIR_TEMP,
                    default=current.get(c.CONF_FROST_AIR_TEMP, 3.0),
                ): _positive(-10, 10, 0.5),
                vol.Optional(
                    c.CONF_MAX_PRICE, default=current.get(c.CONF_MAX_PRICE, 0.30)
                ): _positive(0, 3, 0.01),
                vol.Optional(
                    c.CONF_NEGATIVE_PRICE_BASIS,
                    default=current.get(c.CONF_NEGATIVE_PRICE_BASIS, "total"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["total", "market"],
                        translation_key="negative_price_basis",
                    )
                ),
                vol.Optional(
                    c.CONF_SOLAR_THRESHOLD_W,
                    default=current.get(c.CONF_SOLAR_THRESHOLD_W, 1500),
                ): _positive(0, 20000, 50),
                vol.Optional(
                    c.CONF_SOLAR_HYSTERESIS_W,
                    default=current.get(c.CONF_SOLAR_HYSTERESIS_W, 300),
                ): _positive(0, 5000, 50),
                vol.Optional(
                    c.CONF_ECO_PRICE_FACTOR,
                    default=current.get(c.CONF_ECO_PRICE_FACTOR, 0.7),
                ): _positive(0.1, 1.0, 0.05),
                vol.Optional(
                    c.CONF_CHEMISTRY_MINUTES,
                    default=current.get(c.CONF_CHEMISTRY_MINUTES, 30),
                ): _positive(5, 240, 5),
                vol.Optional(
                    c.CONF_LEARNING_ENABLED,
                    default=current.get(c.CONF_LEARNING_ENABLED, True),
                ): bool,
            }
        )
        return self.async_show_form(step_id="general", data_schema=schema)
