"""Tests for the settings rework: T87 - T96.

Three things went in together: a settings menu organised by subject, a setup
wizard whose questions follow the heating source, and learned history surviving
a reinstall.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

from core import safety  # noqa: E402
from core.config import (  # noqa: E402
    INITIAL_HEAT_LOSS,
    SOURCE_TRAITS,
    HeatingSource,
    PoolKind,
)
from core.models import SensorReading  # noqa: E402

from test_acceptance import TZ, make_config, make_state  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"


# ---------------------------------------------------------------------------
# T87 - a heating source is not a label
# ---------------------------------------------------------------------------

def test_t87_sources_differ_in_what_they_have():
    """Everything the ladder does with a source comes from one table.

    An immersion element is exactly as efficient at every temperature, works in
    any weather, and can be switched freely. Those are not simplifications of a
    heat pump's behaviour — they are the absence of things a heat pump has.
    """
    heat_pump = SOURCE_TRAITS[HeatingSource.HEAT_PUMP]
    electric = SOURCE_TRAITS[HeatingSource.ELECTRIC]
    solar = SOURCE_TRAITS[HeatingSource.SOLAR]

    assert heat_pump["efficiency_varies"] and not electric["efficiency_varies"]
    assert heat_pump["air_temp_limits"] and not electric["air_temp_limits"]
    assert heat_pump["compressor"] and not electric["compressor"]

    # A manual three-way valve cannot be switched by software, and saying
    # otherwise would fill the decision log with instructions nobody carried out.
    assert solar["controllable"] is False
    assert solar["free"] is True

    # Every source is described, or a lookup fails at runtime rather than here.
    for source in HeatingSource:
        assert source in SOURCE_TRAITS, source


def test_t87b_electric_heaters_have_no_operating_envelope():
    """Refusing to heat because the outdoor probe is missing would be inventing
    a restriction the hardware does not have."""
    config = make_config(heating_source="electric")
    now = datetime(2026, 12, 1, 3, 0, tzinfo=TZ)
    freezing = make_state(
        now,
        water_temp=SensorReading(15.0, 10, "water"),
        air_temp=SensorReading(-5.0, 10, "air"),
    )
    available, reason = safety.heat_pump_available(freezing, config, [])
    assert available is True, reason

    # The same weather stops a heat pump, which does have limits.
    heat_pump = make_config(heating_source="heat_pump")
    available, reason = safety.heat_pump_available(freezing, heat_pump, [])
    assert available is False
    assert "below" in reason.lower()


def test_t87c_no_outdoor_probe_does_not_block_an_element():
    config = make_config(heating_source="electric")
    now = datetime(2026, 8, 1, 12, 0, tzinfo=TZ)
    state = make_state(now, air_temp=SensorReading(None, None, "air"))
    available, _reason = safety.heat_pump_available(state, config, [])
    assert available is True


def test_t87d_a_manual_source_is_advisory_only():
    config = make_config(heating_source="solar")
    now = datetime(2026, 8, 1, 12, 0, tzinfo=TZ)
    state = make_state(now)
    available, reason = safety.heat_pump_available(state, config, [])
    assert available is False
    assert "by hand" in reason


# ---------------------------------------------------------------------------
# T88 - compressor protection applies where there is a compressor
# ---------------------------------------------------------------------------

def test_t88_no_compressor_no_guard():
    """Holding an immersion element off for ten minutes protects nothing."""
    source = (ROOT / "core" / "ladder.py").read_text()
    guard = source[source.index("def _compressor_guard") :]
    guard = guard[: guard.index("\ndef ")]
    assert 'source_has("compressor")' in guard
    # And the check happens before either timing test, not after.
    assert guard.index('source_has("compressor")') < guard.index("min_off")


# ---------------------------------------------------------------------------
# T89 - pool construction sets a believable starting point
# ---------------------------------------------------------------------------

def test_t89_starting_heat_loss_follows_construction():
    """An uninsulated inflatable loses heat several times faster than a
    built-in pool. Starting everyone at the same figure starts most people at
    the wrong one — during exactly the days they are deciding whether this
    works.
    """
    for kind in PoolKind:
        assert kind in INITIAL_HEAT_LOSS, kind

    assert INITIAL_HEAT_LOSS[PoolKind.INFLATABLE] > INITIAL_HEAT_LOSS[PoolKind.FRAME]
    assert INITIAL_HEAT_LOSS[PoolKind.FRAME] > INITIAL_HEAT_LOSS[PoolKind.ABOVE_GROUND]
    assert (
        INITIAL_HEAT_LOSS[PoolKind.ABOVE_GROUND] > INITIAL_HEAT_LOSS[PoolKind.IN_GROUND]
    )
    # Roughly a factor of four across the range, which matches how differently
    # these actually behave.
    assert INITIAL_HEAT_LOSS[PoolKind.INFLATABLE] / INITIAL_HEAT_LOSS[
        PoolKind.IN_GROUND
    ] > 3


# ---------------------------------------------------------------------------
# T90 - the solar collector advises rather than switches
# ---------------------------------------------------------------------------

def test_t90_collector_advice():
    """Water pushed through a cold collector loses heat rather than gaining it,
    which is worth saying as clearly as when to open the valve."""
    config = make_config(has_solar_collector=True, collector_margin=3.0)
    now = datetime(2026, 8, 1, 13, 0, tzinfo=TZ)

    warm = make_state(
        now,
        water_temp=SensorReading(24.0, 10, "water"),
        collector_temp=SensorReading(32.0, 10, "collector"),
    )
    worth_it, why, numbers = safety.solar_collector_advice(warm, config)
    assert worth_it is True
    assert "free heat" in why
    assert numbers["difference"] == 8.0

    cold = warm.replace(collector_temp=SensorReading(21.0, 10, "collector"))
    worth_it, why, _ = safety.solar_collector_advice(cold, config)
    assert worth_it is False
    assert "lose heat" in why

    marginal = warm.replace(collector_temp=SensorReading(25.5, 10, "collector"))
    worth_it, why, _ = safety.solar_collector_advice(marginal, config)
    assert worth_it is False
    assert "under the" in why


def test_t90b_no_collector_no_advice():
    config = make_config()
    now = datetime(2026, 8, 1, 13, 0, tzinfo=TZ)
    worth_it, why, _ = safety.solar_collector_advice(make_state(now), config)
    assert worth_it is False
    assert why == ""


# ---------------------------------------------------------------------------
# T91 - the settings menu is organised by subject
# ---------------------------------------------------------------------------

def test_t91_menu_has_no_general_bin():
    """Twenty-eight unrelated settings under one heading is not a category.

    It is what was left after categorising everything else, and it made the
    fifteen settings anyone actually changes harder to find.
    """
    source = (ROOT / "config_flow.py").read_text()
    menu = re.search(r"menu_options=\[(.*?)\]", source, re.S).group(1)
    items = set(re.findall(r'"(\w+)"', menu))

    assert "general" not in items, "the general bin is back"
    assert items == {
        "entities",
        "pool",
        "weather_price",
        "heating",
        "when_to_heat",
        "filtration",
        "water",
        "notifications",
        "advanced",
    }, sorted(items)

    for step in items:
        assert f"async def async_step_{step}" in source, f"{step} has no handler"


def test_t91b_saving_returns_to_the_menu():
    """Saving used to close the dialog, so changing three things meant opening
    Configure three times."""
    source = (ROOT / "config_flow.py").read_text()
    options_flow = source[source.index("class PoolSmartOptionsFlow") :]

    assert "def _save" in options_flow
    assert "async_show_menu" in options_flow[options_flow.index("def _save") :]
    # No options step closes the dialog outright any more.
    assert "async_create_entry(data=options)" not in options_flow


def test_t91c_every_menu_item_is_translated():
    for language in ("en", "nl"):
        translations = json.loads(
            (ROOT / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        menu = translations["options"]["step"]["init"]["menu_options"]
        for item in (
            "entities",
            "pool",
            "weather_price",
            "heating",
            "when_to_heat",
            "filtration",
            "water",
            "notifications",
            "advanced",
        ):
            assert item in menu, f"{language}: {item} has no menu label"


# ---------------------------------------------------------------------------
# T92 - the wizard asks only what the source can answer
# ---------------------------------------------------------------------------

def test_t92_setup_branches_on_the_heating_source():
    source = (ROOT / "config_flow.py").read_text()

    # One step decides the shape of the rest, so there is one place to test.
    assert "def _kind_schema" in source
    assert "def _heating_schema" in source
    assert "async def async_step_heating" in source

    heating = source[source.index("def _heating_schema") :]
    heating = heating[: heating.index("\ndef ")]
    assert 'traits["efficiency_varies"]' in heating
    assert 'traits["air_temp_limits"]' in heating
    assert 'source == "none"' in heating
    assert 'source == "solar"' in heating


def test_t92b_a_flat_efficiency_curve_is_still_a_curve():
    """A source whose efficiency does not vary gets a flat curve rather than a
    curve pretending to vary, so every downstream calculation keeps working."""
    source = (ROOT / "config_flow.py").read_text()
    step = source[source.index("async def async_step_heating") :]
    step = step[: step.index("\n    async def ")]
    assert "CONF_HP_COP_REF" in step
    assert "cop_ref" in step


# ---------------------------------------------------------------------------
# T93 - learned history survives a reinstall
# ---------------------------------------------------------------------------

def test_t93_orphan_detection_and_adoption():
    """A reinstall gives a new entry id, and the storage key is built from it.

    Nothing deletes the old file, so weeks of measurement sit on disk under a
    key nothing reads. Rebuilding takes days of idle periods and completed
    sessions — a poor thing to ask of someone who only changed a setting.
    """
    import ha_stubs

    ha_stubs.install()
    ha_stubs.load("const", "const.py")
    ha_stubs.load("core", "core/__init__.py")
    ha_stubs.load("core.learning", "core/learning.py")
    store_module = ha_stubs.load_store()

    store = store_module.PoolStore.__new__(store_module.PoolStore)
    store.learned = store_module.LearnedValues()
    store.session_log, store.dose_log, store.last_water_test = [], [], None
    store.accepted_suggestions = []

    taken = store.adopt(
        {
            "learned": {
                "heat_loss_c_per_h": 0.23,
                "measured_flow_m3h": 1.07,
                "cop_by_air_bucket": {"25-30": 3.36},
                "session_count": 14,
            },
            "session_log": [
                {"usable": True, "measured_cop": 3.3, "air_avg": 26.0},
                {"usable": True, "measured_cop": 3.4, "air_avg": 27.0},
                {"usable": True, "measured_cop": 3.5, "air_avg": 28.0},
            ],
        }
    )

    assert "heat_loss_c_per_h" in taken
    assert store.learned.heat_loss_c_per_h == 0.23
    assert store.learned.measured_flow_m3h == 1.07
    # The evidence comes across too, or the adopted figures are numbers nothing
    # could ever check or improve.
    assert len(store.session_log) == 3
    assert store.learned.cop_sessions_by_bucket["25-30"] == 3


def test_t93b_locally_measured_values_win():
    """A figure measured on this installation beats an imported one."""
    import ha_stubs

    store_module = ha_stubs.load_store()
    store = store_module.PoolStore.__new__(store_module.PoolStore)
    store.learned = store_module.LearnedValues(heat_loss_c_per_h=0.19)
    store.session_log, store.dose_log, store.last_water_test = [], [], None
    store.accepted_suggestions = []

    store.adopt({"learned": {"heat_loss_c_per_h": 0.23, "measured_flow_m3h": 1.07}})
    assert store.learned.heat_loss_c_per_h == 0.19, "local measurement overwritten"
    # But a gap is still filled.
    assert store.learned.measured_flow_m3h == 1.07


def test_t93c_adoption_is_offered_during_setup():
    source = (ROOT / "config_flow.py").read_text()
    assert "async def async_step_adopt" in source
    assert "find_orphans" in source

    init_source = (ROOT / "__init__.py").read_text()
    assert "_async_adopt_history" in init_source
    # Adopted once and then forgotten, or a later restart would overwrite
    # figures the pool has since measured for itself.
    assert "data.pop(MIGRATION_ADOPT" in init_source


# ---------------------------------------------------------------------------
# T94 - an export describes a pool, not a moment
# ---------------------------------------------------------------------------

def test_t94_export_leaves_out_the_transient():
    recovery_source = (ROOT / "recovery.py").read_text()
    payload = recovery_source[recovery_source.index("def export_payload") :]
    payload = payload[: payload.index("\ndef ")]

    for kept in ("learned", "session_log", "dose_log", "last_water_test"):
        assert f'"{kept}"' in payload, kept
    # Today's quota and the current mode belong to a moment, not to a pool.
    for dropped in ("decision_log", "quota_date", "intervals", '"mode"'):
        assert dropped not in payload, f"{dropped} should not travel"


def test_t94b_a_bad_import_is_refused_outright():
    """A half-applied import leaves the model in a state nobody can reason
    about, and refusing is easier to recover from."""
    import ha_stubs

    ha_stubs.install()
    ha_stubs.load("const", "const.py")
    sys.modules.setdefault("poolsmart.core", None)

    recovery_source = (ROOT / "recovery.py").read_text()
    tree = ast.parse(recovery_source)
    functions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "validate_import" in functions
    assert "export_payload" in functions
    assert "find_orphans" in functions
    assert "read_history" in functions

    body = recovery_source[recovery_source.index("def validate_import") :]
    assert 'payload.get("version") != 1' in body
    assert "return False" in body


# ---------------------------------------------------------------------------
# T95 - services exist for the whole lifecycle
# ---------------------------------------------------------------------------

def test_t95_lifecycle_services():
    import yaml

    services = yaml.safe_load((ROOT / "services.yaml").read_text())
    for name in ("record_dose", "reset_learned", "export_learning", "import_learning"):
        assert name in services, name

    init_source = (ROOT / "__init__.py").read_text()
    for name in ("export_learning", "import_learning"):
        assert f'async_register(DOMAIN, "{name}"' in init_source, name


# ---------------------------------------------------------------------------
# T96 - nothing regressed in the config keys
# ---------------------------------------------------------------------------

def test_t96_new_keys_are_defined_before_use():
    """const.py executes top to bottom; a tuple built from names declared later
    fails at import, which is a startup failure rather than a warning."""
    source = (ROOT / "const.py").read_text()

    defined_at: dict[str, int] = {}
    for number, line in enumerate(source.splitlines()):
        match = re.match(r"^([A-Z][A-Z0-9_]*)\s*=", line)
        if match:
            defined_at.setdefault(match.group(1), number)

    for key in (
        "CONF_HEATING_SOURCE",
        "CONF_POOL_KIND",
        "CONF_HAS_SOLAR_COLLECTOR",
        "CONF_COLLECTOR_SENSOR",
        "CONF_COLLECTOR_MARGIN",
        "CONF_ADOPT_FROM",
    ):
        assert key in defined_at, f"{key} never defined"

    for number, line in enumerate(source.splitlines()):
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or re.match(r"^[A-Z][A-Z0-9_]*\s*=", stripped)
        ):
            continue
        for name in re.findall(r"\b(CONF_[A-Z0-9_]+)\b", stripped):
            assert name in defined_at, f"line {number + 1}: {name} never defined"
            assert defined_at[name] < number, (
                f"line {number + 1} uses {name}, defined later"
            )


# ---------------------------------------------------------------------------
# T97 - every step and every field has words
# ---------------------------------------------------------------------------

def _fields_asked(blob: str, step: str) -> set[str]:
    """Which settings a flow step actually puts on screen."""
    import const

    block = re.search(
        rf"async def async_step_{step}\(.*?(?=\n    async def |\Z)", blob, re.S
    )
    if block is None:
        return set()
    keys = re.findall(r"c\.(CONF_[A-Z0-9_]+)", block.group(0))
    return {
        getattr(const, key)
        for key in set(keys)
        if hasattr(const, key) and isinstance(getattr(const, key), str)
    }


def test_t97_every_flow_step_is_translated():
    """A step without a translation renders as an empty screen.

    Reworking the wizard and the menu moved fields between steps and left their
    words behind: two menu items showed nothing at all, and the pool step in
    setup showed raw keys. Nothing caught it, because the tests checked that
    dropdown *options* were translated and never that the steps holding them
    were.
    """
    source = (ROOT / "config_flow.py").read_text()

    config_flow = source[
        source.index("class PoolSmartConfigFlow") : source.index(
            "class PoolSmartOptionsFlow"
        )
    ]
    options_flow = source[source.index("class PoolSmartOptionsFlow") :]

    for language in ("en", "nl"):
        translations = json.loads(
            (ROOT / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        for section, blob in (
            ("config", config_flow),
            ("options", options_flow),
        ):
            steps = set(re.findall(r"async def async_step_(\w+)\(", blob))
            translated = set(translations[section]["step"])
            missing = steps - translated - {"init"}
            assert not missing, f"{language}/{section}: no translation for {sorted(missing)}"


def test_t97b_every_field_on_screen_has_a_label():
    """A field with no label shows its raw key, or nothing at all."""
    source = (ROOT / "config_flow.py").read_text()
    options_flow = source[source.index("class PoolSmartOptionsFlow") :]

    #: Stored under this key rather than shown as a field of its own.
    not_a_field = {"notify_targets"}

    for language in ("en", "nl"):
        translations = json.loads(
            (ROOT / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        for step in re.findall(r"async def async_step_(\w+)\(", options_flow):
            if step == "init":
                continue
            asked = _fields_asked(options_flow, step) - not_a_field
            labelled = set(
                translations["options"]["step"].get(step, {}).get("data", {})
            )
            missing = asked - labelled
            assert not missing, f"{language}/{step}: no label for {sorted(missing)}"


def test_t97c_no_orphan_translations():
    """A translation for a step that no longer exists is dead weight, and hides
    that the live step has none."""
    source = (ROOT / "config_flow.py").read_text()
    config_flow = source[
        source.index("class PoolSmartConfigFlow") : source.index(
            "class PoolSmartOptionsFlow"
        )
    ]
    steps = set(re.findall(r"async def async_step_(\w+)\(", config_flow))

    for language in ("en", "nl"):
        translations = json.loads(
            (ROOT / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        orphans = set(translations["config"]["step"]) - steps
        assert not orphans, f"{language}: translations with no step: {sorted(orphans)}"


def test_t97d_the_user_step_describes_what_it_asks():
    """Fields moved to the pool step; their descriptions did not move with them."""
    source = (ROOT / "config_flow.py").read_text()

    kind = re.search(r"def _kind_schema\(.*?(?=\ndef )", source, re.S).group(0)
    import const

    asked = {"name"}
    for key in set(re.findall(r"c\.(CONF_[A-Z0-9_]+)", kind)):
        if hasattr(const, key) and isinstance(getattr(const, key), str):
            asked.add(getattr(const, key))

    for language in ("en", "nl"):
        translations = json.loads(
            (ROOT / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        described = set(translations["config"]["step"]["user"]["data"])
        assert described == asked, (
            f"{language}: user step describes {sorted(described)} "
            f"but asks {sorted(asked)}"
        )


# ---------------------------------------------------------------------------
# T98 - the pool kind explanation answers the question people have
# ---------------------------------------------------------------------------

def test_t98_pool_kind_is_explained_by_example():
    """"Do I have a frame pool or an above ground one?" is the actual question.

    A list of four words does not answer it; naming a product someone can
    recognise does.
    """
    for language in ("en", "nl"):
        translations = json.loads(
            (ROOT / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        help_text = translations["config"]["step"]["user"]["data_description"][
            "pool_kind"
        ]
        assert "Intex" in help_text, "no recognisable example"
        for kind in ("rame", "pblaas") if language == "nl" else ("rame", "nflat"):
            assert kind in help_text, kind
        assert len(help_text) > 150, "too short to distinguish the four kinds"


# ---------------------------------------------------------------------------
# T99 - the simple page answers three questions and asks nothing
# ---------------------------------------------------------------------------

def test_t99_simple_status_exists_and_stays_simple():
    source = (ROOT / "sensor.py").read_text()

    assert "def _simple_status" in source
    assert "def _price_verdict" in source

    block = source[source.index("def _simple_status") :]
    block = block[: block.index("\ndef ")]
    # The three questions, and nothing that asks the reader to decide anything.
    for answer in ("warm_enough", "water_quality", "price_verdict"):
        assert answer in block, answer
    for setting in ("async_set", "input_number", "dose_for"):
        assert setting not in block, f"the simple page should not offer {setting}"


def test_t99b_price_is_judged_against_the_day():
    """0.24 means nothing to someone who does not follow tariffs.

    Where it sits within today's range does: the same figure is a bargain in
    January and daylight robbery in a sunny week.
    """
    source = (ROOT / "sensor.py").read_text()
    block = source[source.index("def _price_verdict") :]
    block = block[: block.index("\ndef ")]

    assert "today_low" in block and "today_high" in block
    for verdict in ("cheap", "normal", "expensive"):
        assert f'"{verdict}"' in block, verdict
    # Falls back to the cheap-period signal, which knows the shape of the day
    # better than a fixed ceiling does.
    assert "cheap_price_now" in block


def test_t99c_the_simple_dashboard_is_valid_and_read_only():
    import yaml

    path = ROOT.parents[1] / "docs" / "lovelace" / "simple.yaml"
    assert path.exists(), "no simple dashboard shipped"

    dashboard = yaml.safe_load(path.read_text())
    assert dashboard["views"], "no views"

    text = path.read_text()
    # Nothing on this page changes anything.
    for interactive in ("input_number.", "input_boolean.", "call-service", "button."):
        assert interactive not in text, f"the simple page should not include {interactive}"


# ---------------------------------------------------------------------------
# T100 - the stubs must give way to a real Home Assistant
# ---------------------------------------------------------------------------

def test_t100_stubs_defer_to_the_real_package():
    """Two answers to one import is worse than either answer alone.

    The suite passed here and failed on CI for a reason that took a while to
    see: this machine has no Home Assistant, so the stubs were always used, and
    the runner installs the real one, so they collided. The failure surfaced as
    a circular import inside `asyncio` — nowhere near the cause.
    """
    import ha_stubs

    assert hasattr(ha_stubs, "HAVE_REAL_HA")
    if ha_stubs.HAVE_REAL_HA:
        # Nothing stubbed, and the real modules left untouched.
        assert ha_stubs._INSTALLED is False
        import homeassistant

        assert homeassistant.__file__ is not None, "the real package was replaced"
    else:
        assert ha_stubs._INSTALLED is True
        assert "homeassistant" in sys.modules


def test_t100b_stubs_never_overwrite_an_existing_module():
    """An entry already in sys.modules is either the real package or an earlier
    stub, and both are better than a fresh empty one."""
    import ha_stubs

    source = Path(ha_stubs.__file__).read_text()
    module_fn = source[source.index("def _module") :]
    module_fn = module_fn[: module_fn.index("\ndef ")]

    assert "sys.modules.get(name)" in module_fn
    assert "if module is None" in module_fn
    # Never an unconditional assignment over what is already there.
    assert "sys.modules[name] = types.ModuleType" not in module_fn


def test_t100c_the_store_loads_either_way():
    """Whichever path was taken, the storage layer must actually execute."""
    import ha_stubs

    store_module = ha_stubs.load_store()
    assert hasattr(store_module, "PoolStore")
    assert hasattr(store_module, "LearnedValues")

    store = store_module.PoolStore.__new__(store_module.PoolStore)
    store.learned = store_module.LearnedValues(
        cop_by_air_bucket={"25-30": 3.4}, cop_sessions_by_bucket={}
    )
    store.session_log = []
    assert store.backfill_cop_counts() is True
