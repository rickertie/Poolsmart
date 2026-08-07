"""Self-learning.

Three rules keep the model honest, and all three exist because a model that
learns from bad data is worse than one that does not learn at all:

1.  A session is only used if it closed cleanly. Interrupted sessions, sessions
    with faults, and sessions too short to measure anything are recorded and
    marked, not fed into the model.
2.  Every update is capped. One strange session may move a learned value by a
    limited fraction, never replace it.
3.  Outliers are rejected on physical grounds -- a COP outside the appliance's
    own clamps, a negative temperature rise while heating -- rather than
    statistically, because there is rarely enough data for statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .config import PoolConfig

#: Width of the air-temperature buckets used for the COP curve, in degrees.
COP_BUCKET_WIDTH = 5.0

#: A session shorter than this measures noise, not performance.
MIN_SESSION_MINUTES = 20.0

#: An idle period shorter than this measures noise, not heat loss.
MIN_IDLE_MINUTES = 60.0


def bucket_key(air_temp: float) -> str:
    """Bucket label for an air temperature, e.g. ``15-20``."""
    low = int(air_temp // COP_BUCKET_WIDTH * COP_BUCKET_WIDTH)
    return f"{low}-{low + int(COP_BUCKET_WIDTH)}"


@dataclass
class SessionRecord:
    """One heating session, from the heat pump starting to it stopping."""

    start: datetime
    end: datetime | None = None
    water_start: float | None = None
    water_end: float | None = None
    air_sum: float = 0.0
    air_samples: int = 0
    energy_kwh: float = 0.0
    thermal_kwh: float = 0.0
    interrupted: bool = False
    faults: list[str] = field(default_factory=list)

    # -- Derived -----------------------------------------------------------

    @property
    def duration_h(self) -> float:
        if self.end is None:
            return 0.0
        return max(0.0, (self.end - self.start).total_seconds() / 3600.0)

    @property
    def air_avg(self) -> float | None:
        if not self.air_samples:
            return None
        return self.air_sum / self.air_samples

    @property
    def degrees_gained(self) -> float | None:
        if self.water_start is None or self.water_end is None:
            return None
        return self.water_end - self.water_start

    @property
    def heating_rate(self) -> float | None:
        """Degrees per hour actually achieved."""
        gained = self.degrees_gained
        if gained is None or self.duration_h <= 0:
            return None
        return gained / self.duration_h

    @property
    def measured_cop(self) -> float | None:
        if self.energy_kwh <= 0:
            return None
        if self.thermal_kwh > 0:
            return self.thermal_kwh / self.energy_kwh
        return None

    def sample_air(self, value: float | None) -> None:
        if value is not None:
            self.air_sum += value
            self.air_samples += 1

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "duration_h": round(self.duration_h, 3),
            "water_start": self.water_start,
            "water_end": self.water_end,
            "air_avg": round(self.air_avg, 2) if self.air_avg is not None else None,
            "energy_kwh": round(self.energy_kwh, 3),
            "thermal_kwh": round(self.thermal_kwh, 3),
            "heating_rate": (
                round(self.heating_rate, 4) if self.heating_rate is not None else None
            ),
            "measured_cop": (
                round(self.measured_cop, 3) if self.measured_cop is not None else None
            ),
            "interrupted": self.interrupted,
            "faults": self.faults,
        }


#: How far above the appliance's theoretical best a measured rise may sit before
#: it is rejected. A little slack absorbs sensor noise and a warm afternoon
#: adding solar gain; beyond that the number is measuring something other than
#: the heat pump.
MAX_PLAUSIBLE_RATE_FACTOR = 1.25


@dataclass(frozen=True)
class SessionVerdict:
    """Whether a session may be learned from, and why not if it may not."""

    usable: bool
    reason: str


def assess(record: SessionRecord, config: PoolConfig) -> SessionVerdict:
    """Decide whether a closed session is fit to learn from."""
    if record.end is None:
        return SessionVerdict(False, "the session has not finished")
    if record.interrupted:
        return SessionVerdict(False, "the session was interrupted")
    if record.faults:
        return SessionVerdict(False, f"faults occurred: {', '.join(record.faults)}")
    if record.duration_h * 60 < MIN_SESSION_MINUTES:
        return SessionVerdict(
            False, f"too short to measure ({record.duration_h * 60:.0f} minutes)"
        )

    gained = record.degrees_gained
    if gained is None:
        return SessionVerdict(False, "the water temperature was not recorded")
    if gained <= 0:
        return SessionVerdict(
            False, f"the water did not warm up ({gained:+.2f} C), which is implausible"
        )

    cop = record.measured_cop
    if cop is not None:
        limits = config.heat_pump
        if not limits.cop_clamp_min <= cop <= limits.cop_clamp_max:
            return SessionVerdict(
                False, f"the measured COP of {cop:.2f} is outside the plausible range"
            )

    # Nothing else here checks the rise against what the appliance can physically
    # deliver, and without that check a session where the pump stirred stratified
    # water reads as a spectacular heating rate. Because the learned rate is
    # trusted ahead of any COP calculation, one such session quietly drives every
    # subsequent estimate -- a pool that really rises 0.15 C/h being planned as
    # though it rises 1.0.
    rate = record.heating_rate
    if rate is not None:
        ceiling = max_plausible_rate(config, record.air_avg)
        if rate > ceiling:
            return SessionVerdict(
                False,
                (
                    f"a rise of {rate:.2f} C/h is above the {ceiling:.2f} C/h this "
                    "heat pump can physically deliver, so something other than "
                    "heating caused it"
                ),
            )

    return SessionVerdict(True, "clean session")


def max_plausible_rate(config: PoolConfig, air_temp: float | None) -> float:
    """The fastest this pool can rise, from the appliance's own specification.

    Thermal output divided by the energy one degree takes. Solar gain and a
    generous tolerance are folded in through MAX_PLAUSIBLE_RATE_FACTOR rather
    than modelled, because the point is to catch the impossible rather than to
    predict the merely optimistic.
    """
    per_degree = config.pool.kwh_thermal_per_degree
    if per_degree <= 0:
        return float("inf")
    thermal = config.heat_pump.thermal_kw_at(air_temp if air_temp is not None else 20.0)
    return thermal / per_degree * MAX_PLAUSIBLE_RATE_FACTOR


def capped_update(current: float | None, proposed: float, max_step_ratio: float) -> float:
    """Move a learned value towards a new observation, by a limited step."""
    if current is None or current == 0:
        return proposed
    limit = abs(current) * max_step_ratio
    delta = max(-limit, min(limit, proposed - current))
    return current + delta


def update_cop_curve(
    curve: dict[str, float],
    record: SessionRecord,
    config: PoolConfig,
) -> dict[str, float]:
    """Fold a session's measured COP into the per-temperature curve.

    The heat pump does not modulate, so output is a function of outdoor
    temperature alone. That makes one value per bucket sufficient and the data
    clean.
    """
    cop = record.measured_cop
    air = record.air_avg
    if cop is None or air is None:
        return curve

    key = bucket_key(air)
    updated = dict(curve)
    updated[key] = round(
        capped_update(curve.get(key), cop, config.learning.max_step_ratio), 3
    )
    return updated


def heat_loss_from_idle(
    water_start: float,
    water_end: float,
    duration_h: float,
    covered: bool = False,
) -> float | None:
    """Heat loss in degrees per hour, measured over an idle period.

    ``covered`` is carried through so the cover's effect can be learned as soon
    as a sensor or switch reports its position. Until then every observation is
    attributed to the uncovered case, which is the conservative direction.
    """
    if duration_h * 60 < MIN_IDLE_MINUTES:
        return None
    drop = water_start - water_end
    if drop <= 0:
        # The pool warmed up on its own: sunshine, not heat loss.
        return None
    return drop / duration_h


#: Sessions needed in a bucket before its measured COP is trusted for planning.
#: One session is an anecdote; three is a pattern.
COP_CONFIDENCE_SESSIONS = 3


def cop_for(
    curve: dict[str, float],
    counts: dict[str, int],
    air_temp: float | None,
    neighbours: bool = True,
) -> float | None:
    """The measured COP to plan with at this outdoor temperature.

    Returns ``None`` until enough sessions have been recorded in the relevant
    band, because planning from a single measurement is not obviously better than
    planning from the datasheet -- and a wrong learned value is harder to spot
    than a wrong published one.

    With ``neighbours``, an adjacent band is used when the exact one is empty.
    Efficiency changes gradually with air temperature, so the band next door is a
    much better guess than a datasheet written for a different installation.
    """
    if air_temp is None or not curve:
        return None

    key = bucket_key(air_temp)
    if curve.get(key) is not None and counts.get(key, 0) >= COP_CONFIDENCE_SESSIONS:
        return curve[key]

    if not neighbours:
        return None

    low = int(air_temp // COP_BUCKET_WIDTH * COP_BUCKET_WIDTH)
    for offset in (-COP_BUCKET_WIDTH, COP_BUCKET_WIDTH):
        near = f"{int(low + offset)}-{int(low + offset + COP_BUCKET_WIDTH)}"
        if curve.get(near) is not None and counts.get(near, 0) >= COP_CONFIDENCE_SESSIONS:
            return curve[near]
    return None


def rate_confidence(sessions: int) -> str:
    """How much weight a learned figure deserves, in words."""
    if sessions >= 8:
        return "reliable"
    if sessions >= COP_CONFIDENCE_SESSIONS:
        return "usable"
    if sessions > 0:
        return "provisional"
    return "not learned yet"


#: Which learned figure each reset name clears, and the counter that goes with
#: it. Kept here rather than in the storage layer because it is a fact about the
#: learning model, not about how it happens to be persisted -- and because the
#: storage layer imports Home Assistant, which would put this beyond the reach
#: of the tests.
RESETTABLE = {
    "heating_rate": ("heating_rate_c_per_h", "heating_rate_sessions"),
    "heat_loss": ("heat_loss_c_per_h", "heat_loss_samples"),
    "heat_loss_covered": ("heat_loss_covered_c_per_h", "heat_loss_covered_samples"),
    "measured_flow": ("measured_flow_m3h", None),
    "cop": ("cop_by_air_bucket", "cop_sessions_by_bucket"),
}


def recover_cop_counts(
    curve: dict[str, float], sessions: list[dict]
) -> dict[str, int]:
    """Rebuild per-bucket session counts from the recorded sessions.

    The curve has existed far longer than the counter that gates it, so anyone
    who upgraded has learned values with a count of zero -- sitting behind a
    gate that can never open no matter how many sessions produced them.

    Where the session log has been trimmed away, one is assumed: enough to show
    the value exists, not enough to trust it for planning. That is the honest
    position for a figure whose provenance was lost.
    """
    counts: dict[str, int] = {}
    for entry in sessions:
        if not entry.get("usable") or entry.get("measured_cop") is None:
            continue
        air = entry.get("air_avg")
        if air is None:
            continue
        key = bucket_key(float(air))
        counts[key] = counts.get(key, 0) + 1

    for key in curve:
        counts.setdefault(key, 1)
    return counts
