"""Persistent state for PoolSmart.

Filtration runtime is kept as a list of closed intervals rather than a running
counter. That distinction is what makes a restart survivable: a counter that
lives in an entity loses everything, whereas a list of intervals loses at most
the tick that was in flight, and an interval left open by a crash is closed at
the last timestamp that was written.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

if TYPE_CHECKING:
    from .core.config import PoolConfig

from .const import (
    ACCEPTED_SUGGESTIONS_LOG_SIZE,
    DAILY_SUMMARY_MAX_DAYS,
    DATA_VERSION,
    DECISION_LOG_SIZE,
    DOSE_LOG_SIZE,
    MONTHLY_AGGREGATE_MAX_MONTHS,
    SESSION_LOG_SIZE,
    STORAGE_KEY,
    STORAGE_SAVE_DEBOUNCE_SECONDS,
    STORAGE_VERSION,
)
from .core.aggregates import MonthlyAggregate, month_key
from .core.trace import NearMissLog

_LOGGER = logging.getLogger(__name__)


@dataclass
class RuntimeInterval:
    """A period during which the circulation pump was running."""

    start: datetime
    end: datetime | None = None

    @property
    def hours(self) -> float:
        if self.end is None:
            return 0.0
        return max(0.0, (self.end - self.start).total_seconds() / 3600.0)

    def as_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> RuntimeInterval:
        return cls(
            start=datetime.fromisoformat(raw["start"]),
            end=datetime.fromisoformat(raw["end"]) if raw.get("end") else None,
        )


@dataclass
class LearnedValues:
    """Values the system improves after each session."""

    heating_rate_c_per_h: float | None = None
    #: Heat loss with the pool open to the air.
    heat_loss_c_per_h: float | None = None
    #: Heat loss with the cover on, learned separately.
    #:
    #: Averaging the two would produce a figure that is wrong in both states, and
    #: wrong by a lot: a cover typically halves the loss or better. On a pool
    #: losing two thirds of its input to the air, that is the difference between
    #: a two degree rise taking fourteen hours and taking five.
    heat_loss_covered_c_per_h: float | None = None
    heat_loss_samples: int = 0
    heat_loss_covered_samples: int = 0
    measured_flow_m3h: float | None = None
    cop_by_air_bucket: dict[str, float] = field(default_factory=dict)
    #: Sessions behind each bucket, so a single measurement is not mistaken for
    #: a settled figure.
    cop_sessions_by_bucket: dict[str, int] = field(default_factory=dict)
    heating_rate_sessions: int = 0
    session_count: int = 0
    heating_rate_updated_at: datetime | None = None
    heat_loss_updated_at: datetime | None = None
    heat_loss_covered_updated_at: datetime | None = None
    cop_updated_at: dict[str, datetime] = field(default_factory=dict)
    #: How this pool's pH actually responds to a dose, versus the table
    #: figure -- 1.0 means "matches the table". See core.chemistry.
    ph_correction: float = 1.0
    ph_correction_sessions: int = 0
    ph_correction_updated_at: datetime | None = None
    #: Same, for chlorine.
    chlorine_correction: float = 1.0
    chlorine_correction_sessions: int = 0
    chlorine_correction_updated_at: datetime | None = None

    def as_dict(self) -> dict:
        return {
            "heating_rate_c_per_h": self.heating_rate_c_per_h,
            "heat_loss_c_per_h": self.heat_loss_c_per_h,
            "heat_loss_covered_c_per_h": self.heat_loss_covered_c_per_h,
            "heat_loss_samples": self.heat_loss_samples,
            "heat_loss_covered_samples": self.heat_loss_covered_samples,
            "measured_flow_m3h": self.measured_flow_m3h,
            "cop_by_air_bucket": self.cop_by_air_bucket,
            "cop_sessions_by_bucket": self.cop_sessions_by_bucket,
            "heating_rate_sessions": self.heating_rate_sessions,
            "session_count": self.session_count,
            "heating_rate_updated_at": (
                self.heating_rate_updated_at.isoformat()
                if self.heating_rate_updated_at
                else None
            ),
            "heat_loss_updated_at": (
                self.heat_loss_updated_at.isoformat()
                if self.heat_loss_updated_at
                else None
            ),
            "heat_loss_covered_updated_at": (
                self.heat_loss_covered_updated_at.isoformat()
                if self.heat_loss_covered_updated_at
                else None
            ),
            "cop_updated_at": {
                k: v.isoformat() for k, v in self.cop_updated_at.items()
            },
            "ph_correction": self.ph_correction,
            "ph_correction_sessions": self.ph_correction_sessions,
            "ph_correction_updated_at": (
                self.ph_correction_updated_at.isoformat()
                if self.ph_correction_updated_at
                else None
            ),
            "chlorine_correction": self.chlorine_correction,
            "chlorine_correction_sessions": self.chlorine_correction_sessions,
            "chlorine_correction_updated_at": (
                self.chlorine_correction_updated_at.isoformat()
                if self.chlorine_correction_updated_at
                else None
            ),
        }

    @classmethod
    def from_dict(cls, raw: dict) -> LearnedValues:
        cop_updated_at = {
            k: datetime.fromisoformat(v)
            for k, v in raw.get("cop_updated_at", {}).items()
        }
        return cls(
            heating_rate_c_per_h=raw.get("heating_rate_c_per_h"),
            heat_loss_c_per_h=raw.get("heat_loss_c_per_h"),
            heat_loss_covered_c_per_h=raw.get("heat_loss_covered_c_per_h"),
            heat_loss_samples=raw.get("heat_loss_samples", 0),
            heat_loss_covered_samples=raw.get("heat_loss_covered_samples", 0),
            measured_flow_m3h=raw.get("measured_flow_m3h"),
            cop_by_air_bucket=raw.get("cop_by_air_bucket", {}),
            cop_sessions_by_bucket=raw.get("cop_sessions_by_bucket", {}),
            heating_rate_sessions=raw.get("heating_rate_sessions", 0),
            session_count=raw.get("session_count", 0),
            heating_rate_updated_at=(
                datetime.fromisoformat(raw["heating_rate_updated_at"])
                if raw.get("heating_rate_updated_at")
                else None
            ),
            heat_loss_updated_at=(
                datetime.fromisoformat(raw["heat_loss_updated_at"])
                if raw.get("heat_loss_updated_at")
                else None
            ),
            heat_loss_covered_updated_at=(
                datetime.fromisoformat(raw["heat_loss_covered_updated_at"])
                if raw.get("heat_loss_covered_updated_at")
                else None
            ),
            cop_updated_at=cop_updated_at,
            ph_correction=raw.get("ph_correction", 1.0),
            ph_correction_sessions=raw.get("ph_correction_sessions", 0),
            ph_correction_updated_at=(
                datetime.fromisoformat(raw["ph_correction_updated_at"])
                if raw.get("ph_correction_updated_at")
                else None
            ),
            chlorine_correction=raw.get("chlorine_correction", 1.0),
            chlorine_correction_sessions=raw.get("chlorine_correction_sessions", 0),
            chlorine_correction_updated_at=(
                datetime.fromisoformat(raw["chlorine_correction_updated_at"])
                if raw.get("chlorine_correction_updated_at")
                else None
            ),
        )


class PoolStore:
    """Wrapper around Home Assistant's Store helper."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}")
        #: Serialises saves so an unload can never overtake a save in flight.
        self._save_lock = asyncio.Lock()
        #: Monotonic time of the last write, for the debounce in :meth:`async_save`.
        self._last_saved_at: float = 0.0
        #: Wall-clock time of the last write that actually reached disk, kept
        #: for diagnostics -- monotonic time answers "how long ago" but not
        #: "at what moment", which is what a bug report needs.
        self.last_synced_at: datetime | None = None
        self.quota_date: date | None = None
        self.intervals: list[RuntimeInterval] = []
        #: The open interval, so :meth:`record_pump` does not have to rescan the
        #: whole list on every tick.
        self._open_interval: RuntimeInterval | None = None
        #: Running total of closed intervals' hours, so :meth:`runtime_hours`
        #: stays O(1) regardless of how many start/stop cycles occur today.
        self._closed_hours: float = 0.0
        self.learned = LearnedValues()
        self.active_block: dict | None = None
        #: A heating session still in progress, so it survives a reload instead
        #: of vanishing from the Sessions tab. See core.learning.SessionRecord.
        self.active_session: dict | None = None
        self.heat_pump_stopped_at: datetime | None = None
        self.heat_pump_started_at: datetime | None = None
        self.chemistry_until: datetime | None = None
        self.mode: str | None = None
        self.target_temp: float | None = None
        self.decision_log: deque[dict] = deque(maxlen=DECISION_LOG_SIZE)
        self.session_log: deque[dict] = deque(maxlen=SESSION_LOG_SIZE)
        self.dose_log: deque[dict] = deque(maxlen=DOSE_LOG_SIZE)
        #: Accepted AI suggestions, each with a "before" snapshot and, once
        #: the outcome window has passed, an outcome. See ai.advisor and #10.
        self.accepted_suggestions: deque[dict] = deque(
            maxlen=ACCEPTED_SUGGESTIONS_LOG_SIZE
        )
        self.last_water_test: datetime | None = None
        self.energy_today_kwh: float = 0.0
        self.cost_today: float = 0.0
        self.cost_baseline_today: float = 0.0
        self.near_miss_log = NearMissLog()
        self.daily_summaries: list[dict] = []
        #: One row per calendar month, kept indefinitely (subject only to
        #: MONTHLY_AGGREGATE_MAX_MONTHS) so a slow drift in a learned value is
        #: still visible long after the session log and daily summaries that
        #: fed it have rolled off their caps. See core.aggregates.
        self.monthly_aggregates: dict[str, MonthlyAggregate] = {}

    @property
    def path(self) -> str:
        """Where this pool's state lives on disk, for stats and diagnostics."""
        return self._store.path

    @property
    def open_interval_since(self) -> datetime | None:
        """When the pump's currently-running interval started, if any."""
        return self._open_interval.start if self._open_interval else None

    def stats(self) -> dict:
        """In-memory counts, cheap enough to compute on every request.

        File size is not included here -- that needs a blocking stat() call,
        kept out of this method so callers stay free to run it without an
        executor.
        """
        return {
            "sessions": len(self.session_log),
            "doses": len(self.dose_log),
            "decisions": len(self.decision_log),
            "near_misses": len(self.near_miss_log.tallies),
            "daily_summaries": len(self.daily_summaries),
            "monthly_aggregates": len(self.monthly_aggregates),
        }

    # -- Loading and saving ------------------------------------------------

    async def async_load(self) -> None:
        try:
            raw = await self._store.async_load() or {}
        except KeyError:
            _LOGGER.warning(
                "Stored PoolSmart state was missing its version key and has been reset"
            )
            return
        raw = self._migrate_data(raw.get("data_version", 0), raw)
        synced_at: datetime | None = None
        if raw.get("synced_at"):
            try:
                synced_at = datetime.fromisoformat(raw["synced_at"])
            except (TypeError, ValueError):
                synced_at = None
        # Each group below is parsed and committed independently. A single
        # malformed field (e.g. a corrupt timestamp) must only reset that
        # group -- it must never abort the rest of the load and leave later
        # groups (in particular the session/dose logs) silently stuck at
        # their fresh __init__ defaults while earlier groups (like `learned`)
        # keep the value already assigned. See issues #20 and #18: a single
        # swallowed exception here used to look like a full reset but was
        # actually only a partial one, desyncing session/dose counts from
        # the learned counters and losing mode/target_temp along with it.
        try:
            if raw.get("quota_date"):
                self.quota_date = date.fromisoformat(raw["quota_date"])
        except (ValueError, TypeError):
            _LOGGER.warning("Stored quota date was unreadable and has been reset")

        # Parsed one interval at a time rather than as a single list
        # comprehension: today's filtration credit is exactly what a
        # comprehension throws away wholesale the moment any one entry is
        # malformed, even though quota_date (parsed above) survives and still
        # reads as today -- so roll_day sees no day change and the pool looks
        # completely unfiltered despite everything else having gone right.
        # One bad entry should cost that one interval, not the whole day.
        intervals: list[RuntimeInterval] = []
        for item in raw.get("intervals", []):
            try:
                intervals.append(RuntimeInterval.from_dict(item))
            except (ValueError, KeyError, TypeError):
                _LOGGER.warning(
                    "Discarding one unreadable filtration interval; the rest of "
                    "today's runtime is kept"
                )
        self.intervals = intervals

        try:
            self.learned = LearnedValues.from_dict(raw.get("learned", {}))
        except (ValueError, KeyError, TypeError):
            _LOGGER.warning("Stored learned values were unreadable and have been reset")

        self.active_block = raw.get("active_block")
        self.active_session = raw.get("active_session")

        try:
            if raw.get("heat_pump_stopped_at"):
                self.heat_pump_stopped_at = datetime.fromisoformat(raw["heat_pump_stopped_at"])
            if raw.get("heat_pump_started_at"):
                self.heat_pump_started_at = datetime.fromisoformat(raw["heat_pump_started_at"])
            if raw.get("chemistry_until"):
                self.chemistry_until = datetime.fromisoformat(raw["chemistry_until"])
        except (ValueError, KeyError, TypeError):
            _LOGGER.warning(
                "Stored heat-pump/chemistry timestamps were unreadable and have "
                "been reset"
            )

        self.mode = raw.get("mode")
        self.target_temp = raw.get("target_temp")

        try:
            self.decision_log = deque(raw.get("decision_log", []), maxlen=DECISION_LOG_SIZE)
            self.session_log = deque(raw.get("session_log", []), maxlen=SESSION_LOG_SIZE)
            self.dose_log = deque(raw.get("dose_log", []), maxlen=DOSE_LOG_SIZE)
        except (ValueError, KeyError, TypeError):
            _LOGGER.warning(
                "Stored session/dose/decision logs were unreadable and have been reset"
            )

        try:
            self.accepted_suggestions = deque(
                raw.get("accepted_suggestions", []),
                maxlen=ACCEPTED_SUGGESTIONS_LOG_SIZE,
            )
        except (ValueError, KeyError, TypeError):
            _LOGGER.warning(
                "Stored accepted AI suggestions were unreadable and have been reset"
            )

        try:
            if raw.get("last_water_test"):
                self.last_water_test = datetime.fromisoformat(raw["last_water_test"])
        except (ValueError, KeyError, TypeError):
            _LOGGER.warning(
                "Stored last water-test timestamp was unreadable and has been reset"
            )

        self.energy_today_kwh = raw.get("energy_today_kwh", 0.0)
        self.cost_today = raw.get("cost_today", 0.0)
        self.cost_baseline_today = raw.get("cost_baseline_today", 0.0)

        try:
            self.near_miss_log = NearMissLog.from_dict(raw.get("near_miss_log", {}))
        except (ValueError, KeyError, TypeError):
            _LOGGER.warning("Stored near-miss log was unreadable and has been reset")

        self.daily_summaries = raw.get("daily_summaries", [])

        try:
            self.monthly_aggregates = {
                key: MonthlyAggregate.from_dict(value)
                for key, value in raw.get("monthly_aggregates", {}).items()
            }
        except (ValueError, KeyError, TypeError, AttributeError):
            _LOGGER.warning(
                "Stored monthly aggregates were unreadable and have been reset"
            )

        self.last_synced_at = synced_at
        self._close_open_interval(synced_at)
        self._open_interval = None
        self._closed_hours = sum(
            max(0.0, (i.end - i.start).total_seconds() / 3600.0)
            for i in self.intervals
            if i.end is not None
        )
        # One line, always visible at the default log level, that answers the
        # question a lost-filtration-credit report always starts with: what
        # did this boot actually find on disk. Reaching for debug logging or
        # hunting through the full log after the fact should not be necessary
        # to see whether today's runtime came back or not.
        _LOGGER.info(
            "PoolSmart state restored: quota_date=%s, filtration credited=%.2fh "
            "from %d interval(s), last write to disk was %s",
            self.quota_date.isoformat() if self.quota_date else "none",
            self._closed_hours,
            len(self.intervals),
            self.last_synced_at.isoformat() if self.last_synced_at else "unknown",
        )
        if self.backfill_cop_counts():
            _LOGGER.info(
                "Recovered COP session counts for learned values that predate the "
                "confidence counter"
            )

        if self.backfill_monthly_aggregates():
            _LOGGER.info(
                "Reconstructed monthly trend rows from session and daily history "
                "that predates long-term trend retention"
            )

    def _migrate_data(self, old_version: int, raw: dict) -> dict:
        """Upgrade stored data from an older schema version to the current one.

        Runs incrementally: each version step is handled in sequence, so data
        written by any older version arrives at the current schema through a
        chain of small, individually reviewable transformations.

        The current schema is v1, which is the structure this parser expects.
        v0 data has no ``data_version`` field -- it predates this mechanism --
        but is structurally identical, so the v0 step is a no-op that only
        establishes the pattern. Future schema changes add real steps here.
        """
        if old_version >= DATA_VERSION:
            return raw

        data = dict(raw)
        version = old_version

        if version < 1:
            # v0: pre-versioning data. Structurally identical to v1.
            version = 1

        # if version < 2:
        #     # v2: describe the structural change here.
        #     version = 2

        data["data_version"] = version
        return data

    def _close_open_interval(self, synced_at: datetime | None) -> None:
        """Close an interval that a crash or restart left open.

        The pump state after the gap is unknown, so the interval cannot simply
        be left running. ``synced_at`` -- when a previous save actually reached
        disk -- is the latest moment this integration can vouch for, and is
        used as the close point so an interval that had been open for hours
        loses only the unsaved tail, not the whole thing. Without a usable
        ``synced_at`` (an old file predating this field, or one somehow from
        the future) the interval is closed at its own start instead, crediting
        it nothing -- the same conservative fallback this always used, kept
        for exactly the cases it was meant to cover.
        """
        for interval in self.intervals:
            if interval.end is None:
                if synced_at is not None and synced_at > interval.start:
                    interval.end = synced_at
                else:
                    interval.end = interval.start
                _LOGGER.debug("Closed a filtration interval left open by a restart")

    async def _async_save_atomic(self, data: dict, path: str) -> None:
        """Write data to disk with a temp-file-then-rename pattern.

        A crash mid-write can leave a truncated JSON file that cannot be parsed
        on the next load. Writing to a temporary file and renaming it over the
        target replaces the old contents atomically: the rename is a single
        metadata operation on the filesystem, not a copy, so it either
        completes or it does not.
        """
        loop = asyncio.get_running_loop()
        target = Path(path)
        tmp = target.with_suffix(".tmp")

        def _write() -> None:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, target)

        await loop.run_in_executor(None, _write)

    async def async_save(self, *, force: bool = False) -> None:
        """Persist the state, debounced and serialised.

        The tick saves every thirty seconds, so a save can never be more than
        one interval old. The quiet calls in between -- a dose logged, a learned
        value reset -- do not each need their own write: the next tick would
        write exactly the same file a moment later. Skipping them leaves the disk
        with the same content either way and spares the executor the serialisation.

        ``force`` bypasses the debounce. It is used where waiting for the next
        tick would mean losing data for good: unloading, and substantial import
        or reset operations whose effect lives in this file.
        """
        now = time.monotonic()
        if now - self._last_saved_at < STORAGE_SAVE_DEBOUNCE_SECONDS and not force:
            return

        synced_at = datetime.now(timezone.utc)
        data = {
            "data_version": DATA_VERSION,
            #: Wall-clock time this save actually reached disk, so a dangling
            #: open interval found on the next load can be closed here instead
            #: of at its own start -- see _close_open_interval.
            "synced_at": synced_at.isoformat(),
            "quota_date": self.quota_date.isoformat() if self.quota_date else None,
            "intervals": [i.as_dict() for i in self.intervals],
            "learned": self.learned.as_dict(),
            "active_block": self.active_block,
            "active_session": self.active_session,
            "heat_pump_stopped_at": (
                self.heat_pump_stopped_at.isoformat()
                if self.heat_pump_stopped_at
                else None
            ),
            "heat_pump_started_at": (
                self.heat_pump_started_at.isoformat()
                if self.heat_pump_started_at
                else None
            ),
            "chemistry_until": (
                self.chemistry_until.isoformat()
                if self.chemistry_until
                else None
            ),
            "mode": self.mode,
            "target_temp": self.target_temp,
            "decision_log": list(self.decision_log),
            "session_log": list(self.session_log),
            "dose_log": list(self.dose_log),
            "accepted_suggestions": list(self.accepted_suggestions),
            "last_water_test": (
                self.last_water_test.isoformat() if self.last_water_test else None
            ),
            "energy_today_kwh": self.energy_today_kwh,
            "cost_today": self.cost_today,
            "cost_baseline_today": self.cost_baseline_today,
            "near_miss_log": self.near_miss_log.as_dict(),
            "daily_summaries": self.daily_summaries,
            "monthly_aggregates": {
                key: agg.as_dict() for key, agg in self.monthly_aggregates.items()
            },
        }

        async with self._save_lock:
            self._last_saved_at = time.monotonic()
            await self._async_save_atomic(data, self._store.path)
            self.last_synced_at = synced_at

    # -- Filtration quota --------------------------------------------------

    def roll_day(self, now: datetime) -> bool:
        """Reset the quota when the date changes. Returns True if it rolled."""
        if self.quota_date == now.date():
            return False
        if self.quota_date is not None:
            runtime = sum(i.hours for i in self.intervals if i.end is not None)
            self.daily_summaries.append(
                {
                    "date": self.quota_date.isoformat(),
                    "runtime_hours": round(runtime, 3),
                    "energy_kwh": round(self.energy_today_kwh, 3),
                    "cost_euro": round(self.cost_today, 2),
                }
            )
            if len(self.daily_summaries) > DAILY_SUMMARY_MAX_DAYS:
                self.daily_summaries = self.daily_summaries[-DAILY_SUMMARY_MAX_DAYS:]
            agg = self._month_agg(self.quota_date)
            agg.runtime_hours += runtime
            agg.energy_kwh += self.energy_today_kwh
            agg.cost_euro += self.cost_today
        self.quota_date = now.date()
        self.intervals = []
        self._open_interval = None
        self._closed_hours = 0.0
        self.active_block = None
        self.energy_today_kwh = 0.0
        self.cost_today = 0.0
        self.cost_baseline_today = 0.0
        return True

    def record_pump(self, now: datetime, running: bool) -> None:
        """Update the interval list from the pump's actual state.

        The open interval is held separately rather than hunted for each call,
        so a tick costs O(1) no matter how the interval list has grown.
        """
        if running and self._open_interval is None:
            self._open_interval = RuntimeInterval(start=now)
            self.intervals.append(self._open_interval)
        elif running and self._open_interval is not None:
            # Keep the open interval open, but remember how far it has come so a
            # crash loses only the last tick.
            self._open_interval.end = None
        elif not running and self._open_interval is not None:
            self._open_interval.end = now
            self._closed_hours += max(
                0.0, (now - self._open_interval.start).total_seconds() / 3600.0
            )
            self._open_interval = None

    def clear_runtime(self) -> None:
        """Forget today's credited runtime so a full cycle can run again."""
        self.intervals = []
        self._open_interval = None
        self._closed_hours = 0.0

    def runtime_hours(self, now: datetime) -> float:
        """Filtration runtime credited today, including any open interval.

        Heating sessions run the pump too, so their runtime lands here
        automatically. Without that credit the system would filter substantially
        more than needed on heating days.
        """
        total = self._closed_hours
        if self._open_interval is not None:
            total += max(0.0, (now - self._open_interval.start).total_seconds() / 3600.0)
        return total

    # -- Decision log ------------------------------------------------------

    def log_decision(self, payload: dict) -> None:
        self.decision_log.append(payload)

    def log_dose(self, payload: dict) -> None:
        """Record a dose that was applied."""
        self.dose_log.append(payload)

    def log_accepted_suggestion(self, payload: dict) -> None:
        """Record an AI suggestion that was accepted, for the outcome check."""
        self.accepted_suggestions.append(payload)

    def log_session(self, payload: dict) -> None:
        """Record a finished heating session, usable or not.

        Rejected sessions are kept deliberately: when the model stops improving,
        the reasons things were rejected are the first place to look.
        """
        self.session_log.append(payload)

    def set_session_review(self, session_start: str, review: str) -> bool:
        """Override whether one logged session counts toward learning.

        ``session_start`` is the session's ``start`` field -- its natural id,
        since two sessions cannot begin at the same instant. Returns whether a
        matching session was found. Does not itself recompute the learned
        values; call :meth:`rebuild_learned` afterwards so a batch of reviews
        only costs one rebuild.
        """
        from .core.learning import SESSION_REVIEW_STATES

        if review not in SESSION_REVIEW_STATES:
            return False
        for entry in self.session_log:
            if entry.get("start") == session_start:
                entry["review"] = review
                return True
        return False

    # -- Learned values ----------------------------------------------------

    def rebuild_learned(self, config: "PoolConfig") -> None:
        """Recompute the session-derived learned values from the current log.

        Replaces rather than nudges: unlike the incremental update applied as
        each session finishes, this re-derives the heating rate and COP curve
        from every session that currently counts, so a review change made long
        after the fact actually changes what the model believes. Leaves heat
        loss and measured flow alone -- those come from idle periods and flow
        sensors, not sessions, so a session review has nothing to say about
        them.
        """
        from .core.learning import rebuild_learned as _rebuild_learned

        result = _rebuild_learned(list(self.session_log), config)
        self.learned.heating_rate_c_per_h = result["heating_rate_c_per_h"]
        self.learned.heating_rate_sessions = result["heating_rate_sessions"]
        self.learned.heating_rate_updated_at = result["heating_rate_updated_at"]
        self.learned.cop_by_air_bucket = result["cop_by_air_bucket"]
        self.learned.cop_updated_at = result["cop_updated_at"]
        self.learned.cop_sessions_by_bucket = result["cop_sessions_by_bucket"]
        self.learned.session_count = result["session_count"]

    def backfill_cop_counts(self) -> bool:
        """Give pre-1.1 buckets a session count they were never given.

        `cop_by_air_bucket` has existed since 0.9; the counter that gates it was
        added in 1.1. Anyone who upgraded therefore has learned values sitting
        behind a gate that can never open, because the count starts at zero no
        matter how many sessions produced the value.

        Counting the recorded sessions per bucket recovers the real figure. Where
        the session log has been trimmed away, one is assumed: enough to show the
        value exists, not enough to trust it for planning, which is the honest
        position for a number whose provenance was lost.
        """
        if not self.learned.cop_by_air_bucket:
            return False
        if self.learned.cop_sessions_by_bucket:
            return False

        from .core.learning import recover_cop_counts

        self.learned.cop_sessions_by_bucket = recover_cop_counts(
            self.learned.cop_by_air_bucket, self.session_log
        )
        return True

    def adopt(self, history: dict) -> str:
        """Take on learned history from elsewhere.

        Merges rather than replaces where it can: an adopted heat loss is better
        than no heat loss, but if this pool has already learned something of its
        own since setup, that is measured on the actual installation and wins.
        """
        learned = history.get("learned") or {}
        incoming = LearnedValues.from_dict(learned)
        taken: list[str] = []

        for attr in (
            "heating_rate_c_per_h",
            "heat_loss_c_per_h",
            "heat_loss_covered_c_per_h",
            "measured_flow_m3h",
        ):
            if getattr(self.learned, attr) is None:
                value = getattr(incoming, attr)
                if value is not None:
                    setattr(self.learned, attr, value)
                    taken.append(attr)

        if not self.learned.cop_by_air_bucket and incoming.cop_by_air_bucket:
            self.learned.cop_by_air_bucket = dict(incoming.cop_by_air_bucket)
            self.learned.cop_sessions_by_bucket = dict(
                incoming.cop_sessions_by_bucket
            )
            taken.append("cop_by_air_bucket")

        for attr in (
            "session_count",
            "heating_rate_sessions",
            "heat_loss_samples",
            "heat_loss_covered_samples",
        ):
            if not getattr(self.learned, attr):
                setattr(self.learned, attr, getattr(incoming, attr))

        # The logs are the evidence the figures were derived from; adopting a
        # summary without them leaves numbers nothing can check or improve.
        if not self.session_log and history.get("session_log"):
            self.session_log = deque(history["session_log"], maxlen=SESSION_LOG_SIZE)
            taken.append("session_log")
        if not self.dose_log and history.get("dose_log"):
            self.dose_log = deque(history["dose_log"], maxlen=DOSE_LOG_SIZE)
            taken.append("dose_log")
        if not self.accepted_suggestions and history.get("accepted_suggestions"):
            self.accepted_suggestions = deque(
                history["accepted_suggestions"], maxlen=ACCEPTED_SUGGESTIONS_LOG_SIZE
            )
            taken.append("accepted_suggestions")
        if self.last_water_test is None and history.get("last_water_test"):
            try:
                self.last_water_test = datetime.fromisoformat(
                    history["last_water_test"]
                )
            except (TypeError, ValueError):
                pass

        self.backfill_cop_counts()
        return ", ".join(taken) if taken else "nothing was missing"

    def replace(self, history: dict, sections: "list[str] | None" = None) -> str:
        """Overwrite (not merge) with history from elsewhere.

        The advanced counterpart to :meth:`adopt`: where that keeps whatever
        this pool has already measured for itself, this discards it in favour
        of the import outright. For recovering from a bad rebuild or bringing
        a backup back exactly as it was -- not for routine use, which is what
        :meth:`adopt` is for. ``sections`` limits which parts are replaced;
        omitted sections are left untouched.
        """
        from .recovery import EXPORT_SECTIONS

        chosen = set(sections) if sections is not None else set(EXPORT_SECTIONS)
        replaced: list[str] = []

        if "learned" in chosen and "learned" in history:
            self.learned = LearnedValues.from_dict(history.get("learned") or {})
            replaced.append("learned")
        if "session_log" in chosen and "session_log" in history:
            self.session_log = deque(history["session_log"], maxlen=SESSION_LOG_SIZE)
            replaced.append("session_log")
        if "dose_log" in chosen and "dose_log" in history:
            self.dose_log = deque(history["dose_log"], maxlen=DOSE_LOG_SIZE)
            replaced.append("dose_log")
        if "accepted_suggestions" in chosen and "accepted_suggestions" in history:
            self.accepted_suggestions = deque(
                history["accepted_suggestions"], maxlen=ACCEPTED_SUGGESTIONS_LOG_SIZE
            )
            replaced.append("accepted_suggestions")
        if "last_water_test" in chosen and "last_water_test" in history:
            raw = history.get("last_water_test")
            try:
                self.last_water_test = datetime.fromisoformat(raw) if raw else None
            except (TypeError, ValueError):
                pass
            else:
                replaced.append("last_water_test")

        self.backfill_cop_counts()
        return ", ".join(replaced) if replaced else "nothing to replace"

    def reset_learned(self, name: str) -> bool:
        """Clear one learned value without discarding the rest.

        A single implausible figure should not cost someone their whole learning
        history -- particularly the heat loss, which takes days of idle periods
        to establish and is the hardest one to rebuild.
        """
        from .core.learning import RESETTABLE

        if name not in RESETTABLE:
            return False

        value_attr, count_attr = RESETTABLE[name]
        current = getattr(self.learned, value_attr)
        setattr(self.learned, value_attr, {} if isinstance(current, dict) else None)
        if count_attr:
            counter = getattr(self.learned, count_attr)
            setattr(self.learned, count_attr, {} if isinstance(counter, dict) else 0)
        return True

    def apply_learned(
        self,
        name: str,
        value: float,
        max_step_ratio: float,
        now: datetime,
        updated_at_attr: str | None = None,
    ) -> float:
        """Update a learned value with a capped step.

        A single strange session must not be able to wreck the model, so each
        update may move the value by at most ``max_step_ratio``.
        """
        from .core.learning import capped_update

        current = getattr(self.learned, name, None)
        updated_at = getattr(self.learned, updated_at_attr) if updated_at_attr else None
        updated = capped_update(current, value, max_step_ratio, updated_at, now)
        setattr(self.learned, name, updated)
        if updated_at_attr:
            setattr(self.learned, updated_at_attr, now)
        return updated

    def daily_summary(self) -> list[dict]:
        """Return persisted daily runtime and energy summaries."""
        return list(self.daily_summaries)

    # -- Monthly aggregates --------------------------------------------------

    def _month_agg(self, when) -> MonthlyAggregate:
        """Get or create the aggregate row for ``when``'s calendar month.

        ``when`` may be a ``date`` or a ``datetime`` -- only ``year``/``month``
        are used. Enforces MONTHLY_AGGREGATE_MAX_MONTHS by dropping the oldest
        rows, which only ever matters after a decade of continuous use.
        """
        key = month_key(when)
        agg = self.monthly_aggregates.get(key)
        if agg is None:
            agg = MonthlyAggregate(month=key)
            self.monthly_aggregates[key] = agg
            if len(self.monthly_aggregates) > MONTHLY_AGGREGATE_MAX_MONTHS:
                oldest = sorted(self.monthly_aggregates)[
                    : len(self.monthly_aggregates) - MONTHLY_AGGREGATE_MAX_MONTHS
                ]
                for stale_key in oldest:
                    del self.monthly_aggregates[stale_key]
        return agg

    def record_monthly_metric(self, name: str, value: float, when: datetime) -> None:
        """Fold one observation into the named field of ``when``'s month.

        ``name`` is one of ``heating_rate``, ``heat_loss``, ``heat_loss_covered``
        -- the MetricStat fields on MonthlyAggregate. Mirrors exactly what
        already gets folded into the corresponding learned value, at the same
        call sites, so the monthly trend can never diverge from what the model
        actually learned from.
        """
        agg = self._month_agg(when)
        getattr(agg, name).fold(value)

    def record_monthly_cop(self, air_temp: float, cop: float, when: datetime) -> None:
        """Fold one measured COP into the right temperature bucket of ``when``'s month."""
        from .core.learning import bucket_key

        agg = self._month_agg(when)
        agg.cop_stat(bucket_key(air_temp)).fold(cop)

    def bump_monthly_session_count(self, when: datetime) -> None:
        """Count one more usable session against ``when``'s month.

        Called once per session that taught the model anything -- mirrors
        ``learned.session_count`` in :meth:`~PoolStore.rebuild_learned`, just
        never rebuilt, since a monthly row is never re-derived from the log
        the way the overall learned values are.
        """
        self._month_agg(when).session_count += 1

    def monthly_summary(self) -> list[dict]:
        """Monthly aggregates, oldest first, for the panel and websocket API."""
        return [
            self.monthly_aggregates[key].as_dict()
            for key in sorted(self.monthly_aggregates)
        ]

    def backfill_monthly_aggregates(self) -> bool:
        """Reconstruct monthly trend rows for history that predates them.

        Long-term trend retention only folds in observations from the moment a
        session finishes or a day rolls over -- see the ``record_monthly_*``
        and ``bump_monthly_session_count`` call sites in the coordinator.
        Nothing replays what was already sitting in ``session_log`` and
        ``daily_summaries`` when that feature shipped, so anyone upgrading
        with existing history saw trends start from zero and need
        ``TREND_MIN_MONTHS`` more months to say anything at all, despite
        already having the data to say it immediately.

        Only ever runs while no monthly aggregate exists yet: once the live
        path has folded in a single observation, replaying the logs again
        would double-count whatever overlaps between them and the raw history.
        Heat loss and heat-loss-covered are not recovered here -- unlike
        heating rate and COP, no raw sample of either survives anywhere once
        it has been folded into ``learned``, so there is nothing left to
        replay.
        """
        if self.monthly_aggregates:
            return False

        recovered = False

        for day in self.daily_summaries:
            try:
                when = date.fromisoformat(day["date"])
            except (KeyError, ValueError, TypeError):
                continue
            agg = self._month_agg(when)
            agg.runtime_hours += day.get("runtime_hours", 0.0)
            agg.energy_kwh += day.get("energy_kwh", 0.0)
            agg.cost_euro += day.get("cost_euro", 0.0)
            recovered = True

        # Mirrors rebuild_learned's review handling in core.learning: an
        # explicit "excluded" always drops the session, "included" forces it
        # in as long as the value it would contribute actually exists, and
        # "auto" (or a log written before review existed) falls back to the
        # verdict recorded when the session finished.
        for entry in self.session_log:
            if entry.get("review") == "excluded":
                continue
            included = entry.get("review") == "included"
            verdict = entry.get("measurements") or {}
            end = entry.get("end")
            if not end:
                continue
            try:
                when = datetime.fromisoformat(end)
            except (ValueError, TypeError):
                continue

            use_rate = (included or verdict.get("heating_rate")) and entry.get(
                "heating_rate"
            ) is not None
            use_cop = (included or verdict.get("cop")) and entry.get(
                "measured_cop"
            ) is not None

            if use_rate:
                self.record_monthly_metric("heating_rate", entry["heating_rate"], when)
            if use_cop:
                air = entry.get("air_avg")
                if air is not None:
                    self.record_monthly_cop(float(air), entry["measured_cop"], when)
            if use_rate or use_cop:
                self.bump_monthly_session_count(when)
                recovered = True

        return recovered
