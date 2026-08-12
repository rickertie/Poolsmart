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
    except (OSError, ValueError):
        return None

    data = raw.get("data") or {}
    learned = data.get("learned") or {}
    return Orphan(
        path=str(path),
        entry_id=path.name.rsplit(".", 1)[-1],
        modified=datetime.fromtimestamp(path.stat().st_mtime),
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
    return (raw.get("data") or {}).get("learned")


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

    data = raw.get("data") or {}
    return {
        key: data[key]
        for key in ("learned", "session_log", "dose_log", "last_water_test")
        if key in data
    }


def export_payload(store) -> dict:
    """What an export contains.

    Deliberately not the whole storage file: today's filtration quota, the
    current mode and the decision log describe a moment rather than a pool, and
    carrying them to another system would be carrying noise.
    """
    return {
        "version": 1,
        "exported": datetime.now().isoformat(),
        "learned": store.learned.as_dict(),
        "session_log": store.session_log,
        "dose_log": store.dose_log,
        "last_water_test": (
            store.last_water_test.isoformat() if store.last_water_test else None
        ),
    }


def validate_import(payload: dict) -> tuple[bool, str]:
    """Whether an imported file is usable.

    Checked rather than trusted: an import that half-applies leaves the model in
    a state nobody can reason about, and refusing outright is easier to recover
    from than a silent partial load.
    """
    if not isinstance(payload, dict):
        return False, "the file does not contain an export"
    if payload.get("version") != 1:
        return False, f"unsupported export version {payload.get('version')!r}"
    learned = payload.get("learned")
    if not isinstance(learned, dict):
        return False, "the export contains no learned values"
    for key in ("session_log", "dose_log"):
        if key in payload and not isinstance(payload[key], list):
            return False, f"{key} is not a list"

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
        if not isinstance(value, (int, float)) or not lo <= value <= hi:
            return False, f"{field_name} of {value!r} is outside the plausible range of {lo} to {hi}"

    buckets = learned.get("cop_by_air_bucket")
    if isinstance(buckets, dict):
        for key, cop in buckets.items():
            if not isinstance(cop, (int, float)) or not 1.0 <= cop <= 10.0:
                return False, f"COP of {cop!r} in bucket {key!r} is outside the plausible range of 1.0 to 10.0"

    return True, "usable"
