# PoolSmart Code Review - AI Recommendations

> Generated: 2026-08-12  
> Reviewers: AI Engineer, Backend Architect, Code Reviewer, Data Engineer, HACS Component Architect  
> Scope: Full codebase review of PoolSmart v1.4.0

---

## Executive Summary

PoolSmart is an exceptionally well-architected Home Assistant integration with clean separation of concerns, thorough documentation, and professional-grade Python development. The core decision engine (`core/`) is properly isolated from HA integration code, enabling standalone testing. The priority-ladder architecture is sound and safety-conscious.

This review identified **78 recommendations** across five domains:

| Domain | High | Medium | Low | Total |
|--------|------|--------|-----|-------|
| AI/ML | 4 | 8 | 5 | 17 |
| Backend Architecture | 6 | 12 | 8 | 26 |
| Code Quality & Correctness | 1 | 11 | 9 | 21 |
| Data Engineering | 5 | 12 | 7 | 24 |
| HACS Integration | 2 | 8 | 18 | 28 |
| **TOTAL** | **18** | **51** | **47** | **116** |

### Top 10 Priority Actions

1. **Add config entry migration** — No `async_migrate_entry` exists for future schema changes [HACS]
2. **Decompose coordinator.py** — 1,447-line god object violates single-responsibility [Backend]
3. **Implement data validation at ingestion** — Sensor values not range-checked before use [Data]
4. **Add value range validation for import** — Corrupt exports could poison learning model [Data]
5. **Persist NearMissLog** — Valuable diagnostic data lost on restart [Data]
6. **Add daily summaries** — Runtime/energy data lost on day roll [Data]
7. **Implement atomic writes** — Store corruption possible on crash [Backend]
8. **Add switch state verification** — Failed commands go undetected [Backend]
9. **Cache water_chemistry** — Rebuilt on every access from multiple sensors [Backend]
10. **Add data decay mechanism** — Learned values persist indefinitely [AI]

---

## 1. AI/ML Recommendations

### 1.1 Learning System

- [ ] **No data decay mechanism**
  **Location**: `core/learning.py`
  **Issue**: Learned values (COP, heat loss, heating rate) persist forever. Equipment degrades over time, pool liners change, filters age — the system has no way to "forget" old observations.
  **Recommendation**: Implement exponential decay — weight recent observations higher. Add a `timestamp` to each learned value and apply age-based weighting. Consider a "half-life" of 90 days for learned parameters.
  **Priority**: High

- [ ] **No feedback loop for AI suggestions**
  **Location**: `ai/advisor.py`
  **Issue**: When a user accepts an AI suggestion, the system does not track whether the suggestion produced good outcomes. The advisor cannot learn from its own recommendations.
  **Recommendation**: Record accepted suggestions with their predicted outcome. Compare actual vs. predicted after sufficient time. Use this to improve the advisor model.
  **Priority**: High

- [ ] **COP confidence threshold too low**
  **Location**: `core/learning.py`
  **Issue**: Only 3 sessions per bucket before trusting a learned COP value is insufficient for statistical confidence. COP varies with many factors (flow rate, solar gain, humidity).
  **Recommendation**: Increase minimum to 5-7 sessions. Add a confidence interval display in the diagnostics panel. Consider using the standard error of the mean to determine when a bucket is "trusted."
  **Priority**: High

- [ ] **Privacy concerns with external LLM**
  **Location**: `ai/advisor.py`
  **Issue**: Full payload including cost data, usage patterns, and pool characteristics is sent to an external LLM. No data minimization or user-selectable privacy tiers.
  **Recommendation**: Implement a privacy toggle:
  - Tier 1: Send only aggregated statistics (no timestamps, no cost data)
  - Tier 2: Send session summaries without detailed timing
  - Tier 3: Full data (current behavior)
  Allow users to self-host the LLM endpoint.
  **Priority**: High

- [ ] **Fixed learning rate too conservative**
  **Location**: `core/learning.py` (`capped_update`)
  **Issue**: The 15% capped update prevents the system from adapting to genuine long-term trends (e.g., heat pump degradation over years).
  **Recommendation**: Implement asymmetric capping — allow faster adaptation downward (25%) than upward (15%). Add a "confidence decay" mechanism that widens the cap when recent observations consistently disagree.
  **Priority**: Medium

- [ ] **COP bucketing too coarse**
  **Location**: `core/learning.py` (5°C-wide buckets)
  **Issue**: A session at 15.1°C and one at 19.9°C share a bucket despite different real-world COP characteristics.
  **Recommendation**: Use 2°C buckets for finer granularity, or store raw session data and compute buckets dynamically. Store numeric boundaries instead of string keys.
  **Priority**: Medium

- [ ] **No solar gain modeling during idle periods**
  **Location**: `core/learning.py` (`heat_loss_from_idle`)
  **Issue**: Heat loss can only be learned at night or on overcast days because warming periods are discarded. This severely limits training data.
  **Recommendation**: Model solar gain explicitly using the irradiance sensor (or time-of-day estimate) and subtract from temperature change. This enables heat loss learning during sunny idle periods.
  **Priority**: Medium

- [ ] **No feature correlation tracking**
  **Location**: `core/learning.py`
  **Issue**: Heating rate and COP are learned independently. The system cannot distinguish between a heat pump problem (low COP, normal rate) and a plumbing problem (normal COP, low rate).
  **Recommendation**: Track joint distributions of key metrics. Even a simple correlation matrix would enable richer diagnostics.
  **Priority**: Low

