/**
 * PoolSmart management panel.
 *
 * Plain custom element, no build step and no external imports, so it keeps
 * working offline -- which is one of the requirements the whole system is built
 * around.
 *
 * This panel is for the person maintaining the system. The simple Lovelace page
 * is for everyone else, and the two are deliberately not the same thing.
 */


/**
 * Panel wording, by language.
 *
 * Entity names are translated by Home Assistant from translations/*.json, so on
 * a Dutch system everything outside this file already reads Dutch. A hardcoded
 * English panel next to Dutch entity names is the actual inconsistency, and the
 * fix is to translate the panel rather than to stop translating the entities:
 * the entity names are what appear on dashboards, in automations and in the
 * logbook, and those should follow the user's language.
 *
 * English is the fallback for any language not listed here, and for any key a
 * translation happens to be missing.
 */
const STRINGS = {
  en: {
    overview: "Overview", planning: "Planning", water: "Water",
    sessions: "Sessions", learning: "Learning", settings: "Settings",
    diagnostics: "Diagnostics",
    ph: "pH", chlorine: "Free chlorine", testEvery: "Test every",
    nextTest: "Next test", overdue: "overdue", days: "days",
    balanced: "Balanced", nothingToAdd: "Nothing to add.",
    doseLog: "Dose log",
    doseLogNote: "What was added, and what it did. Without this, dosing is guessing.",
    when: "When", added: "Added", before: "Before", after: "After",
    effect: "Effect", pending: "pending",
    noChemistry: "No water chemistry configured.",
    aimFirst: (v) =>
      `Aiming for ${v} first — a correction this large overshoots if done in ` +
      `one go. Measure again after an hour.`,
    runningFor: (t) => `Running for ${t}`,
    used: "Used", risePerHour: "Rise per hour", expected: "expected",
    tooEarly: "Too early to judge the rate.",
    whereHeatGoes: "Where the heat goes",
    heatPumpAdds: "Heat pump adds", poolLoses: "Pool loses", net: "Net",
    cover: "Cover", coverOn: "on", coverOff: "off",
    notConfigured: "not configured",
  },
  nl: {
    overview: "Overzicht", planning: "Planning", water: "Water",
    sessions: "Sessies", learning: "Leren", settings: "Instellingen",
    diagnostics: "Diagnose",
    ph: "pH", chlorine: "Vrij chloor", testEvery: "Meten elke",
    nextTest: "Volgende meting", overdue: "te laat", days: "dagen",
    balanced: "In balans", nothingToAdd: "Niets toe te voegen.",
    doseLog: "Doseerlogboek",
    doseLogNote:
      "Wat er is toegevoegd, en wat het deed. Zonder dit blijft doseren gokken.",
    when: "Wanneer", added: "Toegevoegd", before: "Voor", after: "Na",
    effect: "Effect", pending: "nog niet gemeten",
    noChemistry: "Geen waterchemie ingesteld.",
    aimFirst: (v) =>
      `Eerst naar ${v} — een correctie van deze grootte schiet in één keer ` +
      `door. Meet na een uur opnieuw.`,
    runningFor: (t) => `${t} bezig`,
    used: "Verbruikt", risePerHour: "Stijging per uur", expected: "verwacht",
    tooEarly: "Nog te vroeg om de stijging te beoordelen.",
    whereHeatGoes: "Waar de warmte blijft",
    heatPumpAdds: "Warmtepomp levert", poolLoses: "Bad verliest", net: "Netto",
    cover: "Afdekhoes", coverOn: "ligt erop", coverOff: "eraf",
    notConfigured: "niet ingesteld",
  },
};

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "planning", label: "Planning" },
  { id: "water", label: "Water" },
  { id: "sessions", label: "Sessions" },
  { id: "learning", label: "Learning" },
  { id: "settings", label: "Settings" },
  { id: "diagnostics", label: "Diagnostics" },
];

