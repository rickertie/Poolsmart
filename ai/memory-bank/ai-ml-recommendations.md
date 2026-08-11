# AI/ML Recommendations — Poolsmart

## 1. AI/ML Architecture

### 1.1 Model Design & Maintainability

- [ ] **Issue**: The AI advisor relies entirely on an external LLM via Home Assistant's `ai_task.generate_data` service with no local fallback or caching. If the service is unavailable, slow, or rate-limited, the advisory layer produces nothing.
  **Location**: `ai/advisor.py:173-182`
  **Recommendation**: Add a local rule-based fallback advisor that can produce basic observations (e.g., "Your heating rate has dropped 20% over the last month") using the same `_payload()` data. This ensures the feature remains useful even without an AI Task entity configured. Consider caching the last successful review result with a TTL.
  **Priority**: Medium

- [ ] **Issue**: The LLM prompt (`PROMPT`) is a module-level constant with no versioning or A/B testing capability. Prompt improvements require a full integration update.
  **Location**: `ai/advisor.py:40-67`
  **Recommendation**: Store the prompt template in a separate file or in the integration's config entry options. This allows prompt tuning without code changes and enables future support for multiple prompt strategies. Consider adding a prompt version field to the stored result for traceability.
  **Priority**: Low

- [ ] **Issue**: The `_parse` method truncates the summary to 600 characters and observations to 200 characters each, but there's no validation that the truncated JSON fields are semantically meaningful after truncation.
  **Location**: `ai/advisor.py:245-248`
  **Recommendation**: Validate truncation boundaries at word/sentence boundaries to avoid cutting mid-sentence. Consider using `textwrap.shorten` or similar that respects word boundaries.
  **Priority**: Low

### 1.2 Data Pipeline for Training/Learning

- [ ] **Issue**: The session log (`SESSION_LOG_SIZE = 60`) is trimmed to the last 60 entries, but the learned COP values persist indefinitely. Over time, the learned COP curve may be based on data that no longer exists in the session log, making it impossible to audit or re-derive the learned values.
  **Location**: `const.py:38`, `store.py:318-320`
  **Recommendation**: Implement a retention policy for learned values that mirrors the session log. Either (a) store the raw session data that produced each learned value for as long as the value persists, or (b) implement a decay mechanism that reduces confidence in older learned values when their source data is trimmed.
  **Priority**: High

- [ ] **Issue**: The `_payload()` method for the AI advisor truncates the JSON data to 12,000 characters with no intelligence about what gets cut. Critical recent sessions might be dropped while older, less relevant data is included.
  **Location**: `ai/advisor.py:168`
  **Recommendation**: Implement priority-based truncation that ensures the most recent sessions and decisions are always included. Consider a tiered approach: always include the last 7 days of sessions, then fill remaining space with decisions and energy data.
  **Priority**: Medium

- [ ] **Issue**: No feature engineering is performed before sending data to the LLM. The raw session data includes absolute timestamps and temperatures but not derived features like "average COP trend over time" or "heating rate degradation."
  **Location**: `ai/advisor.py:117-160`
  **Recommendation**: Add pre-computed trend features to the payload: COP trend (slope over recent sessions), heating rate deviation from initial learned value, heat loss trend, and seasonal comparisons. This gives the LLM higher-quality signals to reason about.
  **Priority**: Medium

### 1.3 Suggestion Quality & Relevance

- [ ] **Issue**: The `ADJUSTABLE` whitelist only exposes 6 settings. Many impactful parameters (chemistry target pH, chemistry target chlorine, filtration windows, min daily hours) cannot be suggested by the AI.
  **Location**: `ai/advisor.py:30-38`
  **Recommendation**: Expand the adjustable set to include chemistry targets and operational parameters. Add a separate "informational" suggestion type for things the AI can observe but not suggest changes to (e.g., "Your filter media may need replacement based on flow decline").
  **Priority**: Medium

- [ ] **Issue**: There is no feedback mechanism to track whether accepted suggestions led to improved outcomes. The system cannot learn from its own recommendations.
  **Location**: `ai/advisor.py:253-269`
  **Recommendation**: Record the suggestion context (payload snapshot, suggestion made) when a suggestion is accepted. After a configurable period (e.g., 7 days), compare the predicted vs. actual outcome. Use this to build a local model of suggestion quality and adjust the prompt accordingly.
  **Priority**: High

