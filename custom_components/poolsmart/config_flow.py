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


def _kind_schema(d: dict) -> vol.Schema:
    """The questions that change every question after them.

    Asked first and on their own, because the answers decide which of the later
    steps make sense at all. A pool with an immersion element has no COP curve
    to describe and no minimum air temperature; asking anyway produces fields
    someone has to guess at, and guesses are worse than defaults.
    """
    return vol.Schema(
        {
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(
                c.CONF_POOL_KIND, default=d[c.CONF_POOL_KIND]
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["inflatable", "frame", "above_ground", "in_ground"],
                    translation_key="pool_kind",
                )
            ),
            vol.Required(
                c.CONF_HEATING_SOURCE, default=d[c.CONF_HEATING_SOURCE]
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["heat_pump", "electric", "solar", "gas", "none"],
                    translation_key="heating_source",
                )
            ),
            vol.Required(
                c.CONF_HAS_SOLAR_COLLECTOR,
                default=d[c.CONF_HAS_SOLAR_COLLECTOR],
            ): bool,
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


def _heating_schema(d: dict, source: str) -> vol.Schema:
    """Only the questions this heating source can answer.

    An immersion element is exactly as efficient at every temperature and works
    in any weather, so a COP curve and an operating envelope are not simplified
    for it -- they do not exist. A solar collector is not switched by the
    integration at all.
    """
    from .core.config import SOURCE_TRAITS, HeatingSource

    traits = SOURCE_TRAITS[HeatingSource(source)]

    if source == "none":
        return vol.Schema({})

    if source == "solar":
        return vol.Schema(
            {
                vol.Optional(
                    c.CONF_COLLECTOR_MARGIN, default=d.get(c.CONF_COLLECTOR_MARGIN, 3.0)
                ): _positive(0.5, 15, 0.5),
            }
        )

    fields: dict = {
        vol.Required(c.CONF_HP_INPUT_KW, default=d[c.CONF_HP_INPUT_KW]): _positive(
            0.05, 50, 0.01
        ),
        vol.Required(
            c.CONF_HP_THERMAL_KW, default=d[c.CONF_HP_THERMAL_KW]
        ): _positive(0.1, 200, 0.1),
    }

    if traits["efficiency_varies"]:
        fields.update(
            {
                vol.Required(
                    c.CONF_HP_COP_REF_TEMP, default=d[c.CONF_HP_COP_REF_TEMP]
                ): _positive(-10, 45, 0.5),
                vol.Optional(c.CONF_HP_COP_LOW): _positive(1, 15, 0.01),
                vol.Optional(
                    c.CONF_HP_COP_LOW_TEMP, default=d[c.CONF_HP_COP_LOW_TEMP]
                ): _positive(-10, 45, 0.5),
            }
        )

    if traits["air_temp_limits"]:
        fields.update(
            {
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

    return vol.Schema(fields)



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


def _required_entities(source: str) -> vol.Schema:
    """What must be configured, which depends on what heats the water.

    Demanding a heat pump switch from someone whose collector is on a manual
    three-way valve asks them to name a switch that does not exist -- and there
    is nothing for the integration to operate anyway. The same applies to a pool
    with no heating at all, which still benefits from filtration scheduling and
    water chemistry.

    Circulation and a water temperature are required in every case: without the
    first there is nothing to control, and without the second nothing to reason
    about.
    """
    from .core.config import SOURCE_TRAITS, HeatingSource

    fields: dict = {
        vol.Required(c.CONF_PUMP_SWITCH): SWITCH,
        vol.Required(c.CONF_WATER_TEMP_SENSOR): TEMP_SENSOR,
    }
    if SOURCE_TRAITS[HeatingSource(source)]["controllable"]:
        fields[vol.Required(c.CONF_HP_SWITCH)] = SWITCH
    return vol.Schema(fields)


#: Kept for the options flow, where every field is optional anyway.
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
        vol.Optional(c.CONF_COLLECTOR_SENSOR): TEMP_SENSOR,
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
        self._orphans: list = []

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        if not self._defaults:
            self._defaults = await async_load_defaults(self.hass)
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_pool()
        return self.async_show_form(
            step_id="user", data_schema=_kind_schema(self._defaults)
        )

    async def async_step_pool(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(derive_pool_shape(dict(user_input)))
            return await self.async_step_pump()
        return self.async_show_form(
            step_id="pool", data_schema=_pool_schema(self._defaults)
        )

    async def async_step_pump(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_heating()

        return self.async_show_form(
            step_id="pump",
            data_schema=_pump_schema(self._defaults),
            description_placeholders={
                "derate": f"{int(100 * 0.7)}",
            },
        )

    async def async_step_heating(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Only what this heating source has."""
        source = self._data.get(c.CONF_HEATING_SOURCE, "heat_pump")

        if user_input is not None:
            if source in ("heat_pump", "electric", "gas"):
                input_kw = float(user_input.get(c.CONF_HP_INPUT_KW, 0) or 0)
                thermal_kw = float(user_input.get(c.CONF_HP_THERMAL_KW, 0) or 0)
                cop_ref = thermal_kw / input_kw if input_kw else 1.0
                user_input[c.CONF_HP_COP_REF] = round(cop_ref, 3)
                if not user_input.get(c.CONF_HP_COP_LOW):
                    # A source whose efficiency does not vary gets a flat curve
                    # rather than a curve pretending to vary.
                    user_input[c.CONF_HP_COP_LOW] = round(cop_ref, 3)
                    user_input[c.CONF_HP_COP_LOW_TEMP] = user_input.get(
                        c.CONF_HP_COP_REF_TEMP, 26.0
                    )
            self._data.update(user_input)
            return await self.async_step_entities()

        recommended = float(self._data.get(c.CONF_MAX_TEMP, 32.0)) + 2.0
        return self.async_show_form(
            step_id="heating",
            data_schema=_heating_schema(self._defaults, source),
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
            return await self.async_step_adopt()

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

    async def async_step_adopt(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Offer learned history left behind by an earlier installation.

        Removing an integration and adding it again gives a new entry id, and the
        storage key is built from that id — so weeks of measured heat loss, a COP
        curve and a session history are still on disk under a key nothing reads
        any more. Rebuilding that takes days of idle periods and completed
        sessions, which is a poor thing to ask of someone who only wanted to
        change a setting.
        """
        from .recovery import find_orphans

        if user_input is not None:
            chosen = user_input.get(c.CONF_ADOPT_FROM)
            if chosen and chosen != "none":
                self._data[c.CONF_ADOPT_FROM] = chosen
            title = self._data.pop(CONF_NAME, DEFAULT_NAME)
            return self.async_create_entry(title=title, data=self._data)

        active = {entry.entry_id for entry in self._async_current_entries()}
        orphans = await self.hass.async_add_executor_job(
            find_orphans, self.hass, active
        )
        if not orphans:
            title = self._data.pop(CONF_NAME, DEFAULT_NAME)
            return self.async_create_entry(title=title, data=self._data)

        self._orphans = orphans
        options = [{"value": "none", "label": "Start fresh"}] + [
            {"value": orphan.path, "label": orphan.describe()} for orphan in orphans
        ]
        return self.async_show_form(
            step_id="adopt",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        c.CONF_ADOPT_FROM, default=orphans[0].path
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options, mode=selector.SelectSelectorMode.LIST
                        )
                    )
                }
            ),
            description_placeholders={"count": str(len(orphans))},
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
        """One menu item per topic, rather than one bin marked "general".

        Twenty-eight unrelated settings under a single heading is not a category,
        it is what is left after categorising everything else. Each item below is
        one subject someone might arrive wanting to change.
        """
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "entities",
                "pool",
                "heating",
                "when_to_heat",
                "filtration",
                "water",
                "notifications",
                "advanced",
            ],
        )

    def _save(self, updates: dict) -> ConfigFlowResult:
        """Store a section and return to the menu instead of closing.

        Saving used to end the dialog, so changing three things meant opening
        Configure three times. Returning to the menu costs nothing and matches
        what anyone adjusting settings is actually doing.
        """
        self._pending.update(updates)
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options={**self.config_entry.options, **updates},
        )
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "entities",
                "pool",
                "heating",
                "when_to_heat",
                "filtration",
                "water",
                "notifications",
                "advanced",
            ],
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
            return self._save(dict(user_input))

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
                field(c.CONF_COLLECTOR_SENSOR): TEMP_SENSOR,
                field(c.CONF_COVER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["cover", "binary_sensor", "input_boolean"]
                    )
                ),
            }
        )
        return self.async_show_form(step_id="entities", data_schema=schema)

    async def async_step_pool(self, user_input: dict | None = None) -> ConfigFlowResult:
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
            return self._save(dict(user_input))

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

    async def async_step_heating(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """The heating appliance, and only the parts it actually has.

        Fields that do not apply are shown anyway, disabled, with the reason.
        Hiding them entirely would leave someone who later fits a heat pump
        wondering where the settings went, and it would hide why certain
        branches of the ladder never fire.
        """
        from .core.config import SOURCE_TRAITS, HeatingSource

        if user_input is not None:
            return self._save(user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        source = current.get(c.CONF_HEATING_SOURCE, "heat_pump")
        traits = SOURCE_TRAITS[HeatingSource(source)]

        fields: dict = {
            vol.Optional(
                c.CONF_HEATING_SOURCE, default=source
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["heat_pump", "electric", "solar", "gas", "none"],
                    translation_key="heating_source",
                )
            ),
            vol.Optional(
                c.CONF_HAS_SOLAR_COLLECTOR,
                default=current.get(c.CONF_HAS_SOLAR_COLLECTOR, False),
            ): bool,
        }

        if source != "none" and traits["controllable"]:
            fields[
                vol.Optional(
                    c.CONF_HP_INPUT_KW, default=current.get(c.CONF_HP_INPUT_KW, 0.58)
                )
            ] = _positive(0.05, 50, 0.01)
            fields[
                vol.Optional(
                    c.CONF_HP_THERMAL_KW,
                    default=current.get(c.CONF_HP_THERMAL_KW, 3.0),
                )
            ] = _positive(0.1, 200, 0.1)

        if traits["efficiency_varies"]:
            fields[
                vol.Optional(
                    c.CONF_HP_COP_REF, default=current.get(c.CONF_HP_COP_REF, 5.17)
                )
            ] = _positive(1, 15, 0.01)
            fields[
                vol.Optional(
                    c.CONF_HP_COP_REF_TEMP,
                    default=current.get(c.CONF_HP_COP_REF_TEMP, 26.0),
                )
            ] = _positive(-10, 45, 0.5)
            fields[
                vol.Optional(
                    c.CONF_HP_COP_LOW, default=current.get(c.CONF_HP_COP_LOW, 4.18)
                )
            ] = _positive(1, 15, 0.01)
            fields[
                vol.Optional(
                    c.CONF_HP_COP_LOW_TEMP,
                    default=current.get(c.CONF_HP_COP_LOW_TEMP, 15.0),
                )
            ] = _positive(-10, 45, 0.5)

        if traits["air_temp_limits"]:
            fields[
                vol.Optional(
                    c.CONF_HP_AIR_TEMP_MIN,
                    default=current.get(c.CONF_HP_AIR_TEMP_MIN, 11.0),
                )
            ] = _positive(-20, 30, 0.5)
            fields[
                vol.Optional(
                    c.CONF_HP_AIR_TEMP_MAX,
                    default=current.get(c.CONF_HP_AIR_TEMP_MAX, 43.0),
                )
            ] = _positive(20, 60, 0.5)
            fields[
                vol.Optional(
                    c.CONF_HP_FLOW_MIN_M3H,
                    default=current.get(c.CONF_HP_FLOW_MIN_M3H, 2.0),
                )
            ] = _positive(0, 50, 0.1)
            fields[
                vol.Optional(
                    c.CONF_HP_FLOW_MIN_BLOCKING,
                    default=current.get(c.CONF_HP_FLOW_MIN_BLOCKING, False),
                )
            ] = bool
            fields[
                vol.Optional(
                    c.CONF_HP_FLOW_MIN_VERIFIED,
                    default=current.get(c.CONF_HP_FLOW_MIN_VERIFIED, False),
                )
            ] = bool

        if current.get(c.CONF_HAS_SOLAR_COLLECTOR) or source == "solar":
            fields[
                vol.Optional(
                    c.CONF_COLLECTOR_MARGIN,
                    default=current.get(c.CONF_COLLECTOR_MARGIN, 3.0),
                )
            ] = _positive(0.5, 15, 0.5)

        inapplicable = [
            name
            for name, has in (
                ("efficiency curve", traits["efficiency_varies"]),
                ("operating envelope", traits["air_temp_limits"]),
                ("compressor protection", traits["compressor"]),
            )
            if not has
        ]
        return self.async_show_form(
            step_id="heating",
            data_schema=vol.Schema(fields),
            description_placeholders={
                "source": source.replace("_", " "),
                "not_applicable": ", ".join(inapplicable) or "none",
            },
        )

    async def async_step_swimming(self, user_input: dict | None = None) -> ConfigFlowResult:
        """When the pool should be at temperature.

        One window per weekday covers nearly every household. A second is offered
        for the exceptions and costs almost nothing, because the planner works
        from a list of deadlines either way.
        """
        if user_input is not None:
            return self._save(user_input)

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
            return self._save({c.CONF_NOTIFY_TARGETS: targets})

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

    async def async_step_filtration(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """How much circulation the pool needs, and when it may happen."""
        if user_input is not None:
            return self._save(user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="filtration",
            data_schema=vol.Schema(
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
                        c.CONF_NIGHT_START,
                        default=current.get(c.CONF_NIGHT_START, "22:00"),
                    ): str,
                    vol.Optional(
                        c.CONF_NIGHT_END,
                        default=current.get(c.CONF_NIGHT_END, "07:00"),
                    ): str,
                    vol.Optional(
                        c.CONF_PUMP_RUNDOWN_MINUTES,
                        default=current.get(c.CONF_PUMP_RUNDOWN_MINUTES, 5),
                    ): _positive(0, 60, 1),
                }
            ),
        )

    async def async_step_when_to_heat(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Temperatures, swimming times, price and sun in one place.

        These belong together because they answer one question between them --
        when is heating worth doing -- and separating the target temperature
        from the price ceiling meant visiting two screens to change one policy.
        """
        if user_input is not None:
            return self._save(user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="when_to_heat",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        c.CONF_TARGET_TEMP,
                        default=current.get(c.CONF_TARGET_TEMP, 28.0),
                    ): _positive(10, 40, 0.5),
                    vol.Optional(
                        c.CONF_MAX_TEMP, default=current.get(c.CONF_MAX_TEMP, 32.0)
                    ): _positive(10, 40, 0.5),
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
                    ): _positive(0, 5, 0.01),
                    vol.Optional(
                        c.CONF_ECO_PRICE_FACTOR,
                        default=current.get(c.CONF_ECO_PRICE_FACTOR, 0.7),
                    ): _positive(0.1, 1.0, 0.05),
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
                        c.CONF_SWIM_TIME,
                        default=current.get(c.CONF_SWIM_TIME, "16:00"),
                    ): str,
                }
            ),
        )

    async def async_step_water(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Which products are used, and how they are dosed."""
        if user_input is not None:
            return self._save(user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        chem_select = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    "acid_15", "acid_37", "ph_plus",
                    "chlorine_granules_70", "chlorine_liquid_15",
                    "shock", "shock_non_chlorine", "algaecide", "tablet",
                ],
                translation_key="chem_product",
            )
        )
        return self.async_show_form(
            step_id="water",
            data_schema=vol.Schema(
                {
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
                        c.CONF_ACID_PRODUCT,
                        default=current.get(c.CONF_ACID_PRODUCT, "acid_15"),
                    ): chem_select,
                    vol.Optional(
                        c.CONF_CHLORINE_PRODUCT,
                        default=current.get(
                            c.CONF_CHLORINE_PRODUCT, "chlorine_granules_70"
                        ),
                    ): chem_select,
                    vol.Optional(
                        c.CONF_TABLET_GRAMS,
                        default=current.get(c.CONF_TABLET_GRAMS, 20),
                    ): _positive(5, 1000, 5),
                    vol.Optional(
                        c.CONF_CHEMISTRY_MINUTES,
                        default=current.get(c.CONF_CHEMISTRY_MINUTES, 60),
                    ): _positive(5, 1440, 5),
                    vol.Optional(
                        c.CONF_FILTER_MEDIA,
                        default=current.get(c.CONF_FILTER_MEDIA, "sand"),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["sand", "glass", "cartridge", "balls", "de"],
                            translation_key="filter_media",
                        )
                    ),
                }
            ),
        )

    async def async_step_advanced(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """What you only touch when something is wrong.

        Kept apart deliberately. Of the settings this integration has, perhaps a
        third are ones anybody adjusts on purpose; the rest exist for when a
        measurement misbehaves. Mixing the two makes the first third harder to
        find, which was the whole complaint about a screen called "general".
        """
        if user_input is not None:
            return self._save(user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="advanced",
            data_schema=vol.Schema(
                {
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
                        c.CONF_TEMP_HYSTERESIS,
                        default=current.get(c.CONF_TEMP_HYSTERESIS, 0.3),
                    ): _positive(0.1, 3.0, 0.1),
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
                    ): _positive(60, 86400, 60),
                    vol.Optional(
                        c.CONF_STALE_BLOCKING_SECONDS,
                        default=current.get(c.CONF_STALE_BLOCKING_SECONDS, 3600),
                    ): _positive(60, 86400, 60),
                    vol.Optional(
                        c.CONF_LEARNING_ENABLED,
                        default=current.get(c.CONF_LEARNING_ENABLED, True),
                    ): bool,
                    vol.Optional(
                        c.CONF_MAX_STEP_RATIO,
                        default=current.get(c.CONF_MAX_STEP_RATIO, 0.15),
                    ): _positive(0.01, 1.0, 0.01),
                }
            ),
        )

    async def async_step_general(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)

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
                    c.CONF_TABLET_GRAMS,
                    default=current.get(c.CONF_TABLET_GRAMS, 20),
                ): _positive(5, 1000, 5),
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
