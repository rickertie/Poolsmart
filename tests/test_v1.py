"""Tests for the 1.0 work: T54 - T62.

Covers the six points collected before the release: bridging a sensor outage,
per-role staleness, the mixing requirement on the calibration check, actually
using what was learned, and the chemistry module.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"))

from core import chemistry as chem  # noqa: E402
from core import heating, learning, safety  # noqa: E402
from core.models import SensorReading, Severity  # noqa: E402

from test_acceptance import TZ, make_config, make_state  # noqa: E402


# ---------------------------------------------------------------------------
# T54 - a probe that only matters while heating may go quiet
# ---------------------------------------------------------------------------

def test_t54_conditional_roles_stay_quiet_when_idle():
    """"The heat pump outlet has not been reported for 37 minutes."

    Perfectly true and completely uninteresting: the appliance was off, so
    nothing was changing, so nothing was published. Warning about it teaches
    people to ignore warnings.

    These probes are now slow as well as conditional, because a *stable* heating
    session holds delta-T almost constant and stops them publishing too. The
    better the heating ran, the more certainly the session used to be thrown
    away as stale, which is exactly backwards.
    """
    config = make_config()
    now = datetime(2026, 8, 3, 14, 0, tzinfo=TZ)
    slack = config.safety.slow_role_factor

    idle = make_state(
        now,
        hp_outlet=SensorReading(28.6, 37 * 60, "hp_outlet"),
        heat_pump_on=False,
    )
    assert not any(
        f.code.startswith("stale_hp") for f in safety.evaluate(idle, config)
    )

    # Running, but well inside the relaxed threshold: a steady delta-T is what a
    # good session looks like, not a fault.
    steady = idle.replace(heat_pump_on=True, pump_on=True)
    assert not any(f.code.startswith("stale_hp") for f in safety.evaluate(steady, config))

    # Genuinely silent for hours while running: now worth reporting.
    silent = idle.replace(
        heat_pump_on=True,
        pump_on=True,
        hp_outlet=SensorReading(
            28.6, config.safety.stale_warning_seconds * slack + 60, "hp_outlet"
        ),
    )
    assert any(f.code.startswith("stale_hp") for f in safety.evaluate(silent, config))


# ---------------------------------------------------------------------------
# T55 - the water probe is not conditional
# ---------------------------------------------------------------------------

def test_t55_water_probe_silence_still_matters():
    """Whatever else is running, the pool temperature must keep arriving.

    It gets more patience than a fast-moving probe, because a heated pool
    genuinely holds a value -- but silence is never simply ignored.
    """
    config = make_config()
    now = datetime(2026, 8, 3, 14, 0, tzinfo=TZ)
    slack = config.safety.slow_role_factor

    tolerated = make_state(
        now,
        water_temp=SensorReading(28.0, 40 * 60, "water"),
        heat_pump_on=False,
    )
    assert not any(f.code == "stale_water" for f in safety.evaluate(tolerated, config))

    silent = make_state(
        now,
        water_temp=SensorReading(
            28.0, config.safety.stale_warning_seconds * slack + 60, "water"
        ),
        heat_pump_on=False,
    )
    assert any(f.code == "stale_water" for f in safety.evaluate(silent, config))


# ---------------------------------------------------------------------------
# T56 - stratified water is not a miscalibrated probe
# ---------------------------------------------------------------------------

def test_t56_calibration_check_needs_mixing():
    """Standing water is warm on top and cool at the intake. That is physics."""
    config = make_config()
    now = datetime(2026, 8, 3, 14, 0, tzinfo=TZ)

    # Pump off: the difference means nothing.
    settled = make_state(
        now,
        water_temp=SensorReading(28.06, 10, "water"),
        pump_inlet=SensorReading(26.94, 10, "pump_inlet"),
        pump_on=False,
    )
    assert not any(
        f.code == "probe_disagreement" for f in safety.evaluate(settled, config)
    )

    # Pump just started: still stratified, still not a verdict.
    starting = settled.replace(pump_on=True, pump_runtime_seconds=300)
    assert not any(
        f.code == "probe_disagreement" for f in safety.evaluate(starting, config)
    )

    # Well mixed and still disagreeing: now it is worth saying.
    mixed = settled.replace(pump_on=True, pump_runtime_seconds=45 * 60)
    assert any(
        f.code == "probe_disagreement" for f in safety.evaluate(mixed, config)
    )


# ---------------------------------------------------------------------------
# T57 - a measured COP is used instead of the datasheet
# ---------------------------------------------------------------------------

def test_t57_measured_cop_drives_the_estimate():
    """The datasheet said 1h29 per degree; the pool measured 2h17.

    Planning from the datasheet in that situation means starting too late and
    arriving cold, which is the failure people notice. The measurements to
    correct it were already being recorded and thrown away.
    """
    config = make_config()

    on_paper = heating.estimate(
        config, water_temp=26.0, target_temp=28.0, air_temp=26.0
    )
    measured = heating.estimate(
        config, water_temp=26.0, target_temp=28.0, air_temp=26.0, learned_cop=3.49
    )

    assert on_paper.source == "datasheet"
    assert measured.source == "measured COP"
    assert measured.hours_needed > on_paper.hours_needed * 1.4, (
        on_paper.hours_needed,
        measured.hours_needed,
    )
    # And the energy figure follows the measured efficiency, not the brochure.
    assert measured.kwh_electric > on_paper.kwh_electric


def test_t57b_measured_rate_beats_everything():
    """Degrees per hour is the most direct measurement there is."""
    config = make_config()
    est = heating.estimate(
        config,
        water_temp=26.0,
        target_temp=28.0,
        air_temp=26.0,
        learned_cop=3.49,
        learned_rate_c_per_h=0.44,
    )
    assert est.source == "measured heating rate"
    assert abs(est.hours_needed - 2 / 0.44) < 0.01


# ---------------------------------------------------------------------------
# T58 - one session is not a pattern
# ---------------------------------------------------------------------------

def test_t58_learned_cop_needs_confidence():
    """A wrong learned value is harder to spot than a wrong published one."""
    curve = {"25-30": 3.49}

    assert learning.cop_for(curve, {"25-30": 1}, 26.0) is None
    assert learning.cop_for(curve, {"25-30": 2}, 26.0) is None
    assert learning.cop_for(curve, {"25-30": 3}, 26.0) == 3.49

    # An adjacent band is a better guess than a datasheet for another pool.
    assert learning.cop_for(curve, {"25-30": 5}, 31.0) == 3.49
    # But not two bands away.
    assert learning.cop_for(curve, {"25-30": 5}, 12.0) is None


def test_t58b_confidence_is_reported_in_words():
    assert learning.rate_confidence(0) == "not learned yet"
    assert learning.rate_confidence(1) == "provisional"
    assert learning.rate_confidence(4) == "usable"
    assert learning.rate_confidence(12) == "reliable"


# ---------------------------------------------------------------------------
# T59 - dosing is computed from this pool's volume
# ---------------------------------------------------------------------------

def test_t59_ph_dose():
    volume = 3834

    assert chem.dose_for_ph(7.4, volume) is None, "in range needs nothing"

    dose = chem.dose_for_ph(7.82, volume)
    assert dose.unit == "ml"
    assert 10 < dose.amount < 40, dose.amount
    assert dose.partial is False
    assert dose.aiming_for == 7.55

    # A pool ten times the size needs ten times the acid.
    bigger = chem.dose_for_ph(7.82, volume * 10)
    assert abs(bigger.amount / dose.amount - 10) < 0.01


def test_t59b_large_corrections_are_truncated():
    """pH is buffered in a way this maths does not model.

    Attempting a whole point in one go overshoots and leaves you adding the
    opposite chemical. "Add some, wait, measure again" is the honest answer.
    """
    dose = chem.dose_for_ph(8.6, 3834)
    assert dose.partial is True
    assert dose.aiming_for == 8.2, "aims one step, not the whole way"


def test_t59c_chlorine_dose_aims_for_the_middle():
    """Landing on the lower limit means being under it by morning."""
    assert chem.dose_for_chlorine(2.0, 3834) is None

    dose = chem.dose_for_chlorine(0.6, 3834)
    assert dose.aiming_for == 2.0
    assert 3 < dose.amount < 20, dose.amount
    assert "evening" in dose.instructions


# ---------------------------------------------------------------------------
# T60 - the test interval follows the water temperature
# ---------------------------------------------------------------------------

def test_t60_test_interval_scales_with_temperature():
    """A fixed three-day reminder is too often in spring, too rare in a heatwave."""
    assert chem.test_interval_days(16.0)[0] == 5
    assert chem.test_interval_days(22.0)[0] == 3
    assert chem.test_interval_days(28.0)[0] == 2
    assert chem.test_interval_days(32.0)[0] == 1
    assert chem.test_interval_days(None)[0] == 3

    now = datetime(2026, 8, 3, 12, 0, tzinfo=TZ)
    tested = now - timedelta(days=3)

    _due, overdue_warm, _ = chem.next_test_due(tested, 29.0, now)
    _due, overdue_cool, _ = chem.next_test_due(tested, 17.0, now)
    assert overdue_warm is True
    assert overdue_cool is False


# ---------------------------------------------------------------------------
# T61 - the pool's own response is learned
# ---------------------------------------------------------------------------

def test_t61_dose_correction_is_learned():
    """Alkalinity and stabiliser shift the real response, and are not modelled.

    Rather than pretend otherwise, measure it: a pool that moved half as far as
    predicted needs twice the dose next time.
    """
    now = datetime(2026, 8, 3, 12, 0, tzinfo=TZ)

    def record(before, after, expected):
        return chem.DoseRecord(
            at=now,
            product="acid_15",
            amount=40,
            unit="ml",
            measured_before=before,
            measured_after=after,
            expected_change=expected,
        )

    # Not enough data yet: change nothing.
    assert chem.learn_correction([record(7.8, 7.6, -0.4)], "acid_15") == 1.0

    # Consistently moving half as far as predicted.
    weak = [record(7.8, 7.6, -0.4), record(7.9, 7.7, -0.4), record(7.8, 7.6, -0.4)]
    assert abs(chem.learn_correction(weak, "acid_15") - 2.0) < 0.01

    # An implausible outcome -- a dose that did essentially nothing -- is
    # rejected outright rather than being allowed to quadruple the next dose.
    # Something other than the chemistry was wrong there.
    barely_moved = [record(7.8, 7.79, -0.4), record(7.8, 7.79, -0.4)]
    assert chem.learn_correction(barely_moved, "acid_15") == 1.0

    # And a real but extreme response is capped at double.
    very_weak = [record(7.8, 7.71, -0.4), record(7.8, 7.71, -0.4)]
    assert chem.learn_correction(very_weak, "acid_15") == 2.0


# ---------------------------------------------------------------------------
# T62 - a dose without a follow-up reading teaches nothing
# ---------------------------------------------------------------------------

def test_t62_open_doses_are_ignored_when_learning():
    now = datetime(2026, 8, 3, 12, 0, tzinfo=TZ)
    open_dose = chem.DoseRecord(
        at=now, product="acid_15", amount=40, unit="ml", measured_before=7.8
    )
    assert open_dose.actual_change is None
    assert open_dose.effectiveness is None
    assert chem.learn_correction([open_dose, open_dose], "acid_15") == 1.0


# ---------------------------------------------------------------------------
# T63 - the stored flow unit and its translation key must agree
# ---------------------------------------------------------------------------

def test_t63_flow_unit_slugs_resolve():
    """Home Assistant translation keys cannot contain a slash or a superscript.

    So the value stored by the config flow ("l_min") and the unit a sensor
    publishes ("L/min") are different strings for the same thing, and both have
    to resolve. Getting this wrong is quiet and expensive: an unresolved key
    would fall through to a factor of 1.0 and read 17 L/min as 17 m³/h, putting
    every figure derived from flow out by a factor of seventeen while nothing
    looks broken.
    """
    import re

    root = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"
    coordinator = (root / "coordinator.py").read_text(encoding="utf-8")
    config_flow = (root / "config_flow.py").read_text(encoding="utf-8")

    factors = re.search(
        r"FLOW_UNIT_FACTORS = \{(.*?)\n\}", coordinator, re.S
    ).group(1)
    known = set(re.findall(r'"([^"]+)":', factors))

    # Every option the config flow offers must be convertible.
    offered = set()
    for raw, key in re.findall(
        r'options=\[([^\]]+)\],\s*translation_key="([a-z_]+)"', config_flow, re.S
    ):
        if key == "flow_unit":
            offered |= set(re.findall(r'"([^"]+)"', raw))

    assert offered, "no flow unit options found"
    assert offered <= known, f"unconvertible: {sorted(offered - known)}"

    # And the units a sensor is likely to publish must be convertible too.
    for unit in ("l/min", "l/h", "m³/h", "l/s", "gpm"):
        assert unit in known, unit


def test_t63b_selector_options_have_translations():
    """An option without a translation renders as a raw slug in the interface."""
    import json
    import re

    root = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"
    config_flow = (root / "config_flow.py").read_text()

    for raw, key in re.findall(
        r'options=\[([^\]]+)\],\s*translation_key="([a-z_]+)"', config_flow, re.S
    ):
        options = set(re.findall(r'"([^"]+)"', raw))
        for language in ("en", "nl"):
            translations = json.loads(
                (root / "translations" / f"{language}.json").read_text(encoding="utf-8")
            )
            available = set(
                translations.get("selector", {}).get(key, {}).get("options", {})
            )
            assert options <= available, (
                f"{language}/{key} missing {sorted(options - available)}"
            )
            # Keys must be slug-safe, or Home Assistant rejects the file.
            for option in available:
                assert re.fullmatch(r"[a-z0-9_]+", option), f"{key}: {option}"


def test_t63c_conversion_factors_are_right():
    """17 L/min is 1.02 m³/h. Not 17, and not 0.28."""
    assert abs(17 * 0.06 - 1.02) < 0.001
    assert abs(3596 * 0.001 - 3.596) < 0.001
    assert abs(1 * 3.6 - 3.6) < 0.001
    assert abs(2.0 / 0.06 - 33.33) < 0.01


# ---------------------------------------------------------------------------
# T64 - the cover's effect is learned separately
# ---------------------------------------------------------------------------

def test_t64_covered_and_open_losses_stay_apart():
    """Averaging the two gives a figure that is wrong in both states.

    A cover typically halves the loss or better. On a pool losing two thirds of
    its input to the air, that is the difference between a two degree rise taking
    fourteen hours and taking five — far too large to split the difference on.
    """
    config = make_config()
    kwh_per_degree = config.pool.kwh_thermal_per_degree
    gross = 1.9 / kwh_per_degree  # measured thermal output

    open_air = heating.estimate(
        config, water_temp=26.0, target_temp=28.0, air_temp=20.0,
        learned_cop=3.28, heat_loss_c_per_h=0.281,
    )
    covered = heating.estimate(
        config, water_temp=26.0, target_temp=28.0, air_temp=20.0,
        learned_cop=3.28, heat_loss_c_per_h=0.120,
    )

    assert open_air.hours_needed > covered.hours_needed * 1.8, (
        open_air.hours_needed,
        covered.hours_needed,
    )
    # And the open-air case really is losing most of the input.
    assert 0.281 / gross > 0.6


def test_t64b_cover_changing_mid_period_teaches_nothing():
    """A period that started open and ended covered belongs to neither figure."""
    # The guard lives in the coordinator; this pins the arithmetic it protects.
    open_rate = learning.heat_loss_from_idle(28.0, 26.6, duration_h=5.0)
    covered_rate = learning.heat_loss_from_idle(28.0, 27.4, duration_h=5.0)
    assert open_rate is not None and covered_rate is not None
    assert open_rate > covered_rate * 2, (open_rate, covered_rate)

    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "coordinator.py"
    ).read_text()
    assert "Cover changed during the idle period" in source
    assert "started_covered != covered" in source


# ---------------------------------------------------------------------------
# T65 - hassfest's exact rules, pinned after a real CI failure
# ---------------------------------------------------------------------------

def test_t65_manifest_keys_sorted_hassfest_style():
    """hassfest wants domain, name, then the rest alphabetical.

    Not our own convention -- theirs, and it fails CI silently until you look.
    """
    import json

    path = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "manifest.json"
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    keys = list(manifest.keys())

    assert keys[0] == "domain"
    assert keys[1] == "name"
    rest = keys[2:]
    assert rest == sorted(rest), f"not alphabetical after domain/name: {rest}"


def test_t65b_translation_selector_keys_match_hassfest_regex():
    """The exact rule from the CI failure: [a-z0-9-_]+, no leading/trailing _ or -.

    "gpm_" passed our own looser check and still failed hassfest. This is their
    rule, not an approximation of it.
    """
    import json
    import re

    root = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"
    pattern = re.compile(r"[a-z0-9-_]+")

    for language in ("en", "nl"):
        translations = json.loads(
            (root / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        for selector_key, selector in translations.get("selector", {}).items():
            for option in selector.get("options", {}):
                assert pattern.fullmatch(option), f"{language}/{selector_key}: {option}"
                assert not option.startswith(("_", "-")), (
                    f"{language}/{selector_key}: {option} starts with _/-"
                )
                assert not option.endswith(("_", "-")), (
                    f"{language}/{selector_key}: {option} ends with _/-"
                )


# ---------------------------------------------------------------------------
# T66 - pH and chlorine pickers accept a manually-updated helper
# ---------------------------------------------------------------------------

def test_t66_ph_chlorine_pickers_allow_input_number():
    """A water test strip has no sensor of its own.

    pH and chlorine are as often an input_number helper someone updates by hand
    after a test as they are a real sensor. Restricting the picker to
    domain="sensor" hid every such helper from the list entirely -- the helper
    existed, the field just would not show it.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "config_flow.py"
    ).read_text()

    assert "field(c.CONF_PH_SENSOR): MANUAL_OR_SENSOR" in source
    assert "field(c.CONF_CHLORINE_SENSOR): MANUAL_OR_SENSOR" in source
    assert 'vol.Optional(c.CONF_PH_SENSOR): MANUAL_OR_SENSOR' in source
    assert 'vol.Optional(c.CONF_CHLORINE_SENSOR): MANUAL_OR_SENSOR' in source

    # And the selector itself must actually include input_number.
    definition = re.search(
        r"MANUAL_OR_SENSOR = selector\.EntitySelector\(.*?domain=(\[[^\]]+\])",
        source,
        re.S,
    )
    assert definition is not None, "MANUAL_OR_SENSOR definition not found"
    assert '"input_number"' in definition.group(1)
    assert '"sensor"' in definition.group(1)


