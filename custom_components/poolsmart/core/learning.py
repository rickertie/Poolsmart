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
    #: Irradiance samples, where anything can estimate how bright it was.
    irradiance_samples: list[float] = field(default_factory=list)
    #: Whether any part of the session fell in daylight hours. A session that
    #: touched daylight is allowed a sunnier ceiling, because for those hours the
    #: sky was heating the pool alongside the appliance.
    spans_daylight: bool = False
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

    def sample_irradiance(self, value: float | None) -> None:
        """Record how much sun was falling on the pool."""
        if value is not None:
            self.irradiance_samples.append(value)

    @property
    def irradiance_avg(self) -> float | None:
        if not self.irradiance_samples:
            return None
        return sum(self.irradiance_samples) / len(self.irradiance_samples)

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

    def snapshot(self) -> dict:
        """Full state of a still-running session, for resuming it after a restart.

        Unlike :meth:`as_dict`, which is a rounded summary for the finished-session
        log, this keeps every raw field the running session still needs to
        accumulate correctly -- the sample counts behind ``air_avg``, not the
        average itself.
        """
        return {
            "start": self.start.isoformat(),
            "water_start": self.water_start,
            "air_sum": self.air_sum,
            "air_samples": self.air_samples,
            "irradiance_samples": list(self.irradiance_samples),
            "spans_daylight": self.spans_daylight,
            "energy_kwh": self.energy_kwh,
            "thermal_kwh": self.thermal_kwh,
            "interrupted": self.interrupted,
            "faults": list(self.faults),
        }

    @classmethod
    def from_snapshot(cls, raw: dict) -> SessionRecord:
        return cls(
            start=datetime.fromisoformat(raw["start"]),
            water_start=raw.get("water_start"),
            air_sum=raw.get("air_sum", 0.0),
            air_samples=raw.get("air_samples", 0),
            irradiance_samples=list(raw.get("irradiance_samples", [])),
            spans_daylight=raw.get("spans_daylight", False),
            energy_kwh=raw.get("energy_kwh", 0.0),
            thermal_kwh=raw.get("thermal_kwh", 0.0),
            interrupted=raw.get("interrupted", False),
            faults=list(raw.get("faults", [])),
        )


#: How far above the appliance's theoretical best a measured rise may sit before
#: it is rejected. A little slack absorbs sensor noise and a warm afternoon
#: adding solar gain; beyond that the number is measuring something other than
#: the heat pump.
MAX_PLAUSIBLE_RATE_FACTOR = 1.25


@dataclass(frozen=True)
class MeasurementVerdicts:
    """What a session can and cannot teach.

    One flag per session threw away everything when anything went wrong, and on
    a real installation something is nearly always slightly wrong. A stale probe
    on the heat pump outlet ruins the COP and says nothing whatever about how
    fast the water rose -- so the rise is still worth learning from.
    """

    heating_rate: bool = False
    cop: bool = False
    reasons: dict = field(default_factory=dict)

    @property
    def anything_usable(self) -> bool:
        return self.heating_rate or self.cop

    def describe(self) -> str:
        """What this session contributed, rather than only why it fell short."""
        gained = []
        if self.heating_rate:
            gained.append("heating rate")
        if self.cop:
            gained.append("COP")
        if not gained:
            return "; ".join(self.reasons.values()) or "nothing usable"
        text = "learned " + " and ".join(gained)
        rejected = [f"{k}: {v}" for k, v in self.reasons.items()]
        return f"{text} ({'; '.join(rejected)})" if rejected else text

    def as_dict(self) -> dict:
        return {
            "heating_rate": self.heating_rate,
            "cop": self.cop,
            "reasons": self.reasons,
            "summary": self.describe(),
        }


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
        ceiling = max_plausible_rate(
            config,
            record.air_avg,
            irradiance_w_m2=record.irradiance_avg,
            daytime=record.spans_daylight,
        )
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


#: Fraction of incoming sunlight a pool surface actually retains as heat. The
#: rest is reflected or re-radiated. Widely quoted between 0.75 and 0.9.
SOLAR_ABSORPTION = 0.85

#: Assumed midday irradiance when there is no solar sensor to ask, in W/m2.
#: Deliberately on the generous side: the figure exists to avoid discarding real
#: measurements, and a ceiling set too low throws away good sessions while one
#: set too high merely lets a doubtful one through.
ASSUMED_PEAK_IRRADIANCE = 600.0


