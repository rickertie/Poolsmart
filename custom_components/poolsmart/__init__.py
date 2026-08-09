"""PoolSmart: an intelligent swimming pool controller for Home Assistant.

Architecture in one sentence: ESPHome measures, Home Assistant decides, and every
decision comes from a single priority ladder in :mod:`core.ladder`.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration
from homeassistant.util import slugify

from . import websocket as poolsmart_ws
from .const import CONF_ADOPT_FROM as MIGRATION_ADOPT
from .const import DOMAIN, MIGRATION_FLAG, PANEL_URL
from .coordinator import PoolSmartCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def _async_panel_version(hass: HomeAssistant) -> str:
    """The integration version, used to bust the browser cache on the panel.

    Taken from the integration Home Assistant has already loaded rather than
    read off disk. Reading the manifest here looked harmless and was not: file
    access inside the event loop blocks every other integration for the duration,
    and Home Assistant reports it as a stability problem. It was also redundant
    -- the version was already in memory a function call away.
    """
    try:
        integration = await async_get_integration(hass, DOMAIN)
        return str(integration.version)
    except Exception:  # noqa: BLE001 -- a cache buster must never break setup
        return str(int(time.time()))


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register the sidebar panel once, no matter how many pools exist."""
    if hass.data.get(f"{DOMAIN}_panel"):
        return

    from homeassistant.components import panel_custom
    from homeassistant.components.http import StaticPathConfig

    module_path = hass.config.path(f"custom_components/{DOMAIN}/www")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(f"/{DOMAIN}_panel", module_path, True)]
    )
    version = await _async_panel_version(hass)
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="poolsmart-panel",
        frontend_url_path=PANEL_URL,
        # The version query is what makes an update actually visible. Without it
        # the browser keeps serving the cached copy of the panel, so a new tab or
        # a fixed card silently does not appear and the integration looks like it
        # did not update at all.
        module_url=f"/{DOMAIN}_panel/poolsmart-panel.js?v={version}",
        sidebar_title="Pool",
        sidebar_icon="mdi:pool",
        require_admin=False,
    )
    hass.data[f"{DOMAIN}_panel"] = True