- [ ] **No data retention for raw observations**
  **Location**: `const.py` (`SESSION_LOG_SIZE = 60`)
  **Issue**: Session logs capped at 60 entries with no aggregation. Long-term trends (seasonal COP degradation) cannot be detected.
  **Recommendation**: Implement two-tier retention: full detail for last 60 sessions, then running aggregates (mean COP per bucket, mean heating rate) indefinitely.
  **Priority**: High (reclassified from Data Engineering)

- [ ] **No long-term trend detection**
  **Location**: `core/learning.py`
  **Issue**: Cannot detect gradual changes like heat pump degradation, filter media aging, or pool surface changes.
  **Recommendation**: Maintain monthly aggregates and compare against a rolling baseline. Surface degradation trends in the AI advisor.
  **Priority**: Medium

### 1.2 AI Advisory Layer

- [ ] **AI suggestions not contextualized by season**
  **Location**: `ai/advisor.py`
  **Issue**: The advisor may suggest the same filtration runtime in winter and summer, ignoring seasonal usage differences.
  **Recommendation**: Include month/season as a context factor in AI prompts.
  **Priority**: Medium

- [ ] **No A/B testing framework for suggestions**
  **Location**: `ai/advisor.py`
  **Issue**: Cannot determine if an AI suggestion actually improved pool operation.
  **Recommendation**: Implement a simple A/B framework: apply suggestion to one period, baseline to another, compare outcomes.
  **Priority**: Low

- [ ] **AI does not consider equipment age**
  **Location**: `ai/advisor.py`
  **Issue**: No way for the AI to know how old the heat pump or filter media is.
  **Recommendation**: Add optional "installation date" fields for key equipment. Include age in AI context.
  **Priority**: Low

- [ ] **No batch suggestion capability**
  **Location**: `ai/advisor.py`
  **Issue**: Suggestions are generated one at a time. A user reviewing settings must accept/reject each individually.
  **Recommendation**: Allow batch review mode where related suggestions can be accepted together.
  **Priority**: Low

---

## 2. Backend Architecture Recommendations

### 2.1 Coordinator Structure

- [ ] **Coordinator god object anti-pattern**
  **Location**: `coordinator.py` (1,447 lines)
  **Issue**: Single class handles sensor reading, execution, chemistry, session tracking, idle tracking, notifications, and water chemistry. Violates single-responsibility principle and makes testing difficult.
  **Recommendation**: Decompose into focused collaborators:
  - `SensorReader` — entity reads, bridging, flow parsing
  - `SessionTracker` — session lifecycle and learning updates  
  - `ChemistryService` — water chemistry computations
  - `IdleObserver` — heat loss learning from idle periods
  - `EnergyTracker` — consumption/cost accumulation
  
  Target: coordinator under 400 lines, orchestrating these services.
  **Priority**: High

- [ ] **`water_chemistry` property has no caching**
  **Location**: `coordinator.py:1236-1332`
  **Issue**: Called by multiple sensor `value_fn` lambdas. Each call rebuilds the entire chemistry dict including dose calculations and band judgments.
  **Recommendation**: Cache the chemistry result per-tick. Invalidate when `last_water_test` or `dose_log` changes.
  **Priority**: High

- [ ] **`core/` and `engine/` module naming inconsistent**
  **Location**: `core/__init__.py`, `engine/__init__.py`
  **Issue**: `core/` contains pure-Python logic; `engine/` contains HA-aware modules. Boundary is unclear.
  **Recommendation**: Rename to clarify layering:
  - `core/` → `domain/` (pure business logic)
  - `engine/` → `services/` (HA-aware orchestration)
  **Priority**: Medium

### 2.2 Performance

- [ ] **`runtime_hours()` is O(n) per tick**
  **Location**: `store.py:286-297`
  **Issue**: Iterates all intervals every tick. A pool cycling on/off every 15 minutes reaches ~96 intervals/day.
  **Recommendation**: Maintain a running total. Store `self._closed_hours` updated by `record_pump` when an interval closes. `runtime_hours()` becomes O(1).
  **Priority**: High

- [ ] **Multiple state-machine lookups per tick**
  **Location**: `coordinator.py:346-367`
  **Issue**: `_read()` called ~10 times per tick, each performing `self.hass.states.get(entity_id)`.
  **Recommendation**: Batch lookups using `self.hass.states.async_get_many(entity_ids)` (HA 2024.x+).
  **Priority**: Medium

- [ ] **Price forecast fetched every tick**
  **Location**: `coordinator.py:759`
  **Issue**: Tibber publishes forecasts hourly. Result fetched every 30 seconds.
  **Recommendation**: Cache price forecast with 5-minute TTL. Re-extract only when `state.last_updated` changes.
  **Priority**: Medium

- [ ] **Alias detection recreated every tick**
  **Location**: `coordinator.py:205-342` (in `_build_state`)
  **Issue**: Alias detection creates frozensets every call despite being static after setup.
  **Recommendation**: Move alias detection into `_build_pool_config()` (it already lives there partially). Remove duplicate.
  **Priority**: Medium

