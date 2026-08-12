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

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

#: Ideal ranges, as printed on an AquaChek comparator and agreed on widely
#: enough not to be worth arguing about.
PH_IDEAL = (7.2, 7.6)
CHLORINE_IDEAL = (1.0, 3.0)
BROMINE_IDEAL = (2.0, 6.0)
ALKALINITY_IDEAL = (80.0, 120.0)
CYANURIC_IDEAL = (30.0, 50.0)
HARDNESS_IDEAL = (200.0, 400.0)
SALT_IDEAL = (2700.0, 3400.0)

#: Combined chlorine above this means the sanitiser is being consumed by
#: contamination faster than it is working, and shocking is the answer rather
#: than topping up.
COMBINED_CHLORINE_SHOCK = 0.5

#: Above this, cyanuric acid locks up so much of the free chlorine that adding
#: more achieves very little. The only real fix is diluting the water.
CYANURIC_LOCKOUT = 100.0


class Sanitiser(str, Enum):
    """What keeps the water clean. These are alternatives, not additions."""

    CHLORINE = "chlorine"
    BROMINE = "bromine"
    SALT = "salt"


#: Which readings are worth asking for, per sanitiser. Showing a bromine field
#: to someone running chlorine is not neutral: it is a field they will wonder
#: about, leave blank, and see reported as missing.
RELEVANT_READINGS = {
    Sanitiser.CHLORINE: (
        "ph", "free_chlorine", "total_chlorine", "alkalinity", "cyanuric", "hardness",
    ),
    Sanitiser.BROMINE: ("ph", "bromine", "alkalinity", "hardness"),
    Sanitiser.SALT: (
        "ph", "free_chlorine", "total_chlorine", "alkalinity", "cyanuric",
        "hardness", "salt",
    ),
}

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


@dataclass(frozen=True)
class Band:
    """A reading judged against its ideal range."""

    key: str
    label: str
    value: float
    unit: str
    low: float
    high: float
    #: "ok", "low", "high", "very_low" or "very_high".
    verdict: str
    note: str = ""

    @property
    def urgent(self) -> bool:
        return self.verdict in ("very_low", "very_high")

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "ideal_low": self.low,
            "ideal_high": self.high,
            "verdict": self.verdict,
            "urgent": self.urgent,
            "note": self.note,
        }


#: Label, unit and ideal range for every reading an AquaChek strip produces,
#: plus salt for electrolysis systems.
READINGS = {
    "ph": ("pH", "", PH_IDEAL),
    "free_chlorine": ("Free chlorine", "mg/L", CHLORINE_IDEAL),
    "total_chlorine": ("Total chlorine", "mg/L", CHLORINE_IDEAL),
    "bromine": ("Bromine", "mg/L", BROMINE_IDEAL),
    "alkalinity": ("Total alkalinity", "ppm", ALKALINITY_IDEAL),
    "cyanuric": ("Cyanuric acid", "ppm", CYANURIC_IDEAL),
    "hardness": ("Total hardness", "ppm", HARDNESS_IDEAL),
    "salt": ("Salt", "ppm", SALT_IDEAL),
}

#: Notes worth attaching when a reading strays, because the number alone rarely
#: says what to do about it.
BAND_NOTES = {
    ("alkalinity", "low"): (
        "Low alkalinity lets pH swing on its own. Correct this before chasing pH."
    ),
    ("alkalinity", "high"): (
        "High alkalinity makes pH stubborn and can cloud the water."
    ),
    ("cyanuric", "low"): (
        "Little stabiliser means sunlight destroys chlorine within hours."
    ),
    ("cyanuric", "high"): (
        "Too much stabiliser holds chlorine hostage. Adding more chlorine will "
        "not help; diluting the water is the only real fix."
    ),
    ("hardness", "low"): (
        "Soft water is aggressive and pulls calcium out of grout and fittings."
    ),
    ("hardness", "high"): "Hard water scales heat exchangers and leaves deposits.",
    ("salt", "low"): "The chlorinator will produce little or nothing below range.",
    ("salt", "high"): "Excess salt corrodes fittings and can trip the cell.",
}