- [ ] **Issue**: The prompt instructs the LLM to "suggest nothing if the data does not clearly support a change," but provides no threshold or criteria for what constitutes clear support. Different LLMs may interpret this differently.
  **Location**: `ai/advisor.py:62-63`
  **Recommendation**: Add quantitative thresholds to the prompt. For example: "Only suggest a turnover_factor change if the pool is consistently under-filtered by more than 15% over the week." This makes suggestions more consistent and testable.
  **Priority**: Medium

### 1.4 Privacy & Data Handling

- [ ] **Issue**: The AI payload includes pool volume, daily filtration hours, target temperature, learned parameters, recent sessions, decisions, energy consumption, and cost data. This is sent to an external LLM service with no data minimization.
  **Location**: `ai/advisor.py:117-160`
  **Recommendation**: Implement a privacy tier system:
  - **Minimal**: Only aggregated statistics (no raw session data)
  - **Standard**: Aggregated stats + recent session summaries (current behavior)
  - **Detailed**: Full payload for advanced troubleshooting
  
  Allow users to select their tier. Ensure the default tier does not expose cost data externally unless explicitly opted in.
  **Priority**: High

- [ ] **Issue**: No data retention or deletion policy for AI review results. The `last_result` persists in memory indefinitely across restarts.
  **Location**: `ai/advisor.py:112`
  **Recommendation**: Clear `last_result` after a configurable TTL (e.g., 7 days) and do not persist AI review results to disk. If persistence is needed, encrypt the data at rest.
  **Priority**: Medium

---

## 2. AI Integration Patterns

### 2.1 Separation of Concerns

- [ ] **Issue**: The integration between the AI advisor and the core decision engine is entirely one-directional (advisor reads state, produces suggestions). The decision engine provides no feedback about whether the advisor's suggestions were sound.
  **Location**: `coordinator.py:116`, `ai/advisor.py:109-114`
  **Recommendation**: Create a formal interface (`AdvisoryProvider` protocol) that the advisor implements, allowing the coordinator to inject feedback. The decision engine should record when an accepted suggestion leads to a measurable improvement or degradation, enabling closed-loop learning.
  **Priority**: Medium

- [ ] **Issue**: The advisor has direct access to `coordinator.store` and `coordinator.pool_config`, tightly coupling it to the coordinator's internal structure.
  **Location**: `ai/advisor.py:117-119`
  **Recommendation**: Define a `DataProvider` protocol that exposes only the data the advisor needs. This makes the advisor testable in isolation and decouples it from coordinator internals.
  **Priority**: Medium

- [ ] **Issue**: The advisor runs asynchronously (`async_review`) but there's no scheduling mechanism shown. It appears to be triggered manually or via an external automation.
  **Location**: `ai/advisor.py:164-204`
  **Recommendation**: Add built-in scheduling (e.g., weekly automatic review) with configurable timing. Ensure reviews don't run during heating sessions to avoid conflicting state. Expose the schedule as a configuration option.
  **Priority**: Low

---

## 3. Learning System Quality

### 3.1 Algorithm Soundness

- [ ] **Issue**: The `capped_update` function uses a fixed 15% step ratio (`max_step_ratio`). This is appropriate for preventing outliers from dominating, but means the system is slow to adapt to genuine long-term changes (e.g., heat pump degradation over years, seasonal variations in pool usage).
  **Location**: `core/learning.py:302-308`, `core/config.py:495`
  **Recommendation**: Implement an adaptive step ratio that increases when consecutive sessions consistently indicate the same direction of change (suggesting a genuine trend rather than noise). Consider a two-timescale approach: fast adaptation for clear trends, slow for noisy data.
  **Priority**: High

- [ ] **Issue**: The COP curve uses fixed 5°C buckets with no interpolation between adjacent buckets. At bucket boundaries (e.g., 14.9°C vs 15.1°C), the COP value can jump discontinuously.
  **Location**: `core/learning.py:33-36`, `core/learning.py:311-332`
  **Recommendation**: Implement linear interpolation between adjacent buckets for COP lookup. When the exact bucket has insufficient data, use a weighted average of nearby buckets based on distance, not just the nearest neighbor.
  **Priority**: Medium