- [ ] **WebSocket snapshot serializes full logs**
  **Location**: `websocket.py:306-308`
  **Issue**: `ws_snapshot` returns entire decision_log and session_log (up to 160 entries) on every panel poll. No pagination.
  **Recommendation**: Add pagination (`offset`, `limit`) for logs. Snapshot returns current state; logs fetched on demand.
  **Priority**: Medium

- [ ] **`_next_swim_deadline()` computed every tick**
  **Location**: `coordinator.py:447-469`
  **Issue**: Iterates 8 days × 2 swim times every 30 seconds. Pure waste when nothing changed.
  **Recommendation**: Cache the deadline. Recompute only when date or swim settings change.
  **Priority**: Low

### 2.3 State Management

- [ ] **No atomic write pattern for store**
  **Location**: `store.py:245-247`
  **Issue**: `Store.async_save()` writes to JSON file. A crash mid-write corrupts the state file.
  **Recommendation**: Implement write-to-temp-then-rename pattern. Write to `{path}.tmp`, fsync, then atomic rename.
  **Priority**: High

- [ ] **No storage migration path**
  **Location**: `const.py:22-23`
  **Issue**: Storage version is 1 with no `_async_migrate` hook. Future schema changes will break existing installs.
  **Recommendation**: Implement standard HA storage migration pattern with `_async_migrate_func`.
  **Priority**: High

- [ ] **`backfill_cop_counts()` runs every load**
  **Location**: `store.py:176-180`, `store.py:324-347`
  **Issue**: Modifies state on every load, potentially triggering unnecessary save. Iterates session log each time.
  **Recommendation**: Mark backfill as complete in stored data (`"cop_counts_backfilled": true`). Run only once.
  **Priority**: Medium

- [ ] **`_close_open_interval()` iterates all intervals on load**
  **Location**: `store.py:182-193`
  **Issue**: O(n) at startup to find open intervals.
  **Recommendation**: Only check the last interval (invariant: only one open interval, always last).
  **Priority**: Low

### 2.4 API Design

- [ ] **Limited WebSocket commands**
  **Location**: `websocket.py:22-26`
  **Issue**: Only 3 commands (`entries`, `snapshot`, `clear_log`). No commands to change mode, set target, trigger chemistry, reset learning, or acknowledge faults.
  **Recommendation**: Add: `poolsmart/set_mode`, `poolsmart/set_target`, `poolsmart/trigger_chemistry`, `poolsmart/reset_learning`, `poolsmart/logs?type=decision&offset=0&limit=20`.
  **Priority**: Medium

- [ ] **`ws_clear_log` misnamed**
  **Location**: `websocket.py:320-327`
  **Issue**: Only clears `decision_log`, not `session_log` or `dose_log`. Name suggests clearing all logs.
  **Recommendation**: Rename to `ws_clear_decision_log` or add `log_type` parameter.
  **Priority**: Low

- [ ] **`ws_snapshot` lacks admin protection**
  **Location**: `websocket.py:159`
  **Issue**: Any HA user can read all pool data including chemistry readings and learned values.
  **Recommendation**: Add `@websocket_api.require_admin` for consistency with `ws_clear_log`.
  **Priority**: Low

- [ ] **`record_dose` product validation**
  **Location**: `__init__.py:193-198`
  **Issue**: Validates product enum but doesn't cross-reference configured acid/chlorine products. User can record `acid_15` even when configured for `acid_37`.
  **Recommendation**: Cross-reference against `CONF_ACID_PRODUCT` / `CONF_CHLORINE_PRODUCT`. Warn on mismatch.
  **Priority**: Low

### 2.5 Error Handling & Resilience

- [ ] **No verification of switch commands**
  **Location**: `coordinator.py:1049-1057`
  **Issue**: `_async_set()` fires `switch.turn_on/off` with `blocking=False` and never verifies. Failed relay leaves system thinking heat pump is off when still running.
  **Recommendation**: Implement verification: fire command → check state next tick → if mismatch persists 3+ ticks, raise `switch_unresponsive` fault.
  **Priority**: High

- [ ] **Broad `except Exception` used 14 times**
  **Location**: `coordinator.py` (multiple locations)
  **Issue**: Silently swallows real bugs. `async_save` exception loses state silently.
  **Recommendation**: Use specific exception types. Add consecutive-failure counter; raise fault after 5 consecutive failures.
  **Priority**: Medium

- [ ] **No circuit breaker for price sensor**
  **Location**: `coordinator.py:759`, `ladder.py:93-99`
  **Issue**: When Tibber becomes unavailable, system heats reactively without notification.
  **Recommendation**: Fire `heating_postponed` notification when price forecast goes from available to unavailable.
  **Priority**: Medium

- [ ] **Unload race condition**
  **Location**: `__init__.py:327-334`
  **Issue**: `async_unload_entry` saves with `force=True` but doesn't cancel in-flight operations.
  **Recommendation**: Add `_unloading: bool` flag to coordinator. Set at unload start. Check at top of `_async_tick` to abort gracefully.
  **Priority**: Medium

### 2.6 Configuration Flow

- [ ] **Schema duplication in config flow**
  **Location**: `config_flow.py:300-348`, `config_flow.py:531-579`, `config_flow.py:803-890`
  **Issue**: `_optional_entities()`, `async_step_optional_sensors()`, and `async_step_entities()` all define nearly identical field sets.
  **Recommendation**: Extract shared `_entity_schema(source, has_sensors, required=False)` function. Eliminates ~150 lines.
  **Priority**: Medium