def judge(key: str, value: float | None) -> Band | None:
    """Place one reading in its band.

    Two levels of "wrong" rather than one: a pH of 7.7 wants attention this week,
    a pH of 8.6 wants attention now, and collapsing those into a single warning
    means the urgent one arrives looking like the routine one.
    """
    if value is None or key not in READINGS:
        return None
    label, unit, (low, high) = READINGS[key]
    span = high - low

    if value < low:
        verdict = "very_low" if value < low - span else "low"
    elif value > high:
        verdict = "very_high" if value > high + span else "high"
    else:
        verdict = "ok"

    direction = "low" if verdict.endswith("low") else "high"
    note = BAND_NOTES.get((key, direction), "") if verdict != "ok" else ""
    return Band(key, label, value, unit, low, high, verdict, note)


def combined_chlorine(free: float | None, total: float | None) -> float | None:
    """Total minus free: the chlorine already spent on contamination.

    Worth deriving because it is the one figure a strip gives you that answers
    "should I shock?", and it only exists if someone subtracts two columns.
    """
    if free is None or total is None:
        return None
    return round(max(0.0, total - free), 2)


class Product(str, Enum):
    """Chemical types, in the concentrations sold for domestic pools."""

    ACID_15 = "acid_15"
    ACID_37 = "acid_37"
    PH_PLUS = "ph_plus"
    CHLORINE_GRANULES_70 = "chlorine_granules_70"
    CHLORINE_LIQUID_15 = "chlorine_liquid_15"
    SHOCK = "shock"
    SHOCK_NON_CHLORINE = "shock_non_chlorine"
    ALGAECIDE = "algaecide"
    TABLET = "tablet"


#: Minutes of circulation each product needs, from published guidance.
#:
#: One fixed duration for "chemistry" was always going to be wrong, because the
#: products are not comparable. Non-chlorine shock is done in a quarter of an
#: hour; chlorine shock wants a full night so it reaches every corner and gets
#: pulled through the filter; an algae treatment runs until the water clears.
#: Getting this wrong in the short direction leaves undissolved product on the
#: floor bleaching the liner.
CIRCULATION_MINUTES = {
    Product.ACID_15: 60,
    Product.ACID_37: 60,
    Product.PH_PLUS: 60,
    Product.CHLORINE_GRANULES_70: 240,
    Product.CHLORINE_LIQUID_15: 240,
    Product.SHOCK: 600,
    Product.SHOCK_NON_CHLORINE: 30,
    Product.ALGAECIDE: 1440,
    Product.TABLET: 0,
}

#: Why each duration is what it is, shown to the user rather than left implicit.
CIRCULATION_REASON = {
    Product.ACID_15: "an hour to disperse, then measure again",
    Product.ACID_37: "an hour to disperse, then measure again",
    Product.PH_PLUS: "an hour to disperse, then measure again",
    Product.CHLORINE_GRANULES_70: "four hours for a maintenance dose to spread",
    Product.CHLORINE_LIQUID_15: "four hours for a maintenance dose to spread",
    Product.SHOCK: (
        "ten hours: shock needs a full night to reach every corner and be pulled "
        "through the filter, and undissolved product left sitting will bleach "
        "the liner"
    ),
    Product.SHOCK_NON_CHLORINE: "half an hour is enough for non-chlorine shock",
    Product.ALGAECIDE: (
        "a full day, and keep going until the water is visibly clear rather than "
        "stopping on the clock"
    ),
    Product.TABLET: (
        "none: a tablet dissolves over days in a floater or skimmer, so there is "
        "nothing to circulate now"
    ),
}


PRODUCT_LABELS = {
    Product.ACID_15: ("pH-minus (15% hydrochloric acid)", "ml"),
    Product.ACID_37: ("pH-minus (37% hydrochloric acid)", "ml"),
    Product.PH_PLUS: ("pH-plus (sodium carbonate)", "g"),
    Product.CHLORINE_GRANULES_70: ("chlorine granules (70%)", "g"),
    Product.CHLORINE_LIQUID_15: ("liquid chlorine (15%)", "ml"),
    Product.SHOCK: ("chlorine shock", "g"),
    Product.SHOCK_NON_CHLORINE: ("non-chlorine shock", "g"),
    Product.ALGAECIDE: ("algaecide", "ml"),
    Product.TABLET: ("chlorine tablet", "g"),
}


