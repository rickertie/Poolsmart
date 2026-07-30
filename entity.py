"""Heating time calculations and the choice of planning mode.

Warming a pool is slow. For a 3800 litre pool with a 3 kW heat pump it takes
roughly an hour and a half per degree, so a six degree rise is nine to eleven
hours of continuous running. There are not nine cheap hours in a day, which is
why the planner needs two modes rather than one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .config import PoolConfig


class PlanMode(str, Enum):
    """Which kind of plan the situation calls for."""

    #: Compensate the daily heat loss. Fits inside a day's cheap hours.
    MAINTENANCE = "maintenance"
    #: Bring a cold pool up to temperature. Spans several days.
    SEASONAL = "seasonal"
    #: Nothing to do.
    NONE = "none"


@dataclass(frozen=True)
class HeatingEstimate:
    """What it takes to reach the target from here."""

    degrees_needed: float
    hours_needed: float
    kwh_thermal: float
    kwh_electric: float
    cop: float
    thermal_kw: float
    plan_mode: PlanMode

    @property
    def cost(self) -> float:
        """Cost at a given price is left to the caller; this is the energy."""
        return self.kwh_electric


def estimate(
    config: PoolConfig,
    water_temp: float,
    target_temp: float,
    air_temp: float,
    hours_available: float | None = None,
    heat_loss_c_per_h: float | None = None,
) -> HeatingEstimate:
    """Estimate the run time needed to reach the target.

    ``hours_available`` is the time until the pool is wanted at temperature. When
    the required run time does not fit, the plan mode becomes seasonal and the
    caller should communicate a date rather than a time.
    """
    loss = (
        heat_loss_c_per_h
        if heat_loss_c_per_h is not None
        else config.learning.initial_heat_loss_c_per_h
    )

    degrees = max(0.0, target_temp - water_temp)
    thermal_kw = config.heat_pump.thermal_kw_at(air_temp)
    cop = config.heat_pump.cop_at(air_temp)
    kwh_per_degree = config.pool.kwh_thermal_per_degree

    if degrees <= 0 or thermal_kw <= 0:
        return HeatingEstimate(0.0, 0.0, 0.0, 0.0, cop, thermal_kw, PlanMode.NONE)

    # Solve for run time including the heat lost while heating. Net rise per hour
    # is the heat pump's contribution minus the standing loss.
    gross_rise_per_h = thermal_kw / kwh_per_degree
    net_rise_per_h = gross_rise_per_h - loss
    if net_rise_per_h <= 0:
        # The pool loses heat faster than the appliance can add it.
        hours = float("inf")
    else:
        hours = degrees / net_rise_per_h

    kwh_thermal = degrees * kwh_per_degree
    kwh_electric = kwh_thermal / cop if cop else 0.0

    if hours_available is not None and hours > hours_available:
        mode = PlanMode.SEASONAL
    else:
        mode = PlanMode.MAINTENANCE

    return HeatingEstimate(
        degrees_needed=degrees,
        hours_needed=hours,
        kwh_thermal=kwh_thermal,
        kwh_electric=kwh_electric,
        cop=cop,
        thermal_kw=thermal_kw,
        plan_mode=mode,
    )
