"""Tests for the eight points collected before this build: T70 - T82."""

from __future__ import annotations

import ast
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

from core import chemistry as chem  # noqa: E402
from core import learning  # noqa: E402
from core.config import UnitSystem, display_amount, to_gallons  # noqa: E402
from core.models import Branch  # noqa: E402
from core.trace import NearMissLog, Trace, Verdict  # noqa: E402

from test_acceptance import TZ, make_config  # noqa: E402


# ---------------------------------------------------------------------------
# T70 - imperial units, for pools measured in gallons
# ---------------------------------------------------------------------------

def test_t70_imperial_presentation():
    """Calculation stays metric; only presentation changes.

    Doing it the other way round would mean two sets of formulas and two sets of
    rounding errors to keep in step.
    """
    assert abs(to_gallons(3834) - 1013) < 1

    assert display_amount(18, "ml", UnitSystem.METRIC) == (18.0, "ml")
    amount, unit = display_amount(18, "ml", UnitSystem.IMPERIAL)
    assert unit == "fl oz" and abs(amount - 0.61) < 0.01

    amount, unit = display_amount(250, "g", UnitSystem.IMPERIAL)
    assert unit == "oz" and abs(amount - 8.82) < 0.01


def test_t70b_dosing_is_unchanged_by_the_unit_setting():
    """A pool is the same size whichever units it is described in."""
    metric = chem.dose_for_ph(7.82, 3834)
    imperial_pool = chem.dose_for_ph(7.82, 3834)  # same pool, same litres
    assert metric.amount == imperial_pool.amount


# ---------------------------------------------------------------------------
# T71 - circulation time follows the product
# ---------------------------------------------------------------------------

def test_t71_circulation_per_product():
    """One fixed duration was always going to be wrong.

    Non-chlorine shock is done in half an hour; chlorine shock wants a full
    night so it reaches every corner and gets pulled through the filter.
    Stopping early leaves undissolved product bleaching the liner.
    """
    assert chem.circulation_for(chem.Product.SHOCK_NON_CHLORINE)[0] == 30
    assert chem.circulation_for(chem.Product.ACID_15)[0] == 60
    assert chem.circulation_for(chem.Product.CHLORINE_GRANULES_70)[0] == 240
    assert chem.circulation_for(chem.Product.SHOCK)[0] == 600
    assert chem.circulation_for(chem.Product.ALGAECIDE)[0] == 1440

    # A tablet dissolves over days in a floater; there is nothing to circulate.
    minutes, why = chem.circulation_for(chem.Product.TABLET)
    assert minutes == 0
    assert "dissolves over days" in why

    # An unknown product gets a cautious default rather than an exception.
    assert chem.circulation_for("something_else")[0] == 60


def test_t71b_chemistry_outranks_a_met_filtration_quota():
    """Dosing in the evening must still get its circulation.

    Chemistry sits above the filtration branches in the ladder precisely so a
    day whose quota is already met cannot suppress it.
    """
    from core.models import MODE_BRANCHES, Mode

    assert int(Branch.CHEMISTRY) < int(Branch.FILTRATION_DEADLINE)
    assert int(Branch.CHEMISTRY) < int(Branch.FILTRATION_BLOCK)
    for mode in (Mode.AUTO, Mode.ECO, Mode.BOOST, Mode.STANDBY, Mode.PUMP):
        assert Branch.CHEMISTRY in MODE_BRANCHES[mode], mode


# ---------------------------------------------------------------------------
# T72 - near misses counted across the day
# ---------------------------------------------------------------------------

def test_t72_near_miss_tally():
    """One tick answers "why not now"; this answers "why not today"."""
    log = NearMissLog()
    log.roll_day("2026-08-05")

    trace = Trace()
    trace.record(Branch.HEATING, Verdict.PRICE, "price too high")
    trace.record(Branch.FREE_POWER, Verdict.ENVELOPE, "too cold")

    for _ in range(20):
        log.record(trace, 30)

    rows = log.as_list()
    heating = next(r for r in rows if r["branch"] == "HEATING")
    assert heating["count"] == 20
    assert heating["seconds"] == 600
    # Sorted by time lost, because that is what matters.
    assert rows[0]["seconds"] >= rows[-1]["seconds"]