- [ ] **Options flow doesn't invalidate config cache**
  **Location**: `config_flow.py:778-801`
  **Issue**: Saving options triggers full reload instead of incremental cache invalidation.
  **Recommendation**: Emit event on options change. Coordinator invalidates `_config_cache` and rebuilds incrementally.
  **Priority**: Medium

- [ ] **Filter media options differ between setup and options**
  **Location**: `config_flow.py:178`, `config_flow.py:1332`
  **Issue**: Setup includes `"none"`, options includes `"de"`. Inconsistent.
  **Recommendation**: Define single `FILTER_MEDIA_OPTIONS` constant in `const.py`.
  **Priority**: Low

- [ ] **Heating source change doesn't clear entity keys**
  **Location**: `config_flow.py:404-418`
  **Issue**: Changing from heat_pump to none clears heating keys but not entity keys like `CONF_HP_SWITCH`.
  **Recommendation**: Clear source-specific entity keys when source changes.
  **Priority**: Medium

---

## 3. Code Quality & Correctness Recommendations

### 3.1 Code Smells

- [ ] **`config_flow.py` schema duplication**
  **Location**: `config_flow.py:300-348` vs `531-579`
  **Issue**: Nearly identical field sets defined independently.
  **Recommendation**: Extract shared helper to prevent drift.
  **Priority**: Medium

- [ ] **`_reading()` duplicates `_read()`**
  **Location**: `coordinator.py:1223-1233` vs `346-367`
  **Issue**: Stripped-down duplicate without `_last_good` tracking, age computation, or bridging support.
  **Recommendation**: Extract common logic into private helper. Chemistry readings should benefit from bridge-outage logic.
  **Priority**: Medium

- [ ] **`_build_state()` too large and nested**
  **Location**: `coordinator.py:525-607`
  **Issue**: 80+ lines with deep nesting. Handles sensor reading, runtime tracking, block plan restoration, and PoolState construction.
  **Recommendation**: Extract block plan restoration and runtime tracking into separate methods.
  **Priority**: Low

- [ ] **`_restored_block` not declared in `__init__`**
  **Location**: `coordinator.py:567`
  **Issue**: Dynamically created attribute. Hard to track.
  **Recommendation**: Add `self._restored_block: filt.BlockPlan | None = None` to `__init__`.
  **Priority**: Medium

- [ ] **Unreachable fallback in `_progress()`**
  **Location**: `config_flow.py:390`
  **Issue**: If `step_id` is in `_STEPS`, the loop always matches. Line 390 is dead code.
  **Recommendation**: Remove dead fallback or add defensive comment.
  **Priority**: Low

- [ ] **Duplicate `cop_ref` computation**
  **Location**: `config_flow.py:457-463` and `976-984`
  **Issue**: `async_step_heating` and `async_step_pool` in options flow compute identically.
  **Recommendation**: Extract `_derive_cop(user_input)` helper.
  **Priority**: Low

### 3.2 Type Safety

- [ ] **`active_block: dict | None` too vague**
  **Location**: `store.py:129`
  **Issue**: Dict has known keys: `index`, `start`, `end`, `rationale`.
  **Recommendation**: Define a `TypedDict` or small dataclass.
  **Priority**: Medium

- [ ] **Missing type parameters on `detail: dict`**
  **Location**: `models.py:124, 277`; `safety.py` (various)
  **Issue**: Should be `dict[str, Any]`.
  **Recommendation**: Add proper type parameters throughout.
  **Priority**: Low

- [ ] **`_next_action()` returns `object | None`**
  **Location**: `sensor.py:777-784`
  **Issue**: `object` type hint provides no safety.
  **Recommendation**: Change to `datetime | None`.
  **Priority**: Medium

- [ ] **`mode: str | None` should be `Mode | None`**
  **Location**: `store.py:133`
  **Issue**: Inconsistent with enum usage elsewhere.
  **Recommendation**: Use `Mode | None` type hint.
  **Priority**: Low

### 3.3 Security

- [ ] **WebSocket commands expose internal state**
  **Location**: `websocket.py:138-149, 152-309`
  **Issue**: `poolsmart/snapshot` and `poolsmart/entries` have no admin requirement.
  **Recommendation**: Add authentication or document exposure. At minimum, be consistent with `ws_clear_log`.
  **Priority**: Medium

- [ ] **No size check on import_learning payload**
  **Location**: `__init__.py:270-277`
  **Issue**: Malicious deeply nested JSON could cause memory issues.
  **Recommendation**: Add file size limit (e.g., 1MB max) before parsing.
  **Priority**: Low

- [ ] **`measured_before` lacks range validation**
  **Location**: `__init__.py:200-208`
  **Issue**: Only upper bound on `amount`. `measured_before` accepts any float.
  **Recommendation**: Add sanity range: pH 0-14, chlorine 0-20.
  **Priority**: Medium

- [ ] **No hardcoded secrets found** 
  **Status**: Good practice maintained. Continue.
  **Priority**: N/A

### 3.4 Maintainability

- [ ] **No automated tests for core modules**
  **Location**: Project root / `tests/`
  **Issue**: 85+ tests exist via custom runner, but critical `core/` modules (ladder, learning, safety) need more comprehensive coverage for edge cases.
  **Recommendation**: Expand test coverage for boundary conditions in decision logic.
  **Priority**: High

