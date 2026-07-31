"""Chemical treatment support.

Dosing hardware is not installed yet, so this module is an interface with one
working piece: a manual cycle that runs the pump for a configured time. Branch 3
of the ladder already honours it, so when hardware does arrive the only change
needed is filling in :meth:`ChemistryModule.async_evaluate`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ChemistryRequest:
    """A request for circulation on chemical grounds."""

    until: datetime
    reason: str


class ChemistryModule:
    """Decides when chemistry requires circulation.

    Today the only source is the manual button. Once a dosing pump, ORP probe or
    pH probe exists, ``async_evaluate`` gains the automatic sources and nothing
    else in the system has to change.
    """

    def __init__(self, coordinator) -> None:
        self._coordinator = coordinator

    def manual_cycle(self, now: datetime, minutes: int) -> ChemistryRequest:
        return ChemistryRequest(
            until=now + timedelta(minutes=minutes),
            reason=f"Manual chemical treatment cycle of {minutes} minutes.",
        )

    async def async_evaluate(self, now: datetime) -> ChemistryRequest | None:
        """Automatic chemistry triggers.

        Returns ``None`` until dosing hardware exists. Placeholder rather than
        missing, so the branch is exercised by the existing tests and cannot rot.
        """
        return None