def circulation_for(product: Product | str) -> tuple[int, str]:
    """How long to circulate after adding this, and why."""
    try:
        item = Product(product)
    except ValueError:
        return 60, "an hour by default for an unrecognised product"
    return CIRCULATION_MINUTES[item], CIRCULATION_REASON[item]


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


#: Sizes chlorine tablets are actually sold in, in grams.
TABLET_SIZES = (20, 200, 500)


def dose_for_chlorine(
    measured_mgl: float,
    volume_l: float,
    product: Product = Product.CHLORINE_GRANULES_70,
    correction: float = 1.0,
    tablet_grams: float = 20.0,
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

    if product is Product.TABLET:
        # "Add 11 g of tablet" is not an instruction anyone can follow. Tablets
        # come in fixed sizes, cannot be halved usefully, and take days to
        # dissolve -- which makes them the wrong product for a reading that is
        # low right now. Say that, rather than quietly rounding a slow-release
        # product into a correction it cannot make.
        whole = max(1, round(grams / tablet_grams))
        overshoot = whole * tablet_grams / grams if grams else 1.0
        return Dose(
            product=product,
            amount=whole,
            unit="tablet" if whole == 1 else "tablets",
            reason=(
                f"Free chlorine is {measured_mgl:.1f} mg/L, below the ideal "
                f"{low:.1f}–{high:.1f}. This needs about {grams:.0f} g of "
                f"chlorine; your tablets are {tablet_grams:.0f} g, so "
                f"{whole} would be "
                + (
                    "roughly right"
                    if 0.8 <= overshoot <= 1.25
                    else f"{overshoot:.1f}× that"
                )
                + "."
            ),
            instructions=(
                "Tablets dissolve over days in a floater or skimmer, so they hold "
                "a level rather than correct one. If the pool needs chlorine "
                "today, use granules or liquid for the correction and let the "
                "tablets carry it from there."
            ),
            aiming_for=round(target, 2),
        )

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


def water_advice(readings: dict[str, float | None]) -> list[str]:
    """Conclusions that need more than one reading to reach.

    Each band judges its own number. These are the things that only become
    visible when the numbers are read together, and they are the ones that
    change what you should actually do.
    """
    advice: list[str] = []

    combined = combined_chlorine(
        readings.get("free_chlorine"), readings.get("total_chlorine")
    )
    if combined is not None and combined >= COMBINED_CHLORINE_SHOCK:
        advice.append(
            f"Combined chlorine is {combined:.1f} mg/L. The sanitiser is being "
            "used up by contamination, so shocking will do more than topping up."
        )

    cyanuric = readings.get("cyanuric")
    free = readings.get("free_chlorine")
    if cyanuric is not None and cyanuric > CYANURIC_LOCKOUT:
        advice.append(
            f"Cyanuric acid is {cyanuric:.0f} ppm. Above about "
            f"{CYANURIC_LOCKOUT:.0f} it holds chlorine hostage: adding more will "
            "not raise the effective level. Partially draining and refilling is "
            "the only fix."
        )
    elif cyanuric is not None and free is not None and cyanuric > 0:
        # The rule of thumb pool professionals use: free chlorine wants to sit
        # around 7.5% of the stabiliser level to stay effective.
        wanted = cyanuric * 0.075
        if wanted > CHLORINE_IDEAL[1] and free < wanted:
            advice.append(
                f"With {cyanuric:.0f} ppm of stabiliser, free chlorine needs to "
                f"be nearer {wanted:.1f} mg/L than the usual "
                f"{CHLORINE_IDEAL[0]:.1f}–{CHLORINE_IDEAL[1]:.1f} to stay effective."
            )

    ph = readings.get("ph")
    alkalinity = readings.get("alkalinity")
    if (
        ph is not None
        and alkalinity is not None
        and not ALKALINITY_IDEAL[0] <= alkalinity <= ALKALINITY_IDEAL[1]
        and not PH_IDEAL[0] <= ph <= PH_IDEAL[1]
    ):
        advice.append(
            "Both pH and alkalinity are out of range. Correct alkalinity first: "
            "it is what holds pH steady, and adjusting pH against a bad buffer "
            "means doing it again next week."
        )

    if ph is not None and ph > PH_IDEAL[1] and free is not None:
        advice.append(
            f"At pH {ph:.1f} chlorine works at a fraction of its strength. "
            "Bring the pH down before judging whether the chlorine is enough."
        )

    return advice


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