def test_t72b_tallies_reset_on_a_new_day():
    log = NearMissLog()
    log.roll_day("2026-08-05")
    trace = Trace()
    trace.record(Branch.HEATING, Verdict.PRICE, "expensive")
    log.record(trace, 30)
    assert log.as_list()

    assert log.roll_day("2026-08-06") is True
    assert log.as_list() == []
    assert log.roll_day("2026-08-06") is False


def test_t72c_tallies_survive_a_restart():
    log = NearMissLog()
    log.roll_day("2026-08-05")
    trace = Trace()
    trace.record(Branch.HEATING, Verdict.PRICE, "expensive")
    log.record(trace, 45)

    restored = NearMissLog.from_dict(log.as_dict())
    assert restored.day == "2026-08-05"
    assert restored.as_list() == log.as_list()


# ---------------------------------------------------------------------------
# T73 - the physical ceiling on a learned heating rate
# ---------------------------------------------------------------------------

def test_t73_impossible_heating_rate_is_rejected():
    """A learned 1.02 °C/h on a pool whose maximum is 0.67.

    Nothing checked the rise against what the appliance can physically deliver,
    so a session where the pump stirred stratified water read as spectacular
    heating. Because the learned rate is trusted ahead of any COP calculation,
    that one session drove every later estimate: two hours predicted for a rise
    that really takes fourteen.
    """
    config = make_config()

    # At night, only the appliance is heating.
    ceiling = learning.max_plausible_rate(config, 26.0, daytime=False)
    assert 0.6 < ceiling < 1.0, ceiling

    start = datetime(2026, 8, 5, 22, 0, tzinfo=TZ)
    impossible = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=2),
        water_start=26.0,
        water_end=28.05,  # 1.02 °C/h, at night
        energy_kwh=1.2,
    )
    impossible.sample_air(26.0)
    verdict = learning.assess_measurements(impossible, config)
    assert verdict.heating_rate is False
    assert "full sun" in verdict.reasons["heating_rate"]

    plausible = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=4),
        water_start=26.0,
        water_end=26.6,  # 0.15 °C/h, what this pool really does
        energy_kwh=2.3,
        thermal_kwh=8.0,
    )
    plausible.sample_air(26.0)
    assert learning.assess_measurements(plausible, config).heating_rate is True


def test_t73b_sunshine_raises_the_ceiling():
    """Two real sessions were rejected as impossible. They were not.

    Six square metres of water under an August sun takes in two to three
    kilowatts — comparable to the heat pump itself. A ten hour session starting
    at nine in the morning legitimately outruns the appliance rating, because
    for most of those hours the sky was heating the pool too. The first version
    of this ceiling ignored that and threw away the best sessions of the year.
    """
    config = make_config()

    night = learning.max_plausible_rate(config, 26.0, daytime=False)
    day = learning.max_plausible_rate(config, 26.0)
    assert day > night * 1.8, (night, day)

    # The two sessions this was found on, measured on a real pool.
    for hours, gain in ((3.16, 3.13), (10.23, 8.88)):
        rate = gain / hours
        assert rate > night, "these were rejected before, correctly under the old rule"
        assert rate < day, f"{rate:.2f} C/h should be plausible in daylight"


def test_t73c_a_measured_sun_beats_an_assumed_one():
    config = make_config()
    dull = learning.max_plausible_rate(config, 26.0, irradiance_w_m2=100)
    bright = learning.max_plausible_rate(config, 26.0, irradiance_w_m2=900)
    assert bright > dull
    # An overcast day is barely above the appliance's own ceiling.
    assert dull < learning.max_plausible_rate(config, 26.0, daytime=False) * 1.3