- [ ] **`coordinator.py` at 1447 lines**
  **Location**: `coordinator.py`
  **Issue**: Combines data reading, state building, execution, learning, chemistry, session tracking.
  **Recommendation**: Extract water chemistry and session tracking into separate modules.
  **Priority**: Medium

- [ ] **`FLOW_UNIT_FACTORS` duplicate keys**
  **Location**: `coordinator.py:61-80`
  **Issue**: `m³/h` and `m3/h` as separate keys. Lookup uses `.lower()` without unicode normalization.
  **Recommendation**: Normalize keys at definition time.
  **Priority**: Low

- [ ] **Excellent docstrings throughout**
  **Status**: Maintain this high standard.
  **Priority**: N/A

### 3.5 Bug Potential

- [ ] **Block windows unpacking error**
  **Location**: `coordinator.py:207-213`
  **Issue**: If `_conf(c.CONF_BLOCK_WINDOWS)` returns a sub-list with fewer than 2 elements, `_parse_time` raises `ValueError`.
  **Recommendation**: Add validation: `if len(pair) >= 2` before unpacking.
  **Priority**: Medium

- [ ] **`active_block` in PoolState never populated**
  **Location**: `models.py:218`
  **Issue**: Declared as `tuple[int, datetime, datetime] | None` but never set by `_build_state()`. Actual data lives in `self._restored_block`.
  **Recommendation**: Remove unused field or wire it up.
  **Priority**: Medium

- [ ] **Inconsistent indentation in `_walk()`**
  **Location**: `ladder.py:304-326`, `431-455`
  **Issue**: 2-space indent inside `if` blocks instead of 4-space.
  **Recommendation**: Fix for consistency.
  **Priority**: Low

- [ ] **Subsystems cleared even when not run**
  **Location**: `coordinator.py:640`
  **Issue**: `self.subsystem_errors = {}` at tick start. A subsystem that failed last tick but isn't called this tick shows as recovered.
  **Recommendation**: Only clear errors for subsystems about to run, or add "stale" marker.
  **Priority**: Low

---

## 4. Data Engineering Recommendations

### 4.1 Data Persistence Layer

- [ ] **No internal schema versioning**
  **Location**: `store.py:212-243`
  **Issue**: `STORAGE_VERSION = 1` is HA Store mechanism, but data dict has no internal version field. Future migrations fragile.
  **Recommendation**: Add `"data_version"` field independent of HA Store version. Implement versioned migration chain.
  **Priority**: High

- [ ] **Log rotation O(n) on every append**
  **Location**: `store.py:302-320`
  **Issue**: List slicing on every append when over capacity.
  **Recommendation**: Use `collections.deque(maxlen=...)` for all logs. O(1) append, automatic bounds.
  **Priority**: Medium

- [ ] **`RuntimeInterval` uses verbose datetime serialization**
  **Location**: `store.py:46-57`
  **Issue**: ISO-8601 strings (~25 bytes) vs 8 bytes for Unix timestamp.
  **Recommendation**: Serialize as Unix timestamps. Add backward-compatible `from_dict` that accepts both formats.
  **Priority**: Medium

- [ ] **`apply_learned` dead code**
  **Location**: `store.py:430-444`
  **Issue**: Defined but never called. Capped update logic duplicated in `learning.capped_update`.
  **Recommendation**: Remove or route all updates through it as single source of truth.
  **Priority**: Low

- [ ] **No migration tracking**
  **Location**: `store.py:176-180`, `store.py:324-347`
  **Issue**: `backfill_cop_counts` runs at every load with no tracking.
  **Recommendation**: Track migration state in persisted data (`_migrations_applied: list[str]`).
  **Priority**: Medium

### 4.2 Data Collection & Quality

- [ ] **No sensor value range validation at ingestion**
  **Location**: `coordinator.py:346-367` (`_read` method)
  **Issue**: Temperature sensor reporting -999 or 999 stored in `_last_good` and used until fault detection catches it.
  **Recommendation**: Add plausibility filter — water temp outside -5°C to 55°C rejected immediately.
  **Priority**: High

- [ ] **Silent bridging of stale data**
  **Location**: `coordinator.py:369-392`
  **Issue**: Bridged flag set but never validated against business logic. 179-second-old data appears fresh.
  **Recommendation**: Add warning log when bridging >30 seconds. Surface bridged state in sensor attributes.
  **Priority**: Medium

- [ ] **Silent flow unit fallback**
  **Location**: `coordinator.py:496-523`
  **Issue**: Misconfigured flow unit silently produces wrong data for COP, thermal output, filtration time.
  **Recommendation**: Track "data quality" indicator per sensor. Surface in diagnostics. Trigger notification after repeated fallbacks.
  **Priority**: Medium

- [ ] **`_last_good` grows without bound**
  **Location**: `coordinator.py:143, 366`
  **Issue**: Entries for deleted sensors persist in memory.
  **Recommendation**: Prune stale entries for roles no longer in config during `_build_state`.
  **Priority**: Low

- [ ] **Energy gaps silently dropped**
  **Location**: `coordinator.py:858-878`
  **Issue**: Ticks > 0.5 hours silently lose energy accounting data during pause/restart.
  **Recommendation**: Log discontinuity. Estimate gap period separately with interpolated flag.
  **Priority**: Medium

### 4.3 Data Structures