def solar_gain_kw(config: PoolConfig, irradiance_w_m2: float | None) -> float:
    """Free heat arriving through the surface.

    Easy to forget and far from negligible: six square metres of water under a
    summer sun takes in two to three kilowatts, comparable to the heat pump
    itself. A ceiling that ignores it will reject the best sessions of the year
    -- the long sunny ones -- as physically impossible.
    """
    surface = config.pool.surface_m2
    if surface <= 0 or not irradiance_w_m2:
        return 0.0
    return surface * irradiance_w_m2 * SOLAR_ABSORPTION / 1000.0


def max_plausible_rate(
    config: PoolConfig,
    air_temp: float | None,
    irradiance_w_m2: float | None = None,
    daytime: bool = True,
) -> float:
    """The fastest this pool can rise, appliance and sunshine together.

    The appliance's own output is the easy part. The sun is what the first
    version of this missed: a ten hour session starting at nine in the morning
    legitimately outruns the heat pump's rating, because for most of those hours
    the sky was heating the pool too.

    With a solar sensor the figure is measured. Without one, a generous midday
    assumption is used during daylight and none at night, since the whole point
    is to catch the impossible rather than to second-guess the merely good.
    """
    per_degree = config.pool.kwh_thermal_per_degree
    if per_degree <= 0:
        return float("inf")

    thermal = config.heat_pump.thermal_kw_at(air_temp if air_temp is not None else 20.0)

    if irradiance_w_m2 is not None:
        solar = solar_gain_kw(config, irradiance_w_m2)
    elif daytime:
        solar = solar_gain_kw(config, ASSUMED_PEAK_IRRADIANCE)
    else:
        solar = 0.0

    return (thermal + solar) / per_degree * MAX_PLAUSIBLE_RATE_FACTOR


#: Half-life for learned value decay, in days. After this many days an
#: observation has half the weight of a fresh one, so the model tracks
#: degrading equipment rather than trusting values from years ago.
DECAY_HALF_LIFE_DAYS = 90.0


def capped_update(
    current: float | None,
    proposed: float,
    max_step_ratio: float,
    last_updated: datetime | None = None,
    now: datetime | None = None,
) -> float:
    """Move a learned value towards a new observation, by a limited step.

    When ``last_updated`` is supplied the step grows with age: a value not
    updated in months may move further, because its age says it is measuring
    a pool that no longer exists -- equipment degrades, liners change.
    """
    if current is None or current == 0:
        return proposed
    ratio = max_step_ratio
    if last_updated is not None and now is not None:
        age_days = (now - last_updated).total_seconds() / 86400.0
        if age_days > 0:
            ratio = min(1.0, max_step_ratio * (2.0 ** (age_days / DECAY_HALF_LIFE_DAYS)))
    limit = abs(current) * ratio
    delta = max(-limit, min(limit, proposed - current))
    return current + delta


def update_cop_curve(
    curve: dict[str, float],
    cop: float | None,
    air: float | None,
    config: PoolConfig,
    updated_at: dict[str, datetime] | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, float], dict[str, datetime]]:
    """Fold one measured COP into the per-temperature curve.

    Returns ``(curve, updated_at)`` so callers can persist when each bucket
    was last refreshed. When ``updated_at`` is not given a fresh dict is
    created and decay is not applied.

    Takes the raw ``cop``/``air`` rather than a :class:`SessionRecord` so that
    :func:`rebuild_learned`, replaying the logged session history rather than a
    live session, can call the exact same update rule.
    """
    if cop is None or air is None:
        return curve, dict(updated_at) if updated_at else {}

    key = bucket_key(air)
    updated = dict(curve)
    timestamps = dict(updated_at) if updated_at else {}
    previous_at = timestamps.get(key)
    if now is not None:
        timestamps[key] = now
    updated[key] = round(
        capped_update(
            curve.get(key), cop, config.learning.max_step_ratio, previous_at, now
        ),
        3,
    )
    return updated, timestamps


#: Conservative fallback irradiance for an idle period with no solar sensor,
#: in W/m2. Deliberately far below :data:`ASSUMED_PEAK_IRRADIANCE`: that figure
#: is a ceiling a measured rate must stay under, so erring generous is the safe
#: direction. This one is subtracted from the observed warming instead, so
#: erring generous here would manufacture heat loss that never happened.
#: Erring conservative only costs some of the sunniest idle periods, which
#: stay discarded exactly as before -- the same outcome as today, not a worse
#: one.
ESTIMATED_IDLE_IRRADIANCE_W_M2 = 150.0