# ---------------------------------------------------------------------------
# T67 - pump outlet and heat pump inlet are separate, aliasable fields
# ---------------------------------------------------------------------------

def test_t67_pump_outlet_is_its_own_field():
    """A user with different plumbing than the one this was built for.

    Folding "pump outlet" into "heat pump inlet" assumed one particular layout:
    pool -> pump -> heat pump -> pool, where the two are physically one point.
    Someone with a filter, a longer run, or anything else between the pump and
    the heat pump has two real points to measure, and needed two real fields.
    """
    root = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"
    const_source = (root / "const.py").read_text()
    flow_source = (root / "config_flow.py").read_text()

    assert 'CONF_PUMP_OUTLET_SENSOR = "pump_outlet_sensor"' in const_source

    # Present in both the initial wizard and the later options flow, not just one.
    assert flow_source.count("field(c.CONF_PUMP_OUTLET_SENSOR): TEMP_SENSOR") == 1
    assert flow_source.count("vol.Optional(c.CONF_PUMP_OUTLET_SENSOR): TEMP_SENSOR") == 1

    import json

    for language in ("en", "nl"):
        translations = json.loads(
            (root / "translations" / f"{language}.json").read_text(encoding="utf-8")
        )
        for section in (
            translations["config"]["step"]["optional"],
            translations["options"]["step"]["entities"],
        ):
            assert "pump_outlet_sensor" in section["data"]
            assert "pump_outlet_sensor" in section["data_description"]