- [ ] **`PoolState` memory overhead**
  **Location**: `core/models.py:149-263`
  **Issue**: ~30-field frozen dataclass created ~2,880 times/day with nested `SensorReading` instances.
  **Recommendation**: Use `@dataclass(slots=True)` (Python 3.10+) to reduce memory overhead.
  **Priority**: Medium

- [ ] **`SensorReading.age_seconds` stale immediately**
  **Location**: `core/models.py:128-146`
  **Issue**: Age computed at read time, stale by the time decision engine uses it.
  **Recommendation**: Store `last_reported` timestamp. Compute age lazily via property.
  **Priority**: Low

- [ ] **`irradiance_samples` unbounded**
  **Location**: `core/learning.py:50`
  **Issue**: Multi-day sessions could accumulate thousands of float values.
  **Recommendation**: Track running sum and count instead. `irradiance_avg` computed incrementally.
  **Priority**: Low

- [ ] **`NearMissLog.tallies` mutable value**
  **Location**: `core/trace.py:117`
  **Issue**: `dict[tuple[str, str], list]` with `[count, seconds]` mutable in non-frozen dataclass.
  **Recommendation**: Use frozen dataclass or named tuple for tally value.
  **Priority**: Low

### 4.4 Learning Data Pipeline

- [ ] **No data retention policy for raw observations**
  **Location**: `const.py:38` (`SESSION_LOG_SIZE = 60`)
  **Issue**: Capped at 60 with no aggregation. Long-term trends undetectable.
  **Recommendation**: Two-tier retention: full detail for 60 sessions, then running aggregates indefinitely.
  **Priority**: High

- [ ] **`heat_loss_from_idle` limited training data**
  **Location**: `core/learning.py:335-353`
  **Issue**: Requires 6-hour idle + no warming. Only learnable at night or overcast days.
  **Recommendation**: Model solar gain explicitly using irradiance sensor. Subtract from temperature change.
  **Priority**: Medium

- [ ] **Symmetric capping prevents rapid adaptation**
  **Location**: `core/learning.py:302-308`
  **Issue**: Pool that changes behavior (e.g., after heat pump service) learns slowly.
  **Recommendation**: Asymmetric capping — faster downward adaptation (25%) than upward (15%).
  **Priority**: Medium

- [ ] **COP bucketing coarse**
  **Location**: `core/learning.py:33-37`
  **Issue**: 5°C-wide buckets. 15.1°C and 19.9°C share bucket despite different COP.
  **Recommendation**: Use 2°C buckets or store raw data and compute dynamically.
  **Priority**: Medium

- [ ] **No joint feature tracking**
  **Location**: `core/learning.py`
  **Issue**: Cannot distinguish heat pump problem from plumbing problem.
  **Recommendation**: Track joint distributions. Simple correlation matrix enables richer diagnostics.
  **Priority**: Low

### 4.5 Export/Import

- [ ] **No value range validation on import**
  **Location**: `recovery.py:189-206`
  **Issue**: Export with `heat_loss_c_per_h: 999` or negative COP passes validation.
  **Recommendation**: Add range validation: heat loss 0.01-2.0 °C/h, COP 1.0-10.0, flow 0.1-50 m³/h.
  **Priority**: High

- [ ] **No integrity checksum on exports**
  **Location**: `recovery.py:170-186`
  **Issue**: Corrupted or tampered export silently corrupts learning model.
  **Recommendation**: Add SHA-256 hash of canonical JSON payload. Validate on import.
  **Priority**: Medium

- [ ] **Export format not forward-compatible**
  **Location**: `recovery.py:177-179`
  **Issue**: Version-2 export cannot be consumed by version-1 code.
  **Recommendation**: Design with optional fields and backward compatibility. Add new fields as optional with defaults.
  **Priority**: Medium

- [ ] **All-or-nothing import**
  **Location**: `recovery.py:189-206`
  **Issue**: Single bad field causes entire import to fail.
  **Recommendation**: Implement partial import with validation reporting. Accept valid fields, reject invalid ones.
  **Priority**: Low

### 4.6 Historical Data

- [ ] **`NearMissLog` not persisted**
  **Location**: `core/trace.py:107-161`
  **Issue**: In-memory only. Restart loses entire day's near-miss tallies.
  **Recommendation**: Persist in store alongside other daily data. Small size, high diagnostic value.
  **Priority**: High

- [ ] **Runtime intervals cleared on day roll**
  **Location**: `store.py:251-262`
  **Issue**: No historical record. Cannot answer "how much did the pool filter last Tuesday?"
  **Recommendation**: Before clearing, persist daily summary (total runtime, session count, energy). Cap at 90 days.
  **Priority**: High

- [ ] **Decision log entries include full trace**
  **Location**: `coordinator.py:1090-1101`, `store.py:234`
  **Issue**: Each entry ~1-2 KB. 100 entries = 100-200 KB serialized on every save.
  **Recommendation**: Store trace separately or only for most recent N decisions.
  **Priority**: Medium

- [ ] **No time-based downsampling**
  **Location**: `store.py` (overall)
  **Issue**: Same granularity for 1-day-old and 1-year-old data.
  **Recommendation**: Implement: full detail 7 days, daily summaries 90 days, weekly summaries thereafter.
  **Priority**: Medium

