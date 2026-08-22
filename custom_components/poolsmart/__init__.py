"""PoolSmart: an intelligent swimming pool controller for Home Assistant.

Architecture in one sentence: ESPHome measures, Home Assistant decides, and every
decision comes from a single priority ladder in :mod:`core.ladder`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration
from homeassistant.util import slugify

from . import websocket as poolsmart_ws
from .const import CONF_ADOPT_FROM as MIGRATION_ADOPT
from .const import DOMAIN, MAX_PRICE_BOUNDS, MIGRATION_FLAG, PANEL_URL
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


def _resolve_config_path(hass: HomeAssistant, path: str) -> Path:
    """Resolve a user-supplied path, refusing anything outside the config dir.

    The import and export services used to write wherever the caller pointed
    them. A path like ``..\\..\\secrets.yaml`` walked straight out of the config
    directory, and on a multi-user Home Assistant that is a way to read and
    write arbitrary files. Resolving first and then checking the result is the
    only safe order: a symlink that points outward is caught by the resolved
    comparison, not by looking at the raw string.
    """
    base = Path(hass.config.path()).resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(base):
        raise ValueError(
            f"refusing to touch {candidate}: import/export paths must stay inside "
            "the Home Assistant configuration directory"
        )
    return candidate


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


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a config entry to the latest version.

    Home Assistant calls this during setup if ``entry.version`` is lower than
    the ``VERSION`` declared in the ``ConfigFlow``. Each migration step bumps
    the version by one, so a v1 entry passes through every intermediate step on
    its way to the current version instead of being migrated in one opaque leap.

    Returns ``True`` so setup continues regardless: a migration that partially
    fails still leaves a usable entry, and the version is only advanced once the
    data is actually in the expected shape.
    """
    if entry.version == 1:
        # Version 2 placeholder: no structural changes yet. Add migration logic
        # here when the ConfigFlow VERSION is bumped to 2, for example:
        #
        #   data = {**entry.data}
        #   data["some_new_key"] = default_value
        #   hass.config_entries.async_update_entry(entry, data=data, version=2)
        #
        # Returning True without bumping is safe: HA re-runs this on the next
        # startup until the version matches the flow.
        pass

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PoolSmart from a config entry."""
    await _async_migrate_entity_ids(hass, entry)

    coordinator = PoolSmartCoordinator(hass, entry)
    await coordinator.async_restore()
    await _async_warn_about_orphaned_history(hass, entry)
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


def _target_coordinator(hass: HomeAssistant, action: str) -> PoolSmartCoordinator | None:
    """The one coordinator a per-pool service call should act on.

    None of the services below take a target: they were written when a single
    pool was the only case anyone tested. With two or more config entries,
    looping over every coordinator means a dose recorded for one pool gets
    logged against all of them, and an export silently overwrites itself once
    per pool, leaving only the last one's history on disk. Refusing is safer
    than guessing which pool was meant.
    """
    coordinators = list(hass.data.get(DOMAIN, {}).values())
    if len(coordinators) == 1:
        return coordinators[0]
    if not coordinators:
        _LOGGER.error("Cannot %s: no PoolSmart pool is set up", action)
    else:
        _LOGGER.error(
            "Cannot %s: %d PoolSmart pools are set up and this service cannot "
            "yet target one of them specifically",
            action,
            len(coordinators),
        )
    return None


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the dose-recording service once."""
    if hass.services.has_service(DOMAIN, "record_dose"):
        return

    async def _record(call) -> None:
        from .core.chemistry import Product

        product = call.data["product"]
        try:
            Product(product)
        except ValueError:
            _LOGGER.error(
                "Refusing to record a dose for unknown product %r", product
            )
            return
        try:
            amount = float(call.data["amount"])
        except (TypeError, ValueError):
            _LOGGER.error("Dose amount %r is not a number", call.data["amount"])
            return
        if amount <= 0 or amount > 100000:
            # A garbage amount would poison the correction factors the doses
            # are used to learn from, so it is refused rather than stored.
            _LOGGER.error("Refusing implausible dose amount %s", amount)
            return
        unit = str(call.data.get("unit") or "")
        if unit not in ("g", "ml", "l", "L", "kg"):
            _LOGGER.error("Refusing dose with unrecognised unit %r", unit)
            return

        coordinator = _target_coordinator(hass, "record a dose")
        if coordinator is None:
            return
        chemistry = coordinator.water_chemistry
        before = (
            chemistry["ph"]
            if product in ("acid_15", "acid_37", "ph_plus")
            else chemistry["chlorine"]
        )
        await coordinator.async_record_dose(
            product=product,
            amount=amount,
            unit=unit,
            measured_before=before if before is not None else 0.0,
        )

    hass.services.async_register(DOMAIN, "record_dose", _record)

    async def _reset(call) -> None:
        coordinator = _target_coordinator(hass, "reset a learned value")
        if coordinator is None:
            return
        if coordinator.store.reset_learned(call.data["value"]):
            await coordinator.store.async_save(force=True)
            await coordinator.async_request_refresh()
            _LOGGER.info("Reset learned value: %s", call.data["value"])

    hass.services.async_register(DOMAIN, "reset_learned", _reset)

    async def _set_setting(call) -> None:
        """Change one of the values also exposed as a number entity.

        A domain service rather than a call to the number entity directly,
        because the panel that calls this has no reliable way to know the
        entity_id -- it depends on the pool's name, which the panel does not
        assume. See issue #23.

        Unlike this integration's other services, invalid input is raised
        rather than logged and swallowed: the panel calls this synchronously
        and shows its own "Saved"/"failed" status from whether the call
        succeeded, so a silent no-op here would have it claim success for a
        value that was actually rejected.
        """
        key = str(call.data["key"])
        try:
            value = float(call.data["value"])
        except (TypeError, ValueError):
            raise ServiceValidationError(
                f"Setting value {call.data.get('value')!r} is not a number"
            ) from None

        coordinator = _target_coordinator(hass, "change a setting")
        if coordinator is None:
            raise ServiceValidationError(
                "Cannot change a setting: no PoolSmart pool is set up, or more "
                "than one is and this service cannot yet target one specifically"
            )

        bounds = {
            "target_temp": (10.0, coordinator.pool_config.comfort.max_temp),
            # Shared with the options flow, number.py and the AI advisor's
            # whitelist -- see const.MAX_PRICE_BOUNDS.
            "max_price": MAX_PRICE_BOUNDS,
            "solar_threshold": (0.0, 20000.0),
            "power_limit": (0.0, 30000.0),
            "max_temp": (coordinator.pool_config.comfort.target_temp, 40.0),
            "min_daily_hours": (0.5, 24.0),
            "eco_price_factor": (0.1, 1.0),
        }
        limits = bounds.get(key)
        if limits is None:
            raise ServiceValidationError(f"Unknown setting {key!r}")
        low, high = limits
        if not (low <= value <= high):
            raise ServiceValidationError(
                f"{value} is outside the {low}-{high} range for {key}"
            )

        setters = {
            "target_temp": coordinator.async_set_target,
            "max_price": coordinator.async_set_max_price,
            "solar_threshold": coordinator.async_set_solar_threshold,
            "power_limit": coordinator.async_set_power_limit,
            "max_temp": coordinator.async_set_max_temp,
            "min_daily_hours": coordinator.async_set_min_daily_hours,
            "eco_price_factor": coordinator.async_set_eco_price_factor,
        }
        await setters[key](value)

    hass.services.async_register(DOMAIN, "set_setting", _set_setting)

    async def _set_session_review(call) -> None:
        from .core.learning import SESSION_REVIEW_STATES

        review = str(call.data["review"])
        if review not in SESSION_REVIEW_STATES:
            _LOGGER.error("Refusing unknown review %r", review)
            return

        coordinator = _target_coordinator(hass, "review a session")
        if coordinator is None:
            return
        session_start = str(call.data["session_start"])
        found = await coordinator.async_set_session_review(session_start, review)
        if not found:
            _LOGGER.error(
                "Refusing to set review %r: no session starting at %s was found",
                review,
                session_start,
            )
            return
        _LOGGER.info("Session %s reviewed as %r", session_start, review)

    hass.services.async_register(DOMAIN, "set_session_review", _set_session_review)

    async def _export(call) -> None:
        from .recovery import export_payload

        try:
            path = _resolve_config_path(
                hass, call.data.get("path") or "poolsmart_learning.json"
            )
        except ValueError as err:
            _LOGGER.error("%s", err)
            return

        coordinator = _target_coordinator(hass, "export learned history")
        if coordinator is None:
            return
        payload = export_payload(coordinator.store, call.data.get("sections"))

        def _write() -> None:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        await hass.async_add_executor_job(_write)
        _LOGGER.info("Exported learned history to %s", path)

    hass.services.async_register(DOMAIN, "export_learning", _export)

    async def _import(call) -> None:
        from .recovery import validate_import

        try:
            path = _resolve_config_path(hass, call.data["path"])
        except (ValueError, KeyError) as err:
            _LOGGER.error("Refusing to import: %s", err)
            return

        def _read() -> dict:
            return json.loads(path.read_text(encoding="utf-8"))

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

        coordinator = _target_coordinator(hass, "import learned history")
        if coordinator is None:
            return
        taken = coordinator.store.adopt(payload)
        await coordinator.store.async_save(force=True)
        await coordinator.async_request_refresh()
        _LOGGER.info("Imported learned history from %s: %s", path, taken)

    hass.services.async_register(DOMAIN, "import_learning", _import)

    async def _replace(call) -> None:
        from .recovery import validate_import

        if not call.data.get("confirm"):
            _LOGGER.error(
                "Refusing to replace learned history: confirm was not set to true"
            )
            return

        try:
            path = _resolve_config_path(hass, call.data["path"])
        except (ValueError, KeyError) as err:
            _LOGGER.error("Refusing to import: %s", err)
            return

        def _read() -> dict:
            return json.loads(path.read_text(encoding="utf-8"))

        try:
            payload = await hass.async_add_executor_job(_read)
        except (OSError, ValueError) as err:
            _LOGGER.error("Could not read %s: %s", path, err)
            return

        usable, why = validate_import(payload)
        if not usable:
            _LOGGER.error("Refusing to import %s: %s", path, why)
            return

        coordinator = _target_coordinator(hass, "replace learned history")
        if coordinator is None:
            return
        replaced = await coordinator.async_replace_history(
            payload, call.data.get("sections")
        )
        _LOGGER.warning(
            "Replaced learned history from %s, discarding what was there before: %s",
            path,
            replaced,
        )

    hass.services.async_register(DOMAIN, "replace_learning", _replace)

    async def _rebuild_learning(call) -> None:
        coordinator = _target_coordinator(hass, "reprocess learning history")
        if coordinator is None:
            return
        await coordinator.async_rebuild_learning()
        _LOGGER.info("Reprocessed learning history from the session log")

    hass.services.async_register(DOMAIN, "rebuild_learning", _rebuild_learning)

    async def _clear_debug_log(call) -> None:
        coordinator = _target_coordinator(hass, "clear the debug log")
        if coordinator is None:
            return
        await coordinator.async_clear_debug_log()
        _LOGGER.info("Cleared the decision log and near-miss tally")

    hass.services.async_register(DOMAIN, "clear_debug_log", _clear_debug_log)

    async def _clear_all_history(call) -> None:
        if not call.data.get("confirm"):
            _LOGGER.error(
                "Refusing to clear all history: confirm was not set to true"
            )
            return
        coordinator = _target_coordinator(hass, "clear all history")
        if coordinator is None:
            return
        await coordinator.async_clear_all_history()
        _LOGGER.warning("Cleared all learned history, sessions, doses, and logs")

    hass.services.async_register(DOMAIN, "clear_all_history", _clear_all_history)


