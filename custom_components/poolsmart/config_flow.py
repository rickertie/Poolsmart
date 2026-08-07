"""Config and options flow.

The installation wizard is deliberately short: it asks only what is needed to
calculate and to switch. Filtration duration, heating time and the energy budget
are derived from volume and flow rather than entered as hours, which is what makes
the integration work for a 1000 litre pool and a 10000 litre pool alike.

Every optional entity may be left blank. The matching capability is then switched
off and reported, because inventing a value would be worse than not having one.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import const as c
from .const import DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

TEMP_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
)
ANY_SENSOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
#: For readings people commonly enter by hand -- a water test strip has no
#: sensor of its own, so pH and chlorine are as often an input_number helper
#: updated manually as they are a real sensor. Restricting the picker to
#: domain="sensor" hid every such helper from the list, which is what point 1
#: below was: the helper existed, the picker just would not show it.
MANUAL_OR_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["sensor", "input_number"])
)
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


async def async_load_defaults(hass) -> dict:
    """Starting values for the wizard.

    Built-in defaults describe a generic mid-sized pool. If a
    `poolsmart_defaults.json` file exists in the configuration directory, its
    keys override them -- which is how you stop retyping your own figures every
    time you reinstall, without baking one particular pool into the integration
    and spoiling it for everyone else.
    """
    defaults = dict(c.SETUP_DEFAULTS)
    path = hass.config.path(c.DEFAULTS_FILE)

    def _read() -> dict | None:
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    try:
        override = await hass.async_add_executor_job(_read)
    except (OSError, ValueError) as err:
        _LOGGER.warning("Ignoring %s because it could not be read: %s", c.DEFAULTS_FILE, err)
        return defaults

    if override:
        unknown = set(override) - set(defaults)
        if unknown:
            _LOGGER.debug("Ignoring unknown keys in %s: %s", c.DEFAULTS_FILE, unknown)
        defaults.update({k: v for k, v in override.items() if k in defaults})
        _LOGGER.info("Loaded setup defaults from %s", c.DEFAULTS_FILE)
    return defaults


def _pool_schema(d: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(c.CONF_VOLUME_L, default=d[c.CONF_VOLUME_L]): _positive(
                100, 500000, 1
            ),
            vol.Optional(c.CONF_DEPTH_M, default=d[c.CONF_DEPTH_M]): _positive(
                0.1, 5, 0.01
            ),
            vol.Optional(c.CONF_SURFACE_M2): _positive(1, 500, 0.1),
            vol.Required(c.CONF_TARGET_TEMP, default=d[c.CONF_TARGET_TEMP]): _positive(
                10, 40, 0.5
            ),
            vol.Required(c.CONF_MAX_TEMP, default=d[c.CONF_MAX_TEMP]): _positive(
                10, 40, 0.5
            ),
            vol.Required(
                c.CONF_UNIT_SYSTEM, default=d[c.CONF_UNIT_SYSTEM]
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["metric", "imperial"], translation_key="unit_system"
                )
            ),
            vol.Required(
                c.CONF_SANITISER, default=d[c.CONF_SANITISER]
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["chlorine", "bromine", "salt"],
                    translation_key="sanitiser",
                )
            ),
        }
    )


def _pump_schema(d: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                c.CONF_PUMP_FLOW_M3H, default=d[c.CONF_PUMP_FLOW_M3H]
            ): _positive(0.1, 100, 0.001),
            vol.Required(
                c.CONF_PUMP_FLOW_MEASURED, default=d[c.CONF_PUMP_FLOW_MEASURED]
            ): bool,
            vol.Required(
                c.CONF_PUMP_POWER_KW, default=d[c.CONF_PUMP_POWER_KW]
            ): _positive(0.01, 10, 0.01),
            vol.Required(
                c.CONF_FILTER_MEDIA, default=d[c.CONF_FILTER_MEDIA]
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["sand", "glass", "balls", "cartridge", "none"],
                    translation_key="filter_media",
                )
            ),
        }
    )


def _heat_pump_schema(d: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(c.CONF_HP_INPUT_KW, default=d[c.CONF_HP_INPUT_KW]): _positive(
                0.05, 50, 0.01
            ),
            vol.Required(
                c.CONF_HP_THERMAL_KW, default=d[c.CONF_HP_THERMAL_KW]
            ): _positive(0.1, 200, 0.1),
            vol.Required(
                c.CONF_HP_COP_REF_TEMP, default=d[c.CONF_HP_COP_REF_TEMP]
            ): _positive(-10, 45, 0.5),
            vol.Optional(c.CONF_HP_COP_LOW): _positive(1, 15, 0.01),
            vol.Optional(
                c.CONF_HP_COP_LOW_TEMP, default=d[c.CONF_HP_COP_LOW_TEMP]
            ): _positive(-10, 45, 0.5),
            vol.Required(
                c.CONF_HP_AIR_TEMP_MIN, default=d[c.CONF_HP_AIR_TEMP_MIN]
            ): _positive(-20, 30, 0.5),
            vol.Required(
                c.CONF_HP_AIR_TEMP_MAX, default=d[c.CONF_HP_AIR_TEMP_MAX]
            ): _positive(20, 60, 0.5),
            vol.Required(
                c.CONF_HP_FLOW_MIN_M3H, default=d[c.CONF_HP_FLOW_MIN_M3H]
            ): _positive(0, 50, 0.1),
            vol.Required(
                c.CONF_HP_FLOW_MIN_BLOCKING,
                default=d[c.CONF_HP_FLOW_MIN_BLOCKING],
            ): bool,
            vol.Required(
                c.CONF_HP_FLOW_MIN_VERIFIED,
                default=d[c.CONF_HP_FLOW_MIN_VERIFIED],
            ): bool,
        }
    )


def derive_pool_shape(data: dict) -> dict:
    """Fill in the pool dimensions that were left blank.

    Surface area only affects the heat-loss estimate, and that estimate is
    replaced by a measured one within a few days. Asking for a number people
    would have to go and measure, in order to seed a value that gets overwritten
    anyway, is a poor trade.
    """
    volume = float(data.get(c.CONF_VOLUME_L, 0) or 0)
    depth = float(data.get(c.CONF_DEPTH_M) or 1.2)
    if not data.get(c.CONF_SURFACE_M2) and volume and depth:
        data[c.CONF_SURFACE_M2] = round(volume / 1000.0 / depth, 2)
    data[c.CONF_DEPTH_M] = depth
    return data


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
        vol.Optional(c.CONF_PUMP_INLET_SENSOR): TEMP_SENSOR,
        vol.Optional(c.CONF_PUMP_OUTLET_SENSOR): TEMP_SENSOR,
        vol.Optional(c.CONF_HP_INLET_SENSOR): TEMP_SENSOR,
        vol.Optional(c.CONF_HP_OUTLET_SENSOR): TEMP_SENSOR,
        vol.Optional(c.CONF_FLOW_SENSOR): ANY_SENSOR,
        vol.Optional(c.CONF_FLOW_UNIT, default="l_min"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["l_min", "l_h", "m3_h", "l_s", "gpm"],
                        translation_key="flow_unit",
                    )
                ),
        vol.Optional(c.CONF_PUMP_POWER_SENSOR): POWER_SENSOR,
        vol.Optional(c.CONF_HP_POWER_SENSOR): POWER_SENSOR,
        vol.Optional(c.CONF_PRICE_SENSOR): ANY_SENSOR,
        vol.Optional(c.CONF_PH_SENSOR): MANUAL_OR_SENSOR,
        vol.Optional(c.CONF_CHLORINE_SENSOR): MANUAL_OR_SENSOR,
        vol.Optional(c.CONF_TOTAL_CHLORINE_SENSOR): MANUAL_OR_SENSOR,
        vol.Optional(c.CONF_BROMINE_SENSOR): MANUAL_OR_SENSOR,
        vol.Optional(c.CONF_ALKALINITY_SENSOR): MANUAL_OR_SENSOR,
        vol.Optional(c.CONF_CYANURIC_SENSOR): MANUAL_OR_SENSOR,
        vol.Optional(c.CONF_HARDNESS_SENSOR): MANUAL_OR_SENSOR,
        vol.Optional(c.CONF_SALT_SENSOR): MANUAL_OR_SENSOR,
        vol.Optional(c.CONF_CHEAP_PRICE_SENSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
        ),
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
        self._defaults: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        if not self._defaults:
            self._defaults = await async_load_defaults(self.hass)
        if user_input is not None:
            self._data.update(derive_pool_shape(dict(user_input)))
            return await self.async_step_pump()
        return self.async_show_form(
            step_id="user", data_schema=_pool_schema(self._defaults)
        )

    async def async_step_pump(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_heat_pump()

        return self.async_show_form(
            step_id="pump",
            data_schema=_pump_schema(self._defaults),
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
            data_schema=_heat_pump_schema(self._defaults),
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
        turnover_h = (volume * 3.0) / (effective * 1000) if effective else 0
        # The daily minimum usually wins on pools with a generously sized pump,
        # so quoting only the turnover figure would understate the real runtime.
        daily_h = max(turnover_h, 4.0)

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
            menu_options=["entities", "hardware", "general", "swimming", "notifications"],
        )

    async def async_step_entities(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Change which entities the integration uses.

        Picking the wrong temperature sensor during setup is easy to do and used
        to be permanent, which was a design error: entity choices belong in
        options, where they can be corrected, not locked into the entry data.
        """
        if user_input is not None:
            cleaned = {k: v for k, v in user_input.items() if v}
            # Explicitly clear anything the user emptied, so an optional entity
            # can be removed again and not merely replaced.
            for key in c.OPTIONAL_ENTITY_KEYS:
                if key not in cleaned:
                    cleaned[key] = ""
            options = {**self.config_entry.options, **cleaned}
            return self.async_create_entry(data=options)

        current = {**self.config_entry.data, **self.config_entry.options}

        def field(key, required=False):
            marker = vol.Required if required else vol.Optional
            return marker(key, description={"suggested_value": current.get(key) or None})

        schema = vol.Schema(
            {
                field(c.CONF_PUMP_SWITCH, True): SWITCH,
                field(c.CONF_HP_SWITCH, True): SWITCH,
                field(c.CONF_WATER_TEMP_SENSOR, True): TEMP_SENSOR,
                field(c.CONF_AIR_TEMP_SENSOR): TEMP_SENSOR,
                field(c.CONF_PUMP_INLET_SENSOR): TEMP_SENSOR,
                field(c.CONF_PUMP_OUTLET_SENSOR): TEMP_SENSOR,
                field(c.CONF_HP_INLET_SENSOR): TEMP_SENSOR,
                field(c.CONF_HP_OUTLET_SENSOR): TEMP_SENSOR,
                field(c.CONF_FLOW_SENSOR): ANY_SENSOR,
                vol.Optional(
                    c.CONF_FLOW_UNIT,
                    default=current.get(c.CONF_FLOW_UNIT, "l_min"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["l_min", "l_h", "m3_h", "l_s", "gpm"],
                        translation_key="flow_unit",
                    )
                ),
                field(c.CONF_PUMP_POWER_SENSOR): POWER_SENSOR,
                field(c.CONF_HP_POWER_SENSOR): POWER_SENSOR,
                field(c.CONF_PRICE_SENSOR): ANY_SENSOR,
                field(c.CONF_PH_SENSOR): MANUAL_OR_SENSOR,
                field(c.CONF_CHLORINE_SENSOR): MANUAL_OR_SENSOR,
                field(c.CONF_TOTAL_CHLORINE_SENSOR): MANUAL_OR_SENSOR,
                field(c.CONF_BROMINE_SENSOR): MANUAL_OR_SENSOR,
                field(c.CONF_ALKALINITY_SENSOR): MANUAL_OR_SENSOR,
                field(c.CONF_CYANURIC_SENSOR): MANUAL_OR_SENSOR,
                field(c.CONF_HARDNESS_SENSOR): MANUAL_OR_SENSOR,
                field(c.CONF_SALT_SENSOR): MANUAL_OR_SENSOR,
                field(c.CONF_CHEAP_PRICE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["binary_sensor", "input_boolean"]
                    )
                ),
                field(c.CONF_SOLAR_POWER_SENSOR): POWER_SENSOR,
                field(c.CONF_SOLAR_FORECAST_SENSOR): ANY_SENSOR,
                field(c.CONF_WEATHER_ENTITY): WEATHER,
                field(c.CONF_COVER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["cover", "binary_sensor", "input_boolean"]
                    )
                ),
            }
        )
        return self.async_show_form(step_id="entities", data_schema=schema)

    async def async_step_hardware(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Correct the pool, pump and heat pump figures after setup."""
        if user_input is not None:
            data = derive_pool_shape(dict(user_input))
            input_kw = float(data.get(c.CONF_HP_INPUT_KW) or 0)
            thermal_kw = float(data.get(c.CONF_HP_THERMAL_KW) or 0)
            if input_kw:
                data[c.CONF_HP_COP_REF] = round(thermal_kw / input_kw, 3)
                if not data.get(c.CONF_HP_COP_LOW):
                    data[c.CONF_HP_COP_LOW] = data[c.CONF_HP_COP_REF]
                    data[c.CONF_HP_COP_LOW_TEMP] = data.get(c.CONF_HP_COP_REF_TEMP, 26.0)
            options = {**self.config_entry.options, **data}
            return self.async_create_entry(data=options)

        current = {**self.config_entry.data, **self.config_entry.options}

        def num(key, default, low, high, step=0.01):
            return vol.Optional(key, default=current.get(key, default)), _positive(
                low, high, step
            )

        pairs = [
            num(c.CONF_VOLUME_L, 10000, 100, 500000, 1),
            num(c.CONF_DEPTH_M, 1.2, 0.1, 5, 0.01),
            num(c.CONF_SURFACE_M2, 10.0, 1, 500, 0.1),
            num(c.CONF_MAX_TEMP, 32.0, 10, 40, 0.5),
            num(c.CONF_PUMP_FLOW_M3H, 3.0, 0.1, 100, 0.001),
            num(c.CONF_PUMP_POWER_KW, 0.1, 0.01, 10, 0.01),
            num(c.CONF_HP_INPUT_KW, 1.0, 0.05, 50, 0.01),
            num(c.CONF_HP_THERMAL_KW, 4.0, 0.1, 200, 0.1),
            num(c.CONF_HP_COP_REF_TEMP, 26.0, -10, 45, 0.5),
            num(c.CONF_HP_COP_LOW, 4.0, 1, 15, 0.01),
            num(c.CONF_HP_COP_LOW_TEMP, 15.0, -10, 45, 0.5),
            num(c.CONF_HP_AIR_TEMP_MIN, 11.0, -20, 30, 0.5),
            num(c.CONF_HP_AIR_TEMP_MAX, 43.0, 20, 60, 0.5),
            num(c.CONF_HP_FLOW_MIN_M3H, 2.0, 0, 50, 0.1),
        ]
        schema = vol.Schema(dict(pairs))
        schema = schema.extend(
            {
                vol.Optional(
                    c.CONF_PUMP_FLOW_MEASURED,
                    default=current.get(c.CONF_PUMP_FLOW_MEASURED, False),
                ): bool,
                vol.Optional(
                    c.CONF_UNIT_SYSTEM,
                    default=current.get(c.CONF_UNIT_SYSTEM, "metric"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["metric", "imperial"],
                        translation_key="unit_system",
                    )
                ),
                vol.Optional(
                    c.CONF_SANITISER,
                    default=current.get(c.CONF_SANITISER, "chlorine"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["chlorine", "bromine", "salt"],
                        translation_key="sanitiser",
                    )
                ),
                vol.Optional(
                    c.CONF_FILTER_MEDIA,
                    default=current.get(c.CONF_FILTER_MEDIA, "sand"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["sand", "glass", "balls", "cartridge", "none"],
                        translation_key="filter_media",
                    )
                ),
                vol.Optional(
                    c.CONF_HP_FLOW_MIN_BLOCKING,
                    default=current.get(c.CONF_HP_FLOW_MIN_BLOCKING, False),
                ): bool,
                vol.Optional(
                    c.CONF_HP_FLOW_MIN_VERIFIED,
                    default=current.get(c.CONF_HP_FLOW_MIN_VERIFIED, False),
                ): bool,
            }
        )
        return self.async_show_form(step_id="hardware", data_schema=schema)

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
                    default=current.get(c.CONF_TURNOVER_FACTOR, 3.0),
                ): _positive(0.5, 6.0, 0.1),
                vol.Optional(
                    c.CONF_MIN_DAILY_HOURS,
                    default=current.get(c.CONF_MIN_DAILY_HOURS, 4.0),
                ): _positive(0.5, 24.0, 0.5),
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
                    c.CONF_COMPRESSOR_MIN_OFF,
                    default=current.get(c.CONF_COMPRESSOR_MIN_OFF, 10),
                ): _positive(0, 60, 1),
                vol.Optional(
                    c.CONF_COMPRESSOR_MIN_ON,
                    default=current.get(c.CONF_COMPRESSOR_MIN_ON, 10),
                ): _positive(0, 60, 1),
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
                    c.CONF_MAX_PRICE,
                    default=current.get(c.CONF_MAX_PRICE, c.DEFAULT_MAX_PRICE),
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
                    description={
                        "suggested_value": current.get(c.CONF_SOLAR_THRESHOLD_W)
                    },
                ): _positive(0, 20000, 50),
                vol.Optional(
                    c.CONF_SOLAR_MARGIN_W,
                    default=current.get(c.CONF_SOLAR_MARGIN_W, 200),
                ): _positive(0, 5000, 50),
                vol.Optional(
                    c.CONF_SOLAR_HYSTERESIS_W,
                    default=current.get(c.CONF_SOLAR_HYSTERESIS_W, 300),
                ): _positive(0, 5000, 50),
                vol.Optional(
                    c.CONF_ECO_PRICE_FACTOR,
                    default=current.get(c.CONF_ECO_PRICE_FACTOR, 0.7),
                ): _positive(0.1, 1.0, 0.05),
                vol.Optional(
                    c.CONF_ACID_PRODUCT,
                    default=current.get(c.CONF_ACID_PRODUCT, "acid_15"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            "acid_15", "acid_37", "ph_plus",
                            "chlorine_granules_70", "chlorine_liquid_15",
                            "shock", "shock_non_chlorine", "algaecide", "tablet",
                        ],
                        translation_key="chem_product",
                    )
                ),
                vol.Optional(
                    c.CONF_CHLORINE_PRODUCT,
                    default=current.get(
                        c.CONF_CHLORINE_PRODUCT, "chlorine_granules_70"
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            "acid_15", "acid_37", "ph_plus",
                            "chlorine_granules_70", "chlorine_liquid_15",
                            "shock", "shock_non_chlorine", "algaecide", "tablet",
                        ],
                        translation_key="chem_product",
                    )
                ),
                vol.Optional(
                    c.CONF_CHEMISTRY_MINUTES,
                    default=current.get(c.CONF_CHEMISTRY_MINUTES, 30),
                ): _positive(5, 240, 5),
                vol.Optional(
                    c.CONF_PUMP_STARTUP_GRACE,
                    default=current.get(c.CONF_PUMP_STARTUP_GRACE, 120),
                ): _positive(0, 900, 10),
                vol.Optional(
                    c.CONF_CALIBRATION_TOLERANCE,
                    default=current.get(c.CONF_CALIBRATION_TOLERANCE, 0.6),
                ): _positive(0.1, 5.0, 0.1),
                vol.Optional(
                    c.CONF_STALE_WARNING_SECONDS,
                    default=current.get(c.CONF_STALE_WARNING_SECONDS, 900),
                ): _positive(60, 7200, 30),
                vol.Optional(
                    c.CONF_STALE_BLOCKING_SECONDS,
                    default=current.get(c.CONF_STALE_BLOCKING_SECONDS, 3600),
                ): _positive(300, 86400, 60),
                vol.Optional(
                    c.CONF_LEARNING_ENABLED,
                    default=current.get(c.CONF_LEARNING_ENABLED, True),
                ): bool,
            }
        )
        return self.async_show_form(step_id="general", data_schema=schema)
