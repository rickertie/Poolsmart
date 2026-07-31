"""Choosing when to heat.

Two situations need different treatment, and conflating them was what produced
promises the system could not keep.

*Maintenance* means compensating a day's heat loss: one to three degrees, a few
hours of running, comfortably inside a day's cheap intervals. The optimizer picks
the cheapest intervals before the deadline and is done.

*Seasonal* means bringing a cold pool up to temperature. For a small pool with a
3 kW heat pump that is nine to fifteen hours of running, and there are not that
many cheap hours in a day. The optimizer then projects across days, accounting
for the heat lost overnight, and reports a date rather than a time. Saying
"ready at 15:30" when it cannot be true is worse than saying "ready Wednesday".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .config import PoolConfig
from .heating import HeatingEstimate, PlanMode

#: A priced interval: start, end, price per kWh.
PriceSlot = tuple[datetime, datetime, float]

#: Assumed number of usable cheap hours per day when planning beyond the price
#: forecast horizon. Deliberately conservative: a plan that finishes early is a
#: pleasant surprise, one that finishes late is a broken promise.
DEFAULT_DAILY_CAPACITY_H = 8.0


@dataclass(frozen=True)
class HeatingPlan:
    """When to run the heat pump, and what it will cost."""

    mode: PlanMode
    slots: tuple[PriceSlot, ...] = ()
    hours_planned: float = 0.0
    hours_needed: float = 0.0
    expected_cost: float | None = None
    ready_at: datetime | None = None
    reason: str = ""
    detail: dict = field(default_factory=dict)

    def is_active(self, now: datetime) -> bool:
        """Whether heating should be running at this moment."""
        return any(start <= now < end for start, end, _price in self.slots)

    @property
    def next_start(self) -> datetime | None:
        return self.slots[0][0] if self.slots else None


def _slot_hours(slot: PriceSlot) -> float:
    start, end, _price = slot
    return (end - start).total_seconds() / 3600.0


def _eligible(
    slots: tuple[PriceSlot, ...],
    now: datetime,
    deadline: datetime | None,
    max_price: float | None,
) -> list[PriceSlot]:
    """Slots that lie ahead, end before the deadline and are affordable."""
    result = []
    for start, end, price in slots:
        if end <= now:
            continue
        if deadline is not None and start >= deadline:
            continue
        if max_price is not None and price > max_price:
            continue
        result.append((max(start, now), min(end, deadline) if deadline else end, price))
    return [s for s in result if _slot_hours(s) > 0]


def _daily_capacity(slots: list[PriceSlot]) -> float:
    """Usable hours per day, measured from the forecast we actually have.

    A price forecast rarely covers whole days. Treating a six-hour horizon as if
    it were a full day makes the capacity look far smaller than it is and turns
    reachable targets into unreachable ones, so a short horizon is extrapolated
    and then capped at the conservative default rather than taken at face value.
    """
    if not slots:
        return DEFAULT_DAILY_CAPACITY_H

    span_h = (
        max(end for _s, end, _p in slots) - min(start for start, _e, _p in slots)
    ).total_seconds() / 3600.0
    affordable_h = sum(_slot_hours(s) for s in slots)

    if span_h >= 20:
        by_day: dict[str, float] = {}
        for slot in slots:
            key = slot[0].date().isoformat()
            by_day[key] = by_day.get(key, 0.0) + _slot_hours(slot)
        values = sorted(by_day.values())
        return values[len(values) // 2]

    if span_h <= 0:
        return DEFAULT_DAILY_CAPACITY_H
    return min(DEFAULT_DAILY_CAPACITY_H, affordable_h * 24.0 / span_h)


def _project_seasonal(
    now: datetime,
    config: PoolConfig,
    estimate: HeatingEstimate,
    capacity_h: float,
    heat_loss_c_per_h: float,
) -> tuple[datetime | None, float, str]:
    """Project a finish date when the job does not fit in the remaining window.

    Net progress is what the heat pump adds during the usable hours minus what
    the pool loses over the whole day. If that is not positive the pool cannot
    reach the target at all under these conditions, and saying so is more useful
    than producing a date.
    """
    kwh_per_degree = config.pool.kwh_thermal_per_degree
    if kwh_per_degree <= 0 or estimate.thermal_kw <= 0:
        return None, 0.0, "the heat pump specification does not allow a projection"

    gross_rise_per_h = estimate.thermal_kw / kwh_per_degree
    net_degrees_per_day = capacity_h * gross_rise_per_h - 24.0 * heat_loss_c_per_h

    if net_degrees_per_day <= 0:
        return None, net_degrees_per_day, (
            "the pool loses heat as fast as the heat pump can add it under these "
            "conditions, so the target cannot be reached"
        )

    days = estimate.degrees_needed / net_degrees_per_day
    return now + timedelta(days=days), net_degrees_per_day, (
        f"about {math.ceil(days)} day(s) at roughly {net_degrees_per_day:.1f} C of "
        f"net gain per day"
    )


def plan(
    now: datetime,
    config: PoolConfig,
    estimate: HeatingEstimate,
    slots: tuple[PriceSlot, ...] = (),
    deadline: datetime | None = None,
    heat_loss_c_per_h: float | None = None,
    boost: bool = False,
) -> HeatingPlan:
    """Decide when to heat between now and the deadline."""
    if estimate.plan_mode is PlanMode.NONE or estimate.hours_needed <= 0:
        return HeatingPlan(
            mode=PlanMode.NONE,
            reason="The pool is at or above target; no heating is planned.",
        )

    loss = (
        heat_loss_c_per_h
        if heat_loss_c_per_h is not None
        else config.learning.initial_heat_loss_c_per_h
    )
    needed = estimate.hours_needed

    if boost:
        end = now + timedelta(hours=needed)
        return HeatingPlan(
            mode=PlanMode.MAINTENANCE,
            slots=((now, end, 0.0),),
            hours_planned=needed,
            hours_needed=needed,
            ready_at=end,
            reason="Boost: heating continuously until the target is reached.",
        )

    max_price = config.energy.max_price
    if config.energy.max_price is not None and config.energy.eco_price_factor:
        pass  # ECO tightening is applied by the ladder, not here.

    affordable = _eligible(slots, now, deadline, max_price)
    if not affordable and slots:
        # Nothing within the price limit. Fall back to the cheapest available, so
        # a deadline is still met rather than silently missed.
        affordable = _eligible(slots, now, deadline, None)

    if not affordable:
        # No price data at all: heat straight away and be transparent about why.
        end = now + timedelta(hours=needed)
        return HeatingPlan(
            mode=estimate.plan_mode,
            slots=((now, end, 0.0),),
            hours_planned=needed,
            hours_needed=needed,
            ready_at=end,
            reason="No price forecast available, so heating starts immediately.",
        )

    chosen: list[PriceSlot] = []
    accumulated = 0.0
    for slot in sorted(affordable, key=lambda s: (s[2], s[0])):
        if accumulated >= needed:
            break
        chosen.append(slot)
        accumulated += _slot_hours(slot)

    chosen.sort(key=lambda s: s[0])
    cost = sum(
        _slot_hours(s) * config.heat_pump.input_kw * s[2] for s in chosen
    )

    if accumulated + 1e-6 >= needed:
        ready_at = chosen[-1][1] if chosen else None
        cheapest = min(s[2] for s in chosen)
        dearest = max(s[2] for s in chosen)
        return HeatingPlan(
            mode=PlanMode.MAINTENANCE,
            slots=tuple(chosen),
            hours_planned=accumulated,
            hours_needed=needed,
            expected_cost=round(cost, 3),
            ready_at=ready_at,
            reason=(
                f"Heating for {needed:.1f} h in the cheapest intervals available "
                f"({cheapest:.3f} to {dearest:.3f} per kWh)."
            ),
            detail={"slots": len(chosen), "cost": round(cost, 3)},
        )

    # Not enough affordable time before the deadline: this is a seasonal job.
    capacity = _daily_capacity(affordable)
    ready_at, net_per_day, note = _project_seasonal(now, config, estimate, capacity, loss)
    return HeatingPlan(
        mode=PlanMode.SEASONAL,
        slots=tuple(chosen),
        hours_planned=accumulated,
        hours_needed=needed,
        expected_cost=round(cost, 3) if chosen else None,
        ready_at=ready_at,
        reason=(
            f"This needs {needed:.1f} h of heating, more than fits before the "
            f"deadline. Spreading it over several days: {note}."
        ),
        detail={
            "daily_capacity_h": round(capacity, 2),
            "net_degrees_per_day": round(net_per_day, 3),
            "hours_short": round(needed - accumulated, 2),
        },
    )
