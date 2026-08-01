"""Recording what the ladder considered.

A decision on its own answers "what is it doing". It does not answer the harder
question, which is "why is it not doing the other thing" -- and that is what
people actually ask when a pool is not heating.

The ladder knows the answer at the moment it walks past each branch, and used to
throw it away. This module keeps it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import Branch


class Verdict(str, Enum):
    """What happened to a branch when the ladder reached it."""

    #: This branch produced the decision.
    WON = "won"
    #: Conditions were not met.
    NOT_APPLICABLE = "not_applicable"
    #: The current mode does not include this branch.
    MODE = "mode"
    #: Blocked by the night window.
    NIGHT = "night"
    #: The heat pump is outside its operating envelope.
    ENVELOPE = "envelope"
    #: Electricity is too expensive right now.
    PRICE = "price"
    #: A higher branch already won, so this was never evaluated.
    NOT_REACHED = "not_reached"


#: Verdicts that mean the branch would otherwise have run. These are the ones
#: worth surfacing: "not applicable" is usually just noise, but "the mode
#: excludes it" or "the price is too high" is an answer.
INFORMATIVE = frozenset({Verdict.MODE, Verdict.NIGHT, Verdict.ENVELOPE, Verdict.PRICE})


@dataclass(frozen=True)
class TraceEntry:
    """One branch, and what became of it."""

    branch: Branch
    verdict: Verdict
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "branch": self.branch.name,
            "number": int(self.branch),
            "verdict": self.verdict.value,
            "detail": self.detail,
        }

    def describe(self) -> str:
        name = self.branch.name.replace("_", " ").lower()
        if self.verdict is Verdict.WON:
            return f"{name}: chosen"
        if self.verdict is Verdict.NOT_REACHED:
            return f"{name}: not reached"
        return f"{name}: {self.detail or self.verdict.value}"


@dataclass
class Trace:
    """The full walk down the ladder for one tick."""

    entries: list[TraceEntry] = field(default_factory=list)

    def record(self, branch: Branch, verdict: Verdict, detail: str = "") -> None:
        self.entries.append(TraceEntry(branch, verdict, detail))

    def fill_unreached(self, winner: Branch) -> None:
        """Mark everything below the winner as never evaluated.

        Being explicit about this matters: a branch missing from the trace looks
        like an oversight, whereas "not reached" is a fact about how the ladder
        works.
        """
        seen = {entry.branch for entry in self.entries}
        for branch in Branch:
            if branch not in seen and int(branch) > int(winner):
                self.entries.append(TraceEntry(branch, Verdict.NOT_REACHED))
        self.entries.sort(key=lambda e: int(e.branch))

    @property
    def blockers(self) -> list[TraceEntry]:
        """Branches that would have run but for a specific obstacle."""
        return [e for e in self.entries if e.verdict in INFORMATIVE]

    def as_list(self) -> list[dict]:
        return [entry.as_dict() for entry in self.entries]

    def summary(self) -> str:
        """One line naming the obstacles, for the log."""
        blockers = self.blockers
        if not blockers:
            return ""
        return "; ".join(entry.describe() for entry in blockers[:3])