- [ ] **Issue**: The `heat_loss_from_idle` function requires a minimum 6-hour idle period and only learns from periods where the cover state didn't change. In practice, many pools rarely have 6+ continuous idle hours, meaning heat loss may never be learned on some installations.
  **Location**: `core/learning.py:335-353`, `coordinator.py:996-997`
  **Recommendation**: Consider shorter idle periods (2-3 hours) with appropriate uncertainty weighting. Shorter periods should update the learned value with a larger uncertainty, but still contribute to the model. Alternatively, use the heating session data itself to infer heat loss (the net rise = gross rise - loss).
  **Priority**: Medium

- [ ] **Issue**: The `recover_cop_counts` function assumes a count of 1 when session data is unavailable, which is described as "enough to show the value exists, not enough to trust it." However, this value sits behind the `COP_CONFIDENCE_SESSIONS = 3` gate, so it will never be used for planning regardless.
  **Location**: `core/learning.py:421-446`, `core/learning.py:357-358`
  **Recommendation**: Either (a) set the recovered count to `COP_CONFIDENCE_SESSIONS - 1` so it's clear the value is provisional and will require additional sessions to become trusted, or (b) implement a separate "legacy" flag that allows planning to use these values with a warning rather than blocking them entirely.
  **Priority**: Medium

### 3.2 Statistical Concerns

- [ ] **Issue**: `COP_CONFIDENCE_SESSIONS = 3` is very low for statistical confidence. Three sessions in a bucket could all be anomalous (e.g., three consecutive cloudy days with unusual usage patterns).
  **Location**: `core/learning.py:357-358`
  **Recommendation**: Increase to 5-8 sessions for full confidence, with a "provisional" tier at 3 sessions that can be used for planning but is flagged as uncertain. Track the variance within each bucket—high variance should require more sessions before the value is trusted.
  **Priority**: High

- [ ] **Issue**: The learning system has no concept of measurement uncertainty. All sensor readings are treated as ground truth, but temperature sensors have ±0.5°C accuracy and flow meters have their own error margins.
  **Location**: `core/learning.py:80-94`
  **Recommendation**: Propagate sensor uncertainty through the learning calculations. When computing a learned value, weight each session's contribution by its estimated measurement precision. Report confidence intervals alongside learned values.
  **Priority**: Medium

- [ ] **Issue**: The `max_plausible_rate` function uses `ASSUMED_PEAK_IRRADIANCE = 600.0` when no solar sensor is available. This is a generous assumption that may allow physically impossible sessions through the filter.
  **Location**: `core/learning.py:248-252`, `core/learning.py:293-296`
  **Recommendation**: Make the assumed irradiance configurable based on geographic location and season. Alternatively, use the Home Assistant weather entity (if configured) to estimate solar irradiance rather than a fixed assumption.
  **Priority**: Medium

- [ ] **Issue**: The `assess` function (all-or-nothing) and `assess_measurements` (granular) are both present, but `assess` is not used in the coordinator's `_finish_session`—only `assess_measurements` is. The dead code path could confuse maintainers.
  **Location**: `core/learning.py:188-241`, `coordinator.py:938-939`
  **Recommendation**: Remove the unused `assess` function or repurpose it as a public API for external validation. Document which function is the canonical assessment path.
  **Priority**: Low

---

## 4. Scalability & Long-Running Installations

### 4.1 Data Retention

- [ ] **Issue**: Learned values (heating_rate_c_per_h, heat_loss_c_per_h, cop_by_air_bucket) never expire or decay. A value learned during the first month of operation persists forever, even if the pool's characteristics change significantly (new heat pump, renovated plumbing, changed usage patterns).
  **Location**: `store.py:61-82`
  **Recommendation**: Implement a recency-weighted decay for learned values. Each learned value should have an associated `last_updated` timestamp. Values not updated within a configurable period (e.g., 90 days) should be flagged as stale and either reset or given reduced confidence. Track the number of contributing sessions as a confidence indicator.
  **Priority**: High

- [ ] **Issue**: The `cop_by_air_bucket` dictionary grows indefinitely as new temperature ranges are encountered. While the number of possible buckets is bounded by the heat pump's operating range (typically -5°C to 43°C = ~10 buckets), the dictionary is never pruned.
  **Location**: `store.py:77`, `core/learning.py:311-332`
  **Recommendation**: Implement bucket pruning: remove buckets that haven't been updated in a configurable period (e.g., 1 year) since they represent conditions that no longer apply or are seasonal extremes that haven't recurred.
  **Priority**: Low