def idle_solar_gain_c(
    config: PoolConfig | None,
    duration_h: float,
    irradiance_w_m2: float | None,
    daytime: bool,
) -> float:
    """Degrees the sun alone likely added to the pool over an idle period.

    With a real irradiance reading (a solar sensor, averaged over the period)
    the figure is measured directly. Without one, a conservative flat estimate
    stands in for whatever part of the period fell in daylight hours, and
    nothing at all is assumed for a period with no daylight in it.
    """
    if config is None:
        return 0.0
    if irradiance_w_m2 is not None:
        watts = irradiance_w_m2
    elif daytime:
        watts = ESTIMATED_IDLE_IRRADIANCE_W_M2
    else:
        return 0.0
    per_degree = config.pool.kwh_thermal_per_degree
    if per_degree <= 0:
        return 0.0
    return solar_gain_kw(config, watts) * duration_h / per_degree


def heat_loss_from_idle(
    water_start: float,
    water_end: float,
    duration_h: float,
    config: PoolConfig | None = None,
    covered: bool = False,
    irradiance_w_m2: float | None = None,
    daytime: bool = False,
) -> float | None:
    """Heat loss in degrees per hour, measured over an idle period.

    ``covered`` is carried through so the cover's effect can be learned as soon
    as a sensor or switch reports its position. Until then every observation is
    attributed to the uncovered case, which is the conservative direction.

    A sunny idle period used to be a dead end: any period in which the water
    warmed up was discarded outright as "sunshine, not heat loss", which meant
    heat loss could only ever be learned at night or under cloud. Here the
    solar contribution estimated by :func:`idle_solar_gain_c` is added back
    into the observed change before judging it, so a warming period is
    understood rather than thrown away -- the loss the sun was masking still
    comes through as long as it exceeds what the sun can plausibly explain.
    Passing neither ``irradiance_w_m2`` nor ``daytime=True`` reproduces the old
    behaviour exactly, since the estimate is then zero.
    """
    if duration_h * 60 < MIN_IDLE_MINUTES:
        return None
    solar = idle_solar_gain_c(config, duration_h, irradiance_w_m2, daytime)
    drop = (water_start - water_end) + solar
    if drop <= 0:
        # Even crediting the sun its due, the water still net warmed up: real
        # sunshine outside what could be estimated, not heat loss.
        return None
    return drop / duration_h


#: Sessions needed in a bucket before its measured COP is trusted for planning.
#: COP varies with flow rate, solar gain, humidity, and more; three sessions is
#: the minimum before a measured figure is trusted over the datasheet.
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


#: Review states a logged session can carry. "auto" leaves the verdict that
#: was recorded when the session finished in charge; the other two are a
#: human's explicit correction and outrank it.
SESSION_REVIEW_STATES = ("auto", "included", "excluded")


def rebuild_learned(session_log: list[dict], config: PoolConfig) -> dict:
    """Recompute everything sessions teach, replaying the whole log in order.

    ``_finish_session`` updates the learned values incrementally, once, as each
    session finishes. That is fine until a session's review changes after the
    fact -- a capped incremental update has no way to go back and un-teach a
    session that turns out to have been excluded, or teach one that was
    wrongly rejected. Call this whenever a review changes, and use the result
    to replace (not merge into) the corresponding learned fields.

    Per entry, in order: "excluded" drops it regardless of what the automatic
    verdict said; "included" forces it in as long as the underlying value
    actually exists; "auto" (or a missing review, for logs written before this
    existed) falls back to the verdict recorded in ``measurements`` at the
    time. Only touches what sessions actually feed -- the heating rate and the
    COP curve -- because heat loss and measured flow come from idle periods
    and flow sensors, not sessions.
    """
    heating_rate_c_per_h: float | None = None
    heating_rate_updated_at: datetime | None = None
    heating_rate_sessions = 0
    cop_by_air_bucket: dict[str, float] = {}
    cop_updated_at: dict[str, datetime] = {}
    cop_sessions_by_bucket: dict[str, int] = {}
    session_count = 0

    ratio = config.learning.max_step_ratio

    for entry in session_log:
        if entry.get("review") == "excluded":
            continue
        included = entry.get("review") == "included"
        verdict = entry.get("measurements") or {}
        use_rate = (included or verdict.get("heating_rate")) and entry.get(
            "heating_rate"
        ) is not None
        use_cop = (included or verdict.get("cop")) and entry.get(
            "measured_cop"
        ) is not None
        if not (use_rate or use_cop):
            continue

        end = datetime.fromisoformat(entry["end"]) if entry.get("end") else None

        if use_rate:
            heating_rate_c_per_h = round(
                capped_update(
                    heating_rate_c_per_h,
                    entry["heating_rate"],
                    ratio,
                    heating_rate_updated_at,
                    end,
                ),
                4,
            )
            heating_rate_updated_at = end
            heating_rate_sessions += 1

        if use_cop:
            cop_by_air_bucket, cop_updated_at = update_cop_curve(
                cop_by_air_bucket,
                entry["measured_cop"],
                entry.get("air_avg"),
                config,
                cop_updated_at,
                end,
            )
            air = entry.get("air_avg")
            if air is not None:
                key = bucket_key(float(air))
                cop_sessions_by_bucket[key] = cop_sessions_by_bucket.get(key, 0) + 1

        session_count += 1

    return {
        "heating_rate_c_per_h": heating_rate_c_per_h,
        "heating_rate_sessions": heating_rate_sessions,
        "heating_rate_updated_at": heating_rate_updated_at,
        "cop_by_air_bucket": cop_by_air_bucket,
        "cop_updated_at": cop_updated_at,
        "cop_sessions_by_bucket": cop_sessions_by_bucket,
        "session_count": session_count,
    }


