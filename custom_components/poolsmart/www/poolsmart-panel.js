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
    nearMisses: "What it ran into",
    nearMissesNote:
      "Branches that wanted to run today, and what stopped them. Twenty refusals " +
      "on price is a setting worth revisiting; one is a passing expensive hour.",
    onSchedule: "On schedule",
    previousSessions: "Previous sessions",
    duration: "Duration", gain: "Gain",
    usedFor: "Used for", resetThis: "Reset this value",
    readings: "Readings", combinedChlorine: "Combined chlorine",
    whatItMeans: "What this means together", circulate: "Circulate for",
    target: "target", outdoors: "outdoors",
    reviewAuto: "Auto", reviewInclude: "Include", reviewExclude: "Exclude",
    needsReview: "worth a look",
    reviewHint:
      "Auto leaves the automatic verdict in charge. Include/Exclude override " +
      "it and take effect immediately -- the heating rate and COP curve are " +
      "recomputed from every session that currently counts.",
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
    nearMisses: "Waar het op afketste",
    nearMissesNote:
      "Takken die vandaag wilden draaien, en wat ze tegenhield. Twintig keer " +
      "afketsen op prijs is een instelling om te heroverwegen; één keer is een " +
      "duur uurtje.",
    onSchedule: "Op schema",
    previousSessions: "Vorige sessies",
    duration: "Duur", gain: "Winst",
    usedFor: "Gebruikt voor", resetThis: "Deze waarde wissen",
    readings: "Metingen", combinedChlorine: "Gebonden chloor",
    whatItMeans: "Wat dit samen betekent", circulate: "Laat circuleren",
    target: "doel", outdoors: "buiten",
    reviewAuto: "Auto", reviewInclude: "Meetellen", reviewExclude: "Uitsluiten",
    needsReview: "even bekijken",
    reviewHint:
      "Auto laat het automatische oordeel gelden. Meetellen/Uitsluiten overrulen " +
      "dat en gelden meteen -- de stijgsnelheid en COP-curve worden herberekend " +
      "uit alle sessies die op dat moment meetellen.",
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