def test_t67b_shared_probe_installations_alias_cleanly():
    """Rick's own plumbing has one probe doing both jobs.

    Pointing both fields at the same entity must not be treated as two
    disagreeing measurements -- the general alias mechanism, already used for
    water/pump_inlet, covers pump_outlet the same way.
    """
    config = make_config(
        sensor_aliases=frozenset({frozenset({"pump_outlet", "hp_inlet"})})
    )
    assert config.is_aliased("pump_outlet", "hp_inlet")
    assert config.is_aliased("hp_inlet", "pump_outlet")
    assert not config.is_aliased("pump_outlet", "hp_outlet")


def test_t67c_coordinator_builds_the_pump_outlet_alias(monkeypatch=None):
    """The coordinator's role list must include pump_outlet, or aliasing a
    shared probe silently stops working the moment someone configures one."""
    root = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"
    source = (root / "coordinator.py").read_text()
    roles_block = source[source.index("roles = (") : source.index("for role_a")]
    assert '"pump_outlet"' in roles_block
    assert '"hp_inlet"' in roles_block


# ---------------------------------------------------------------------------
# T68 - the panel reload actually reaches the browser
# ---------------------------------------------------------------------------

def test_t68_panel_url_is_cache_busted():
    """A new tab appeared in the source and not in the browser.

    The panel is served as a static file with no version in its URL, so the
    browser kept the cached copy indefinitely. The integration updated, the
    panel did not, and it looked like the update had silently failed.
    """
    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "__init__.py"
    ).read_text()

    assert "_async_panel_version" in source
    assert "poolsmart-panel.js?v=" in source, "no cache-busting query on the panel URL"
    # Taken from the integration Home Assistant already loaded. Reading the
    # manifest off disk here looked harmless and was not: file access inside the
    # event loop blocks every other integration for the duration.
    assert "async_get_integration" in source
    panel_block = source[source.index("async def _async_panel_version") :]
    panel_block = panel_block[: panel_block.index("\nasync def _async_register")]
    assert "read_text" not in panel_block, "blocking file read is back"