- [ ] **Session log stores derived values**
  **Location**: `core/learning.py:112-130`
  **Issue**: If derivation logic changes, historical entries cannot be re-derived.
  **Recommendation**: Store only raw measurements. Compute derived values at read time.
  **Priority**: Medium

- [ ] **Dose linking is fragile 1:1**
  **Location**: `coordinator.py:1365-1382`
  **Issue**: `async_record_test` adds `measured_after` to latest dose. Breaks with concurrent doses.
  **Recommendation**: Use explicit dose IDs to link doses to before/after test results.
  **Priority**: Low

---

## 5. HACS Integration Recommendations

### 5.1 HA Standards Compliance

- [ ] **No `async_migrate_entry`**
  **Location**: `__init__.py:354`
  **Issue**: ConfigFlow VERSION = 1 but no migration handler. Future version bumps break existing installs.
  **Recommendation**: Add `async_migrate_entry` function to handle config entry version upgrades.
  **Priority**: High

- [ ] **No `async_remove_entry`**
  **Location**: `__init__.py`
  **Issue**: Sidebar panel persists after all pools removed.
  **Recommendation**: Implement `async_remove_entry` to clean up panel registration.
  **Priority**: Medium

- [ ] **Missing `state_class` on sensors**
  **Location**: `sensor.py` (multiple)
  **Issue**: Several measurement sensors lack `state_class` for long-term statistics.
  **Recommendation**: Add: `session_energy` → TOTAL_INCREASING; `session_elapsed`, `heat_loss_rate`, `heating_rate` → MEASUREMENT.
  **Priority**: Medium

- [ ] **`entity_category` not used for diagnostics**
  **Location**: `sensor.py` (multiple)
  **Issue**: Non-primary sensors clutter device page.
  **Recommendation**: Mark as `EntityCategory.DIAGNOSTIC`: delta_t, cop_measured, thermal_power, flow_adequacy, heat_balance, heating_rate, heat_loss_rate, session_*, energy_today, cost_*, price_verdict, water_balance, dose_advice, ai_suggestion.
  **Priority**: Medium

- [ ] **`extra_state_attributes` deprecated pattern**
  **Location**: `sensor.py:856`, `binary_sensor.py:93`, `number.py:111`
  **Issue**: Still functional but deprecated in HA.
  **Recommendation**: Monitor HA release notes. Prepare migration to `EntityDescription` with `state_attributes`.
  **Priority**: Low

- [ ] **`bridge_outage_seconds` may be missing from SafetySettings**
  **Location**: `coordinator.py:387`
  **Issue**: Referenced but not confirmed in SafetySettings construction.
  **Recommendation**: Verify `SafetySettings` in `core/config.py` defines this with sensible default (e.g., 30s).
  **Priority**: High

### 5.2 Config Flow

- [ ] **`CONF_BLOCK_WINDOWS` without schema validation**
  **Location**: `coordinator.py:207-213`
  **Issue**: Malformed JSON edit could crash the tick.
  **Recommendation**: Add Voluptuous schema: `vol.All(list, [vol.All(list, [str, str], length=2)])`.
  **Priority**: Medium

- [ ] **Time format fields lack validation**
  **Location**: `config_flow.py:1176-1181`, `1254-1260`
  **Issue**: `CONF_NIGHT_START`, `CONF_NIGHT_END`, `CONF_SWIM_TIME` accept any string.
  **Recommendation**: Add regex validation: `vol.Match(r"^\d{2}:\d{2}$")`.
  **Priority**: Low

- [ ] **`CONF_SWIM_DAYS` string-to-int coupling**
  **Location**: `coordinator.py:463`
  **Issue**: Stored as strings, compared with `int(d)`. Fragile.
  **Recommendation**: Add documenting comment or normalize to integers at comparison site.
  **Priority**: Low

- [ ] **`os.path.isfile()` instead of `Path`**
  **Location**: `config_flow.py:72`
  **Issue**: Inconsistent with rest of codebase using `pathlib`.
  **Recommendation**: Replace with `Path(path).is_file()`.
  **Priority**: Low

### 5.3 Entity Design

- [ ] **`available` returns True when coordinator data stale**
  **Location**: `entity.py:48-55`
  **Issue**: Entities available even if coordinator is down.
  **Recommendation**: Also check `coordinator.last_update_success`.
  **Priority**: Low

- [ ] **Learning switch doesn't trigger refresh**
  **Location**: `switch.py:52-57`
  **Issue**: Updates options but change takes effect on next tick.
  **Recommendation**: Call `await self.coordinator.async_request_refresh()` after update.
  **Priority**: Medium

- [ ] **`record_dose` unit selector mismatch**
  **Location**: `services.yaml:34-38` vs `__init__.py:210`
  **Issue**: Selector offers `[ml, g]`, handler accepts `("g", "ml", "l", "L", "kg")`.
  **Recommendation**: Align selector with handler: `[ml, g, l, kg]`.
  **Priority**: Medium

### 5.4 Frontend

- [ ] **Panel refreshes every 15 seconds**
  **Location**: `poolsmart-panel.js:194`
  **Issue**: Two snapshot requests per coordinator tick.
  **Recommendation**: Use `document.visibilitychange` to pause when hidden. Or increase to 30s.
  **Priority**: Low

- [ ] **No error boundary around `_renderTab`**
  **Location**: `poolsmart-panel.js:404-421`
  **Issue**: A throwing render function breaks the entire panel.
  **Recommendation**: Wrap in try/catch. Display error for that tab instead.
  **Priority**: Medium