#: Faults that spoil one measurement without touching the other. A probe on the
#: heat pump outlet is what delta-T and therefore COP are built from; it has
#: nothing to do with how fast the pool warmed up.
COP_ONLY_FAULTS = frozenset(
    {
        "stale_hp_inlet",
        "stale_hp_outlet",
        "heat_pump_not_producing",
        "delta_t_implausible",
        "aliased_delta_t",
    }
)

#: Faults that make the temperature rise itself untrustworthy.
RATE_FAULTS = frozenset({"stale_water", "no_flow_while_pump_running"})


def needs_review(record: SessionRecord, measurements: MeasurementVerdicts) -> bool:
    """Whether a finished session is worth a human look before trusting the verdict.

    Mirrors the downgrade-only quality gates a confirm/correct workflow like
    WashData's uses: this never makes the automatic verdict more confident, it
    only flags the two cases where a person is likely to know something the
    heuristic does not -- a session long enough to hold real data that the
    heuristic rejected outright, or one it kept despite a fault having occurred
    during it.
    """
    long_enough = record.duration_h * 60 >= MIN_SESSION_MINUTES
    if not measurements.anything_usable and long_enough:
        return True
    if measurements.anything_usable and record.faults:
        return True
    return False


def assess_measurements(
    record: SessionRecord, config: PoolConfig
) -> MeasurementVerdicts:
    """Judge each measurement on its own merits.

    The all-or-nothing version discarded seven sessions out of seven on a real
    installation, several of which held perfectly good evidence of how fast the
    pool warms up. What ruined them was a probe on the heat pump going quiet --
    which spoils the efficiency figure and tells you nothing at all about the
    temperature rise.
    """
    reasons: dict[str, str] = {}
    faults = set(record.faults or ())

    if record.interrupted:
        return MeasurementVerdicts(
            reasons={
                "heating_rate": "the session was interrupted",
                "cop": "the session was interrupted",
            }
        )

    # -- Heating rate ------------------------------------------------------
    rate_ok = True
    if record.duration_h * 60 < MIN_SESSION_MINUTES:
        rate_ok = False
        reasons["heating_rate"] = (
            f"too short to measure ({record.duration_h * 60:.0f} minutes)"
        )
    elif record.heating_rate is None or record.heating_rate <= 0:
        rate_ok = False
        reasons["heating_rate"] = "the pool did not get warmer"
    elif faults & RATE_FAULTS:
        rate_ok = False
        reasons["heating_rate"] = (
            "the water temperature was unreliable: "
            + ", ".join(sorted(faults & RATE_FAULTS))
        )
    else:
        ceiling = max_plausible_rate(
            config,
            record.air_avg,
            irradiance_w_m2=record.irradiance_avg,
            daytime=record.spans_daylight,
        )
        if record.heating_rate > ceiling:
            rate_ok = False
            reasons["heating_rate"] = (
                f"a rise of {record.heating_rate:.2f} C/h is above the "
                f"{ceiling:.2f} C/h possible even with full sun, so something "
                "other than heating caused it"
            )

    # -- COP ---------------------------------------------------------------
    cop_ok = True
    cop = record.measured_cop
    if cop is None:
        cop_ok = False
        reasons["cop"] = "no usable inlet and outlet readings"
    elif faults & COP_ONLY_FAULTS:
        cop_ok = False
        reasons["cop"] = "the heat pump probes were unreliable: " + ", ".join(
            sorted(faults & COP_ONLY_FAULTS)
        )
    elif not (
        config.heat_pump.cop_clamp_min <= cop <= config.heat_pump.cop_clamp_max
    ):
        cop_ok = False
        reasons["cop"] = f"a measured COP of {cop:.2f} is outside the plausible range"

    return MeasurementVerdicts(heating_rate=rate_ok, cop=cop_ok, reasons=reasons)
