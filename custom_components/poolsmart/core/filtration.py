"""Filtration planning.

The daily requirement is expressed as pump runtime derived from pool volume,
pump flow and the turnover factor. It is split over a number of blocks spread
across the day.

Two properties of this module matter more than anything else, because both were
the source of bugs in the previous design:

1.  A block, once started, runs to completion. The engine never asks "has the
    quota been reached?" on every tick -- that is a threshold comparison against
    a value that jitters, and it oscillates. It asks "is a block running, and has
    its end time passed?", which is a state question and cannot oscillate.

2.  If the day would otherwise end with the quota unmet, the deadline becomes
    critical and circulation is forced regardless of price, mode or night
    window. The pool never silently skips a day of filtration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from .config import PoolConfig

#: How much slack to leave before declaring the deadline critical. Without a
#: margin the forced run would start exactly as the window closes and could not
#: finish.
DEADLINE_MARGIN_H = 0.25


@dataclass(frozen=True)
class BlockPlan:
    """A planned filtration block."""

    index: int
    start: datetime
    end: datetime
    #: Why this start time was chosen, for the decision log.
    rationale: str = ""

    @property
    def duration_h(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0


@dataclass(frozen=True)
class FiltrationStatus:
    """Everything the ladder needs to know about filtration right now."""

    required_h: float
    done_h: float
    remaining_h: float
    #: Runtime still available inside today's remaining windows.
    available_h: float
    deadline_critical: bool
    active_block: BlockPlan | None
    next_block: BlockPlan | None
    detail: dict = field(default_factory=dict)

    @property
    def satisfied(self) -> bool:
        return self.remaining_h <= 0.0


def _combine(day: date, value: time, tzinfo) -> datetime:
    return datetime.combine(day, value).replace(tzinfo=tzinfo)


def window_bounds(now: datetime, config: PoolConfig) -> list[tuple[int, datetime, datetime]]:
    """Today's filtration windows as absolute datetimes."""
    bounds: list[tuple[int, datetime, datetime]] = []
    for index, (start, end) in enumerate(config.filtration.windows):
        start_dt = _combine(now.date(), start, now.tzinfo)
        end_dt = _combine(now.date(), end, now.tzinfo)
        if end_dt <= start_dt:
            # Window crosses midnight.
            end_dt += timedelta(days=1)
        bounds.append((index, start_dt, end_dt))
    return bounds


def available_runtime_h(now: datetime, config: PoolConfig) -> float:
    """Runtime still available inside today's remaining windows."""
    total = 0.0
    for _index, start, end in window_bounds(now, config):
        effective_start = max(start, now)
        if end > effective_start:
            total += (end - effective_start).total_seconds() / 3600.0
    return total


def _cheapest_start(
    window_start: datetime,
    window_end: datetime,
    duration_h: float,
    price_forecast: tuple[tuple[datetime, datetime, float], ...],
) -> tuple[datetime, str]:
    """Pick the cheapest start time for a block inside a window.

    Filtration costs very little -- for a typical pool a few cents a day -- so
    this is a mild preference, not an optimisation worth bending the schedule
    for. Without price data the block simply starts when the window opens, which
    is predictable and easy to explain.
    """
    latest_start = window_end - timedelta(hours=duration_h)
    if latest_start <= window_start:
        return window_start, "window too short for a full block, starting immediately"

    candidates = [
        (price, start)
        for start, _end, price in price_forecast
        if window_start <= start <= latest_start
    ]
    if not candidates:
        return window_start, "no price data, starting at window opening"

    price, start = min(candidates)
    return start, f"cheapest interval in window at {price:.3f}/kWh"


def plan_blocks(
    now: datetime,
    config: PoolConfig,
    remaining_h: float,
    price_forecast: tuple[tuple[datetime, datetime, float], ...] = (),
) -> list[BlockPlan]:
    """Distribute the remaining runtime over today's remaining windows.

    Missed runtime is not lost: it rolls forward into the windows that are still
    ahead. If nothing is left ahead, the deadline logic takes over.
    """
    if remaining_h <= 0:
        return []

    upcoming = [(i, s, e) for i, s, e in window_bounds(now, config) if e > now]
    if not upcoming:
        return []

    per_block = remaining_h / len(upcoming)
    min_block_h = config.filtration.min_block_minutes / 60.0

    plans: list[BlockPlan] = []
    for index, window_start, window_end in upcoming:
        duration = per_block
        window_length_h = (window_end - max(window_start, now)).total_seconds() / 3600.0
        duration = min(duration, window_length_h)
        if duration < min_block_h:
            # Too short to be useful on its own. Skip it and let the remaining
            # windows absorb the runtime.
            continue

        start, rationale = _cheapest_start(
            max(window_start, now), window_end, duration, price_forecast
        )
        plans.append(
            BlockPlan(
                index=index,
                start=start,
                end=start + timedelta(hours=duration),
                rationale=rationale,
            )
        )

    if not plans:
        # Every window was too short for a minimum block, but runtime is still
        # owed. Schedule one block in the last window that can hold anything.
        index, window_start, window_end = upcoming[-1]
        start = max(window_start, now)
        duration = min(remaining_h, (window_end - start).total_seconds() / 3600.0)
        if duration > 0:
            plans.append(
                BlockPlan(
                    index=index,
                    start=start,
                    end=start + timedelta(hours=duration),
                    rationale="remaining runtime consolidated into the last window",
                )
            )
    return plans


def evaluate(
    now: datetime,
    config: PoolConfig,
    done_h: float,
    active_block: BlockPlan | None = None,
    price_forecast: tuple[tuple[datetime, datetime, float], ...] = (),
) -> FiltrationStatus:
    """Assess the filtration situation.

    ``done_h`` includes pump runtime from heating sessions, because the pump is
    circulating during those too. Without that credit the system would filter
    substantially more than needed on heating days.
    """
    required_h = config.daily_filtration_hours
    remaining_h = max(0.0, required_h - done_h)
    available_h = available_runtime_h(now, config)

    # A running block keeps running. Its end time is the only thing that stops
    # it, which is what makes this branch immune to oscillation.
    if active_block is not None and now < active_block.end and remaining_h > 0:
        current: BlockPlan | None = active_block
        upcoming: BlockPlan | None = None
    else:
        current = None
        plans = plan_blocks(now, config, remaining_h, price_forecast)
        started = [p for p in plans if p.start <= now < p.end]
        current = started[0] if started else None
        future = [p for p in plans if p.start > now]
        upcoming = future[0] if future else None

    deadline_critical = remaining_h > 0 and available_h <= remaining_h + DEADLINE_MARGIN_H

    return FiltrationStatus(
        required_h=required_h,
        done_h=done_h,
        remaining_h=remaining_h,
        available_h=available_h,
        deadline_critical=deadline_critical,
        active_block=current,
        next_block=upcoming,
        detail={
            "turnover_factor": config.filtration.turnover_factor,
            "effective_flow_m3h": round(config.pump.effective_flow_m3h, 3),
            "block_hours": round(config.block_hours, 3),
            "blocks_per_day": config.filtration.block_count,
        },
    )