async def _async_migrate_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rename entities created before the ids were fixed in code.

    Home Assistant builds an entity id from the entity's displayed name, and that
    name is translated, so a Dutch install ended up with sensor.pool_klaar_om
    where an English one got sensor.pool_ready_at. The registry records whatever
    id was assigned first and never revisits it, so simply shipping the fix does
    nothing for anyone who already installed the integration.

    This runs once per config entry. It will not touch an id that is already
    correct, and it will not steal an id that something else is using. Anything
    referring to the old ids -- automations, dashboards, scripts -- needs
    updating, which is why the renames are logged individually.
    """
    if entry.data.get(MIGRATION_FLAG):
        return

    registry = er.async_get(hass)
    prefix = slugify(entry.title)
    renamed: list[tuple[str, str]] = []

    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        key = reg_entry.unique_id.removeprefix(f"{entry.entry_id}_")
        wanted = f"{reg_entry.domain}.{prefix}_{key}"
        if reg_entry.entity_id == wanted:
            continue
        if registry.async_get(wanted) is not None:
            _LOGGER.warning(
                "Not renaming %s to %s because that id is already in use",
                reg_entry.entity_id,
                wanted,
            )
            continue
        registry.async_update_entity(reg_entry.entity_id, new_entity_id=wanted)
        renamed.append((reg_entry.entity_id, wanted))

    if renamed:
        _LOGGER.warning(
            "PoolSmart renamed %d entities to language-independent ids. Update any "
            "automations or dashboards that use the old ones: %s",
            len(renamed),
            ", ".join(f"{old} -> {new}" for old, new in renamed),
        )

    hass.config_entries.async_update_entry(
        entry, data={**entry.data, MIGRATION_FLAG: True}
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PoolSmart from a config entry."""
    await _async_migrate_entity_ids(hass, entry)

    coordinator = PoolSmartCoordinator(hass, entry)
    await coordinator.async_restore()
    await _async_adopt_history(hass, entry, coordinator)
    await coordinator.async_config_entry_first_refresh()

    coordinator.actions.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    if not hass.data.get(f"{DOMAIN}_ws"):
        poolsmart_ws.async_register(hass)
        hass.data[f"{DOMAIN}_ws"] = True

    try:
        await _async_register_panel(hass)
    except Exception:  # noqa: BLE001 -- the panel is a convenience, not a dependency
        _LOGGER.warning("Could not register the PoolSmart panel; control is unaffected")

    _async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the dose-recording service once."""
    if hass.services.has_service(DOMAIN, "record_dose"):
        return

    async def _record(call) -> None:
        for coordinator in hass.data.get(DOMAIN, {}).values():
            chemistry = coordinator.water_chemistry
            product = call.data["product"]
            before = (
                chemistry["ph"]
                if product in ("acid_15", "acid_37", "ph_plus")
                else chemistry["chlorine"]
            )
            await coordinator.async_record_dose(
                product=product,
                amount=float(call.data["amount"]),
                unit=call.data["unit"],
                measured_before=before if before is not None else 0.0,
            )

    hass.services.async_register(DOMAIN, "record_dose", _record)

    async def _reset(call) -> None:
        for coordinator in hass.data.get(DOMAIN, {}).values():
            if coordinator.store.reset_learned(call.data["value"]):
                await coordinator.store.async_save()
                await coordinator.async_request_refresh()
                _LOGGER.info("Reset learned value: %s", call.data["value"])

    hass.services.async_register(DOMAIN, "reset_learned", _reset)

    async def _export(call) -> None:
        from .recovery import export_payload

        path = call.data.get("path") or hass.config.path("poolsmart_learning.json")
        for coordinator in hass.data.get(DOMAIN, {}).values():
            payload = export_payload(coordinator.store)

            def _write() -> None:
                Path(path).write_text(
                    json.dumps(payload, indent=2), encoding="utf-8"
                )

            await hass.async_add_executor_job(_write)
            _LOGGER.info("Exported learned history to %s", path)

    hass.services.async_register(DOMAIN, "export_learning", _export)

    async def _import(call) -> None:
        from .recovery import validate_import

        path = call.data["path"]

        def _read() -> dict:
            return json.loads(Path(path).read_text(encoding="utf-8"))

        try:
            payload = await hass.async_add_executor_job(_read)
        except (OSError, ValueError) as err:
            _LOGGER.error("Could not read %s: %s", path, err)
            return

        usable, why = validate_import(payload)
        if not usable:
            # Refused outright rather than half-applied: a partial load leaves
            # the model in a state nobody can reason about.
            _LOGGER.error("Refusing to import %s: %s", path, why)
            return

        for coordinator in hass.data.get(DOMAIN, {}).values():
            taken = coordinator.store.adopt(payload)
            await coordinator.store.async_save()
            await coordinator.async_request_refresh()
            _LOGGER.info("Imported learned history from %s: %s", path, taken)

    hass.services.async_register(DOMAIN, "import_learning", _import)


async def _async_adopt_history(hass, entry, coordinator) -> None:
    """Take on learned history the user chose during setup.

    Done once and then forgotten: the marker is cleared from the entry so a
    later restart does not re-adopt over figures this pool has since measured
    for itself.
    """
    from .recovery import read_history

    source = entry.data.get(MIGRATION_ADOPT)
    if not source:
        return

    history = await hass.async_add_executor_job(read_history, source)
    if history:
        taken = coordinator.store.adopt(history)
        await coordinator.store.async_save()
        _LOGGER.info("Adopted learned history from a previous installation: %s", taken)
    else:
        _LOGGER.warning("Could not read the learned history at %s", source)

    data = dict(entry.data)
    data.pop(MIGRATION_ADOPT, None)
    hass.config_entries.async_update_entry(entry, data=data)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: PoolSmartCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.actions.async_stop()
        await coordinator.store.async_save()
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
