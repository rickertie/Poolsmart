"""Long-term trend retention.

The session log and the daily summaries are both capped -- see
``SESSION_LOG_SIZE`` and ``DAILY_SUMMARY_MAX_DAYS`` in ``const.py`` -- so a slow,
months-long drift in a learned value is invisible by the time enough raw data
has rolled off the end to notice it. A heat pump's COP sagging four percent a
month, or a filter fouling gradually, never looks like anything at the session
or daily level; each individual session is unremarkable.

This module keeps a second, unbounded tier: one row per month, holding running
statistics rather than raw samples. A month's mean is all a trend needs, and a
running mean costs the same one float whether it is folding in the first
session or the thousandth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

#: Months needed before a trend is reported at all. Two points make a line
#: through anything; three is the minimum that can look like noise instead.
TREND_MIN_MONTHS = 3

#: Slope below this magnitude (as a fraction of the mean, per month) reads as
#: noise rather than a real trend -- otherwise every metric would forever be
#: reported as very slightly improving or degrading.
TREND_STABLE_THRESHOLD = 0.01


@dataclass
class MetricStat:
    """A running mean/min/max over however many samples have been folded in.

    Keeps none of the raw samples -- the mean is updated in place, so a month
    with a thousand sessions costs exactly as much to store as one with a
    single session.
    """

    mean: float = 0.0
    min: float = 0.0
    max: float = 0.0
    n: int = 0

    def fold(self, value: float) -> None:
        if self.n == 0:
            self.mean = self.min = self.max = value
        else:
            self.mean += (value - self.mean) / (self.n + 1)
            self.min = min(self.min, value)
            self.max = max(self.max, value)
        self.n += 1

    def as_dict(self) -> dict:
        return {"mean": self.mean, "min": self.min, "max": self.max, "n": self.n}

    @classmethod
    def from_dict(cls, raw: dict) -> MetricStat:
        return cls(
            mean=raw.get("mean", 0.0),
            min=raw.get("min", 0.0),
            max=raw.get("max", 0.0),
            n=raw.get("n", 0),
        )


def month_key(when: datetime) -> str:
    """The aggregate row a moment in time belongs to, e.g. ``2026-08``."""
    return f"{when.year:04d}-{when.month:02d}"


@dataclass
class MonthlyAggregate:
    """One calendar month's worth of learning, reduced to running statistics."""

    month: str
    session_count: int = 0
    heating_rate: MetricStat = field(default_factory=MetricStat)
    heat_loss: MetricStat = field(default_factory=MetricStat)
    heat_loss_covered: MetricStat = field(default_factory=MetricStat)
    cop_by_bucket: dict[str, MetricStat] = field(default_factory=dict)
    runtime_hours: float = 0.0
    energy_kwh: float = 0.0
    cost_euro: float = 0.0

    def cop_stat(self, bucket: str) -> MetricStat:
        stat = self.cop_by_bucket.get(bucket)
        if stat is None:
            stat = MetricStat()
            self.cop_by_bucket[bucket] = stat
        return stat

    def as_dict(self) -> dict:
        return {
            "month": self.month,
            "session_count": self.session_count,
            "heating_rate": self.heating_rate.as_dict(),
            "heat_loss": self.heat_loss.as_dict(),
            "heat_loss_covered": self.heat_loss_covered.as_dict(),
            "cop_by_bucket": {k: v.as_dict() for k, v in self.cop_by_bucket.items()},
            "runtime_hours": self.runtime_hours,
            "energy_kwh": self.energy_kwh,
            "cost_euro": self.cost_euro,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> MonthlyAggregate:
        return cls(
            month=raw["month"],
            session_count=raw.get("session_count", 0),
            heating_rate=MetricStat.from_dict(raw.get("heating_rate", {})),
            heat_loss=MetricStat.from_dict(raw.get("heat_loss", {})),
            heat_loss_covered=MetricStat.from_dict(raw.get("heat_loss_covered", {})),
            cop_by_bucket={
                k: MetricStat.from_dict(v)
                for k, v in raw.get("cop_by_bucket", {}).items()
            },
            runtime_hours=raw.get("runtime_hours", 0.0),
            energy_kwh=raw.get("energy_kwh", 0.0),
            cost_euro=raw.get("cost_euro", 0.0),
        )


def _metric_mean(agg: MonthlyAggregate, metric: str) -> float | None:
    """Read a month's mean for a metric, ``None`` if nothing was recorded.

    ``metric`` is either a direct field name (``"heating_rate"``,
    ``"heat_loss"``, ``"heat_loss_covered"``) or a COP bucket addressed as
    ``"cop_by_bucket.<bucket>"``, e.g. ``"cop_by_bucket.20-25"``.
    """
    if metric.startswith("cop_by_bucket."):
        bucket = metric.split(".", 1)[1]
        stat = agg.cop_by_bucket.get(bucket)
    else:
        stat = getattr(agg, metric, None)
        if not isinstance(stat, MetricStat):
            stat = None
    if stat is None or stat.n == 0:
        return None
    return stat.mean


@dataclass(frozen=True)
class TrendResult:
    """Whether a metric has been drifting lately, and how fast."""

    direction: str  # "improving" | "degrading" | "stable" | "insufficient_data"
    pct_per_month: float | None = None
    latest_mean: float | None = None
    months_considered: int = 0

    def as_dict(self) -> dict:
        return {
            "direction": self.direction,
            "pct_per_month": (
                round(self.pct_per_month, 3) if self.pct_per_month is not None else None
            ),
            "latest_mean": (
                round(self.latest_mean, 4) if self.latest_mean is not None else None
            ),
            "months_considered": self.months_considered,
        }


def trend(
    months: list[MonthlyAggregate],
    metric: str,
    *,
    higher_is_better: bool,
    min_months: int = TREND_MIN_MONTHS,
) -> TrendResult:
    """How a metric's monthly mean has been moving, most recent months first.

    ``months`` need not be pre-filtered or sorted by anything other than time;
    only the months that actually recorded ``metric`` are used, in
    chronological order, and only the trailing run of them is considered so an
    old, long-settled period does not dilute a trend that started recently.

    Fits an ordinary least-squares line against month index (0, 1, 2, ...) and
    expresses the slope as a percentage of the mean level per month, which is
    comparable across metrics with very different units. Below
    ``TREND_STABLE_THRESHOLD`` the slope is reported as ``"stable"`` rather
    than as a very small improvement or degradation -- real installations are
    noisy enough that a dead-flat line is the exception, not the rule.

    ``min_months`` overrides :data:`TREND_MIN_MONTHS` -- a pool only filled
    for part of the year has that many fewer months to work with, and may
    want a lower floor so a trend can be read within a single season.
    """
    ordered = sorted(months, key=lambda a: a.month)
    points: list[tuple[int, float]] = []
    for index, agg in enumerate(ordered):
        value = _metric_mean(agg, metric)
        if value is not None:
            points.append((index, value))

    if len(points) < max(2, min_months):
        return TrendResult(direction="insufficient_data", months_considered=len(points))

    n = len(points)
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    denom = sum((x - mean_x) ** 2 for x, _ in points)
    if denom == 0 or mean_y == 0:
        return TrendResult(direction="insufficient_data", months_considered=n)

    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denom
    pct_per_month = slope / abs(mean_y) * 100.0
    latest_mean = points[-1][1]

    if abs(pct_per_month) < TREND_STABLE_THRESHOLD * 100.0:
        direction = "stable"
    else:
        rising = pct_per_month > 0
        improving = rising if higher_is_better else not rising
        direction = "improving" if improving else "degrading"

    return TrendResult(
        direction=direction,
        pct_per_month=pct_per_month,
        latest_mean=latest_mean,
        months_considered=n,
    )


#: The metrics every pool has, and whether a rising value is an improvement.
#: COP buckets are not listed here because which buckets exist depends on the
#: climate a given pool sees -- they are discovered from the data instead.
STANDARD_METRICS = {
    "heating_rate": True,
    "heat_loss": False,
    "heat_loss_covered": False,
}


def all_trends(
    months: list[MonthlyAggregate], *, min_months: int = TREND_MIN_MONTHS
) -> dict[str, TrendResult]:
    """Trend for every standard metric, plus one per COP bucket ever recorded.

    The single place this is assembled, so the panel and the AI advisor can
    never disagree about what counts as trending.
    """
    metrics = dict(STANDARD_METRICS)
    for agg in months:
        for bucket in agg.cop_by_bucket:
            metrics.setdefault(f"cop_by_bucket.{bucket}", True)

    return {
        metric: trend(
            months, metric, higher_is_better=higher_is_better, min_months=min_months
        )
        for metric, higher_is_better in metrics.items()
    }