### 4.2 Performance

- [ ] **Issue**: The `_payload()` method iterates through all sessions and decisions to filter by the 7-day cutoff, then slices the result. With the current session log size of 60, this is negligible, but if the log size increases, this could become a bottleneck.
  **Location**: `ai/advisor.py:122-131`, `ai/advisor.py:156-157`
  **Recommendation**: Maintain a separate index of recent sessions (e.g., a deque with a 7-day TTL) that's updated incrementally. This avoids scanning the entire log on each review.
  **Priority**: Low

- [ ] **Issue**: The store's `async_save` method serializes and writes the entire state on every tick (debounced to 10 seconds). As the session log and learned values grow, this file I/O could become noticeable on resource-constrained devices (e.g., Raspberry Pi).
  **Location**: `store.py:195-247`
  **Recommendation**: Implement differential saves: only write changed sections of the state. Track dirty flags for each major section (intervals, learned, session_log, decision_log) and only serialize/save dirty sections.
  **Priority**: Medium

### 4.3 Long-Term Drift

- [ ] **Issue**: There is no mechanism to detect or alert on model drift. If the heat pump degrades over years (lower COP, slower heating), the learned values will gradually follow, but the user is never informed that their equipment may need servicing.
  **Location**: `core/learning.py:311-332`, `core/learning.py:302-308`
  **Recommendation**: Track a long-term trend metric for each learned parameter. When a parameter degrades beyond a threshold (e.g., COP drops 15% over 6 months), generate a notification suggesting equipment maintenance. Store historical snapshots of learned values for trend analysis.
  **Priority**: High

- [ ] **Issue**: The COP curve is bucketed by air temperature but doesn't account for humidity, which significantly affects heat pump efficiency (especially for air-source units). Two days at the same air temperature but different humidity levels can produce different COP values.
  **Location**: `core/learning.py:33-36`
  **Recommendation**: If a humidity sensor is available, include it as a secondary dimension in the COP model. At minimum, note in the session record whether conditions were humid or dry (derived from weather data) to explain COP variance within a bucket.
  **Priority**: Low

---

## 5. Additional Recommendations

### 5.1 Testing & Validation

- [ ] **Issue**: No unit tests are visible for the learning module. The complex validation logic (session assessment, COP bucketing, capped updates) is error-prone and would benefit from comprehensive testing.
  **Location**: `core/learning.py` (entire module)
  **Recommendation**: Add unit tests covering: session assessment edge cases, COP curve interpolation, capped update behavior at boundaries, heat loss calculation with various idle periods, and `recover_cop_counts` with missing data.
  **Priority**: High

### 5.2 Observability

- [ ] **Issue**: The learning system logs at DEBUG level when a session teaches nothing, but there's no structured metric tracking the overall health of the learning model (e.g., percentage of sessions accepted vs. rejected, average confidence of learned values).
  **Location**: `coordinator.py:948-949`
  **Recommendation**: Expose diagnostic sensors for: session acceptance rate, average learned COP confidence, heating rate sample count, heat loss sample count, and model age (time since last update). This helps users and developers understand whether the learning system is functioning.
  **Priority**: Medium

### 5.3 Model Versioning

- [ ] **Issue**: Learned values have no schema version. If the learning algorithm changes significantly (e.g., switching from capped updates to exponential moving average), existing learned values may be incompatible with the new algorithm.
  **Location**: `store.py:61-82`
  **Recommendation**: Add a model version field to the learned values. On load, if the stored model version differs from the current version, either migrate the values or reset them with a clear log message explaining why.
  **Priority**: Medium

---

## Summary of Priority Actions

| Priority | Count | Key Themes |
|----------|-------|-------------|
| **High** | 7 | Data decay/retention, feedback loops, confidence thresholds, privacy tiers, model drift detection, adaptive learning rates |
| **Medium** | 13 | Payload intelligence, interpolation, uncertainty propagation, scheduling, observability, model versioning |
| **Low** | 6 | Dead code cleanup, prompt versioning, bucket pruning, performance optimization |
