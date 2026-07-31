"""Pool cover support.

No cover sensor exists yet, so the state is reported as unknown and the thermal
model attributes every observation to the uncovered case. That is the
conservative direction: assuming a cover that is not there would make the system
under-heat and miss its deadlines.

When a sensor or a manual switch appears, point ``cover_entity`` at it. Heat loss
is then learned separately for covered and uncovered periods and the difference
becomes visible in the learning tab.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Multiplier applied to heat loss while the cover is on, used only until enough
#: covered and uncovered periods have been observed to learn the real figure.
ASSUMED_COVER_FACTOR = 0.4


@dataclass(frozen=True)
class CoverState:
    """What is known about the cover right now."""

    covered: bool | None
    source: str

    @property
    def known(self) -> bool:
        return self.covered is not None


class CoverModule:
    """Reports cover position and its effect on heat loss."""

    def __init__(self, coordinator, cover_entity: str | None = None) -> None:
        self._coordinator = coordinator
        self._entity = cover_entity

    def state(self) -> CoverState:
        if not self._entity:
            return CoverState(covered=None, source="no cover entity configured")
        raw = self._coordinator.hass.states.get(self._entity)
        if raw is None or raw.state in ("unknown", "unavailable"):
            return CoverState(covered=None, source="cover entity unavailable")
        covered = raw.state in ("on", "closed", "true")
        return CoverState(covered=covered, source=self._entity)

    def heat_loss_factor(self, learned_factor: float | None = None) -> float:
        """Multiplier to apply to the uncovered heat loss figure."""
        state = self.state()
        if not state.known or not state.covered:
            return 1.0
        return learned_factor if learned_factor is not None else ASSUMED_COVER_FACTOR
