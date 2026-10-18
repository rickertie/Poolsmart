"""Finding learned history that a reinstall left behind.

Removing an integration and adding it again gives it a new entry id, and the
storage key is built from that id. The old file is not deleted -- nothing calls
`async_remove` -- so the learning is still sitting on disk under a key nothing
reads any more. Weeks of measured heat loss, a COP curve and a session history,
present and invisible.

Rebuilding that takes days of idle periods and completed heating sessions, which
is a poor thing to ask of someone who only wanted to change a setting. So on
setup, look for it.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import STORAGE_KEY

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Orphan:
    """Learned history from an entry that no longer exists."""

    path: str
    entry_id: str
    modified: datetime
    sessions: int
    heat_loss: float | None
    heating_rate: float | None
    measured_flow: float | None
    cop_buckets: int
    doses: int

    @property
    def worth_adopting(self) -> bool:
        """Whether there is enough here to be worth offering.

        An entry that ran for an hour and learned nothing is not worth a
        question; one with real history is.
        """
        return bool(
            self.sessions
            or self.heat_loss is not None
            or self.measured_flow is not None
            or self.doses
        )

    def describe(self) -> str:
        """A summary someone can judge the offer by.

        "There is a file" is not something anyone can answer. "Fourteen
        sessions, heat loss 0.23 °C/h, last used three days ago" is.
        """
        parts = []
        if self.sessions:
            parts.append(f"{self.sessions} sessions")
        if self.heat_loss is not None:
            parts.append(f"heat loss {self.heat_loss} °C/h")
        if self.heating_rate is not None:
            parts.append(f"heating rate {self.heating_rate} °C/h")
        if self.measured_flow is not None:
            parts.append(f"flow {self.measured_flow} m³/h")
        if self.cop_buckets:
            parts.append(f"COP for {self.cop_buckets} temperature bands")
        if self.doses:
            parts.append(f"{self.doses} recorded doses")
        summary = ", ".join(parts) if parts else "no learned values"
        # %-d (no leading zero) is a glibc extension: it raises on Windows
        # Python builds, so the day is formatted separately instead.
        return f"{summary} — last written {self.modified.day} {self.modified:%B %Y}"

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "entry_id": self.entry_id,
            "modified": self.modified.isoformat(),
            "sessions": self.sessions,
            "heat_loss": self.heat_loss,
            "heating_rate": self.heating_rate,
            "measured_flow": self.measured_flow,
            "cop_buckets": self.cop_buckets,
            "doses": self.doses,
            "description": self.describe(),
        }


def _inspect(path: Path) -> Orphan | None:
    """Read one storage file without disturbing it."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        modified = datetime.fromtimestamp(path.stat().st_mtime)
    except (OSError, ValueError):
        return None

    if not isinstance(raw, dict):
        return None
    data = raw.get("data")
    if not isinstance(data, dict):
        return None
    learned = data.get("learned") or {}
    if not isinstance(learned, dict):
        return None
    return Orphan(
        path=str(path),
        entry_id=path.name.rsplit(".", 1)[-1],
        modified=modified,
        sessions=learned.get("session_count", 0) or 0,
        heat_loss=learned.get("heat_loss_c_per_h"),
        heating_rate=learned.get("heating_rate_c_per_h"),
        measured_flow=learned.get("measured_flow_m3h"),
        cop_buckets=len(learned.get("cop_by_air_bucket") or {}),
        doses=len(data.get("dose_log") or []),
    )


def find_orphans(hass: HomeAssistant, active_entry_ids: set[str]) -> list[Orphan]:
    """Storage files belonging to no current config entry.

    Sorted newest first, because the most recent one is nearly always the one
    someone means.
    """
    storage = Path(hass.config.path(".storage"))
    if not storage.is_dir():
        return []

    found: list[Orphan] = []
    for path in storage.glob(f"{STORAGE_KEY}.*"):
        entry_id = path.name.rsplit(".", 1)[-1]
        if entry_id in active_entry_ids:
            continue
        orphan = _inspect(path)
        if orphan is not None and orphan.worth_adopting:
            found.append(orphan)

    return sorted(found, key=lambda item: item.modified, reverse=True)


