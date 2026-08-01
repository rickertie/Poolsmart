"""Shared entity base for PoolSmart."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import PoolSmartCoordinator


class PoolSmartEntity(CoordinatorEntity[PoolSmartCoordinator]):
    """Base class that ties every entity to one device."""

    _attr_has_entity_name = True

    #: Platform domain, set by each platform. Used to build a stable entity_id.
    _entity_domain: str | None = None

    def __init__(self, coordinator: PoolSmartCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer="PoolSmart",
            model="Pool controller",
        )

        # Fix the entity_id rather than letting Home Assistant derive it from the
        # displayed name. That name is translated, so a Dutch install produces
        # sensor.zwembad_klaar_om where an English one produces
        # sensor.pool_ready_at. Every shared dashboard, automation and piece of
        # documentation would then be wrong for half the users, which is not a
        # price worth paying for a prettier entity_id.
        if self._entity_domain:
            self.entity_id = async_generate_entity_id(
                f"{self._entity_domain}.{{}}",
                f"{slugify(coordinator.entry.title)}_{key}",
                hass=coordinator.hass,
            )

    @property
    def available(self) -> bool:
        """Available once a decision has ever been produced.

        The default behaviour ties availability to the last update succeeding,
        which makes every entity disappear on a single transient failure. The
        decision the pool is currently running on is still perfectly valid in
        that situation, so hiding it helps nobody.
        """
        return self.coordinator.decision is not None