def test_t73d_a_partly_spoiled_session_still_teaches_something():
    """Seven sessions out of seven were discarded on a real installation.

    Several held perfectly good evidence of how fast the pool warms up, ruined
    by a probe on the heat pump going quiet — which spoils the efficiency figure
    and says nothing whatever about the temperature rise.
    """
    config = make_config()
    start = datetime(2026, 8, 8, 9, 0, tzinfo=TZ)
    record = learning.SessionRecord(
        start=start,
        end=start + timedelta(hours=4),
        water_start=26.0,
        water_end=26.8,
        energy_kwh=2.3,
        thermal_kwh=8.0,
        faults=["stale_hp_outlet"],
    )
    record.sample_air(26.0)
    record.spans_daylight = True

    verdict = learning.assess_measurements(record, config)
    assert verdict.heating_rate is True, verdict.reasons
    assert verdict.cop is False
    assert verdict.anything_usable is True
    # And the panel is told what it gained, not only what it lost.
    assert "learned heating rate" in verdict.describe()
    assert "stale_hp_outlet" in verdict.describe()


# ---------------------------------------------------------------------------
# T74 - COP counts recovered for pre-1.1 installations
# ---------------------------------------------------------------------------

def test_t74_cop_counts_are_backfilled():
    """Learned values sitting behind a gate that could never open.

    `cop_by_air_bucket` has existed since 0.9; the counter gating it arrived in
    1.1. Anyone upgrading had values with a count of zero, so the confidence
    gate blocked figures that several sessions had produced.
    """
    curve = {"25-30": 3.362, "30-35": 3.916}
    sessions = [
        {"usable": True, "measured_cop": 3.3, "air_avg": 26.0},
        {"usable": True, "measured_cop": 3.4, "air_avg": 27.0},
        {"usable": True, "measured_cop": 3.5, "air_avg": 28.0},
        {"usable": True, "measured_cop": 3.6, "air_avg": 26.5},
        {"usable": True, "measured_cop": 3.7, "air_avg": 27.5},
        {"usable": False, "measured_cop": None, "air_avg": 26.0},
    ]

    counts = learning.recover_cop_counts(curve, sessions)
    assert counts["25-30"] == 5
    # A bucket with no surviving sessions gets one: enough to show the value
    # exists, not enough to trust it for planning.
    assert counts["30-35"] == 1

    # The gate opens for the bucket that earned it.
    assert learning.cop_for(curve, counts, 26.0) == 3.362

    # 30-35 has only one session of its own, so its own value is not trusted --
    # but the neighbouring band is, and an adjacent air temperature is a far
    # better guess than a datasheet written for a different installation.
    assert learning.cop_for(curve, counts, 32.0) == 3.362
    assert learning.cop_for(curve, counts, 32.0, neighbours=False) is None