def read_learned(path: str) -> dict | None:
    """The learned portion of a storage file, ready to adopt."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        _LOGGER.warning("Could not read learned history from %s: %s", path, err)
        return None
    if not isinstance(raw, dict):
        return None
    data = raw.get("data")
    if not isinstance(data, dict):
        return None
    learned = data.get("learned")
    return learned if isinstance(learned, dict) else None


def read_history(path: str) -> dict:
    """Everything worth carrying across, not only the learned figures.

    The session log is what the COP counts are rebuilt from, and the dose log is
    what the chemistry corrections are learned from. Adopting the summary while
    discarding the evidence behind it would leave figures nothing could ever
    check or improve.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        _LOGGER.warning("Could not read history from %s: %s", path, err)
        return {}

    if not isinstance(raw, dict):
        return {}
    data = raw.get("data")
    if not isinstance(data, dict):
        return {}
    return {
        key: data[key]
        for key in (
            "learned",
            "session_log",
            "dose_log",
            "last_water_test",
            "accepted_suggestions",
        )
        if key in data
    }


#: What an export can contain. All are opt-out: pass ``sections`` to
#: :func:`export_payload` to carry only some of them across.
EXPORT_SECTIONS = (
    "learned",
    "session_log",
    "dose_log",
    "last_water_test",
    "accepted_suggestions",
)


def export_payload(store, sections: "list[str] | None" = None) -> dict:
    """What an export contains.

    Deliberately not the whole storage file: today's filtration quota, the
    current mode and the decision log describe a moment rather than a pool, and
    carrying them to another system would be carrying noise.

    ``sections`` narrows this further, for someone who wants the learned
    figures without also carrying the raw session log across, say. ``None``
    (the default) exports everything above, unchanged from before this
    parameter existed.
    """
    chosen = set(sections) if sections is not None else set(EXPORT_SECTIONS)
    payload = {"version": 1, "exported": datetime.now().isoformat()}
    if "learned" in chosen:
        payload["learned"] = store.learned.as_dict()
    if "session_log" in chosen:
        payload["session_log"] = list(store.session_log)
    if "dose_log" in chosen:
        payload["dose_log"] = list(store.dose_log)
    if "last_water_test" in chosen:
        payload["last_water_test"] = (
            store.last_water_test.isoformat() if store.last_water_test else None
        )
    if "accepted_suggestions" in chosen:
        payload["accepted_suggestions"] = list(store.accepted_suggestions)
    return payload