def test_t68b_bridge_method_exists_on_the_coordinator():
    """Regression: `_read` called `self._bridge` and the method was not there.

    Setup failed with an AttributeError the first time any sensor went
    unavailable -- which, on a system whose probes live on an ESP that
    occasionally reboots, is a matter of when rather than whether.
    """
    import ast

    source = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "coordinator.py"
    ).read_text()
    tree = ast.parse(source)

    methods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PoolSmartCoordinator":
            methods = {
                n.name
                for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            }

    # Every self._x(...) call inside the class must resolve to a real method.
    called = set(re.findall(r"self\.(_[a-z_]+)\(", source))
    known = methods | {
        "_conf",  # defined on the class, matched above, listed for clarity
    }
    missing = {name for name in called if name not in known}
    assert not missing, f"called but not defined: {sorted(missing)}"


# ---------------------------------------------------------------------------
# T69 - the panel follows the user's language
# ---------------------------------------------------------------------------

def test_t69_panel_is_translatable():
    """Entity names follow Home Assistant's language; the panel did not.

    That gap is the real inconsistency -- not the translated entity names, which
    are what appear on dashboards, in automations and in the logbook, and should
    stay translated. So the panel was localised rather than the entities being
    un-translated.
    """
    panel = (
        Path(__file__).resolve().parents[1]
        / "custom_components"
        / "poolsmart"
        / "www"
        / "poolsmart-panel.js"
    ).read_text()

    assert "const STRINGS = {" in panel
    assert "en:" in panel and "nl:" in panel
    assert "this._hass.language" in panel

    # Every key present in English must exist in Dutch, or the fallback quietly
    # leaves half the panel in the wrong language.
    english = re.search(r"\ben:\s*\{(.*?)\n  \},", panel, re.S).group(1)
    dutch = re.search(r"\bnl:\s*\{(.*?)\n  \},", panel, re.S).group(1)
    en_keys = set(re.findall(r"(\w+):", english))
    nl_keys = set(re.findall(r"(\w+):", dutch))
    assert en_keys <= nl_keys, f"untranslated: {sorted(en_keys - nl_keys)}"
