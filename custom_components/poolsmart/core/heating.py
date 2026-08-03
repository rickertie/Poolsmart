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
    #: Where the figures came from: the datasheet, or this pool's own history.
    source: str = "datasheet"

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
    learned_cop: float | None = None,
    learned_rate_c_per_h: float | None = None,
) -> HeatingEstimate:
    """Estimate the run time needed to reach the target.

    Measurement beats the datasheet, and by a wide margin. A pool measuring a COP
    of 3.5 against a quoted 5.2 heats 54% slower than the paperwork says: a two
    degree rise takes four and a half hours rather than three. Planning from the
    datasheet in that situation means starting too late and arriving cold, which
    is the failure people actually notice.

    Three sources, best first:

    1. ``learned_rate_c_per_h`` -- degrees per hour this pool actually achieved.
       The most direct measurement there is: no COP, no flow, no delta-T, just
       how fast the water went up.
    2. ``learned_cop`` -- measured efficiency at this outdoor temperature.
    3. The datasheet curve, used until either of the above exists.

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
    kwh_per_degree = config.pool.kwh_thermal_per_degree

    if learned_cop is not None and learned_cop > 0:
        cop = learned_cop
        thermal_kw = config.heat_pump.input_kw * cop
        source = "measured COP"
    else:
        cop = config.heat_pump.cop_at(air_temp)
        thermal_kw = config.heat_pump.thermal_kw_at(air_temp)
        source = "datasheet"

    if degrees <= 0 or thermal_kw <= 0:
        return HeatingEstimate(0.0, 0.0, 0.0, 0.0, cop, thermal_kw, PlanMode.NONE, source)

    # Solve for run time including the heat lost while heating. Net rise per hour
    # is the heat pump's contribution minus the standing loss.
    if learned_rate_c_per_h is not None and learned_rate_c_per_h > 0:
        # Already a net figure: it was measured on this pool, losses included.
        net_rise_per_h = learned_rate_c_per_h
        source = "measured heating rate"
    else:
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
        source=source,
    )