def validate_import(payload: dict) -> tuple[bool, str]:
    """Whether an imported file is usable.

    Checked rather than trusted: an import that half-applies leaves the model in
    a state nobody can reason about, and refusing outright is easier to recover
    from than a silent partial load.
    """
    if not isinstance(payload, dict):
        return False, "the file does not contain an export"
    if type(payload.get("version")) is not int or payload.get("version") != 1:
        return False, f"unsupported export version {payload.get('version')!r}"
    if not set(EXPORT_SECTIONS) & payload.keys():
        return False, "the export contains none of: " + ", ".join(EXPORT_SECTIONS)
    if "learned" in payload and not isinstance(payload["learned"], dict):
        return False, "learned is not an object"
    for key in ("session_log", "dose_log", "accepted_suggestions"):
        if key in payload and not isinstance(payload[key], list):
            return False, f"{key} is not a list"

    learned = payload.get("learned") or {}
    if "exported" in payload:
        try:
            datetime.fromisoformat(payload["exported"])
        except (TypeError, ValueError):
            return False, "exported is not a valid ISO datetime"

    def finite_number(value: object) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )

    for field_name in ("cop_by_air_bucket", "cop_sessions_by_bucket", "cop_updated_at"):
        if field_name in learned and not isinstance(learned[field_name], dict):
            return False, f"learned.{field_name} is not an object"

    for key, cop in learned.get("cop_by_air_bucket", {}).items():
        if not isinstance(key, str) or not finite_number(cop) or not 1.0 <= cop <= 10.0:
            return False, f"invalid COP value {cop!r} for bucket {key!r}"
    for key, count in learned.get("cop_sessions_by_bucket", {}).items():
        if not isinstance(key, str) or type(count) is not int or count < 0:
            return False, f"invalid COP session count {count!r} for bucket {key!r}"
    for field_name in (
        "heating_rate_updated_at",
        "heat_loss_updated_at",
        "heat_loss_covered_updated_at",
        "ph_correction_updated_at",
        "chlorine_correction_updated_at",
    ):
        value = learned.get(field_name)
        if value is not None:
            try:
                datetime.fromisoformat(value)
            except (TypeError, ValueError):
                return False, f"learned.{field_name} is not a valid ISO datetime"

    for field_name in (
        "heat_loss_samples",
        "heat_loss_covered_samples",
        "heating_rate_sessions",
        "session_count",
        "ph_correction_sessions",
        "chlorine_correction_sessions",
    ):
        value = learned.get(field_name, 0)
        if type(value) is not int or value < 0:
            return False, f"learned.{field_name} must be a non-negative integer"

    for field_name, (lo, hi) in {
        "ph_correction": (0.2, 5.0),
        "chlorine_correction": (0.2, 5.0),
    }.items():
        value = learned.get(field_name, 1.0)
        if not finite_number(value) or not lo <= value <= hi:
            return False, f"learned.{field_name} is outside the plausible range of {lo} to {hi}"
    for key, value in learned.get("cop_updated_at", {}).items():
        if not isinstance(key, str):
            return False, "learned.cop_updated_at contains a non-string key"
        try:
            datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return False, f"learned.cop_updated_at[{key!r}] is not a valid ISO datetime"

    for key in ("session_log", "dose_log", "accepted_suggestions"):
        if key in payload and any(not isinstance(item, dict) for item in payload[key]):
            return False, f"{key} must contain only objects"

    for index, item in enumerate(payload.get("session_log", [])):
        for date_key in ("start", "end"):
            value = item.get(date_key)
            if value is not None:
                try:
                    datetime.fromisoformat(value)
                except (TypeError, ValueError):
                    return False, f"session_log[{index}].{date_key} is not a valid ISO datetime"
        for number_key in (
            "duration_h", "water_start", "water_end", "air_avg", "energy_kwh",
            "thermal_kwh", "heating_rate", "measured_cop",
        ):
            value = item.get(number_key)
            if value is not None and not finite_number(value):
                return False, f"session_log[{index}].{number_key} must be a finite number"
        if not isinstance(item.get("faults", []), list):
            return False, f"session_log[{index}].faults must be a list"
        if "measurements" in item and not isinstance(item["measurements"], dict):
            return False, f"session_log[{index}].measurements must be an object"

    for index, item in enumerate(payload.get("dose_log", [])):
        try:
            datetime.fromisoformat(item["at"])
        except (KeyError, TypeError, ValueError):
            return False, f"dose_log[{index}].at is not a valid ISO datetime"
        if not isinstance(item.get("product"), str) or not isinstance(item.get("unit"), str):
            return False, f"dose_log[{index}] must include product and unit text"
        for number_key in ("amount", "measured_before", "measured_after", "expected_change"):
            value = item.get(number_key)
            if value is not None and not finite_number(value):
                return False, f"dose_log[{index}].{number_key} must be a finite number"

    for index, item in enumerate(payload.get("accepted_suggestions", [])):
        for required in ("id", "setting", "new_value", "accepted_at"):
            if required not in item:
                return False, f"accepted_suggestions[{index}] is missing {required}"
        if not isinstance(item["id"], str) or not isinstance(item["setting"], str):
            return False, f"accepted_suggestions[{index}] id and setting must be text"
        if not finite_number(item["new_value"]):
            return False, f"accepted_suggestions[{index}].new_value must be a finite number"
        if item.get("old_value") is not None and not finite_number(item["old_value"]):
            return False, f"accepted_suggestions[{index}].old_value must be a finite number"
        if not isinstance(item.get("before", {}), dict):
            return False, f"accepted_suggestions[{index}].before must be an object"
        for date_key in ("accepted_at", "outcome_at"):
            value = item.get(date_key)
            if value is not None:
                try:
                    datetime.fromisoformat(value)
                except (TypeError, ValueError):
                    return False, f"accepted_suggestions[{index}].{date_key} is not a valid ISO datetime"

    if "last_water_test" in payload and payload["last_water_test"] is not None:
        try:
            datetime.fromisoformat(payload["last_water_test"])
        except (TypeError, ValueError):
            return False, "last_water_test is not a valid ISO datetime"

    bounds: dict[str, tuple[float, float]] = {
        "heat_loss_c_per_h": (0.01, 2.0),
        "heat_loss_covered_c_per_h": (0.01, 2.0),
        "heating_rate_c_per_h": (0.1, 20.0),
        "measured_flow_m3h": (0.1, 50.0),
    }
    for field_name, (lo, hi) in bounds.items():
        value = learned.get(field_name)
        if value is None:
            continue
        if not finite_number(value) or not lo <= value <= hi:
            return False, f"{field_name} of {value!r} is outside the plausible range of {lo} to {hi}"

    return True, "usable"