const fmtBytes = (n) => {
  if (n === null || n === undefined) return "—";
  const num = Number(n);
  if (num < 1024) return `${num} B`;
  if (num < 1024 * 1024) return `${(num / 1024).toFixed(1)} kB`;
  return `${(num / (1024 * 1024)).toFixed(2)} MB`;
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
    this._loading = true;
    this._refreshing = false;
    this._timer = null;
    this._storageStats = null;
    this._storageStatsLoading = false;
    this._maintStatus = "";
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
    this._refreshing = true;
    this._render();
    try {
      this._snapshot = await this._hass.connection.sendMessagePromise({
        type: "poolsmart/snapshot",
      });
      this._error = null;
      this._loading = false;
    } catch (err) {
      this._error = err && err.message ? err.message : "Could not load pool data";
      this._loading = false;
    }
    this._refreshing = false;
    this._render();
  }

  async _loadStorageStats() {
    if (!this._hass || this._storageStatsLoading) return;
    this._storageStatsLoading = true;
    try {
      this._storageStats = await this._hass.connection.sendMessagePromise({
        type: "poolsmart/storage_stats",
      });
    } catch (err) {
      this._storageStats = { error: err && err.message ? err.message : "Could not load" };
    }
    this._storageStatsLoading = false;
    this._render();
  }

  async _callService(domain, service, data) {
    const btn = this.shadowRoot.querySelector(`[data-service="${domain}.${service}"][data-payload='${data ? JSON.stringify(data) : "{}"}']`);
    if (btn) {
      btn.setAttribute("aria-busy", "true");
      btn.disabled = true;
      btn.style.opacity = "0.6";
    }
    try {
      await this._hass.callService(domain, service, data);
      setTimeout(() => this._refresh(), 800);
    } finally {
      if (btn) {
        btn.removeAttribute("aria-busy");
        btn.disabled = false;
        btn.style.opacity = "";
      }
    }
  }

  _render() {
    const s = this._snapshot;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:16px; font-family: var(--paper-font-body1_-_font-family, sans-serif);
                color: var(--primary-text-color, #212121); background: var(--primary-background-color, #fafafa); }
        h1 { font-size:22px; margin:0 0 4px; }
        .sub { color: var(--secondary-text-color,#666); margin-bottom:16px; font-size:14px; }
        .sub .refreshing { opacity:.5; }
        nav { display:flex; gap:4px; flex-wrap:wrap; margin-bottom:16px; border-bottom:1px solid var(--divider-color,#e0e0e0); }
        nav button { background:none; border:none; padding:10px 14px; cursor:pointer; font-size:14px;
                     color: var(--secondary-text-color,#666); border-bottom:2px solid transparent;
                     transition: color .15s, border-color .15s; }
        nav button:hover { color: var(--primary-text-color,#212121); }
        nav button:focus-visible { outline: 2px solid var(--primary-color,#03a9f4); outline-offset: 2px; border-radius: 4px; }
        nav button.active { color: var(--primary-color,#03a9f4); border-bottom-color: var(--primary-color,#03a9f4); }
        .card { background: var(--card-background-color,#fff); border-radius:14px; padding:16px; margin-bottom:12px;
                box-shadow:0 1px 3px rgba(0,0,0,.12); }
        .card:focus-within { box-shadow: 0 2px 6px rgba(0,0,0,.18); }
        .skeleton { background: linear-gradient(90deg, var(--divider-color,#eee) 25%, var(--card-background-color,#fff) 50%, var(--divider-color,#eee) 75%);
                    background-size: 200% 100%; animation: shimmer 1.5s infinite; border-radius: 8px; }
        @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        .skeleton-title { height: 20px; width: 40%; margin-bottom: 12px; }
        .skeleton-line { height: 14px; margin-bottom: 8px; }
        .skeleton-line:last-child { width: 70%; }
        .skeleton-temp { height: 48px; width: 50%; margin-bottom: 8px; }
        .skeleton-nav { height: 36px; width: 100%; margin-bottom: 16px; }
        .error-banner { background: color-mix(in srgb, #c62828 12%, var(--card-background-color,#fff));
                        border: 1px solid color-mix(in srgb, #c62828 30%, transparent);
                        border-radius: 14px; padding: 14px 16px; margin-bottom: 12px; }
        .error-banner .error-title { color: #c62828; font-weight: 600; margin-bottom: 4px; }
        .error-banner .error-detail { color: var(--secondary-text-color,#666); font-size: 13px; }
        .error-banner button { margin-top: 8px; background: var(--primary-color,#03a9f4); color: #fff;
                               border: none; border-radius: 6px; padding: 6px 12px; cursor: pointer; font-size: 13px; }
        .error-banner button:focus-visible { outline: 2px solid var(--primary-text-color,#212121); outline-offset: 2px; }
        .empty-state { text-align: center; padding: 32px 16px; color: var(--secondary-text-color,#888); }
        .empty-state .empty-icon { font-size: 32px; margin-bottom: 8px; opacity: .5; }
        /* Direction A: dense monospace readouts, for the tabs meant for reading
           closely rather than glancing at. */
        .mono { font-family: ui-monospace,"IBM Plex Mono",Menlo,monospace; }
        .dense { display:grid; gap:0; }
        .dense .d { display:grid; grid-template-columns:1fr auto 74px; gap:10px;
                    align-items:center; padding:8px 0;
                    border-bottom:1px solid var(--divider-color,#eee); font-size:12.5px; }
        .dense .d:last-child { border-bottom:none; }
        .dense .dk { color: var(--secondary-text-color,#777); font-size:10px;
                     letter-spacing:.07em; text-transform:uppercase; }
        .dense .dv { font-family: ui-monospace,monospace; font-weight:600; text-align:right; }
        .spark { height:15px; display:flex; align-items:flex-end; gap:1.5px; }
        .spark i { flex:1; background: var(--primary-color,#03a9f4); opacity:.35; border-radius:1px; }
        .spark i.hi { opacity:1; }
        /* Direction B: the hero block and the ring. */
        /* The hero has to follow the theme rather than impose one. A fixed
           navy block looked right in a dark mockup and wrong on a light Home
           Assistant, which is most installations. Tinting the accent colour
           gives the same emphasis in either. */
        .hero { border-radius:14px; padding:18px; margin-bottom:12px;
                background: color-mix(in srgb, var(--primary-color,#03a9f4) 12%,
                            var(--card-background-color,#fff));
                border:1px solid color-mix(in srgb, var(--primary-color,#03a9f4) 28%,
                            transparent);
                color: var(--primary-text-color,#212121); }
        .hero .ht { font-size:38px; font-weight:600; line-height:1;
                    color: var(--primary-text-color,#212121); }
        .hero .hs { color: var(--secondary-text-color,#666); font-size:14px;
                    margin-top:6px; }
        .hero .pill { display:inline-block; margin-top:12px; padding:5px 12px;
                      border-radius:20px; font-size:12.5px;
                      background: color-mix(in srgb, var(--primary-color,#03a9f4) 20%,
                                  transparent);
                      color: var(--primary-text-color,#212121); }
        .ring { width:56px; height:56px; border-radius:50%; display:grid; place-items:center; }
        .ring span { width:40px; height:40px; border-radius:50%;
                     background: var(--card-background-color,#fff); display:grid;
                     place-items:center; font-size:12px; font-weight:700; }
        .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
        @media(max-width:560px){ .grid2 { grid-template-columns:1fr; } }
        .band { display:grid; grid-template-columns:1fr auto; gap:10px; padding:7px 0;
                border-bottom:1px solid var(--divider-color,#eee); font-size:13px; }
        .band:last-child { border-bottom:none; }
        .band .bv { font-family:ui-monospace,monospace; font-weight:600; }
        .scale { height:5px; border-radius:3px; margin-top:5px; position:relative;
                 background:linear-gradient(90deg,#c62828 0 16%,#ef6c00 16% 30%,
                   #2e7d32 30% 70%,#ef6c00 70% 84%,#c62828 84% 100%); }
        .scale b { position:absolute; top:-3px; width:2px; height:11px;
                   background: var(--primary-text-color,#222); border-radius:1px; }
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
        .review-cell { white-space:nowrap; }
        .needs-review { display:inline-block; margin-bottom:4px; padding:2px 8px; border-radius:10px;
                         font-size:11px; background: color-mix(in srgb, #ef6c00 18%, transparent);
                         color:#ef6c00; }
        .review-btn { background:none; border:1px solid var(--divider-color,#e0e0e0); color: var(--secondary-text-color,#666);
                       border-radius:6px; padding:3px 8px; margin-right:4px; margin-top:2px; cursor:pointer; font-size:11px; }
        .review-btn:hover:not(:disabled) { color: var(--primary-text-color,#212121); }
        .review-btn.active { background: var(--primary-color,#03a9f4); border-color: var(--primary-color,#03a9f4); color:#fff; cursor:default; }
        .review-btn:disabled { cursor:default; }
      </style>
      <h1>${esc(s ? s.title : "PoolSmart")}</h1>
      ${
        this._error
          ? `<div class="error-banner" role="alert" aria-live="assertive">
               <div class="error-title">Unable to load</div>
               <div class="error-detail">${esc(this._error)}</div>
               <button onclick="this.getRootNode().host._refresh()" aria-label="Retry loading data">Retry</button>
             </div>`
          : `<div class="sub ${this._refreshing ? "refreshing" : ""}">${
              esc(s ? s.decision?.reason ?? "" : "Loading…")
            }</div>`
      }
      ${
        this._loading
          ? `<div class="skeleton skeleton-nav" aria-hidden="true"></div>
             <div class="skeleton skeleton-temp" aria-hidden="true"></div>
             <div class="skeleton skeleton-title" aria-hidden="true"></div>
             <div class="skeleton skeleton-line" aria-hidden="true"></div>
             <div class="skeleton skeleton-line" aria-hidden="true"></div>
             <div class="skeleton skeleton-line" aria-hidden="true"></div>`
          : `<nav role="tablist" aria-label="PoolSmart sections">${TABS.map(
              (t) =>
                `<button role="tab" id="tab-${t.id}" data-tab="${t.id}" class="${
                  this._tab === t.id ? "active" : ""
                }" aria-selected="${this._tab === t.id}" aria-controls="panel-${t.id}"
                tabindex="${this._tab === t.id ? "0" : "-1"}">${esc(this.t(t.id) || t.label)}</button>`
            ).join("")}</nav>
            <div id="content" role="tabpanel" id="panel-${this._tab}" aria-labelledby="tab-${this._tab}">${
              s ? this._renderTab(s) : ""
            }</div>`
      }
    `;

    this.shadowRoot.querySelectorAll("nav button").forEach((b, idx, arr) =>
      b.addEventListener("click", () => {
        this._tab = b.dataset.tab;
        this._render();
        this.shadowRoot.querySelector(`#tab-${this._tab}`)?.focus();
      })
    );
    this.shadowRoot.querySelector("nav")?.addEventListener("keydown", (ev) => {
      const tabs = TABS.map((t) => t.id);
      const idx = tabs.indexOf(this._tab);
      let next = null;
      if (ev.key === "ArrowRight") next = tabs[(idx + 1) % tabs.length];
      else if (ev.key === "ArrowLeft") next = tabs[(idx - 1 + tabs.length) % tabs.length];
      else if (ev.key === "Home") next = tabs[0];
      else if (ev.key === "End") next = tabs[tabs.length - 1];
      if (next) {
        ev.preventDefault();
        this._tab = next;
        this._render();
        this.shadowRoot.querySelector(`#tab-${next}`)?.focus();
      }
    });
    this.shadowRoot.querySelectorAll("[data-service]").forEach((b) =>
      b.addEventListener("click", () => {
        const [domain, service] = b.dataset.service.split(".");
        this._callService(domain, service, JSON.parse(b.dataset.payload || "{}"));
      })
    );
    if (this._tab === "learning" && !this._storageStats && !this._storageStatsLoading) {
      this._loadStorageStats();
    }
    this._wireMaintenance();
  }

  _wireMaintenance() {
    const root = this.shadowRoot;
    const setStatus = (msg) => {
      this._maintStatus = msg;
      const el = root.querySelector("#maint-status");
      if (el) el.textContent = msg;
    };

    root.querySelector("#btn-refresh-stats")?.addEventListener("click", () => {
      this._loadStorageStats();
    });

    root.querySelector("#btn-clear-debug")?.addEventListener("click", async () => {
      if (
        !confirm(
          "Clear the decision log and near-miss tally? This only affects diagnostics, not learned values, sessions, or doses."
        )
      )
        return;
      await this._hass.callService("poolsmart", "clear_debug_log", {});
      setStatus("Debug traces cleared.");
      setTimeout(() => this._refresh(), 800);
    });

    root.querySelector("#btn-clear-all")?.addEventListener("click", async () => {
      if (
        !confirm(
          "Permanently delete every learned value, session, dose, and log entry? This cannot be undone."
        )
      )
        return;
      if (!confirm("Really sure? There is no way to get this back unless you have an export."))
        return;
      await this._hass.callService("poolsmart", "clear_all_history", { confirm: true });
      setStatus("All history cleared.");
      setTimeout(() => this._refresh(), 800);
    });

    root.querySelector("#btn-export-chosen")?.addEventListener("click", async () => {
      const sections = Array.from(root.querySelectorAll(".export-section:checked")).map(
        (el) => el.value
      );
      if (!sections.length) {
        setStatus("Choose at least one section to export.");
        return;
      }
      const path = root.querySelector("#export-path")?.value.trim();
      const data = { sections };
      if (path) data.path = path;
      await this._hass.callService("poolsmart", "export_learning", data);
      setStatus(`Exported: ${sections.join(", ")}.`);
    });

    root.querySelector("#btn-import")?.addEventListener("click", async () => {
      const path = root.querySelector("#import-path")?.value.trim();
      if (!path) {
        setStatus("Enter a file path to import.");
        return;
      }
      await this._hass.callService("poolsmart", "import_learning", { path });
      setStatus(`Imported from ${path}.`);
      setTimeout(() => this._refresh(), 800);
    });

    const replaceConfirm = root.querySelector("#replace-confirm");
    const replaceBtn = root.querySelector("#btn-replace");
    replaceConfirm?.addEventListener("change", () => {
      if (replaceBtn) replaceBtn.disabled = !replaceConfirm.checked;
    });
    replaceBtn?.addEventListener("click", async () => {
      const path = root.querySelector("#replace-path")?.value.trim();
      if (!path) {
        setStatus("Enter a file path to replace from.");
        return;
      }
      if (
        !confirm(
          "Overwrite existing learned history from this file? What this pool has measured for itself will be discarded. This cannot be undone."
        )
      )
        return;
      await this._hass.callService("poolsmart", "replace_learning", { path, confirm: true });
      setStatus(`Replaced history from ${path}.`);
      setTimeout(() => this._refresh(), 800);
    });
  }

  _renderTab(s) {
    try {
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
    } catch (err) {
      const tabLabel = this.t(this._tab) || this._tab;
      const message = err && err.message ? err.message : String(err);
      return `<div class="error-banner" role="alert" aria-live="assertive">
        <div class="error-title">Failed to render ${esc(tabLabel)}</div>
        <div class="error-detail">${esc(message)}</div>
      </div>`;
    }
  }

  _overview(s) {
    const d = s.decision || {};
    const colour = BRANCH_COLOURS[d.branch] || "#78909c";
    const f = s.filtration;
    const pct = f && f.required_h ? Math.min(100, (f.done_h / f.required_h) * 100) : 0;

    return `
      <div class="hero">
        <div class="ht">${s.water_temp !== null ? s.water_temp.toFixed(1) : "—"} °C</div>
        <div class="hs">${esc(d.reason || "")}</div>
        <div class="pill">${esc(d.branch || "—")} &middot; ${
      s.target_temp
    } °C ${esc(this.t("target"))} &middot; ${
      s.air_temp !== null ? s.air_temp.toFixed(1) : "—"
    } °C ${esc(this.t("outdoors"))}</div>
      </div>
      <div class="card">
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
          ? `<div class="dense" style="margin-top:10px">
               <div class="d"><span class="dk">${esc(
                 this.t("risePerHour")
               )}</span><span class="dv">${x.actual_rate_c_per_h}</span>
                 <span class="muted mono" style="text-align:right;font-size:11px">/ ${
                   x.expected_rate_c_per_h
                 }</span></div>
               <div class="d"><span class="dk">${esc(
                 this.t("onSchedule")
               )}</span><span class="dv">${Math.round(
                 (x.on_schedule_ratio || 0) * 100
               )}%</span><span></span></div>
             </div>
             <div class="reason" style="color:${verdictColour}">${esc(x.verdict)}</div>`
          : `<div class="reason muted">${esc(this.t("tooEarly"))}</div>`
      }
    </div>
    ${this._previousSessions(s)}`;
  }

  _previousSessions(s) {
    /* A rate means nothing without something to compare it against. Three
       recent sessions turn "0.15 °C/h" into "normal for this pool". */
    const rows = (s.session_log || []).filter((x) => x.usable).slice(0, 3);
    if (!rows.length) return "";
    return `<div class="card">
      <strong>${esc(this.t("previousSessions"))}</strong>
      <table>
        <tr><th>${esc(this.t("when"))}</th><th>${esc(
          this.t("duration")
        )}</th><th>${esc(this.t("gain"))}</th><th>°C/h</th><th>COP</th></tr>
        ${rows
          .map(
            (r) => `<tr>
              <td>${fmtDateTime(r.start)}</td>
              <td>${fmtHours(r.duration_h)}</td>
              <td>${
                r.water_start !== null && r.water_end !== null
                  ? `${(r.water_end - r.water_start).toFixed(2)}`
                  : "—"
              }</td>
              <td>${r.heating_rate ?? "—"}</td>
              <td>${r.measured_cop ?? "—"}</td></tr>`
          )
          .join("")}
      </table>
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
             ${
               d.circulation_minutes
                 ? `<div class="reason"><b>${esc(
                     this.t("circulate")
                   )} ${fmtHours(d.circulation_minutes / 60)}</b> — ${esc(
                     d.circulation_reason
                   )}</div>`
                 : ""
             }
           </div>`
        : "";

    const bands = (w.bands || [])
      .map((b) => {
        const span = b.ideal_high - b.ideal_low;
        const lo = b.ideal_low - span;
        const hi = b.ideal_high + span;
        const pos = Math.max(0, Math.min(100, ((b.value - lo) / (hi - lo)) * 100));
        const colour =
          b.verdict === "ok"
            ? "#2e7d32"
            : b.urgent
            ? "#c62828"
            : "#ef6c00";
        return `<div class="band">
            <div>${esc(b.label)}
              <div class="scale"><b style="left:${pos}%"></b></div>
              ${b.note ? `<div class="reason muted">${esc(b.note)}</div>` : ""}
            </div>
            <div style="text-align:right">
              <div class="bv" style="color:${colour}">${b.value}${
          b.unit ? ` ${esc(b.unit)}` : ""
        }</div>
              <div class="muted" style="font-size:11px">${b.ideal_low}–${
          b.ideal_high
        }</div>
            </div>
          </div>`;
      })
      .join("");

    return `
      ${
        bands
          ? `<div class="card"><strong>${esc(this.t("readings"))}</strong>${bands}
             ${
               w.combined_chlorine !== null && w.combined_chlorine !== undefined
                 ? `<div class="row" style="margin-top:8px"><span>${esc(
                     this.t("combinedChlorine")
                   )}</span><span class="bv">${w.combined_chlorine} mg/L</span></div>`
                 : ""
             }</div>`
          : ""
      }
      ${
        (w.advice || []).length
          ? `<div class="card"><strong>${esc(this.t("whatItMeans"))}</strong>
             ${w.advice.map((a) => `<div class="reason">${esc(a)}</div>`).join("")}</div>`
          : ""
      }
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

  _reviewButtons(x) {
    const current = x.review || "auto";
    const options = [
      ["auto", this.t("reviewAuto")],
      ["included", this.t("reviewInclude")],
      ["excluded", this.t("reviewExclude")],
    ];
    return options
      .map(([value, label]) => {
        const active = current === value;
        const payload = JSON.stringify({
          session_start: x.start,
          review: value,
        }).replace(/'/g, "&#39;");
        return `<button class="review-btn${active ? " active" : ""}"
                  data-service="poolsmart.set_session_review" data-payload='${payload}'
                  ${active ? "disabled" : ""}
                  aria-label="${esc(label)}: ${fmtDateTime(x.start)}">${esc(label)}</button>`;
      })
      .join("");
  }

  _sessions(s) {
    if (!s.session_log.length)
      return `<div class="card muted">No finished heating sessions yet.</div>`;
    return `<div class="card"><table>
      <tr><th>Started</th><th>Duration</th><th>Gain</th><th>COP</th><th>Used</th><th>Review</th></tr>
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
            <td class="review-cell">
              ${
                x.needs_review
                  ? `<div class="needs-review">${esc(this.t("needsReview"))}</div>`
                  : ""
              }
              <div>${this._reviewButtons(x)}</div>
            </td>
          </tr>`
        )
        .join("")}
    </table></div>
    <div class="card muted reason">${esc(this.t("reviewHint"))}</div>`;
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
            ${
              v.confidence
                ? `<div class="bar" style="margin-top:8px"><div style="width:${
                    { "not learned yet": 0, provisional: 25, usable: 60, reliable: 100 }[
                      v.confidence
                    ] ?? 0
                  }%;background:${
                    v.in_use ? "#2e7d32" : "#b0bec5"
                  }"></div></div>`
                : ""
            }
            <div class="reason muted">${esc(this.t("usedFor"))} ${esc(v.used_for)}.</div>
            ${
              v.value !== null && v.value !== undefined
                ? `<button class="action" style="margin-top:10px;background:transparent;
                     border:1px solid var(--divider-color);color:var(--secondary-text-color)"
                     data-service="poolsmart.reset_learned"
                     data-payload='{"value":"${v.key}"}'
                     aria-label="${esc(this.t("resetThis"))}: ${esc(v.key)}">${esc(
                     this.t("resetThis")
                   )}</button>`
                : ""
            }
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
      ${this._trendsCard(s)}
      ${this._advisorCard(s)}
      <div class="card">
        <button class="action" data-service="button.press"
          data-payload='{"entity_id":"button.pool_reset_learned_values"}'
          aria-label="Reset all learned values">Reset learned values</button>
        <div class="reason muted">Updates are capped, so a single odd session cannot move a
          value far. Resetting is only needed after changing hardware.</div>
      </div>
      ${this._maintenanceCard(s)}
    `;
  }

  _trendLabel(metric) {
    if (metric.startsWith("cop_by_bucket.")) {
      return `COP (${metric.slice("cop_by_bucket.".length)} °C)`;
    }
    return { heating_rate: "Heating rate", heat_loss: "Heat loss",
      heat_loss_covered: "Heat loss (covered)" }[metric] || metric;
  }

  _trendBadge(direction) {
    const color = { improving: "#2e7d32", degrading: "#c62828", stable: "#78909c" }[
      direction
    ] || "#78909c";
    const label = { improving: "improving", degrading: "degrading", stable: "stable" }[
      direction
    ] || direction;
    return `<span class="badge" style="background:${color}">${label}</span>`;
  }

  _trendsCard(s) {
    const months = s.monthly_aggregates || [];
    if (!months.length) return "";
    const trends = s.monthly_trends || {};
    const moving = Object.entries(trends).filter(
      ([, t]) => t.direction === "improving" || t.direction === "degrading"
    );

    const recent = months.slice(-12);
    const copMean = (m) => {
      const buckets = Object.values(m.cop_by_bucket || {});
      const n = buckets.reduce((a, b) => a + b.n, 0);
      if (!n) return null;
      return buckets.reduce((a, b) => a + b.mean * b.n, 0) / n;
    };

    return `
      <div class="card">
        <strong>Long-term trends</strong>
        <div class="reason muted">Monthly averages survive the session and daily caps
          indefinitely, so a slow drift over months or seasons stays visible after the
          detail behind it has rolled off.</div>
        ${
          moving.length
            ? moving
                .map(
                  ([metric, t]) =>
                    `<div class="row"><span>${esc(this._trendLabel(metric))}</span>
                     <span>${this._trendBadge(t.direction)}
                       <span class="muted" style="margin-left:6px">${
                         t.pct_per_month > 0 ? "+" : ""
                       }${t.pct_per_month}%/mo over ${t.months_considered} months</span></span></div>`
                )
                .join("")
            : `<div class="muted">Nothing trending yet; everything measured is holding steady.</div>`
        }
        <table style="margin-top:10px">
          <tr><th>Month</th><th>Sessions</th><th>Heating rate</th><th>Heat loss</th><th>COP</th></tr>
          ${recent
            .map((m) => {
              const cop = copMean(m);
              return `<tr>
                <td>${esc(m.month)}</td>
                <td>${m.session_count}</td>
                <td>${m.heating_rate.n ? m.heating_rate.mean.toFixed(3) : "—"}</td>
                <td>${m.heat_loss.n ? m.heat_loss.mean.toFixed(3) : "—"}</td>
                <td>${cop !== null ? cop.toFixed(2) : "—"}</td>
              </tr>`;
            })
            .join("")}
        </table>
      </div>`;
  }

  _maintenanceCard(s) {
    const stats = this._storageStats || {};
    const backupPath = s.entry_id
      ? `/config/poolsmart_learning_backup.${s.entry_id}.json`
      : "";
    return `
      <div class="card">
        <strong>Storage</strong>
        ${
          stats.error
            ? `<div class="reason warn">${esc(stats.error)}</div>`
            : `<div class="row"><span>Sessions</span><span>${stats.sessions ?? "—"}</span></div>
               <div class="row"><span>Doses</span><span>${stats.doses ?? "—"}</span></div>
               <div class="row"><span>Decisions logged</span><span>${
                 stats.decisions ?? "—"
               }</span></div>
               <div class="row"><span>Near misses tracked</span><span>${
                 stats.near_misses ?? "—"
               }</span></div>
               <div class="row"><span>Monthly trend rows</span><span>${
                 stats.monthly_aggregates ?? "—"
               }</span></div>
               <div class="row"><span>File size</span><span>${fmtBytes(
                 stats.file_size_bytes
               )}</span></div>`
        }
        <button class="action" id="btn-refresh-stats" style="margin-top:10px;background:transparent;
          border:1px solid var(--divider-color);color:var(--secondary-text-color)"
          ${this._storageStatsLoading ? "disabled" : ""}>Refresh</button>
      </div>

      <div class="card">
        <strong>Maintenance</strong>
        <div class="reason muted">Reprocess after a batch of session reviews or an import, so
          the effect is immediate instead of waiting on the next session. Clearing debug traces
          is always safe; clearing all history is not.</div>
        <button class="action" data-service="poolsmart.rebuild_learning" data-payload='{}'>Process now</button>
        <button class="action" id="btn-clear-debug" style="background:transparent;
          border:1px solid var(--divider-color);color:var(--secondary-text-color)">Clear debug traces</button>
        <button class="action" id="btn-clear-all" style="background:#c62828">Clear all history</button>
      </div>

      <div class="card">
        <strong>Export</strong>
        <div class="reason muted">Quick export writes everything below. Choosing data lets you
          leave parts out.</div>
        <button class="action" data-service="poolsmart.export_learning" data-payload='{}'>Export everything</button>
        <div style="margin-top:12px;font-size:13px;">
          <label style="display:block;color:var(--secondary-text-color);margin-bottom:6px;font-size:12px;">Sections to export</label>
          ${["learned", "session_log", "dose_log", "last_water_test"]
            .map(
              (v) =>
                `<label style="margin-right:12px;"><input type="checkbox" class="export-section" value="${v}" checked> ${esc(
                  v.replace(/_/g, " ")
                )}</label>`
            )
            .join("")}
        </div>
        <input type="text" id="export-path" placeholder="/config/poolsmart_learning.json (optional)"
          style="width:100%;margin-top:10px;padding:7px 10px;border-radius:6px;
          border:1px solid var(--divider-color);background:transparent;color:var(--primary-text-color);
          box-sizing:border-box;font-size:13px;">
        <button class="action" id="btn-export-chosen" style="margin-top:10px;">Export chosen data</button>
      </div>

      <div class="card">
        <strong>Import</strong>
        <div class="reason muted">Merges: values this pool has already measured for itself are
          kept, not overwritten. Pre-filled with this pool's automatic safety-net backup --
          change it to point at a manual export instead.</div>
        <input type="text" id="import-path" placeholder="/config/poolsmart_learning.json"
          value="${esc(backupPath)}"
          style="width:100%;margin-top:6px;padding:7px 10px;border-radius:6px;
          border:1px solid var(--divider-color);background:transparent;color:var(--primary-text-color);
          box-sizing:border-box;font-size:13px;">
        <button class="action" id="btn-import" style="margin-top:10px;">Import</button>
      </div>

      <div class="card">
        <strong>Advanced: replace from JSON</strong>
        <div class="reason muted">Overwrites instead of merging: what this pool has already
          measured for itself is discarded in favour of the file. Not for routine use.</div>
        <input type="text" id="replace-path" placeholder="/config/poolsmart_learning.json"
          value="${esc(backupPath)}"
          style="width:100%;margin-top:6px;padding:7px 10px;border-radius:6px;
          border:1px solid var(--divider-color);background:transparent;color:var(--primary-text-color);
          box-sizing:border-box;font-size:13px;">
        <label style="display:block;margin-top:10px;font-size:13px;">
          <input type="checkbox" id="replace-confirm"> I understand this overwrites existing
          history and cannot be undone
        </label>
        <button class="action" id="btn-replace" style="margin-top:10px;background:#c62828" disabled>Replace everything</button>
      </div>

      <div class="reason muted" id="maint-status">${esc(this._maintStatus)}</div>
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
        (s.near_misses || []).length
          ? `<div class="card"><strong>${esc(this.t("nearMisses"))}</strong>
             <div class="reason muted">${esc(this.t("nearMissesNote"))}</div>
             <div class="dense">
             ${s.near_misses
               .map(
                 (m) => `<div class="d">
                   <span>${esc(
                     m.branch.replace(/_/g, " ").toLowerCase()
                   )} <span class="muted">— ${esc(
                     (VERDICT_STYLE[m.verdict] || {}).label || m.verdict
                   )}</span></span>
                   <span class="dv">${m.count}×</span>
                   <span class="muted mono" style="text-align:right;font-size:11px">${fmtHours(
                     m.seconds / 3600
                   )}</span></div>`
               )
               .join("")}
             </div></div>`
          : ""
      }
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
