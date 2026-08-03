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
            PoolSmartRunAdvisor(coordinator),
            PoolSmartAcceptSuggestion(coordinator),
            PoolSmartRecordWaterTest(coordinator),
        ]
    )


class PoolSmartBoostNow(PoolSmartEntity, ButtonEntity):
    _entity_domain = "button"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "boost_now")

    async def async_press(self) -> None:
        await self.coordinator.async_set_mode(Mode.BOOST.value)


class PoolSmartForceFiltration(PoolSmartEntity, ButtonEntity):
    _entity_domain = "button"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "force_filtration")

    async def async_press(self) -> None:
        await self.coordinator.async_force_filtration()


class PoolSmartStartChemistry(PoolSmartEntity, ButtonEntity):
    _entity_domain = "button"
    """Circulate for a chemical treatment.

    The hardware for automated dosing does not exist yet; this button makes the
    branch useful in the meantime.
    """

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "start_chemistry_cycle")

    async def async_press(self) -> None:
        await self.coordinator.async_start_chemistry()


class PoolSmartResetLearning(PoolSmartEntity, ButtonEntity):
    _entity_domain = "button"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reset_learning")

    async def async_press(self) -> None:
        await self.coordinator.async_reset_learning()


class PoolSmartRunAdvisor(PoolSmartEntity, ButtonEntity):
    _entity_domain = "button"
    """Ask the advisory layer to review the past week.

    This never changes anything by itself. It produces suggestions that sit
    waiting for a human to accept them.
    """

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "run_advisor")

    async def async_press(self) -> None:
        await self.coordinator.async_run_advisor()


class PoolSmartAcceptSuggestion(PoolSmartEntity, ButtonEntity):
    _entity_domain = "button"
    """Apply the topmost pending suggestion."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "accept_suggestion")

    @property
    def available(self) -> bool:
        result = self.coordinator.advisor.last_result
        return bool(result and result.suggestions)

    async def async_press(self) -> None:
        await self.coordinator.async_accept_suggestion(0)


class PoolSmartRecordWaterTest(PoolSmartEntity, ButtonEntity):
    """Mark the water as tested just now.

    Also closes off the most recent dose by recording what the reading became,
    which is how the correction factor gets its data. Without that follow-up
    reading a dose log is a list of guesses with no outcomes.
    """

    _entity_domain = "button"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "record_water_test")

    async def async_press(self) -> None:
        await self.coordinator.async_record_test()
