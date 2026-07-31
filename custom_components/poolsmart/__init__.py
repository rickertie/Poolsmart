"""PoolSmart: an intelligent swimming pool controller for Home Assistant.

Architecture in one sentence: ESPHome measures, Home Assistant decides, and every
decision comes from a single priority ladder in :mod:`core.ladder`.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import websocket as poolsmart_ws
from .const import DOMAIN, PANEL_URL
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
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="poolsmart-panel",
        frontend_url_path=PANEL_URL,
        module_url=f"/{DOMAIN}_panel/poolsmart-panel.js",
        sidebar_title="Pool",
        sidebar_icon="mdi:pool",
        require_admin=False,
    )
    hass.data[f"{DOMAIN}_panel"] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PoolSmart from a config entry."""
    coordinator = PoolSmartCoordinator(hass, entry)
    await coordinator.async_restore()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    if not hass.data.get(f"{DOMAIN}_ws"):
        poolsmart_ws.async_register(hass)
        hass.data[f"{DOMAIN}_ws"] = True

    try:
        await _async_register_panel(hass)
    except Exception:  # noqa: BLE001 -- the panel is a convenience, not a dependency
        _LOGGER.warning("Could not register the PoolSmart panel; control is unaffected")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: PoolSmartCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.store.async_save()
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