const BRANCH_COLOURS = {
  EMERGENCY_STOP: "#c62828",
  FROST_PROTECTION: "#1565c0",
  MANUAL: "#6a1b9a",
  CHEMISTRY: "#00838f",
  FILTRATION_DEADLINE: "#ef6c00",
  FREE_POWER: "#2e7d32",
  HEATING: "#f57c00",
  FILTRATION_BLOCK: "#0277bd",
  PUMP_RUNDOWN: "#546e7a",
  IDLE: "#78909c",
};


const VERDICT_STYLE = {
  won: { colour: "#2e7d32", label: "chosen" },
  price: { colour: "#ef6c00", label: "price" },
  envelope: { colour: "#c62828", label: "outside limits" },
  mode: { colour: "#6a1b9a", label: "mode" },
  night: { colour: "#37474f", label: "night" },
  not_applicable: { colour: "#b0bec5", label: "n/a" },
  not_reached: { colour: "#cfd8dc", label: "not reached" },
};

const fmtTime = (iso) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—";

const fmtDateTime = (iso) =>
  iso
    ? new Date(iso).toLocaleString([], {
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";

/**
 * Durations, written the way someone would say them.
 *
 * "0.78 h" is a number you have to convert before it means anything. Under an
 * hour, minutes are the natural unit; above it, hours and minutes together.
 */
const fmtHours = (h) => {
  if (h === null || h === undefined) return "—";
  const total = Math.round(Number(h) * 60);
  if (total === 0) return "0 min";
  if (total < 60) return `${total} min`;
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`;
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
  );

class PoolSmartPanel extends HTMLElement {
  /** Translate one key, falling back to English per key. */
  t(key, ...args) {
    const lang = (this._hass && this._hass.language ? this._hass.language : "en")
      .split("-")[0];
    const table = STRINGS[lang] || STRINGS.en;
    const value = table[key] !== undefined ? table[key] : STRINGS.en[key];
    return typeof value === "function" ? value(...args) : value;
  }

  constructor() {
    super();
    this._tab = "overview";
    this._snapshot = null;
    this._error = null;
    this._timer = null;
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._snapshot) this._refresh();
  }

  connectedCallback() {
    this._render();
    this._timer = setInterval(() => this._refresh(), 15000);
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
  }

  async _refresh() {
    if (!this._hass) return;
    try {
      this._snapshot = await this._hass.connection.sendMessagePromise({
        type: "poolsmart/snapshot",
      });
      this._error = null;
    } catch (err) {
      this._error = err && err.message ? err.message : "Could not load pool data";
    }
    this._render();
  }

  async _callService(domain, service, data) {
    await this._hass.callService(domain, service, data);
    setTimeout(() => this._refresh(), 800);
  }

  _render() {
    const s = this._snapshot;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:16px; font-family: var(--paper-font-body1_-_font-family, sans-serif);
                color: var(--primary-text-color, #212121); background: var(--primary-background-color, #fafafa); }
        h1 { font-size:22px; margin:0 0 4px; }
        .sub { color: var(--secondary-text-color,#666); margin-bottom:16px; font-size:14px; }
        nav { display:flex; gap:4px; flex-wrap:wrap; margin-bottom:16px; border-bottom:1px solid var(--divider-color,#e0e0e0); }
        nav button { background:none; border:none; padding:10px 14px; cursor:pointer; font-size:14px;
                     color: var(--secondary-text-color,#666); border-bottom:2px solid transparent; }
        nav button.active { color: var(--primary-color,#03a9f4); border-bottom-color: var(--primary-color,#03a9f4); }
        .card { background: var(--card-background-color,#fff); border-radius:12px; padding:16px; margin-bottom:16px;
                box-shadow:0 1px 3px rgba(0,0,0,.12); }
        .row { display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--divider-color,#f0f0f0); }
        .row:last-child { border-bottom:none; }
        .row span:first-child { color: var(--secondary-text-color,#666); }
        .big { font-size:40px; font-weight:300; }
        .badge { display:inline-block; padding:3px 10px; border-radius:12px; color:#fff; font-size:12px; }
        .reason { margin-top:8px; line-height:1.5; }
        table { width:100%; border-collapse:collapse; font-size:13px; }
        th,td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--divider-color,#f0f0f0); vertical-align:top; }
        th { color: var(--secondary-text-color,#666); font-weight:500; }
        .bar { height:8px; border-radius:4px; background: var(--divider-color,#e0e0e0); overflow:hidden; margin-top:6px; }
        .bar > div { height:100%; background: var(--primary-color,#03a9f4); }
        .warn { color:#c62828; }
        .muted { color: var(--secondary-text-color,#888); }
        button.action { background: var(--primary-color,#03a9f4); color:#fff; border:none; border-radius:8px;
                        padding:8px 14px; cursor:pointer; margin-right:8px; font-size:14px; }
        .slot { display:flex; justify-content:space-between; padding:4px 0; font-size:13px; }
      </style>
      <h1>${esc(s ? s.title : "PoolSmart")}</h1>
      <div class="sub">${
        this._error ? `<span class="warn">${esc(this._error)}</span>` : esc(s ? s.decision?.reason ?? "" : "Loading…")
      }</div>
      <nav>${TABS.map(
        (t) =>
          `<button data-tab="${t.id}" class="${
            this._tab === t.id ? "active" : ""
          }">${esc(this.t(t.id) || t.label)}</button>`
      ).join("")}</nav>
      <div id="content">${s ? this._renderTab(s) : ""}</div>
    `;

    this.shadowRoot.querySelectorAll("nav button").forEach((b) =>
      b.addEventListener("click", () => {
        this._tab = b.dataset.tab;
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-service]").forEach((b) =>
      b.addEventListener("click", () => {
        const [domain, service] = b.dataset.service.split(".");
        this._callService(domain, service, JSON.parse(b.dataset.payload || "{}"));
      })
    );
  }

  _renderTab(s) {
    switch (this._tab) {
      case "planning":
        return this._planning(s);
      case "water":
        return this._water(s);
      case "sessions":
        return this._sessions(s);
      case "learning":
        return this._learning(s);
      case "settings":
        return this._settings(s);
      case "diagnostics":
        return this._diagnostics(s);
      default:
        return this._overview(s);
    }
  }

  _overview(s) {
    const d = s.decision || {};
    const colour = BRANCH_COLOURS[d.branch] || "#78909c";
    const f = s.filtration;
    const pct = f && f.required_h ? Math.min(100, (f.done_h / f.required_h) * 100) : 0;

    return `
      <div class="card">
        <div class="big">${s.water_temp !== null ? s.water_temp.toFixed(1) : "—"} °C</div>
        <div class="muted">target ${s.target_temp} °C &middot; outdoors ${
      s.air_temp !== null ? s.air_temp.toFixed(1) : "—"
    } °C</div>
        <div class="reason">
          <span class="badge" style="background:${colour}">${esc(d.branch || "—")}</span>
          <div style="margin-top:8px">${esc(d.reason || "")}</div>
        </div>
        <div class="row" style="margin-top:12px"><span>Pump</span><span>${d.pump ? "running" : "off"}</span></div>
        <div class="row"><span>Heat pump</span><span>${d.heat_pump ? "running" : "off"}</span></div>
        <div class="row"><span>Held until</span><span>${fmtTime(d.hold_until)}</span></div>
      </div>

      ${this._sessionCard(s)}
      ${this._balanceCard(s)}
      ${
        !s.heat_pump_available
          ? `<div class="card"><strong class="warn">Heating unavailable</strong>
             <div class="reason">${esc(s.heat_pump_gate_reason)}</div></div>`
          : ""
      }

      ${
        s.faults.length
          ? `<div class="card"><strong class="warn">Faults</strong>${s.faults
              .map((x) => `<div class="reason">[${esc(x.severity)}] ${esc(x.message)}</div>`)
              .join("")}</div>`
          : ""
      }

      <div class="card">
        <strong>Filtration today</strong>
        <div class="row"><span>Required</span><span>${fmtHours(f?.required_h)}</span></div>
        <div class="row"><span>Completed</span><span>${fmtHours(f?.done_h)}</span></div>
        <div class="row"><span>Remaining</span><span>${fmtHours(f?.remaining_h)}</span></div>
        <div class="row"><span>Window left</span><span>${fmtHours(f?.available_h)}</span></div>
        <div class="row"><span>Set by</span><span>${
          s.derived.filtration_driver === "turnover"
            ? `turnover (${s.derived.turnover_factor}\u00d7 volume)`
            : `daily minimum at ${s.water_temp !== null ? s.water_temp.toFixed(0) : "?"} \u00b0C`
        }</span></div>
        <div class="bar"><div style="width:${pct}%"></div></div>
        ${
          f?.deadline_critical
            ? `<div class="reason warn">Deadline critical: circulating regardless of price.</div>`
            : ""
        }
      </div>

      <div class="card">
        <strong>Energy today</strong>
        <div class="row"><span>Consumed</span><span>${s.energy.today_kwh} kWh</span></div>
        <div class="row"><span>Cost</span><span>${s.energy.cost_today}</span></div>
        <div class="row"><span>Saved by timing</span><span>${s.energy.saved_today}</span></div>
      </div>
    `;
  }

  _sessionCard(s) {
    const x = s.session;
    if (!x || !x.running) return "";
    const span = x.target_temp - x.start_temp;
    const done = span > 0 ? ((x.current_temp - x.start_temp) / span) * 100 : 100;
    const verdictColour = (x.verdict || "").startsWith("behind")
      ? "#c62828"
      : "#2e7d32";
    return `<div class="card">
      <strong>${esc(this.t("runningFor", x.elapsed_readable))}</strong>
      <div class="bar" style="margin-top:10px"><div style="width:${Math.max(
        0,
        Math.min(100, done)
      )}%"></div></div>
      <div class="row"><span>${x.start_temp} → ${x.target_temp} °C</span>
        <span>${x.current_temp} °C (${x.gain > 0 ? "+" : ""}${x.gain})</span></div>
      <div class="row"><span>${esc(this.t("used"))}</span><span>${x.energy_kwh} kWh · ${x.cost}</span></div>
      ${
        x.actual_rate_c_per_h
          ? `<div class="row"><span>${esc(this.t("risePerHour"))}</span><span>${
              x.actual_rate_c_per_h
            } / ${x.expected_rate_c_per_h} ${esc(this.t("expected"))}</span></div>
             <div class="reason" style="color:${verdictColour}">${esc(x.verdict)}</div>`
          : `<div class="reason muted">${esc(this.t("tooEarly"))}</div>`
      }
    </div>`;
  }

  _balanceCard(s) {
    const b = s.heat_balance;
    if (!b || !b.gross_rise_c_per_h) return "";
    return `<div class="card">
      <strong>${esc(this.t("whereHeatGoes"))}</strong>
      <div class="bar" style="margin-top:10px;display:flex">
        <div style="width:${b.kept_percent}%;background:#2e7d32"></div>
        <div style="width:${b.lost_percent}%;background:#c62828"></div>
      </div>
      <div class="row"><span>${esc(this.t("heatPumpAdds"))}</span><span>${b.gross_rise_c_per_h} °C/h</span></div>
      <div class="row"><span>${esc(this.t("poolLoses"))}</span><span>${b.loss_c_per_h} °C/h</span></div>
      <div class="row"><span><b>${esc(this.t("net"))}</b></span><span><b>${b.net_rise_c_per_h} °C/h</b></span></div>
      <div class="row"><span>${esc(this.t("cover"))}</span><span>${esc(
        b.covered === null || b.covered === undefined
          ? this.t("notConfigured")
          : b.covered
          ? this.t("coverOn")
          : this.t("coverOff")
      )}</span></div>
      ${b.advice ? `<div class="reason">${esc(b.advice)}</div>` : ""}
    </div>`;
  }

  _planning(s) {
    const p = s.plan;
    if (!p) return `<div class="card muted">No plan yet. It appears once water and outdoor temperature are known.</div>`;
    const seasonal = p.mode === "seasonal";
    return `
      <div class="card">
        <strong>${seasonal ? "Seasonal warm-up" : "Maintenance"}</strong>
        <div class="reason">${esc(p.reason)}</div>
        <div class="row"><span>Hours needed</span><span>${fmtHours(p.hours_needed)}</span></div>
        <div class="row"><span>Hours planned</span><span>${fmtHours(p.hours_planned)}</span></div>
        <div class="row"><span>Expected cost</span><span>${p.expected_cost ?? "—"}</span></div>
        <div class="row"><span>${seasonal ? "Expected ready" : "Ready at"}</span>
          <span>${seasonal ? fmtDateTime(p.ready_at) : fmtTime(p.ready_at)}</span></div>
        ${
          seasonal
            ? `<div class="reason muted">A warm-up of this size does not fit in one day of cheap
               hours, so this is a date rather than a time.</div>`
            : ""
        }
      </div>
      <div class="card">
        <strong>Chosen intervals</strong>
        ${
          p.slots.length
            ? p.slots
                .map(
                  (x) =>
                    `<div class="slot"><span>${fmtTime(x.start)} – ${fmtTime(x.end)}</span><span>${x.price.toFixed(
                      3
                    )}</span></div>`
                )
                .join("")
            : `<div class="muted">None.</div>`
        }
      </div>
      <div class="card">
        <strong>Filtration blocks</strong>
        <div class="row"><span>Active</span><span>${
          s.filtration?.active_block
            ? `${fmtTime(s.filtration.active_block.start)} – ${fmtTime(s.filtration.active_block.end)}`
            : "none"
        }</span></div>
        <div class="row"><span>Next</span><span>${
          s.filtration?.next_block
            ? `${fmtTime(s.filtration.next_block.start)} – ${fmtTime(s.filtration.next_block.end)}`
            : "none"
        }</span></div>
        <div class="reason muted">${esc(
          s.filtration?.next_block?.rationale || s.filtration?.active_block?.rationale || ""
        )}</div>
      </div>
    `;
  }

  _water(s) {
    const w = s.chemistry;
    if (!w) return `<div class="card muted">${esc(this.t("noChemistry"))}</div>`;
    const dose = (d) =>
      d
        ? `<div class="card">
             <div class="big" style="font-size:24px">${d.amount} ${esc(d.unit)}</div>
             <div class="muted">${esc(d.label)}</div>
             <div class="reason">${esc(d.reason)}</div>
             ${
               d.partial
                 ? `<div class="reason" style="color:#ef6c00">${esc(
                     this.t("aimFirst", d.aiming_for)
                   )}</div>`
                 : ""
             }
             <div class="reason muted">${esc(d.instructions)}</div>
           </div>`
        : "";

    return `
      <div class="card">
        <div class="row"><span>${esc(this.t("ph"))}</span><span>${
          w.ph ?? "—"
        }</span></div>
        <div class="row"><span>${esc(this.t("chlorine"))}</span><span>${
          w.chlorine ?? "—"
        } mg/L</span></div>
        <div class="row"><span>${esc(this.t("testEvery"))}</span><span>${
          w.test_interval_days
        } ${esc(this.t("days"))}</span></div>
        <div class="row"><span>${esc(this.t("nextTest"))}</span><span>${
          w.test_overdue ? esc(this.t("overdue")) : fmtDateTime(w.test_due_at)
        }</span></div>
        <div class="reason muted">${esc(w.test_interval_reason)}</div>
      </div>
      ${dose(w.ph_dose)}
      ${dose(w.chlorine_dose)}
      ${
        !w.ph_dose && !w.chlorine_dose && (w.ph || w.chlorine)
          ? `<div class="card"><strong>${esc(this.t("balanced"))}</strong>
             <div class="reason muted">${esc(this.t("nothingToAdd"))}</div></div>`
          : ""
      }
      ${
        (w.dose_log || []).length
          ? `<div class="card"><strong>${esc(this.t("doseLog"))}</strong>
             <div class="reason muted">${esc(this.t("doseLogNote"))}</div>
             <table>
               <tr><th>${esc(this.t("when"))}</th><th>${esc(
                 this.t("added")
               )}</th><th>${esc(this.t("before"))}</th><th>${esc(
                 this.t("after")
               )}</th><th>${esc(this.t("effect"))}</th></tr>
               ${w.dose_log
                 .map(
                   (d) => `<tr>
                   <td>${fmtDateTime(d.at)}</td>
                   <td>${d.amount} ${esc(d.unit)} ${esc(d.product)}</td>
                   <td>${d.measured_before ?? "—"}</td>
                   <td>${d.measured_after ?? esc(this.t("pending"))}</td>
                   <td>${
                     d.actual_change !== null && d.actual_change !== undefined
                       ? `${d.actual_change > 0 ? "+" : ""}${d.actual_change}`
                       : "—"
                   }</td></tr>`
                 )
                 .join("")}
             </table></div>`
          : ""
      }`;
  }

  _sessions(s) {
    if (!s.session_log.length)
      return `<div class="card muted">No finished heating sessions yet.</div>`;
    return `<div class="card"><table>
      <tr><th>Started</th><th>Duration</th><th>Gain</th><th>COP</th><th>Used</th></tr>
      ${s.session_log
        .map(
          (x) => `<tr>
            <td>${fmtDateTime(x.start)}</td>
            <td>${Number(x.duration_h).toFixed(2)} h</td>
            <td>${
              x.water_start !== null && x.water_end !== null
                ? `${(x.water_end - x.water_start).toFixed(2)} °C`
                : "—"
            }</td>
            <td>${x.measured_cop ?? "—"}</td>
            <td>${x.usable ? "yes" : `<span class="muted">${esc(x.verdict)}</span>`}</td>
          </tr>`
        )
        .join("")}
    </table></div>`;
  }

  _learning(s) {
    const insight = s.learning_insight || [];
    if (insight.length) {
      return `
        <div class="card">
          <strong>What has been learned, and what reads it</strong>
          <div class="reason muted">A value nobody reads is not knowledge, it is
            storage. Each line names the decision that uses it.</div>
        </div>
        ${insight
          .map(
            (v) => `<div class="card">
            <div class="row"><span><b>${esc(v.key.replace(/_/g, " "))}</b></span>
              <span class="badge" style="background:${
                v.in_use ? "#2e7d32" : "#78909c"
              }">${v.in_use ? "in use" : "not yet used"}</span></div>
            <div class="row"><span>Value</span><span>${
              v.value === null || v.value === undefined
                ? "not learned yet"
                : `${v.value} ${esc(v.unit || "")}`
            }</span></div>
            ${
              v.fallback !== null && v.fallback !== undefined
                ? `<div class="row"><span>Falls back to</span><span>${v.fallback}</span></div>`
                : ""
            }
            ${
              v.sessions !== undefined
                ? `<div class="row"><span>Sessions behind it</span><span>${v.sessions}${
                    v.confidence ? ` — ${esc(v.confidence)}` : ""
                  }</span></div>`
                : ""
            }
            <div class="reason muted">Used for ${esc(v.used_for)}.</div>
          </div>`
          )
          .join("")}
        ${this._legacyLearning(s)}`;
    }
    return this._legacyLearning(s);
  }

  _legacyLearning(s) {
    const l = s.learned;
    const buckets = Object.entries(l.cop_by_air_bucket || {});
    return `
      <div class="card">
        <div class="row"><span>Sessions learned from</span><span>${l.session_count}</span></div>
        <div class="row"><span>Heating rate</span><span>${
          l.heating_rate_c_per_h ?? "not learned yet"
        }</span></div>
        <div class="row"><span>Heat loss</span><span>${
          l.heat_loss_c_per_h ?? "not learned yet"
        }</span></div>
        <div class="row"><span>Measured flow</span><span>${
          l.measured_flow_m3h ?? "—"
        }</span></div>
      </div>
      <div class="card">
        <strong>COP by outdoor temperature</strong>
        ${
          buckets.length
            ? `<table><tr><th>Air</th><th>COP</th></tr>${buckets
                .map(([k, v]) => `<tr><td>${esc(k)} °C</td><td>${v}</td></tr>`)
                .join("")}</table>`
            : `<div class="muted">Nothing measured yet. Until then the curve from the
               datasheet is used, which is less accurate but perfectly workable.</div>`
        }
      </div>
      ${this._advisorCard(s)}
      <div class="card">
        <button class="action" data-service="button.press"
          data-payload='{"entity_id":"button.pool_reset_learned_values"}'>Reset learned values</button>
        <div class="reason muted">Updates are capped, so a single odd session cannot move a
          value far. Resetting is only needed after changing hardware.</div>
      </div>
    `;
  }

  _advisorCard(s) {
    const a = s.advisor;
    if (!a) return "";
    if (a.error)
      return `<div class="card"><strong>Review</strong>
        <div class="reason warn">${esc(a.error)}</div>
        <div class="reason muted">Suggestions are advisory only; nothing is applied
          without pressing accept, and the pool runs the same either way.</div></div>`;
    if (!a.summary && !(a.suggestions || []).length)
      return `<div class="card"><strong>Review</strong>
        <div class="reason muted">No review has been run yet. Press "Ask for a review"
          to have the past week looked over.</div></div>`;
    return `<div class="card">
      <strong>Review${a.last_run ? ` &middot; ${fmtDateTime(a.last_run)}` : ""}</strong>
      <div class="reason">${esc(a.summary)}</div>
      ${(a.observations || []).map((o) => `<div class="reason muted">&bull; ${esc(o)}</div>`).join("")}
      ${(a.suggestions || [])
        .map(
          (x) =>
            `<div class="row"><span>${esc(x.setting)} &rarr; ${esc(x.value)}</span>
             <span class="muted">${esc(x.why)}</span></div>`
        )
        .join("")}
    </div>`;
  }

  _settings(s) {
    const d = s.derived;
    return `
      <div class="card">
        <strong>Derived from your setup</strong>
        <div class="row"><span>Pool volume</span><span>${d.volume_l} L</span></div>
        <div class="row"><span>Effective flow</span><span>${d.effective_flow_m3h} m³/h</span></div>
        <div class="row"><span>Turnover factor</span><span>${d.turnover_factor} × per day</span></div>
        <div class="row"><span>Turnover requirement</span><span>${fmtHours(d.turnover_hours)}</span></div>
        <div class="row"><span>Daily minimum now</span><span>${fmtHours(d.min_hours)}</span></div>
        <div class="row"><span><b>Filtration per day</b></span><span><b>${fmtHours(
          d.daily_filtration_hours
        )}</b></span></div>
        <div class="row"><span>Per block</span><span>${fmtHours(d.block_hours)}</span></div>
        <div class="reason muted">The requirement is the larger of the two. Turnover is
          volume-based: because filtered water mixes back in, one turnover cleans about
          63% of the pool, three about 95%. The daily minimum is time-based — a skimmer
          only catches what lands on the surface while it is running, and water that sits
          still grows algae however well it was filtered earlier. It rises with water
          temperature.</div>
        <div class="row"><span>Energy per degree</span><span>${d.kwh_thermal_per_degree} kWh</span></div>
      </div>
      <div class="card">
        <strong>Changing settings</strong>
        <div class="reason">Settings live in the integration itself, under
          Settings → Devices &amp; Services → PoolSmart → Configure. Keeping them in one
          place avoids a second copy that can drift out of step.</div>
      </div>
      ${
        s.disabled_capabilities.length
          ? `<div class="card"><strong>Switched off</strong>
             <div class="reason muted">These features are inactive because their entity was
             left blank at setup: ${s.disabled_capabilities.map(esc).join(", ")}.</div></div>`
          : ""
      }
    `;
  }

  _traceCard(s) {
    const trace = s.trace || [];
    if (!trace.length) return "";
    return `<div class="card">
      <strong>This tick, branch by branch</strong>
      <div class="reason muted">The ladder is walked top to bottom. The first branch
        that matches decides; everything below it is never evaluated.</div>
      <table>
        ${trace
          .map((t) => {
            const style = VERDICT_STYLE[t.verdict] || VERDICT_STYLE.not_applicable;
            return `<tr>
              <td style="width:28px" class="muted">${t.number}</td>
              <td>${esc(t.branch.replace(/_/g, " ").toLowerCase())}</td>
              <td style="width:110px"><span class="badge" style="background:${
                style.colour
              }">${style.label}</span></td>
              <td class="muted">${esc(t.detail || "")}</td>
            </tr>`;
          })
          .join("")}
      </table>
    </div>`;
  }

  _diagnostics(s) {
    return `
      ${
        (s.blocked_by || []).length
          ? `<div class="card"><strong>Wanted to, but could not</strong>
             ${s.blocked_by
               .map((b) => `<div class="reason">${esc(b)}</div>`)
               .join("")}
             <div class="reason muted">These branches would have run. This is the
               answer to "why is it not heating".</div></div>`
          : ""
      }
      ${this._traceCard(s)}
      ${
        (s.branch_time_today || []).length
          ? `<div class="card"><strong>Today, by branch</strong>
             <div class="reason muted">How much of the day each branch spent in
               charge. One branch taking most of it usually points at a
               measurement, not a setting.</div>
             ${s.branch_time_today
               .map(
                 (b) => `<div class="row"><span>${esc(
                   b.branch.replace(/_/g, " ").toLowerCase()
                 )}</span><span>${fmtHours(b.seconds / 3600)} · ${(
                   b.share * 100
                 ).toFixed(0)}%</span></div>`
               )
               .join("")}</div>`
          : ""
      }
      ${
        s.last_error || Object.keys(s.subsystem_errors || {}).length
          ? `<div class="card"><strong class="warn">Errors</strong>
             ${s.last_error ? `<div class="reason">${esc(s.last_error)}</div>` : ""}
             ${Object.entries(s.subsystem_errors || {})
               .map(([k, v]) => `<div class="reason muted">${esc(k)} failed at ${fmtTime(v)}</div>`)
               .join("")}
             <div class="reason muted">Control continues without the failed part; the
               details are in the Home Assistant log.</div></div>`
          : ""
      }
      <div class="card">
        <strong>Decision log</strong>
        <div class="reason muted">Recorded at the moment of deciding, newest first.</div>
        <table>
          <tr><th>Time</th><th>Branch</th><th>P</th><th>HP</th><th>Reason</th></tr>
          ${s.decision_log
            .map(
              (x) => `<tr>
              <td>${fmtTime(x.at)}${
                x.duration_seconds
                  ? `<div class="muted" style="font-size:11px">+${(
                      x.duration_seconds / 60
                    ).toFixed(0)}m</div>`
                  : ""
              }</td>
              <td><span class="badge" style="background:${
                BRANCH_COLOURS[x.branch] || "#78909c"
              }">${esc(x.branch)}</span></td>
              <td>${x.pump ? "on" : "—"}</td>
              <td>${x.heat_pump ? "on" : "—"}</td>
              <td>${esc(x.reason)}</td></tr>`
            )
            .join("")}
        </table>
      </div>
    `;
  }
}

customElements.define("poolsmart-panel", PoolSmartPanel);