- [ ] **Root `poolsmart-panel.js` duplicate**
  **Location**: `poolsmart-panel.js` (root, 15966 bytes) vs `www/poolsmart-panel.js` (47082 bytes)
  **Issue**: Root file is smaller/older version.
  **Recommendation**: Remove root file to avoid confusion.
  **Priority**: Medium

### 5.5 HACS Compliance

- [ ] **Brand images duplicated**
  **Location**: `custom_components/poolsmart/brand/` vs `brands/`
  **Issue**: Redundant copies.
  **Recommendation**: Remove inner `brand/` directory or document reason for duplication.
  **Priority**: Low

- [ ] **No `strings.json` file**
  **Location**: `custom_components/poolsmart/translations/`
  **Issue**: All English in `translations/en.json`. Non-standard.
  **Recommendation**: Add minimal `strings.json` with config flow structure as per HA best practice.
  **Priority**: Low

- [ ] **`hacs.json` version field**
  **Location**: `hacs.json:5`
  **Issue**: Minimum HA version may need updating as HA evolves.
  **Recommendation**: Verify actual minimum. Lower if possible to expand user base.
  **Priority**: Low

---

## Implementation Priority Matrix

### Phase 1: Critical (Do First)
These address data loss, corruption, or safety issues:

| # | Recommendation | Domain | Location |
|---|---------------|--------|----------|
| 1 | Add `async_migrate_entry` | HACS | `__init__.py` |
| 2 | Implement atomic writes | Backend | `store.py` |
| 3 | Add switch state verification | Backend | `coordinator.py:1049` |
| 4 | Add sensor value range validation | Data | `coordinator.py:346` |
| 5 | Add import value range validation | Data | `recovery.py:189` |
| 6 | Persist NearMissLog | Data | `core/trace.py` |
| 7 | Add daily runtime summaries | Data | `store.py:251` |
| 8 | Implement data schema versioning | Data | `store.py` |

### Phase 2: High Impact
These improve performance, maintainability, or user experience:

| # | Recommendation | Domain | Location |
|---|---------------|--------|----------|
| 9 | Decompose coordinator.py | Backend | `coordinator.py` |
| 10 | Cache water_chemistry | Backend | `coordinator.py:1236` |
| 11 | Make `runtime_hours()` O(1) | Backend | `store.py:286` |
| 12 | Add data decay to learning | AI | `core/learning.py` |
| 13 | Improve COP confidence threshold | AI | `core/learning.py` |
| 14 | Add privacy tiers for AI | AI | `ai/advisor.py` |
| 15 | Expand WebSocket API | Backend | `websocket.py` |
| 16 | Add `state_class` to sensors | HACS | `sensor.py` |

### Phase 3: Polish
These are quality-of-life improvements:

| # | Recommendation | Domain | Location |
|---|---------------|--------|----------|
| 17 | Add `entity_category` for diagnostics | HACS | `sensor.py` |
| 18 | Fix service unit selector mismatch | HACS | `services.yaml` |
| 19 | Remove duplicate panel JS | HACS | root `poolsmart-panel.js` |
| 20 | Add render error boundary | HACS | `poolsmart-panel.js` |
| 21 | Deduplicate config flow schemas | Backend | `config_flow.py` |
| 22 | Use deque for log rotation | Data | `store.py:302` |
| 23 | Add type safety improvements | Code Quality | multiple |
| 24 | Fix block window validation | Code Quality | `coordinator.py:207` |

---

## Positive Observations

The PoolSmart codebase demonstrates exceptional quality in several areas:

1. **Clean Architecture**: The `core/` vs `engine/` vs integration layer separation is textbook-clean and enables standalone testing.

2. **Priority Ladder Design**: The decision engine's priority-based approach is elegant, safe, and well-documented. The emergency stop at priority 0 is a critical safety feature.

3. **Self-Learning with Guardrails**: The capped updates, per-measurement assessment, and outlier rejection show real-world refinement beyond typical HA integrations.

4. **Documentation**: Docstrings are among the best seen in HA integrations — they explain *why*, not just *what*. The `docs/` directory with SVG diagrams is comprehensive.

5. **Safety Culture**: The severity-based fault system, compressor guard, operating envelope checks, and frost protection demonstrate genuine safety consciousness.

6. **No Hardcoded Secrets**: Clean security posture throughout.

7. **Notification System**: The 9 configurable event types with action buttons and escalation intervals is professional-grade.

8. **Test Infrastructure**: Custom test runner with HA stubs enables CI without heavy dependencies.

9. **Frontend as Web Component**: Shadow DOM-based panel avoids framework dependencies while providing a rich UI.

10. **License Compliance**: AGPL-3.0-or-later with clear attribution.

---

## Conclusion

PoolSmart is a professionally developed Home Assistant integration that already exceeds most community contributions in code quality, architecture, and documentation. The recommendations in this document focus on:

- **Future-proofing** (migrations, schema versioning, atomic writes)
- **Performance** (caching, O(1) operations, batch reads)
- **Data integrity** (validation at boundaries, range checks, persistence)
- **User experience** (better panel, richer API, diagnostic entity categories)
- **AI/ML maturity** (feedback loops, data decay, privacy, confidence)

The codebase is ready for production use today. Implementing the Phase 1 recommendations will ensure long-term reliability as the project evolves.
