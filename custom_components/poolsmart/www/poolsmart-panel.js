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

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "planning", label: "Planning" },
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

const fmtHours = (h) => (h === null || h === undefined ? "—" : `${Number(h).toFixed(2)} h`);

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (ch) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])
  );

class PoolSmartPanel extends HTMLElement {
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
          `<button data-tab="${t.id}" class="${this._tab === t.id ? "active" : ""}">${t.label}</button>`
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

  _diagnostics(s) {
    return `
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
              <td>${fmtTime(x.at)}</td>
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