async def _async_warn_about_orphaned_history(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Surface storage files an old, removed-and-re-added entry left behind.

    A plain in-place update never regenerates ``entry.entry_id``, so it never
    orphans anything -- but a remove/re-add (troubleshooting a broken update,
    or reinstalling) does, and the old ``poolsmart.state.<entry_id>`` file
    then sits on disk under a key nothing reads any more, looking exactly like
    "options and history lost after updating" (issue #18) unless the adopt
    flow at setup happens to catch it. This only logs -- adopting still goes
    through the existing setup-time flow -- so it costs nothing when nothing
    is orphaned.
    """
    from .recovery import find_orphans

    active = {e.entry_id for e in hass.config_entries.async_entries(DOMAIN)}
    orphans = await hass.async_add_executor_job(find_orphans, hass, active)
    if orphans:
        _LOGGER.warning(
            "Found %d orphaned PoolSmart storage file(s) from a previous "
            "install that no current config entry reads: %s. If this "
            "pool's options or learned history look reset after an update, "
            "this is likely why -- remove and re-add the integration to be "
            "offered adoption of one of these files, or restore it manually.",
            len(orphans),
            ", ".join(o.path for o in orphans),
        )


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

    try:
        source = str(_resolve_config_path(hass, source))
    except ValueError as err:
        _LOGGER.warning("Not adopting history: %s", err)
        return

    history = await hass.async_add_executor_job(read_history, source)
    if history:
        taken = coordinator.store.adopt(history)
        await coordinator.store.async_save(force=True)
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
        await coordinator.store.async_save(force=True)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change.

    Skipped when the change already took effect live -- see
    :meth:`PoolSmartCoordinator.consume_suppressed_reload`, set by the number
    entities (price ceiling, solar threshold) that update an option without
    needing the integration restarted. A genuine options-flow change still
    reloads as before.

    The options flow's ``_save`` returns to its menu instead of closing, so
    saving several sections in one visit fires this listener once per save --
    each as its own background task, since that is how Home Assistant invokes
    update listeners. Nothing serialised those against each other: two saves a
    moment apart could each begin a full unload/setup cycle for this entry
    while the other was still mid-flight, and whichever one's coordinator
    finished setting up last would win the ``hass.data`` slot while the other
    kept ticking in the background -- eventually persisting its own, older
    session log over the good one. The lock below makes sure only one
    unload/setup cycle for this entry ever runs at a time.
    """
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None and coordinator.consume_suppressed_reload():
        return
    locks: dict[str, asyncio.Lock] = hass.data.setdefault(f"{DOMAIN}_reload_locks", {})
    lock = locks.setdefault(entry.entry_id, asyncio.Lock())
    async with lock:
        await hass.config_entries.async_reload(entry.entry_id)
