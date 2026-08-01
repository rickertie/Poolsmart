"""Tests for the entity id migration (T29 - T33).

The migration touches the entity registry, which is not something to get wrong,
so the rename logic is exercised here against a stand-in registry that behaves
the way Home Assistant's does: ids are unique, and updating one is a rename.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"


@dataclass
class FakeRegistryEntry:
    entity_id: str
    unique_id: str
    domain: str


@dataclass
class FakeRegistry:
    """Stand-in for Home Assistant's entity registry."""

    entries: dict[str, FakeRegistryEntry] = field(default_factory=dict)
    renames: list[tuple[str, str]] = field(default_factory=list)

    def add(self, entity_id: str, unique_id: str) -> None:
        domain = entity_id.split(".", 1)[0]
        self.entries[entity_id] = FakeRegistryEntry(entity_id, unique_id, domain)

    def async_get(self, entity_id: str):
        return self.entries.get(entity_id)

    def async_update_entity(self, entity_id: str, new_entity_id: str) -> None:
        entry = self.entries.pop(entity_id)
        entry.entity_id = new_entity_id
        entry.domain = new_entity_id.split(".", 1)[0]
        self.entries[new_entity_id] = entry
        self.renames.append((entity_id, new_entity_id))


def migrate(registry: FakeRegistry, entry_id: str, title: str) -> list[tuple[str, str]]:
    """The rename logic from __init__.py, kept in step by test T33."""
    prefix = title.lower().replace(" ", "_")
    renamed = []
    for reg_entry in list(registry.entries.values()):
        if not reg_entry.unique_id.startswith(f"{entry_id}_"):
            continue
        key = reg_entry.unique_id[len(entry_id) + 1 :]
        wanted = f"{reg_entry.domain}.{prefix}_{key}"
        if reg_entry.entity_id == wanted:
            continue
        if registry.async_get(wanted) is not None:
            continue
        registry.async_update_entity(reg_entry.entity_id, new_entity_id=wanted)
        renamed.append((reg_entry.entity_id, wanted))
    return renamed


ENTRY = "abc123"


def _dutch_registry() -> FakeRegistry:
    """A registry as it looks after installing on a Dutch system."""
    registry = FakeRegistry()
    for entity_id, key in (
        ("sensor.pool_klaar_om", "ready_at"),
        ("sensor.pool_status", "status"),
        ("sensor.pool_benodigde_opwarmtijd", "heating_time_required"),
        ("binary_sensor.pool_verwarmt", "heating"),
        ("binary_sensor.pool_circuleert", "circulating"),
        ("select.pool_modus", "mode"),
        ("number.pool_doeltemperatuur", "target_temperature"),
        ("button.pool_nu_verwarmen", "boost_now"),
        ("switch.pool_zelflerend", "learning_enabled"),
    ):
        registry.add(entity_id, f"{ENTRY}_{key}")
    return registry


# ---------------------------------------------------------------------------
# T29 - translated ids are renamed to the fixed form
# ---------------------------------------------------------------------------

def test_t29_dutch_ids_are_migrated():
    registry = _dutch_registry()
    renamed = migrate(registry, ENTRY, "Pool")

    assert "sensor.pool_ready_at" in registry.entries
    assert "sensor.pool_klaar_om" not in registry.entries
    assert "binary_sensor.pool_heating" in registry.entries
    assert "select.pool_mode" in registry.entries
    assert "number.pool_target_temperature" in registry.entries

    # sensor.pool_status was already correct and must not be counted as renamed.
    assert not any(old == "sensor.pool_status" for old, _new in renamed)
    assert len(renamed) == 8


# ---------------------------------------------------------------------------
# T30 - the domain is preserved
# ---------------------------------------------------------------------------

def test_t30_domain_is_preserved():
    registry = _dutch_registry()
    migrate(registry, ENTRY, "Pool")
    for entity_id in registry.entries:
        domain = entity_id.split(".", 1)[0]
        assert domain in (
            "sensor",
            "binary_sensor",
            "select",
            "number",
            "button",
            "switch",
        )
    assert registry.entries["binary_sensor.pool_heating"].domain == "binary_sensor"


# ---------------------------------------------------------------------------
# T31 - running it twice changes nothing the second time
# ---------------------------------------------------------------------------

def test_t31_migration_is_idempotent():
    registry = _dutch_registry()
    migrate(registry, ENTRY, "Pool")
    before = set(registry.entries)
    second = migrate(registry, ENTRY, "Pool")
    assert second == []
    assert set(registry.entries) == before


# ---------------------------------------------------------------------------
# T32 - an id already taken by something else is left alone
# ---------------------------------------------------------------------------

def test_t32_occupied_id_is_not_stolen():
    registry = _dutch_registry()
    # Something unrelated already owns the target id.
    registry.add("sensor.pool_ready_at", "some_other_integration")

    migrate(registry, ENTRY, "Pool")

    # The occupied id keeps its original owner, and ours keeps its old name
    # rather than colliding.
    assert registry.entries["sensor.pool_ready_at"].unique_id == "some_other_integration"
    assert "sensor.pool_klaar_om" in registry.entries


# ---------------------------------------------------------------------------
# T33 - the logic here matches the shipped implementation
# ---------------------------------------------------------------------------

def test_t33_matches_shipped_implementation():
    """Guard against this test drifting away from the real code.

    The stand-in above is a transcription, so it is only worth anything if the
    shipped version still does the same three things.
    """
    source = (ROOT / "__init__.py").read_text()

    assert 'removeprefix(f"{entry.entry_id}_")' in source, "unique_id prefix stripped"
    assert 'wanted = f"{reg_entry.domain}.{prefix}_{key}"' in source, "target id built"
    assert "if reg_entry.entity_id == wanted:" in source, "already-correct check"
    assert "if registry.async_get(wanted) is not None:" in source, "collision check"
    assert "MIGRATION_FLAG" in source, "runs once per entry"

    # Every entity key the platforms create must be a valid id fragment.
    keys: set[str] = set()
    for name in (
        "sensor.py",
        "binary_sensor.py",
        "select.py",
        "number.py",
        "switch.py",
        "button.py",
    ):
        text = (ROOT / name).read_text()
        keys |= set(re.findall(r'key="([a-z_0-9]+)"', text))
        keys |= set(
            re.findall(r'super\(\).__init__\(coordinator, "([a-z_0-9]+)"\)', text)
        )
    assert keys, "no entity keys found"
    for key in keys:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", key), f"unusable entity key: {key}"
