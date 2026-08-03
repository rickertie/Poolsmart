"""Turning a water test into something you can do.

A pH of 7.8 is a number. "Add 34 ml of pH-minus and let the pump run for an hour"
is an instruction. Making that translation needs three things, and PoolSmart
already has all of them: the pool volume, the water temperature, and control of
the circulation pump.

This module deliberately stops well short of full water chemistry. The
`ha-poolchem` integration already computes saturation indices and doses for six
chemicals from any sensor source, and reimplementing that would be duplicated
effort producing a second opinion. What is here is the part that needs the pool's
own numbers: simple pH and chlorine dosing, a test interval that follows the
water temperature, and a record of what was added and what it did.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

#: Ideal ranges. Widely agreed and not worth making configurable in a first pass.
PH_IDEAL = (7.2, 7.6)
CHLORINE_IDEAL = (1.0, 3.0)

#: Litres of 15% hydrochloric acid to lower 10 m3 of water by 0.1 pH.
#:
#: pH is logarithmic and buffered by alkalinity, so any figure here is an
#: approximation that holds over a small step and fails over a large one. Hence
#: the cap in `dose_for_ph`: no single dose is allowed to chase more than a few
#: tenths, because the honest answer past that is "add some, wait, measure again".
ACID_L_PER_10M3_PER_01PH = 0.017

#: Grams of 70% calcium hypochlorite to raise 10 m3 by 1 mg/L of free chlorine.
CHLORINE_G_PER_10M3_PER_MGL = 14.3

#: Largest pH step a single dose may aim for.
MAX_PH_STEP = 0.4


class Product(str, Enum):
    """Chemical types, in the concentrations sold for domestic pools."""

    ACID_15 = "acid_15"
    ACID_37 = "acid_37"
    PH_PLUS = "ph_plus"
    CHLORINE_GRANULES_70 = "chlorine_granules_70"
    CHLORINE_LIQUID_15 = "chlorine_liquid_15"


PRODUCT_LABELS = {
    Product.ACID_15: ("pH-minus (15% hydrochloric acid)", "ml"),
    Product.ACID_37: ("pH-minus (37% hydrochloric acid)", "ml"),
    Product.PH_PLUS: ("pH-plus (sodium carbonate)", "g"),
    Product.CHLORINE_GRANULES_70: ("chlorine granules (70%)", "g"),
    Product.CHLORINE_LIQUID_15: ("liquid chlorine (15%)", "ml"),
}


@dataclass(frozen=True)
class Dose:
    """A recommended amount, and how to apply it."""

    product: Product
    amount: float
    unit: str
    reason: str
    instructions: str
    #: True when the target is deliberately short of ideal because the step is
    #: too large to do in one go.
    partial: bool = False
    aiming_for: float | None = None

    @property
    def label(self) -> str:
        return PRODUCT_LABELS[self.product][0]

    def as_dict(self) -> dict:
        return {
            "product": self.product.value,
            "label": self.label,
            "amount": round(self.amount, 1),
            "unit": self.unit,
            "reason": self.reason,
            "instructions": self.instructions,
            "partial": self.partial,
            "aiming_for": self.aiming_for,
        }


@dataclass
class DoseRecord:
    """A dose that was actually applied, and what it achieved.

    Kept because dosing without a record is guessing. After a handful of these
    the correction factor below turns a table figure into this pool's figure.
    """

    at: datetime
    product: str
    amount: float
    unit: str
    measured_before: float
    measured_after: float | None = None
    expected_change: float | None = None

    @property
    def actual_change(self) -> float | None:
        if self.measured_after is None:
            return None
        return self.measured_after - self.measured_before

    @property
    def effectiveness(self) -> float | None:
        """How the pool responded, against what was predicted."""
        actual = self.actual_change
        if actual is None or not self.expected_change:
            return None
        return actual / self.expected_change

    def as_dict(self) -> dict:
        return {
            "at": self.at.isoformat(),
            "product": self.product,
            "amount": round(self.amount, 1),
            "unit": self.unit,
            "measured_before": self.measured_before,
            "measured_after": self.measured_after,
            "expected_change": self.expected_change,
            "actual_change": (
                round(self.actual_change, 2) if self.actual_change is not None else None
            ),
            "effectiveness": (
                round(self.effectiveness, 2) if self.effectiveness is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> DoseRecord:
        return cls(
            at=datetime.fromisoformat(raw["at"]),
            product=raw["product"],
            amount=raw["amount"],
            unit=raw["unit"],
            measured_before=raw["measured_before"],
            measured_after=raw.get("measured_after"),
            expected_change=raw.get("expected_change"),
        )


def dose_for_ph(
    measured_ph: float,
    volume_l: float,
    product: Product = Product.ACID_15,
    correction: float = 1.0,
) -> Dose | None:
    """How much acid or base to add.

    Deliberately conservative. pH is buffered by alkalinity in a way this
    calculation does not model, so a large correction attempted in one go
    overshoots and leaves you adding the opposite chemical. Steps larger than
    ``MAX_PH_STEP`` are truncated and the fact is reported, because "add some,
    wait an hour, measure again" is the honest instruction.
    """
    low, high = PH_IDEAL
    if low <= measured_ph <= high:
        return None

    volume_10m3 = volume_l / 10_000.0

    if measured_ph > high:
        target = high - 0.05
        step = measured_ph - target
        partial = step > MAX_PH_STEP
        if partial:
            step = MAX_PH_STEP
            target = measured_ph - step

        millilitres = (
            step / 0.1
            * ACID_L_PER_10M3_PER_01PH
            * volume_10m3
            * 1000.0
            * correction
        )
        if product is Product.ACID_37:
            millilitres *= 15.0 / 37.0

        return Dose(
            product=product,
            amount=millilitres,
            unit="ml",
            reason=(
                f"pH is {measured_ph:.2f}, above the ideal {low:.1f}–{high:.1f}. "
                "Chlorine loses much of its effect above 7.6."
            ),
            instructions=(
                "Dilute in a bucket of water and pour it in along the edge with the "
                "pump running. Measure again after an hour. Never add two chemicals "
                "within an hour of each other."
            ),
            partial=partial,
            aiming_for=round(target, 2),
        )

    # Below range: sodium carbonate, roughly 60 g per 10 m3 per 0.1 pH.
    target = low + 0.05
    step = target - measured_ph
    partial = step > MAX_PH_STEP
    if partial:
        step = MAX_PH_STEP
        target = measured_ph + step

    grams = step / 0.1 * 60.0 * volume_10m3 * correction
    return Dose(
        product=Product.PH_PLUS,
        amount=grams,
        unit="g",
        reason=(
            f"pH is {measured_ph:.2f}, below the ideal {low:.1f}–{high:.1f}. "
            "Acidic water irritates eyes and corrodes fittings."
        ),
        instructions=(
            "Dissolve in a bucket of water first, then pour it in with the pump "
            "running. Measure again after an hour."
        ),
        partial=partial,
        aiming_for=round(target, 2),
    )


def dose_for_chlorine(
    measured_mgl: float,
    volume_l: float,
    product: Product = Product.CHLORINE_GRANULES_70,
    correction: float = 1.0,
) -> Dose | None:
    """How much chlorine to add to reach the middle of the ideal range.

    Aims for the middle rather than the bottom: chlorine is consumed
    continuously, so landing on the lower limit means being under it by morning.
    """
    low, high = CHLORINE_IDEAL
    if measured_mgl >= low:
        return None

    target = (low + high) / 2
    rise = target - measured_mgl
    volume_10m3 = volume_l / 10_000.0

    grams = rise * CHLORINE_G_PER_10M3_PER_MGL * volume_10m3 * correction
    unit = "g"
    if product is Product.CHLORINE_LIQUID_15:
        grams *= 4.7  # roughly, going from 70% granules to 15% liquid by volume
        unit = "ml"

    return Dose(
        product=product,
        amount=grams,
        unit=unit,
        reason=(
            f"Free chlorine is {measured_mgl:.1f} mg/L, below the ideal "
            f"{low:.1f}–{high:.1f}. Below 0.5 the pool is open to algae."
        ),
        instructions=(
            "Dose in the evening: ultraviolet light breaks chlorine down during "
            "the day. Spread it over the surface with the pump running, and keep "
            "swimmers out until it has circulated."
        ),
        aiming_for=round(target, 2),
    )


def test_interval_days(water_temp: float | None) -> tuple[int, str]:
    """How often to test, given how warm the water is.

    Chlorine is consumed faster in warm water and algae grow faster in it, so a
    fixed three-day reminder is too often in spring and not often enough in a
    heatwave. The pool already knows its own temperature; the interval may as
    well follow it.
    """
    if water_temp is None:
        return 3, "no water temperature available, using a middle interval"
    if water_temp < 20:
        return 5, f"at {water_temp:.0f} °C chlorine is consumed slowly"
    if water_temp < 26:
        return 3, f"at {water_temp:.0f} °C consumption is moderate"
    if water_temp < 30:
        return 2, f"at {water_temp:.0f} °C chlorine burns off quickly"
    return 1, f"at {water_temp:.0f} °C consumption is high and algae grow fast"


def next_test_due(
    last_test: datetime | None, water_temp: float | None, now: datetime
) -> tuple[datetime | None, bool, str]:
    """When the next test is due, and whether it is overdue."""
    days, why = test_interval_days(water_temp)
    if last_test is None:
        return None, True, "no test has been recorded yet"
    due = last_test + timedelta(days=days)
    return due, now >= due, why


def learn_correction(records: list[DoseRecord], product: str) -> float:
    """How this pool responds compared with the table figures.

    Alkalinity, stabiliser and the age of the chemicals all shift the real
    response, and none of them is modelled here. Rather than pretend otherwise,
    the correction is measured: after a few doses the recommendation becomes this
    pool's own rather than a number from a chart.
    """
    ratios = [
        r.effectiveness
        for r in records
        if r.product == product and r.effectiveness is not None and 0.2 < r.effectiveness < 5
    ]
    if len(ratios) < 2:
        return 1.0
    # A pool that moved half as far as predicted needs twice the dose.
    average = sum(ratios) / len(ratios)
    return round(max(0.5, min(2.0, 1 / average)), 3)