def test_t74c_backfill_reads_the_right_object():
    """Regression: the backfill reached for `self.cop_by_air_bucket`.

    Those values live on the store's `learned` object, not on the store itself,
    so setup crashed with an AttributeError the moment anyone restarted. The
    original test for this built a stand-in with the fields hung directly off it
    — encoding the same wrong mental model that produced the bug, and passing
    for exactly that reason. Reading the real source is the only check that
    would have caught it.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "store.py"
    ).read_text()

    tree = ast.parse(source)
    learned_fields: set[str] = set()
    store_fields: set[str] = set()
    store_class = None

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "LearnedValues":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    learned_fields.add(item.target.id)
        if isinstance(node, ast.ClassDef) and node.name == "PoolStore":
            store_class = node
            for item in ast.walk(node):
                if (
                    isinstance(item, ast.Assign)
                    and isinstance(item.targets[0], ast.Attribute)
                    and isinstance(item.targets[0].value, ast.Name)
                    and item.targets[0].value.id == "self"
                ):
                    store_fields.add(item.targets[0].attr)

    assert store_class is not None
    misplaced = {
        (item.lineno, item.attr)
        for item in ast.walk(store_class)
        if isinstance(item, ast.Attribute)
        and isinstance(item.value, ast.Name)
        and item.value.id == "self"
        and item.attr in learned_fields
        and item.attr not in store_fields
    }
    assert not misplaced, (
        "PoolStore reaching for LearnedValues fields on self: "
        f"{sorted(misplaced)}"
    )


def test_t74b_backfill_ignores_unusable_sessions():
    """A rejected session did not produce a trustworthy COP either."""
    curve = {"25-30": 3.4}
    rejected = [
        {"usable": False, "measured_cop": 3.4, "air_avg": 26.0},
        {"usable": True, "measured_cop": None, "air_avg": 26.0},
        {"usable": True, "measured_cop": 3.4, "air_avg": None},
    ]
    counts = learning.recover_cop_counts(curve, rejected)
    assert counts == {"25-30": 1}, counts


# ---------------------------------------------------------------------------
# T75 - one learned value can be cleared without losing the rest
# ---------------------------------------------------------------------------

def test_t75_reset_one_value():
    """Heat loss takes days of idle periods to establish.

    Losing it because the heating rate went wrong would be a poor trade, so each
    value clears on its own.
    """
    assert set(learning.RESETTABLE) == {
        "heating_rate",
        "heat_loss",
        "heat_loss_covered",
        "measured_flow",
        "cop",
        "ph_correction",
        "chlorine_correction",
    }

    # Each entry names a value and, where one exists, its session counter --
    # clearing a value while leaving its count behind would leave the confidence
    # gate believing in evidence that is no longer there.
    for name, (value_attr, count_attr) in learning.RESETTABLE.items():
        assert value_attr, name
        if name != "measured_flow":
            assert count_attr, f"{name} has a count that must be cleared with it"

    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "store.py"
    ).read_text()
    assert "RESETTABLE" in source
    assert "def reset_learned" in source


# ---------------------------------------------------------------------------
# T76 - every AquaChek reading is judged
# ---------------------------------------------------------------------------

def test_t76_all_strip_readings_have_bands():
    """An AquaChek 7-in-1 measures seven things. All of them are worth judging."""
    for key in (
        "ph",
        "free_chlorine",
        "total_chlorine",
        "bromine",
        "alkalinity",
        "cyanuric",
        "hardness",
        "salt",
    ):
        assert key in chem.READINGS, key

    assert chem.judge("alkalinity", 100).verdict == "ok"
    assert chem.judge("alkalinity", 60).verdict == "low"
    assert chem.judge("cyanuric", 120).verdict == "very_high"
    assert chem.judge("hardness", 300).verdict == "ok"
    assert chem.judge("ph", None) is None


def test_t76b_two_levels_of_wrong():
    """A pH of 7.7 wants attention this week; 8.6 wants attention now.

    Collapsing those into one warning means the urgent one arrives looking like
    the routine one.
    """
    mild = chem.judge("ph", 7.7)
    severe = chem.judge("ph", 8.6)
    assert mild.verdict == "high" and mild.urgent is False
    assert severe.verdict == "very_high" and severe.urgent is True


# ---------------------------------------------------------------------------
# T77 - combined chlorine, the figure a strip hides
# ---------------------------------------------------------------------------

def test_t77_combined_chlorine():
    """Total minus free is the one number that answers "should I shock"."""
    assert chem.combined_chlorine(0.8, 1.6) == 0.8
    assert chem.combined_chlorine(2.0, 2.0) == 0.0
    assert chem.combined_chlorine(None, 1.6) is None
    # Never negative, however the strip was read.
    assert chem.combined_chlorine(2.0, 1.5) == 0.0

    advice = chem.water_advice({"free_chlorine": 0.8, "total_chlorine": 1.6})
    assert any("shocking will do more" in line for line in advice)


# ---------------------------------------------------------------------------
# T78 - conclusions that need more than one reading
# ---------------------------------------------------------------------------

def test_t78_cross_reading_advice():
    """Each band judges its own number; these need them read together."""
    locked = chem.water_advice({"cyanuric": 120, "free_chlorine": 1.5})
    assert any("holds chlorine hostage" in line for line in locked)

    both_off = chem.water_advice({"ph": 7.9, "alkalinity": 60})
    assert any("Correct alkalinity first" in line for line in both_off)

    high_ph = chem.water_advice({"ph": 7.9, "free_chlorine": 2.0})
    assert any("fraction of its strength" in line for line in high_ph)

    # A balanced pool gets no advice, rather than reassurance it did not ask for.
    fine = chem.water_advice(
        {"ph": 7.4, "free_chlorine": 2.0, "total_chlorine": 2.1, "alkalinity": 100}
    )
    assert fine == []


def test_t78b_stabiliser_raises_the_chlorine_target():
    """At 80 ppm of stabiliser, 1.5 mg/L of chlorine is not enough."""
    advice = chem.water_advice({"cyanuric": 80, "free_chlorine": 1.5})
    assert any("nearer" in line for line in advice)


# ---------------------------------------------------------------------------
# T79 - readings follow the sanitiser
# ---------------------------------------------------------------------------

def test_t79_relevant_readings_per_sanitiser():
    """Showing a bromine field to a chlorine pool is not neutral.

    It is a field someone wonders about, leaves blank, and then sees reported
    as missing.
    """
    chlorine = chem.RELEVANT_READINGS[chem.Sanitiser.CHLORINE]
    bromine = chem.RELEVANT_READINGS[chem.Sanitiser.BROMINE]
    salt = chem.RELEVANT_READINGS[chem.Sanitiser.SALT]

    assert "free_chlorine" in chlorine and "bromine" not in chlorine
    assert "bromine" in bromine and "free_chlorine" not in bromine
    assert "salt" in salt and "salt" not in chlorine
    # pH matters whatever keeps the water clean.
    for group in (chlorine, bromine, salt):
        assert "ph" in group


# ---------------------------------------------------------------------------
# T80 - everything is wired into the integration, not just the core
# ---------------------------------------------------------------------------

def test_t80_readings_reach_the_config_flow():
    root = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"
    const_source = (root / "const.py").read_text()
    flow_source = (root / "config_flow.py").read_text()

    for key in (
        "CONF_TOTAL_CHLORINE_SENSOR",
        "CONF_BROMINE_SENSOR",
        "CONF_ALKALINITY_SENSOR",
        "CONF_CYANURIC_SENSOR",
        "CONF_HARDNESS_SENSOR",
        "CONF_SALT_SENSOR",
        "CONF_SANITISER",
        "CONF_UNIT_SYSTEM",
    ):
        assert key in const_source, key
        assert key in flow_source, f"{key} not offered in the config flow"

    # Every reading in the core has a config key behind it.
    assert "CHEMISTRY_SENSORS" in const_source
    for key in chem.READINGS:
        assert f'"{key}":' in const_source, f"{key} has no config key"


def test_t80b_services_exist_for_both_actions():
    import yaml

    root = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"
    services = yaml.safe_load((root / "services.yaml").read_text())
    assert "record_dose" in services
    assert "reset_learned" in services

    init_source = (root / "__init__.py").read_text()
    assert 'async_register(DOMAIN, "reset_learned"' in init_source


# ---------------------------------------------------------------------------
# T81 - the panel shows what the mockups promised
# ---------------------------------------------------------------------------

def test_t81_panel_covers_the_agreed_features():
    panel = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "www"
        / "poolsmart-panel.js"
    ).read_text()

    for feature, marker in (
        ("near misses", "nearMisses"),
        ("previous sessions", "_previousSessions"),
        ("water bands", "combinedChlorine"),
        ("cross-reading advice", "whatItMeans"),
        ("per-value reset", "reset_learned"),
        ("circulation time on a dose", "circulation_reason"),
        ("dense readouts from direction A", "class=\"dense\""),
        ("hero block from direction B", "class=\"hero\""),
    ):
        assert marker in panel, f"missing: {feature}"


def test_t81b_panel_strings_stay_in_step():
    panel = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "www"
        / "poolsmart-panel.js"
    ).read_text()

    english = re.search(r"\ben:\s*\{(.*?)\n  \},", panel, re.S).group(1)
    dutch = re.search(r"\bnl:\s*\{(.*?)\n  \},", panel, re.S).group(1)
    en_keys = set(re.findall(r"(\w+):", english))
    nl_keys = set(re.findall(r"(\w+):", dutch))
    assert en_keys == nl_keys, f"out of step: {en_keys ^ nl_keys}"

    # Every t("key") used must exist.
    used = set(re.findall(r'this\.t\("(\w+)"', panel))
    assert used <= en_keys, f"used but not defined: {sorted(used - en_keys)}"


# ---------------------------------------------------------------------------
# T82 - Pool Chem is no longer recommended
# ---------------------------------------------------------------------------

def test_t82_poolchem_recommendation_removed():
    """It turned out not to do what was wanted, so recommending it was wrong.

    The boundary still needs stating -- this is not a full water chemistry
    integration -- but pointing people at a specific alternative that did not
    suit is worse than describing the limit plainly.
    """
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text()
    assert "ha-poolchem" not in readme
    assert "poolchem" not in readme.lower()


# ---------------------------------------------------------------------------
# T83 - modules without Home Assistant imports must actually import
# ---------------------------------------------------------------------------

def test_t83_pure_modules_import_cleanly():
    """Regression: const.py used a name defined seventy lines below it.

    `ast.parse` only checks that a file is grammatical, not that its names
    resolve, so every syntax check passed while Home Assistant refused to load
    the integration at all. Importing the file is the check that would have
    caught it, and it costs nothing for the modules that carry no Home Assistant
    dependency.
    """
    import importlib

    root = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    for name in (
        "const",
        "core.config",
        "core.models",
        "core.chemistry",
        "core.learning",
        "core.heating",
        "core.optimizer",
        "core.filtration",
        "core.safety",
        "core.ladder",
        "core.trace",
    ):
        module = importlib.import_module(name)
        assert module is not None, name


def test_t83b_forward_references_in_const():
    """Every name const.py uses must be defined before the line that uses it.

    Python executes a module top to bottom; a tuple built from names declared
    later fails at import, which is a startup failure rather than a warning.
    """
    root = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"
    source = (root / "const.py").read_text()

    defined_at: dict[str, int] = {}
    for number, line in enumerate(source.splitlines()):
        match = re.match(r"^([A-Z][A-Z0-9_]*)\s*=", line)
        if match:
            defined_at.setdefault(match.group(1), number)

    for number, line in enumerate(source.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or re.match(r"^[A-Z][A-Z0-9_]*\s*=", stripped):
            continue
        for name in re.findall(r"\b(CONF_[A-Z0-9_]+)\b", stripped):
            assert name in defined_at, f"line {number + 1}: {name} never defined"
            assert defined_at[name] < number, (
                f"line {number + 1} uses {name}, defined later at line "
                f"{defined_at[name] + 1}"
            )


# ---------------------------------------------------------------------------
# T84 - the storage layer is executed, not merely parsed
# ---------------------------------------------------------------------------

def test_t84_store_methods_run_against_the_real_class():
    """Regression, twice over.

    A method that called one that was never written, and a method that read
    fields off the wrong object. Both parsed cleanly, both broke setup on the
    first restart, and neither could be caught by a test suite that only ever
    executed the decision core. Running the real class with stub Home Assistant
    modules closes that gap without pretending to simulate Home Assistant.
    """
    import ha_stubs

    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    store.learned = store_module.LearnedValues(
        cop_by_air_bucket={"25-30": 3.362, "30-35": 3.916},
        cop_sessions_by_bucket={},
    )
    store.session_log = [
        {"usable": True, "measured_cop": 3.3, "air_avg": 26.0},
        {"usable": True, "measured_cop": 3.4, "air_avg": 27.0},
        {"usable": True, "measured_cop": 3.5, "air_avg": 28.0},
    ]

    assert store.backfill_cop_counts() is True
    assert store.learned.cop_sessions_by_bucket == {"25-30": 3, "30-35": 1}

    # Running it twice must not double the counts.
    assert store.backfill_cop_counts() is False
    assert store.learned.cop_sessions_by_bucket == {"25-30": 3, "30-35": 1}


def test_t84b_reset_runs_against_the_real_class():
    import ha_stubs

    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    store.learned = store_module.LearnedValues(
        heating_rate_c_per_h=1.02,
        heating_rate_sessions=3,
        heat_loss_c_per_h=0.23,
        measured_flow_m3h=1.07,
        cop_by_air_bucket={"25-30": 3.4},
        cop_sessions_by_bucket={"25-30": 4},
    )

    assert store.reset_learned("heating_rate") is True
    assert store.learned.heating_rate_c_per_h is None
    assert store.learned.heating_rate_sessions == 0
    # Heat loss takes days of idle periods to establish; it must survive.
    assert store.learned.heat_loss_c_per_h == 0.23
    assert store.learned.measured_flow_m3h == 1.07

    assert store.reset_learned("cop") is True
    assert store.learned.cop_by_air_bucket == {}
    assert store.learned.cop_sessions_by_bucket == {}

    assert store.reset_learned("nonsense") is False


def test_t84c_learned_values_round_trip():
    """What is written must come back, or a restart quietly loses the learning."""
    import ha_stubs

    store_module = ha_stubs.load_store()
    original = store_module.LearnedValues(
        heating_rate_c_per_h=0.15,
        heat_loss_c_per_h=0.23,
        heat_loss_covered_c_per_h=0.11,
        heat_loss_samples=14,
        heat_loss_covered_samples=3,
        measured_flow_m3h=1.07,
        cop_by_air_bucket={"25-30": 3.36},
        cop_sessions_by_bucket={"25-30": 5},
        heating_rate_sessions=4,
        session_count=7,
    )
    restored = store_module.LearnedValues.from_dict(original.as_dict())

    for field in (
        "heating_rate_c_per_h",
        "heat_loss_c_per_h",
        "heat_loss_covered_c_per_h",
        "heat_loss_samples",
        "heat_loss_covered_samples",
        "measured_flow_m3h",
        "cop_by_air_bucket",
        "cop_sessions_by_bucket",
        "heating_rate_sessions",
        "session_count",
    ):
        assert getattr(restored, field) == getattr(original, field), field


# ---------------------------------------------------------------------------
# T85 - a tablet is not a dose you can measure out
# ---------------------------------------------------------------------------

def test_t85_tablets_are_counted_not_weighed():
    """"Add 11 g of chlorine tablet" is not an instruction anyone can follow.

    Tablets come in fixed sizes, cannot usefully be halved, and take days to
    dissolve — which makes them the wrong product for a reading that is low
    right now. Rounding a slow-release product into a same-day correction hides
    both problems.
    """
    dose = chem.dose_for_chlorine(0.6, 3834, chem.Product.TABLET, tablet_grams=20)
    assert dose.amount == 1
    assert dose.unit == "tablet"
    assert "20 g" in dose.reason
    assert "dissolve over days" in dose.instructions
    assert "granules or liquid" in dose.instructions

    # Never a fraction of a tablet, whatever the arithmetic says.
    for size in chem.TABLET_SIZES:
        d = chem.dose_for_chlorine(0.6, 3834, chem.Product.TABLET, tablet_grams=size)
        assert d.amount == int(d.amount) and d.amount >= 1, size

    # A large tablet in a small pool is flagged as the overshoot it is.
    big = chem.dose_for_chlorine(0.6, 3834, chem.Product.TABLET, tablet_grams=200)
    assert "×" in big.reason

    # Granules still get a weight, because that is how they are sold.
    granules = chem.dose_for_chlorine(0.6, 3834, chem.Product.CHLORINE_GRANULES_70)
    assert granules.unit == "g"
    assert 5 < granules.amount < 15


# ---------------------------------------------------------------------------
# T86 - slow sensors get proportionate patience
# ---------------------------------------------------------------------------

def test_t86_slow_roles_are_not_nagged_about():
    """"The outdoor temperature has not been reported for 15 minutes."

    True, and unactionable: outdoor air overnight legitimately holds the same
    value to two decimals for far longer than that. Alerts nobody can act on are
    how people learn to ignore the ones that matter.
    """
    from core.config import SafetySettings

    settings = SafetySettings()
    assert "air" in settings.slow_roles
    assert "water" in settings.slow_roles
    # The probes either side of the heat pump are slow too. They are also
    # conditional -- only judged while the appliance runs -- but that alone was
    # not enough: a stable session holds delta-T constant, so they stop
    # publishing precisely when the session is going well.
    assert "hp_inlet" in settings.slow_roles
    assert "hp_outlet" in settings.slow_roles
    assert settings.slow_role_factor > 1

    effective = settings.stale_warning_seconds * settings.slow_role_factor
    assert effective >= 3600, "an hour is the least that makes sense for outdoor air"
