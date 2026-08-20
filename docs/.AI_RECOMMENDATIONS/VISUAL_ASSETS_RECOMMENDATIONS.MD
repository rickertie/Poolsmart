# PoolSmart Visual Asset Recommendation Document

> **Prepared by**: Image Prompt Engineer  
> **Date**: 2026-08-11  
> **Project**: Poolsmart — Intelligent Swimming Pool Controller for Home Assistant  
> **Current assets**: 12 images (hardware photos, wiring overview, valve schematic)  
> **Goal**: Identify high-impact visual additions to improve comprehension and reduce time-to-value for new users

---

## Executive Summary

The PoolSmart documentation is text-rich and concept-dense. The core decision-making concepts (priority ladder, COP-weighted optimization, turnover mathematics, self-learning feedback loop) are currently communicated entirely through prose and tables. This creates unnecessary cognitive load for new users who need to understand *why* the system behaves as it does.

**Priority recommendations at a glance:**

| Rank | Asset | Placement | Impact |
|:---:|---|---|:---:|
| 1 | System Architecture Overview | README.md + ARCHITECTURE.MD | 🔴 Critical |
| 2 | Priority Decision Ladder Flowchart | ARCHITECTURE.MD | 🔴 Critical |
| 3 | Dashboard Screenshot Mockup | README.md + lovelace/README.md | 🔴 Critical |
| 4 | COP Curve & Learning Model Graph | LEARNING.MD | 🟠 High |
| 5 | Heating Planning Timeline | PLANNING.MD | 🟠 High |
| 6 | Turnover Infographic | FILTRATION.MD | 🟠 High |
| 7 | Heat Pump Operating Envelope | ARCHITECTURE.MD | 🟡 Medium |
| 8 | Solar Surplus Threshold Diagram | PLANNING.MD | 🟡 Medium |
| 9 | Data Flow & Entity Map | ARCHITECTURE.MD | 🟡 Medium |
| 10 | Chemistry Test Interval Chart | CHEMISTRY.MD | 🟡 Medium |
| 11 | Pool Construction Heat Loss Comparison | HEATING.MD | 🟢 Nice-to-have |
| 12 | Bucket Test Calibration Photo | ESPHOME.MD | 🟢 Nice-to-have |

---

## 🔴 CRITICAL PRIORITY (Must-Have)

---

### 1. System Architecture Overview Diagram

**Purpose**:  
Instantly communicates *what* PoolSmart is, *how* its components connect, and *where* decisions are made. Currently a new user must read 4+ documents before forming a mental model. This diagram provides immediate orientation — the single highest-ROI visual asset.

**Placement**:  
- Primary: README.md (below the opening paragraph, above Features)  
- Secondary: ARCHITECTURE.MD (as the first heading under the title)

**Recommended format**: SVG vector diagram (clean, scalable, themeable)

**Image prompt**:

```
Clean technical system architecture diagram, flat vector illustration style 
with subtle gradients. Shows a home swimming pool on the left connected via 
pipes to a filtration pump and heat pump. An ESP32 microcontroller board 
(small blue PCB with antenna) sits at the center-left with wired connections 
running to the pool — five small temperature probe icons and one flow meter 
icon. A dashed wireless signal line rises from the ESP32 up to a Home Assistant 
logo (house icon) in the center-right. Below the Home Assistant icon sits a 
decision engine block labeled "Priority Ladder" with a small flowchart icon. 
Arrows flow from the decision engine down to two output blocks: "Pump Control" 
(blue water drop icon) and "Heat Demand" (orange flame icon). A small optional 
AI advisor block sits off to the connected via a dotted line labeled "advisory 
only". Clean sans-serif labels, soft rounded rectangles, Home Assistant blue 
(#03A9F4) and pool blue (#00ACC1) color palette, white background, 
isometric-flat hybrid style, technical documentation quality, no people
```

**File naming**: `images/architecture-overview.svg`

---

### 2. Priority Decision Ladder Flowchart

**Purpose**:  
The priority ladder is the beating heart of PoolSmart's decision logic. The current table format (Priority 0–9 with conditions) is informative but not intuitive. A flowchart immediately communicates the *evaluation order*, *first-match-wins* behavior, *night quiet exceptions*, and *safety interlock* concept — concepts that currently require paragraphs to explain.

**Placement**:  
- Primary: ARCHITECTURE.MD — replacing or supplementing the current table under "The Priority Decision Ladder"  
- Secondary: README.md (as a thumbnail linking to ARCHITECTURE.MD)

**Recommended format**: SVG vector flowchart

**Image prompt**:

```
Vertical priority flowchart diagram, clean technical illustration style. 
Ten stacked rectangular blocks arranged top-to-bottom, connected by downward 
arrows. Each block is color-coded: red blocks at top labeled "0 Emergency Stop", 
"1 Frost Protection" with a small snowflake icon; orange blocks labeled "2 Manual 
Override", "3 Chemistry Cycle"; blue blocks labeled "4 Filtration Deadline", 
"5 Free Electricity"; green blocks labeled "6 Heating Session", "7 Scheduled 
Filtration"; gray blocks labeled "8 Pump Rundown", "9 Idle". A bold green 
checkmark appears on the left of each block. Branches 0-5 have a small crescent 
moon icon with a slash through it (night quiet override). Branches 6-8 have a 
small moon icon without slash (respects night quiet). A sidebar on the right 
shows a small "First Match Wins" indicator — a downward arrow with a stop sign 
at the first green block. Clean sans-serif typography, rounded corners, soft 
shadows, white background, Home Assistant color palette, engineering diagram 
quality, no decorative elements
```

**File naming**: `images/priority-ladder.svg`

---

-

## 🟠 HIGH PRIORITY (Should-Have)

---

### 4. COP Curve & Self-Learning Model Graph

**Purpose**:  
The COP (Coefficient of Performance) curve is central to PoolSmart's heating optimization, yet it's described only in text: "one COP value per 5°C temperature band." A graph showing how COP varies with outdoor temperature instantly makes the concept click — and demonstrates *why* a higher electricity price at 22°C can be cheaper per thermal kWh than a lower price at 12°C.

**Placement**:  
- Primary: LEARNING.MD — under "What Is Learned?" section  
- Secondary: PLANNING.MD — under "COP-weighted cost"

**Recommended format**: SVG vector graph

**Image prompt**:

```
Clean scientific graph illustration, SVG technical style. X-axis labeled 
"Outdoor Temperature (°C)" ranging from 5 to 30. Y-axis labeled "COP 
(Coefficient of Performance)" ranging from 2 to 8. A smooth upward curve 
starts at approximately COP 3.2 at 5°C, rises to COP 5.5 at 15°C, and reaches 
COP 7.2 at 25°C. The curve is colored in a gradient from cool blue (left) to 
warm orange (right). Vertical bands of 5°C width are marked along the axis 
with light gray shading alternating, each band labeled: "5-10°", "10-15°", 
"15-20°", "20-25°", "25-30°". A small annotation arrow points to the curve at 
15°C: "Learned from sessions". A second dashed curve slightly below the main 
one is labeled "Manufacturer spec (starting estimate)". Clean sans-serif 
typography, grid lines in light gray, white background, academic/scientific 
chart quality, no decorative elements
```

**File naming**: `images/cop-curve.svg`

---

### 5. Heating Planning Timeline Visualization

**Purpose**:  
The Maintenance vs. Seasonal mode distinction is conceptually important but abstract. A timeline showing how the system schedules heating across hours (maintenance) vs. days (seasonal) makes the optimization strategy immediately visible — and demonstrates the value proposition of price-aware scheduling.

**Placement**:  
- Primary: PLANNING.MD — under "Maintenance vs. Seasonal Mode"  
- Secondary: README.md (as a thumbnail)

**Recommended format**: SVG vector illustration with two-part timeline

**Image prompt**:

```
Two-part horizontal timeline illustration, clean technical style. 
Top section labeled "Maintenance Mode — Ready Today at 14:30": a horizontal 
timeline from 00:00 to 24:00 with price bars in green (low), yellow (medium), 
and red (high). Three blue blocks labeled "Heat" appear during the cheapest 
green bars (10:00-11:30, 13:00-14:30, 16:00-16:30), totaling 3.5 hours. A 
swimmer icon appears at 14:30 with a checkmark.

Bottom section labeled "Seasonal Mode — Ready Saturday 16:00": a five-day 
timeline (Wed-Sun) with daily heat blocks shown as blue bars of varying 
length. Wed has a short 2h bar, Thu has a 6h bar, Fri has an 8h bar, Sat has 
a 4h bar ending at 16:00. Below each day, a small price trend line shows 
electricity cost fluctuation. A thermometer icon on the left shows a 
progressive fill from "14°C" (cold) to "28°C" (target). Clean rounded 
rectangles, Home Assistant blue palette, white background, infographic 
quality, subtle shadows, sans-serif labels
```

**File naming**: `images/heating-timeline.svg`

---

### 6. Turnover Infographic

**Purpose**:  
The turnover concept (1 turnover = 63% clean, 2 = 86%, 3 = 95%, 4 = 98%) is one of the most elegant yet confusing aspects of pool filtration. Users often wonder "why 3 turnovers?" A visual showing the diminishing returns curve alongside a pool cross-section with debris distribution makes the math intuitive.

**Placement**:  
- Primary: FILTRATION.MD — under "Rule 1: Turnover (volume-based)"  
- Secondary: README.md (as an eye-catching thumbnail linking to docs)

**Recommended format**: SVG dual-panel infographic

**Image prompt**:

```
Two-panel infographic illustration, clean technical style. 
Left panel: line graph titled "Cumulative Filtration Effectiveness". X-axis 
labeled "Number of Turnovers" (1-4). Y-axis labeled "Water Cleanliness (%)" 
(0-100). A curve rises steeply from 0 to 63% at turnover 1, then bends 
flattening through 86% at turnover 2, 95% at turnover 3, and 98% at turnover 4. 
Horizontal dashed lines mark each milestone with labels "63% — 1 turnover", 
"86% — 2 turnovers", "95% — 3 turnovers (recommended)", "98% — 4 turnovers". 
A shaded "diminishing returns" region covers from turnover 3 to 4.

Right panel: four simplified cross-section views of a pool (rectangular, seen 
from the side) each showing particle distribution. At 1 turnover, many dark 
dots scattered throughout with concentration gradient. At 2 turnovers, fewer 
dots. At 3 turnovers, sparse dots mostly at edges. At 4 turnovers, nearly 
empty. Each pool is labeled with its turnover count and cleanliness percentage. 
Pool blue gradient background for pool illustrations, clean sans-serif labels, 
white overall background, educational infographic quality
```

**File naming**: `images/turnover-infographic.svg`

---

## 🟡 MEDIUM PRIORITY (Valuable)

---

### 7. Heat Pump Operating Envelope Graph

**Purpose**:  
The operating envelope gate (heating disabled below minimum air temperature) is described in ARCHITECTURE.MD but a visual clarifies exactly when heating is available vs. when only frost protection circulation runs. This prevents confusion when users wonder "why isn't my heat pump running?"

**Placement**:  
- Primary: ARCHITECTURE.MD — under "Heat Pump Operating Envelope"  
- Secondary: TROUBLESHOOTING.MD (as a reference when diagnosing heating issues)

**Recommended format**: SVG vector graph

**Image prompt**:

```
Technical graph illustration showing heat pump operating envelope. X-axis 
labeled "Outdoor Air Temperature (°C)" ranging from -5 to 35. Y-axis labeled 
"Heat Pump Status" with two states. A green shaded region spans from 11°C to 
35°C labeled "Heating Available" with a small heat pump icon. A blue shaded 
region spans from -5°C to 11°C labeled "Frost Protection Only (circulation)" 
with a small water drop icon. A vertical dashed line at 11°C marks "Minimum 
Operating Temperature" with a label "Envelope Gate". An annotation at 8°C reads 
"Circulation runs to prevent freezing — no heating below 11°C". Clean grid 
lines, rounded region edges, Home Assistant green (#4CAF50) for heating 
available, pool blue (#00ACC1) for circulation only, white background, 
engineering diagram quality
```

**File naming**: `images/operating-envelope.svg`

---

### 8. Solar Surplus Threshold Diagram

**Purpose**:  
The solar surplus concept (treat heating as free above threshold X) is described across multiple docs but is inherently abstract. A visual showing the relationship between solar generation, pool equipment draw, and the threshold makes this optimization strategy immediately understandable.

**Placement**:  
- Primary: PLANNING.MD — under "Solar Surplus"  
- Secondary: HEATING.MD — under "Solar Collectors"

**Recommended format**: SVG vector diagram

**Image prompt**:

```
Technical diagram showing solar surplus threshold concept, clean 
infographic style. A horizontal axis represents "Solar Surplus Power (W)" 
from 0 to 2000. A vertical dashed line at 680W is labeled "Threshold 
(Equipment Draw + Margin)" with an annotation reading "3kW heat pump (580W) 
+ 100W pump + margin". Left of the threshold: a yellow zone labeled "Not 
Enough — Heating Deferred". Right of the threshold: a green zone labeled 
"Surplus — Free Heat!" with a sun icon. Above the threshold line, a small 
graph shows a bell curve representing "Typical Solar Generation Pattern" 
peaking midday. Icons of a solar panel, heat pump, and circulation pump 
sit at the bottom connected by lines to the threshold point. Clean sans-serif 
typography, rounded zones, yellow (#FFC107) and green (#4CAF50) colors, 
white background, educational diagram quality
```

**File naming**: `images/solar-surplus.svg`

---

### 9. Data Flow & Entity Relationship Map

**Purpose**:  
PoolSmart has a complex entity ecosystem (sensors, switches, numbers, attributes). The current ENTITIES.MD lists them without showing relationships. A data flow map helps users understand which sensors feed which decisions and what degrades gracefully when sensors are absent.

**Placement**:  
- Primary: ENTITIES.MD — as the first visual after the introduction  
- Secondary: ARCHITECTURE.MD — under "Entity Mapping & Fallbacks"

**Recommended format**: SVG vector flowchart

**Image prompt**:

```
Entity relationship and data flow diagram, technical flowchart style. 
Three vertical columns. Left column titled "Source Sensors" contains icons 
and labels: "Outdoor Temp", "Water Temp", "Heat Pump In/Out", "Flow Meter", 
"Power Sensor", "Price Feed", "Solar Generation". Middle column titled 
"Decision Engine" contains blocks: "Priority Ladder", "COP Learning", 
"Filtration Calc", "Price Optimizer". Right column titled "Outputs & Actions" 
contains: "Pump Switch", "Heat Demand", "Notifications", "AI Advisor". 
Arrows flow from left to center to right. Some arrows from optional sensors 
are dashed and labeled "optional — graceful fallback". A small legend at 
bottom shows solid arrow = required, dashed arrow = optional. Color-coded 
arrows: blue for temperature data, green for flow, yellow for power/price, 
orange for solar. Clean sans-serif labels, rounded rectangles, white 
background, systems diagram quality
```

**File naming**: `images/data-flow.svg`

---

--

## 🟢 NICE-TO-HAVE (Polish)

---

### 11. Pool Construction Heat Loss Comparison

**Purpose**:  
Pool construction type (inflatable vs. built-in) affects starting heat loss from 0.30°C/h to 0.08°C/h — a ~4x difference. A side-by-side visual comparing heat loss rates makes this tangible and helps users understand why their pool behaves differently from their neighbor's.

**Placement**:  
- Primary: HEATING.MD — under "Pool Construction"

**Recommended format**: SVG comparison illustration

**Image prompt**:

```
Side-by-side comparison illustration of four pool types showing heat loss 
rate, clean infographic style. Four vertical panels, each showing a simple 
pool cross-section with wavy red arrows escaping upward — arrow quantity and 
size visually represents heat loss rate. Panel 1: "Inflatable Pool" — thin 
blue walls, many large red arrows (labeled "0.30°C/h"), no insulation. Panel 
2: "Above-Ground" — slightly thicker walls, fewer medium arrows (0.20°C/h). 
Panel 3: "Built-In (uninsulated)" — concrete walls, some arrows (0.12°C/h). 
Panel 4: "Built-In (insulated)" — thick walls with insulation layer, minimal 
small arrows (0.08°C/h). Each panel has a small thermometer icon showing 
rate. A subtle blue-to-red gradient at the top of each panel indicates 
heat escaping. Clean sans-serif labels, white background, comparison 
infographic quality, no decorative elements
```

**File naming**: `images/heat-loss-comparison.svg`

---
---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
These three assets deliver the highest comprehension ROI and should be created first:

| Asset | Format | Est. Effort |
|---|:---:|:---:|
| System Architecture Overview | SVG | 3-4 hrs |
| Priority Decision Ladder Flowchart | SVG | 2-3 hrs |
| Dashboard Screenshot/Mockup | PNG | 1-2 hrs |

### Phase 2: Core Concepts (Week 3-4)
These clarify the system's intelligence — the "why does it do that?" visuals:

| Asset | Format | Est. Effort |
|---|:---:|:---:|
| COP Curve Graph | SVG | 2 hrs |
| Heating Planning Timeline | SVG | 3 hrs |
| Turnover Infographic | SVG | 2-3 hrs |

### Phase 3: Deep Understanding (Week 5-6)
These answer specific "how does this work?" questions:

| Asset | Format | Est. Effort |
|---|:---:|:---:|
| Operating Envelope Graph | SVG | 1.5 hrs |
| Solar Surplus Diagram | SVG | 2 hrs |
| Data Flow Map | SVG | 3 hrs |

### Phase 4: Polish (Week 7+)
Nice-to-haves that round out the documentation:

| Asset | Format | Est. Effort |
|---|:---:|:---:|
| Chemistry Test Interval Chart | SVG | 1.5 hrs |
| Heat Loss Comparison | SVG | 2 hrs |
| Bucket Test Photo | Photo/Render | 1 hr |

---

## Design Standards for Consistency

To maintain visual coherence across all assets, follow these guidelines:

### Color Palette
| Purpose | Color | Hex |
|---|---|:---:|
| Primary / Pool | Pool Blue | `#00ACC1` |
| Secondary / HA | HA Blue | `#03A9F4` |
| Heat / Warning | Warm Orange | `#FF9800` |
| Active / Success | Green | `#4CAF50` |
| Error / Stop | Red | `#F44336` |
| Neutral / Idle | Gray | `#9E9E9E` |
| Background | Off-White | `#FAFAFA` |

### Typography
- Primary: Inter, Roboto, or system sans-serif
- Monospace for technical labels (entity IDs, pin numbers)
- Minimum 11pt for documentation viewing

### Style
- Flat vector with subtle shadows
- Rounded corners (4-8px radius)
- Consistent stroke width (1.5-2px)
- No photorealistic elements in diagrams
- SVG format for all diagrams (scalable, small file size, editable)

### Technical Specifications
- Export at 2x for retina displays
- Optimized SVG (run through SVGO)
- Maximum width: 800px for inline diagrams
- Alt text for all images (accessibility)

---

## Notes on Existing Assets

The current 12 images are well-chosen for hardware identification. Recommendations for optimization:

| Current Asset | Assessment | Recommendation |
|---|---|---|
| `esp32c6_wiring_overview.png` | ✅ Excellent | Keep as-is; it's the most-viewed diagram |
| `3wayValve Schema.PNG` | ⚠️ Could improve | Redraw as clean SVG for consistency |
| `Bestway_pump.webp` | ✅ Good | Keep — identifies the pump model |
| `w_eau_mini_power_3kw_warmtepomp.webp` | ✅ Good | Keep — identifies the heat pump |
| `DS18B20.jpg` | ✅ Good | Keep — shows probe type |
| `Flow_meter.jpg` | ✅ Good | Keep — shows installation |
| `Pipe_clamp.jpg` | ✅ Good | Keep — shows mounting technique |
| `*.DNG` files (4) | ⚠️ Format issue | Convert to WebP/PNG for web use; DNG is raw format |

---

## Measuring Success

Track these metrics after implementing visual assets:

1. **Time-on-page reduction** for ARCHITECTURE.MD (understanding faster = less time re-reading)
2. **Support questions eliminated** — track which questions disappear from issues/forums
3. **Dashboard adoption** — if dashboard mockup is added, track lovelace/README.md views
4. **GitHub stars / HACS installs** — visual assets improve first-impression conversion
5. **Documentation bounce rate** — are users staying longer or finding answers faster?

---

## Additional Recommendations (Round 2)

> **Prepared by**: Image Prompt Engineer  
> **Date**: 2026-08-11  
> **Focus**: Gap analysis beyond the original 12 recommendations — targeting complex workflows, counterintuitive concepts, and brand/polish opportunities that further reduce cognitive load and support adoption.

---

### Gap Analysis Summary

After reviewing all 10 documentation files and the existing 12 visual assets, the following gaps were identified:

| Gap Category | Documents Affected | Opportunity |
|---|---|---|
| **Multi-step workflows** | CHEMISTRY.MD, ARCHITECTURE.MD | Flowcharts for dosing process and AI advisory loop |
| **Counterintuitive concepts** | FILTRATION.MD, PLANNING.MD | Visual explanations of delta-T judging and COP-weighted pricing |
| **Temporal sequences** | ARCHITECTURE.MD, FILTRATION.MD | Timing diagrams for compressor protection and filter aging |
| **Feature comparisons** | HEATING.MD, FILTRATION.MD | Side-by-side comparisons of heating sources and filter media |
| **UI orientation** | lovelace/README.md, GETTING_STARTED.MD | Dashboard structure overview and user journey roadmap |
| **Diagnostic workflows** | TROUBLESHOOTING.MD | Decision-tree troubleshooting flowchart |
| **Brand & social** | README.md | Hero banner image and Open Graph preview |

---

## 🔴 CRITICAL PRIORITY (Must-Have)

---

### 13. Compressor Protection Timing Diagram

**Purpose**:  
The compressor protection concept is one of the most safety-critical and least intuitive aspects of PoolSmart. The distinction between an ordinary decision hold (breakable) and compressor protection (non-negotiable) is currently explained only in prose. A timing diagram showing minimum off-time, minimum run-time, and the target-temperature override makes this immediately clear — and prevents users from wondering why their heat pump won't restart immediately.

**Placement**:  
- Primary: ARCHITECTURE.MD — under "Compressor Protection" section  
- Secondary: TROUBLESHOOTING.MD — as a reference when diagnosing "heating won't start" issues

**Recommended format**: SVG vector timing diagram

**AI Generation Prompt**:
```
Technical timing diagram illustration, clean engineering style. 
Horizontal time axis showing three scenarios stacked vertically.

Scenario 1 "Minimum Off-Time Enforced": A horizontal timeline 
with a blue bar labeled "Compressor RUN" followed by a red hashed 
bar labeled "Minimum Off-Time (e.g., 3 min)" with a lock icon. 
A dashed line after the red bar shows "Restart Allowed" with a 
green checkmark. A small refrigerant pressure equalization icon 
appears above the red bar.

Scenario 2 "Minimum Run-Time vs Target Temp": A blue bar starts 
labeled "Compressor RUN" but stops early at a point marked 
"Target Temperature Reached" with a green star. The text reads 
"Target reached overrides minimum run-time — stops immediately".

Scenario 3 "Ordinary Decision Hold (Contrast)": A blue bar 
followed by a yellow bar labeled "Decision Hold" with a small 
break icon and text "May be broken if waiting would be worse". 
A curved arrow shows the hold being bypassed.

Clean sans-serif typography, time axis with minute markers, 
Home Assistant color palette, white background, engineering 
diagram quality, no decorative elements
```

**File naming**: `images/compressor-protection-timing.svg`

**Estimated effort**: 2-3 hrs

---

### 14. Delta-T Flow Adequacy Diagram

**Purpose**:  
The concept that flow adequacy should be judged by delta-T (temperature rise across the heat pump) rather than by comparing against a datasheet minimum is counterintuitive and currently one of the most confusing sections in the documentation. Users naturally assume "below datasheet = problem." A diagram showing the relationship between flow rate, heat output, and temperature rise — with clear "healthy," "marginal," and "starved" zones — makes this concept click instantly.

**Placement**:  
- Primary: FILTRATION.MD — under "Judging Flow by Delta-T, Not by the Datasheet"  
- Secondary: TROUBLESHOOTING.MD — under "Flow Warnings" section

**Recommended format**: SVG vector diagram with graph + icons

**AI Generation Prompt**:
```
Technical diagram illustration showing the relationship between 
water flow rate and heat pump temperature rise, clean educational 
style.

Main graph: X-axis labeled "Water Flow Rate (m³/h)" from 0 to 4. 
Y-axis labeled "Temperature Rise / Delta-T (°C)" from 0 to 8. 
A hyperbolic curve starts high on left (7°C rise at 0.5 m³/h) 
and descends right (1°C rise at 3.5 m³/h). The curve is labeled 
"Fixed 3kW Heat Output" with a small lightning icon.

Three colored zones overlay the graph: Green zone (left-bottom, 
delta-T < 3°C) labeled "Healthy Flow" with checkmark. Yellow 
zone (delta-T 3-5°C) labeled "Marginal" with warning icon. 
Red zone (delta-T > 5°C) labeled "Starved — Risk of Derate/Trip" 
with stop icon.

A vertical dashed line at 2.0 m³/h labeled "Datasheet Minimum" 
with a note bubble reading "This is a proxy — not the real test". 
A horizontal arrow points from the curve to the delta-T zones 
emphasizing that delta-T is the verdict.

A small formula box at bottom reads: "ΔT = kW / (flow × 1.163)"

Clean sans-serif typography, grid lines, pool blue curve, 
Home Assistant zone colors, white background, educational 
diagram quality
```

**File naming**: `images/delta-t-flow-adequacy.svg`

**Estimated effort**: 2-3 hrs

---

## 🟠 HIGH PRIORITY (Should-Have)

---

### 15. Chemistry Dosing Workflow Flowchart

**Purpose**:  
The chemistry dosing process involves multiple steps (test → record reading → calculate dose → apply → circulate → log result) with branching logic (truncation for large pH corrections, different circulation durations per product). This workflow is currently described in prose across multiple paragraphs. A single flowchart communicates the entire process at a glance and serves as a quick reference for experienced users.

**Placement**:  
- Primary: CHEMISTRY.MD — under "What PoolSmart Handles" (replacing the text-heavy dosing description)  
- Secondary: GETTING_STARTED.MD — as a reference for "What to expect" section

**Recommended format**: SVG vector flowchart

**AI Generation Prompt**:
```
Vertical flowchart illustration showing pool chemistry dosing 
workflow, clean technical style.

Top: Rounded rectangle "Test Water" with AquaChek strip icon. 
Arrow down to:

Diamond decision "pH correction needed?" — Yes branch goes right 
to "Calculate dose from pool volume", No branch continues down 
to "Record reading for trend".

From "Calculate dose": Arrow to diamond "Correction > 0.4 pH?" 
— Yes branch goes to "Truncate to 0.4 pH max + warn user" with 
orange warning box reading "pH is buffered — overshoot risk". 
No branch goes to "Calculate full dose".

Both converge on "Display dose in ml (e.g., 18 ml pH-minus)" with 
a measuring cup icon. Arrow down to:

"Apply product to pool" with pour icon. Arrow down to diamond 
"Product type?" with four branches: "Non-chlorine shock → 30 min", 
"Maintenance chlorine → 4 hours", "Chlorine shock → 8 hours", 
"Algae treatment → until clear", "Tablet → no circulation needed".

All branches converge on "Circulate (pump runs)" with pump icon. 
Arrow down to "Log result" with clipboard icon. Arrow down to 
"Next test reminder" with calendar icon showing temperature-
based interval.

Clean sans-serif labels, rounded rectangles for processes, 
diamonds for decisions, pool blue and Home Assistant color 
palette, white background, flowchart quality, no decorative 
elements
```

**File naming**: `images/chemistry-dosing-workflow.svg`

**Estimated effort**: 2-3 hrs

---

### 16. Self-Learning Feedback Loop Diagram

**Purpose**:  
The self-learning model is PoolSmart's "secret sauce" — the mechanism that makes predictions more accurate over time. Currently described as a list (heating rate, heat loss, COP) plus three validation rules, the feedback loop nature of the system (session → measure → validate → learn → plan → next session) is not visually communicated. A circular feedback loop diagram instantly conveys that this is a continuous improvement system, not a one-time calculation.

**Placement**:  
- Primary: LEARNING.MD — under "What Is Learned?" (replacing or supplementing the COP curve)  
- Secondary: README.md (as a thumbnail showing "intelligent" aspect)

**Recommended format**: SVG vector circular diagram

**AI Generation Prompt**:
```
Circular feedback loop diagram, clean technical illustration style. 
A central circle labeled "PoolSmart Learning Model" with a brain/ 
gear hybrid icon. Four connected nodes arranged in a clockwise 
circle around the center:

Node 1 (top): "Heating Session" with thermometer icon and small 
graph showing temperature rising over time. Clockwise arrow to:

Node 2 (right): "Measure & Calculate" with calculator icon, 
three small readouts: "°C/h heating rate", "°C/h heat loss", 
"COP value". Clockwise arrow to:

Node 3 (bottom): "Validate" with shield/checkmark icon, three 
small rules listed: "Clean sessions only", "Weighted average", 
"Outlier rejection". A small red X appears next to a rejected 
data point. Clockwise arrow to:

Node 4 (left): "Update Model" with refresh/update icon, small 
graph showing a curve adjusting slightly. Clockwise arrow back 
to Node 1.

A small box outside the circle at bottom reads: "Each valid 
session nudges the model slightly — unusual sessions cannot 
corrupt the baseline."

Dashed arrows from "Validate" node to a small "Rejected Sessions 
Log" box on the right side with a clipboard icon.

Clean sans-serif typography, rounded node boxes, pool blue 
circular arrows, Home Assistant color palette, white background, 
systems diagram quality
```

**File naming**: `images/learning-feedback-loop.svg`

**Estimated effort**: 2 hrs

---

### 17. Filtration Rules Comparison Diagram

**Purpose**:  
The concept that the filtration requirement is the LARGER of two rules (turnover vs. daily minimum) is critical for understanding why a pool with a powerful pump might run much longer than expected. Currently shown only as a table of worked examples, this relationship would be much clearer as a graph showing where each rule dominates — helping users predict their runtime based on their pool volume and pump size.

**Placement**:  
- Primary: FILTRATION.MD — under "The Two Rules" section  
- Secondary: ARCHITECTURE.MD — under "Filtration Calculation"

**Recommended format**: SVG vector graph

**AI Generation Prompt**:
```
Technical graph illustration showing how two filtration rules 
interact, clean educational style. X-axis labeled "Pool Volume 
(L)" logarithmic scale from 1,000 to 100,000. Y-axis labeled 
"Daily Filtration Runtime (hours)" from 0 to 24.

Two curves on the graph: A blue straight line rising left-to-
right labeled "Rule 1: Turnover (volume-based)" — starts at 1h 
for 1000L, rises to 10h for 50000L. A green curve that starts 
low, rises steeply, then flattens labeled "Rule 2: Daily 
Minimum (temp-based)" — starts at 0.5h, rises to 5h at 28°C.

A thick red line traces the HIGHER of the two curves at each 
point, labeled "Actual Requirement (larger of the two)" with a 
bold red line. A shaded region between the red line and the 
lower curve shows "extra runtime from the dominant rule".

Two vertical callout boxes: One at 3800L reads "Small pool: 
minimum dominates (5h vs 3.2h)". One at 50000L reads "Large pool: 
turnover dominates (18.8h vs 5h)".

A legend at bottom identifies each curve. Clean sans-serif 
typography, grid lines, pool blue and Home Assistant colors, 
white background, educational graph quality
```

**File naming**: `images/filtration-rules-comparison.svg`

**Estimated effort**: 2 hrs

---

### 18. Price-Weighted COP Concept Diagram

**Purpose**:  
The idea that a higher electricity price at a warmer outdoor temperature can be cheaper per thermal kWh than a lower price at a colder temperature (due to COP differences) is the intellectual foundation of PoolSmart's price optimization. This concept is described in one sentence but is central to the value proposition. A visual comparison with two scenarios side-by-side makes this immediately intuitive.

**Placement**:  
- Primary: PLANNING.MD — under "Price Optimization Logic" (step 2: COP-weighted cost)  
- Secondary: README.md (as a thumbnail showing "smart" aspect)

**Recommended format**: SVG vector comparison diagram

**AI Generation Prompt**:
```
Side-by-side comparison diagram showing COP-weighted cost concept, 
clean educational infographic style.

Left panel titled "Scenario A: Lower Price, Cold Day": 
At top, a small thermometer showing "12°C" with a blue cold 
icon. Below, a price tag showing "€0.15/kWh" in green. Below, 
a heat pump icon with a small COP badge reading "COP 3.5". 
At bottom, a calculation box: "Effective cost = €0.15 ÷ 3.5 
= €0.043/thermal kWh" with a yellow "medium cost" indicator.

Right panel titled "Scenario B: Higher Price, Warm Day": 
At top, a small thermometer showing "22°C" with a warm orange 
icon. Below, a price tag showing "€0.20/kWh" in yellow. Below, 
a heat pump icon with a small COP badge reading "COP 6.5". 
At bottom, a calculation box: "Effective cost = €0.20 ÷ 6.5 
= €0.031/thermal kWh" with a green "LOWER cost" indicator.

A large comparison arrow between panels points right with 
label "Cheaper per thermal kWh despite higher electricity price!"

A small note at bottom: "The optimizer picks Scenario B — 
that's the self-learning COP curve at work."

Clean sans-serif typography, rounded panels, Home Assistant 
color palette, white background, infographic quality, no 
decorative elements
```

**File naming**: `images/cop-weighted-cost.svg`

**Estimated effort**: 2 hrs

---

## 🟡 MEDIUM PRIORITY (Valuable)

---

### 19. AI Advisory Layer Diagram

**Purpose**:  
The AI advisory layer's "non-blocking advisor" concept is subtle but important: the pool behaves identically whether AI is available or not, because the AI sits outside the control tick. This distinction (advisory vs. autonomous) matters for user trust. A diagram showing the AI layer as a separate track alongside the main control loop clarifies this architecture.

**Placement**:  
- Primary: ARCHITECTURE.MD — under "AI Advisory Layer"  
- Secondary: README.md (Features section — visual for AI capability)

**Recommended format**: SVG vector architecture diagram

**AI Generation Prompt**:
```
Architecture diagram showing AI advisory layer relationship to 
main control system, clean technical style.

Left side: A bold-bordered box labeled "Control Tick (every 
30s)" containing: "Priority Ladder", "Filtration Calc", 
"Heating Decision", "Compressor Protection". These are 
connected with solid arrows showing the main control flow. 
A label reads "This NEVER fails — core safety logic."

Right side: A dashed-border box labeled "AI Advisory Layer 
(optional)" containing: "Session Analysis", "Parameter 
Suggestions", "Manual Approval Gate". A dotted arrow connects 
this box to the control tick labeled "Proposes only — never 
applies automatically."

Below both: A decision diamond "AI unavailable?" with two 
branches: "Yes → Pool operates normally" (green checkmark) 
and "No → Suggestions shown for manual approval" (yellow 
info icon).

A small shield icon on the control tick box reads "Safety 
critical — zero external dependencies". A small brain icon 
on the AI box reads "Enhancement layer — zero risk".

Clean sans-serif typography, rounded boxes, solid vs dashed 
line distinction, pool blue for control, warm orange for AI, 
white background, architecture diagram quality
```

**File naming**: `images/ai-advisory-layer.svg`

**Estimated effort**: 1.5 hrs

---

### 20. Heating Sources Comparison Matrix

**Purpose**:  
The heating sources table (heat pump, electric, solar, gas, none) lists what each source "has" but doesn't communicate the practical implications. A visual comparison showing each source's characteristics (efficiency curve, temperature limits, control method) helps users understand why their heating source matters and what features it unlocks.

**Placement**:  
- Primary: HEATING.MD — under "Heating Sources"  
- Secondary: GETTING_STARTED.MD — as a reference for setup wizard

**Recommended format**: SVG vector comparison illustration

**AI Generation Prompt**:
```
Comparison matrix illustration of five heating sources, clean 
infographic style. Five horizontal rows, each representing a 
heating source, with four characteristic columns.

Row 1 "Heat Pump": Icons showing efficiency curve (upward 
graph), min air temp threshold (thermometer with cutoff), 
compressor protection (lock icon), COP learning (brain icon). 
Row colored light blue.

Row 2 "Electric Heater": Icons showing flat efficiency (straight 
line graph), no temp limit (infinite symbol), no compressor 
protection (dash), no COP (dash). Row colored light orange.

Row 3 "Solar Collector": Icons showing variable efficiency 
(sun graph), manual valve (hand icon), advisory only (speech 
bubble), free heat indicator (sun icon). Row colored light 
yellow.

Row 4 "Gas Heater": Icons showing fixed efficiency (straight 
graph), no temp limit (infinite symbol), no compressor 
protection (dash), fixed efficiency badge (pin icon). Row 
colored light gray.

Row 5 "No Heating": Dash marks across all columns except frost 
protection (snowflake icon). Row colored light gray.

Column headers: "Efficiency", "Temp Limit", "Protection", 
"COP Learning". Checkmarks and X marks for quick scanning. 
Clean sans-serif typography, rounded row backgrounds, Home 
Assistant color palette, white background, comparison 
infographic quality
```

**File naming**: `images/heating-sources-comparison.svg`

**Estimated effort**: 2 hrs

---

### 21. Filter Media Comparison Chart

**Purpose**:  
The filter media table (cartridge, sand, glass, filter balls) lists flow percentages and micron ratings but doesn't communicate the practical trade-offs. A visual comparison showing relative flow rates, filtration fineness, and the filter balls degradation warning helps users make informed decisions about their filter media.

**Placement**:  
- Primary: FILTRATION.MD — under "Filter Media"  
- Secondary: CONFIGURATION.MD — as a reference for media selection

**Recommended format**: SVG vector comparison chart

**AI Generation Prompt**:
```
Comparison chart illustration of four filter media types, clean 
infographic style. Four vertical panels side by side.

Panel 1 "Cartridge": A cylindrical filter icon with pleated 
texture. Below: flow bar at 60% (blue), micron badge "20-40 
micron", longevity icon (2 stars). Light blue background.

Panel 2 "Sand": A cylindrical filter icon with granular texture. 
Below: flow bar at 70% (blue), micron badge "20-40 micron", 
longevity icon (3 stars). Light green background.

Panel 3 "Glass": A cylindrical filter icon with crystalline 
texture. Below: flow bar at 72% (blue), micron badge "3-5 
micron" (highlighted green as best), longevity icon (4 stars). 
Light blue background.

Panel 4 "Filter Balls": A cylindrical filter icon with sphere 
texture. Below: flow bar at 80% (blue, highest), micron badge 
"5-15 micron", longevity icon (3 stars) with a warning triangle. 
A small warning callout reads "Compress over time — flow drops 
worse than sand". Light yellow background with orange warning 
border.

A small comparison arrow at bottom shows "← Less flow to More 
flow" and "← Coarse to Fine filtration". Clean sans-serif 
typography, rounded panels, Home Assistant color palette, 
white background, comparison infographic quality
```

**File naming**: `images/filter-media-comparison.svg`

**Estimated effort**: 1.5 hrs

---

### 22. Solar Collector Advisory Logic Diagram

**Purpose**:  
The solar collector concept (advised, not controlled; free heat when collector > pool; warning when collector < pool) is unique to PoolSmart and not intuitive. A decision-flow diagram showing when the system advises opening/closing the manual valve helps users understand how to act on the integration's recommendations.

**Placement**:  
- Primary: HEATING.MD — under "Solar Collectors"  
- Secondary: PLANNING.MD — under "Solar Surplus" (complementing the surplus threshold diagram)

**Recommended format**: SVG vector decision flowchart

**AI Generation Prompt**:
```
Decision flowchart illustration showing solar collector advisory 
logic, clean technical style.

Top: Two thermometer icons side by side — left labeled 
"Collector Temp" with sun icon, right labeled "Pool Temp" 
with water icon. Arrow down to:

Diamond decision "Collector > Pool?" 
— Yes branch (green): "FREE HEAT — Open valve" with arrow 
icon pointing to open valve symbol. A small sunburst icon 
indicates energy gain.
— No branch (red): "HEAT LOSS — Keep valve closed" with 
closed valve symbol. A small downward arrow indicates energy 
loss.

Below the Yes branch: A note box reading "Above solar surplus 
threshold, heating is treated as free and price limit is ignored."

Below the No branch: A note box reading "Sending water through 
a cooler collector loses heat — integration warns you."

A small manual valve icon at bottom with label "Almost all 
solar collectors use a manual 3-way valve — PoolSmart advises, 
you switch."

Clean sans-serif typography, rounded decision diamond, green 
and red branches, pool blue accents, white background, 
flowchart quality
```

**File naming**: `images/solar-collector-logic.svg`

**Estimated effort**: 1.5 hrs

---

### 23. Chemistry Circulation Timing Comparison

**Purpose**:  
The concept that different chemistry products require vastly different circulation durations (30 min for non-chlorine shock vs. full night for chlorine shock) is important for effective treatment. A visual timeline comparing all five product types makes it easy to see at a glance how long to run the pump after each treatment.

**Placement**:  
- Primary: CHEMISTRY.MD — under "Circulation That Matches the Product"  
- Secondary: CHEMISTRY.MD — near the dosing workflow flowchart

**Recommended format**: SVG vector timeline comparison

**AI Generation Prompt**:
```
Horizontal timeline comparison illustration showing circulation 
duration for five pool chemistry products, clean infographic style.

A shared horizontal time axis from 0 to 12 hours with hour 
markers. Five horizontal bars stacked vertically, each 
representing a product:

Row 1 "Non-Chlorine Shock": A short green bar from 0 to 0.5h. 
Label: "30 min — fast-acting, done quickly".

Row 2 "Maintenance Chlorine": A medium blue bar from 0 to 4h. 
Label: "4 hours — needs contact time".

Row 3 "Chlorine Shock": A long orange bar from 0 to 8h (full 
night). Label: "Full night — reaches every corner, pulled 
through filter".

Row 4 "Algae Treatment": A dashed purple bar from 0 to 12h+ 
with arrow at end. Label: "Until visibly clear — variable".

Row 5 "Tablet (Floater)": A gray bar with "X" through it. 
Label: "None — dissolves over days, nothing to circulate".

A small warning icon next to the chlorine shock bar reads 
"Stopping early leaves undissolved product — bleaches liner".

Clean sans-serif typography, rounded bar ends, product-colored 
bars, Home Assistant palette, white background, comparison 
infographic quality
```

**File naming**: `images/chemistry-circulation-timing.svg`

**Estimated effort**: 1.5 hrs

---

### 24. Dashboard Structure Overview

**Purpose**:  
The lovelace/README.md describes a three-tab dashboard (Water, Energie, [third tab]) but doesn't show what each tab contains. A visual overview showing the dashboard structure with card previews helps users understand what they're installing and how to navigate it — increasing adoption of the dashboard feature.

**Placement**:  
- Primary: lovelace/README.md — under "Installing It" (as a preview)  
- Secondary: README.md — as a thumbnail linking to lovelace docs

**Recommended format**: SVG vector mockup

**AI Generation Prompt**:
```
Dashboard structure overview illustration, clean technical style. 
Three vertical panels side by side representing three dashboard 
tabs, connected by a tab bar at top.

Left panel "Water Tab" with mushroom-style cards: Temperature 
gauge card (circular gauge icon), pH number input card, 
chlorine number input card, chemistry status card. Light blue 
background.

Center panel "Energy Tab" with card previews: Temperature 
graph card (mini-graph icon), COP display card, price display 
card, solar surplus indicator. Light orange background.

Right panel "Equipment Tab" with card previews: Pump status 
indicator, heat pump status, flow meter reading, filter 
service warning. Light green background.

Each card shown as a small rounded rectangle with a simple 
icon representing its content. A label at bottom reads 
"Three-tab Lovelace dashboard — customize by adding/removing 
cards you don't have."

A small note at bottom: "Uses mushroom, button-card, apexcharts-
card, mini-graph-card (optional)."

Clean sans-serif typography, card-style layout, Home Assistant 
color palette, white background, UI mockup quality
```

**File naming**: `images/dashboard-structure.svg`

**Estimated effort**: 2 hrs

---

### 25. Troubleshooting Decision Tree

**Purpose**:  
The troubleshooting document lists symptoms, causes, and fixes in tables — but a decision tree guides users from "something is wrong" to the specific fix through a series of yes/no questions. This is the fastest path to resolution and reduces frustration. The tree should cover the top 5-7 most common issues.

**Placement**:  
- Primary: TROUBLESHOOTING.MD — at the top (before the tables, as a quick-start diagnostic)  
- Secondary: GETTING_STARTED.MD — under "Common First-Day Questions"

**Recommended format**: SVG vector decision tree

**AI Generation Prompt**:
```
Decision tree flowchart for pool system troubleshooting, clean 
technical style. Top-to-bottom flow starting from a single entry 
point.

Top: Rounded rectangle "Something seems wrong" with question 
mark icon. Arrow down to:

Level 1 — Diamond "Pump running?" 
— No branch goes LEFT to Level 2a
— Yes branch goes RIGHT to Level 2b

Level 2a — Diamond "Status sensor shows 'idle'?" 
— Yes: Green box "Normal — no demand right now" with checkmark
— No: Arrow to "Check next scheduled block on panel"

Level 2b — Diamond "Heating or filtering?" 
— Heating path → Diamond "Cold weather?" → Yes: "Envelope gate 
  active — normal below 11°C" / No: "Check price sensor forecast"
— Filtering path → Diamond "Flow detected?" → No: "Check flow 
  meter mapping or clean filter" / Yes: "Delta-T high? Clean 
  filter or verify installation"

A small "Quick Fixes" box at bottom with three items: 
"1. Check Diagnostics tab in /poolsmart panel", 
"2. Verify sensor mappings in Configure → Sensors", 
"3. Download diagnostics file for support"

Clean sans-serif typography, rounded diamonds for decisions, 
colored outcome boxes (green = normal, yellow = check, red = 
fix needed), pool blue arrows, white background, decision 
tree quality
```

**File naming**: `images/troubleshooting-decision-tree.svg`

**Estimated effort**: 2-3 hrs

---

### 26. User Journey Roadmap

**Purpose**:  
The GETTING_STARTED.MD "What to Expect on Day One" table shows timeframes but lacks a visual sense of progression. A roadmap illustration showing the user's journey from installation through mastery (first 5 min → first hour → first day → first week → first month) creates confidence and sets expectations.

**Placement**:  
- Primary: GETTING_STARTED.MD — under "What to Expect on Day One"  
- Secondary: README.md — as a thumbnail showing "easy setup"

**Recommended format**: SVG vector roadmap illustration

**AI Generation Prompt**:
```
Horizontal roadmap illustration showing user journey timeline, 
clean infographic style. Five milestone nodes connected by a 
curved path on a subtle landscape background.

Milestone 1 "First 5 Minutes" (left): Checklist icon with 
"Install via HACS", "Complete wizard", "PoolSmart filtering". 
Green color — quick win.

Milestone 2 "First Hour": Clock icon with "Pump turns on/off", 
"Status sensor updates", "First decision made". Blue color.

Milestone 3 "First Day": Calendar icon with "Filtration blocks 
run", "Heating demand evaluated", "Panel shows progress". 
Blue color.

Milestone 4 "First Week": Chart icon with "Learning model 
collects data", "COP curve starts forming", "First session 
validated". Orange color.

Milestone 5 "First Month": Trophy icon with "Predictions 
improve", "Price optimization tunes", "Fully optimized 
system". Gold/orange color — achievement.

Each milestone has a circular node with icon, a connecting 
arrow to the next, and 2-3 bullet points below. A subtle 
progress bar at bottom fills from left to right. A small 
checkmark appears on completed milestones.

Clean sans-serif typography, rounded nodes, Home Assistant 
color palette progressing from green to gold, white 
background, roadmap infographic quality
```

**File naming**: `images/user-journey-roadmap.svg`

**Estimated effort**: 2 hrs

---

### 27. Filter Resistance Over Time Graph

**Purpose**:  
The filter resistance concept (manufacturer flow is without filter; 60-75% remains with filter; drops as filter fouls) is currently described in two sentences. A graph showing flow rate declining over time as the filter ages — with service warning thresholds marked — helps users understand why their runtime increases over time and when to service the filter.

**Placement**:  
- Primary: FILTRATION.MD — under "Filter Resistance"  
- Secondary: ARCHITECTURE.MD — under "Key Filtration Behaviors"

**Recommended format**: SVG vector graph

**AI Generation Prompt**:
```
Technical graph illustration showing filter resistance effect 
on pump flow over time, clean educational style.

X-axis labeled "Time Since Last Filter Service (weeks)" from 
0 to 20. Y-axis labeled "Effective Pump Flow (% of rated)" 
from 0 to 100.

A declining curve starts at 75% at week 0 (labeled "New filter 
— ~75% of rated flow"), gradually descends to 60% at week 8, 
then drops more steeply to 40% at week 16. The curve is colored 
in gradient from green (top-left) through yellow to red 
(bottom-right).

A horizontal dashed line at 60% labeled "Typical clean filter 
baseline". A horizontal dashed line at 40% labeled "Service 
Warning Threshold" with a warning triangle icon. A shaded 
red zone below 40% reads "Service Recommended".

A small annotation at week 12 reads "Block duration increases 
to compensate — this is automatic with a flow meter".

A small box at bottom reads: "Without a flow meter, the system 
derates rated flow by 25-40% to estimate. With one, block 
duration self-corrects as the filter ages."

Clean sans-serif typography, grid lines, Home Assistant color 
palette, white background, technical graph quality
```

**File naming**: `images/filter-resistance-graph.svg`

**Estimated effort**: 1.5 hrs

---

## 🟢 NICE-TO-HAVE (Polish)

---

### 28. README Hero Banner Image

**Purpose**:  
The README currently has a centered logo at top but lacks a hero banner image that immediately communicates "this is a smart pool controller for Home Assistant." A banner image spanning the width of the README creates a strong first impression and makes the GitHub project page feel more polished and professional.

**Placement**:  
- Primary: README.md — between the title/tagline and the opening paragraph  
- Format: Open Graph compatible (1200×630px for social sharing)

**Recommended format**: SVG vector banner (with PNG export for OG)

**AI Generation Prompt**:
```
Wide banner illustration for a smart pool controller project, 
modern flat design style. Horizontal composition 16:9 aspect 
ratio.

Left side: A stylized swimming pool viewed from above with 
gentle water ripples in pool blue (#00ACC1). Small icons float 
above the pool: a thermometer, a water drop, a sun, and a gear.

Center: A subtle Home Assistant blue (#03A9F4) glow with a 
house icon silhouette, connected to the pool by a thin glowing 
line suggesting data flow.

Right side: A small ESP32 board icon with sensor probe icons 
and a WiFi signal arc.

Background: Clean white (#FAFAFA) with a subtle gradient. 
Text area is left-aligned with space for title overlay. The 
overall feel is technical yet welcoming, smart-home aesthetic, 
no people, no photorealistic elements. Flat vector style with 
subtle shadows.
```

**File naming**: `images/readme-hero-banner.svg` (+ `.png` for OG)

**Estimated effort**: 2-3 hrs

---

### 29. Open Graph Social Preview Image

**Purpose**:  
When the GitHub repo is shared on social media (Twitter, LinkedIn, Discord), the preview card currently shows only the repository description without a custom image. An Open Graph image (1200×630px) with the PoolSmart branding, a pool icon, and a tagline makes shares more eye-catching and professional.

**Placement**:  
- GitHub repository → Settings → Social preview image  
- Also usable for HACS listing, forum posts, Discord shares

**Recommended format**: PNG (1200×630px) — OG standard format

**AI Generation Prompt**:
```
Social media preview image for a GitHub repository, modern 
tech branding style. 1200×630px horizontal canvas.

Background: Gradient from pool blue (#00ACC1) at left to 
Home Assistant blue (#03A9F4) at right, with subtle geometric 
patterns (circuit-board-like lines suggesting smart technology).

Center-left: A clean white rounded rectangle (semi-transparent) 
containing the PoolSmart logo and tagline "Intelligent swimming 
pool controller for Home Assistant".

Center-right: A stylized icon composition showing a pool with 
water waves, a heat pump, a solar panel, and connecting arrows 
forming a circular "optimization" loop.

Bottom-left: Small HACS badge icon. Bottom-right: GitHub stars 
icon placeholder.

Clean, professional, modern SaaS-style branding. No text 
other than logo and tagline. High contrast for readability at 
small sizes. Flat vector style, no gradients on text.
```

**File naming**: `images/og-social-preview.png`

**Estimated effort**: 1-2 hrs

---

### 30. Custom Feature Badge Set

**Purpose**:  
The README uses standard shields.io badges (HACS, Version, License). Custom badges for PoolSmart's key features (Smart Filtration, Price-Aware Heating, Self-Learning, Solar Optimization, Chemistry Dosing) would make the feature list more scannable and visually distinctive.

**Placement**:  
- Primary: README.md — replacing or supplementing the Feature table  
- Secondary: HACS repository description

**Recommended format**: SVG (shields.io compatible) or PNG sprites

**AI Generation Prompt**:
```
Set of five custom badge graphics for a pool controller project, 
shields.io style. Each badge is a small horizontal pill-shaped 
icon (approximately 120×24px) with a flat icon on left and 
label on right.

Badge 1: Water drop icon + "Smart Filtration" — pool blue 
(#00ACC1) background, white text.

Badge 2: Lightning bolt icon + "Price-Aware" — warm orange 
(#FF9800) background, white text.

Badge 3: Brain/chart icon + "Self-Learning" — Home Assistant 
blue (#03A9F4) background, white text.

Badge 4: Sun icon + "Solar Optimized" — yellow (#FFC107) 
background, dark text.

Badge 5: Flask icon + "Chemistry" — green (#4CAF50) background, 
white text.

Clean sans-serif typography (DejaVu Sans or similar), flat 
icons ( Feather/Material style), consistent badge dimensions, 
slight rounded corners (3px), no shadows. Designed to work 
inline with shields.io badges at small scale.
```

**File naming**: `images/badges/` directory with individual SVGs or a single sprite

**Estimated effort**: 1-2 hrs

---

### 31. Entity ID Naming Convention Diagram

**Purpose**:  
The ENTITIES.MD document explains the "fixed IDs, translated names" concept but it's hard to grasp without seeing an example. A side-by-side comparison showing a Dutch install and an English install with the same entity IDs but different display names makes this concept immediately clear.

**Placement**:  
- Primary: ENTITIES.MD — under "Fixed IDs, Translated Names"  
- Secondary: README.md — as a small thumbnail for "works in any language"

**Recommended format**: SVG vector comparison

**AI Generation Prompt**:
```
Side-by-side comparison diagram showing entity ID naming 
convention, clean technical style.

Left panel titled "Dutch Install": Shows a Home Assistant 
entity card with display status "Klaar om 14:30" (Dutch for 
"Ready at 14:30"). Below the card, a code-style label reads 
"sensor.pool_ready_at" in monospace font.

Right panel titled "English Install": Shows the same entity 
card with display status "Ready at 14:30". Below the card, 
the same code-style label reads "sensor.pool_ready_at" in 
monospace font.

A bold double-arrow between panels connects the two code 
labels with text "Same ID — different display". 

A small box at bottom reads: "Names are for reading, IDs are 
for referring to. Dashboards and automations work everywhere."

A warning icon with text "Home Assistant normally derives 
the ID from the name → sensor.pool_klaar_om (useless for 
sharing)".

Clean sans-serif typography, monospace for IDs, Home Assistant 
card styling mockup, white background, comparison diagram 
quality
```

**File naming**: `images/entity-id-convention.svg`

**Estimated effort**: 1 hr

---

### 32. Chemistry Dose Truncation Warning Graphic

**Purpose**:  
The pH dose truncation rule (corrections larger than 0.4 pH are truncated with a warning) is a safety feature that needs visual emphasis. A small warning graphic that appears next to the dose recommendation in documentation (and conceptually in the UI) reinforces this important limitation.

**Placement**:  
- Primary: CHEMISTRY.MD — under "A Dose, Not a Number"  
- Secondary: Could be reused in the management panel UI

**Recommended format**: SVG vector warning graphic

**AI Generation Prompt**:
```
Warning graphic illustration for pH dose truncation, clean 
technical style. A horizontal composition.

Left: A pH scale from 6.8 to 8.2 with a red zone from 6.8 to 
7.2 labeled "Too acidic" and a blue zone from 7.8 to 8.2 
labeled "Too alkaline".

Center: A large measuring cup icon with "pH-minus" label. 
A curved arrow from the cup points to the pH scale showing 
a correction of 0.4 units. Beyond 0.4, a red stop symbol 
appears with text "Truncated — buffered correction, 
overshoot risk".

Right: A small pool cross-section showing pH balanced water 
with a checkmark.

A banner at bottom reads: "pH is buffered by alkalinity. 
Attempting a full point correction in one dose will overshoot."

Warning orange and red color accents, pool blue for balanced 
state, clean sans-serif typography, white background, warning 
graphic quality
```

**File naming**: `images/ph-truncation-warning.svg`

**Estimated effort**: 1 hr

---

### 33. Night Quiet Mode Override Diagram

**Purpose**:  
The "night quiet" exception in the priority ladder (branches 0-5 ignore night quiet, branches 6-8 respect it) is subtle but affects when the pump can run. A visual showing which priorities can run at night and which are silenced helps users understand scheduling behavior — especially relevant for noise-sensitive installations.

**Placement**:  
- Primary: ARCHITECTURE.MD — under "The Priority Decision Ladder" (near the table)  
- Secondary: CONFIGURATION.MD — as a reference for quiet hours settings

**Recommended format**: SVG vector illustration

**AI Generation Prompt**:
```
Diagram illustration showing night quiet mode override behavior, 
clean technical style. Horizontal composition with a day/night 
cycle at top and priority branches below.

Top: A horizontal day/night bar showing 6am-10pm as day (yellow 
sun icon) and 10pm-6am as night (gray moon icon). A label reads 
"Quiet Hours (configurable)".

Below: A vertical list of priority branches 0-9. Each branch 
has a small icon on the right showing either a moon with slash 
(ignores quiet) or a moon without slash (respects quiet).

Branches 0-5 (Emergency, Frost, Manual, Chemistry, Filtration 
Deadline, Free Electricity): Moon-with-slash icon + "Runs at 
any time — safety first". Colored red/orange for emphasis.

Branches 6-8 (Heating, Scheduled Filtration, Pump Rundown): 
Moon icon + "Respects quiet hours — deferred to daytime". 
Colored blue/green.

Branch 9 (Idle): Dash icon — "No action either way". Gray.

A small note at bottom: "Even during quiet hours, safety-critical 
branches (frost protection, emergency stop) can activate the 
pump."

Clean sans-serif typography, consistent icon sizing, Home 
Assistant color palette, white background, technical diagram 
quality
```

**File naming**: `images/night-quiet-override.svg`

**Estimated effort**: 1.5 hrs

---

## Implementation Roadmap (Round 2)

### Phase 5: Safety & Clarity (Week 9-10)
These address the most confusing concepts and safety-critical information:

| Asset | Format | Est. Effort |
|---|:---:|:---:|
| Compressor Protection Timing Diagram | SVG | 2-3 hrs |
| Delta-T Flow Adequacy Diagram | SVG | 2-3 hrs |
| Chemistry Dosing Workflow Flowchart | SVG | 2-3 hrs |
| Self-Learning Feedback Loop | SVG | 2 hrs |
| Filtration Rules Comparison | SVG | 2 hrs |
| Price-Weighted COP Concept | SVG | 2 hrs |

### Phase 6: Feature Understanding (Week 11-12)
These help users understand what their system can do:

| Asset | Format | Est. Effort |
|---|:---:|:---:|
| AI Advisory Layer Diagram | SVG | 1.5 hrs |
| Heating Sources Comparison | SVG | 2 hrs |
| Filter Media Comparison | SVG | 1.5 hrs |
| Solar Collector Logic | SVG | 1.5 hrs |
| Chemistry Circulation Timing | SVG | 1.5 hrs |

### Phase 7: Navigation & Diagnostics (Week 13-14)
These improve findability and problem-solving:

| Asset | Format | Est. Effort |
|---|:---:|:---:|
| Dashboard Structure Overview | SVG | 2 hrs |
| Troubleshooting Decision Tree | SVG | 2-3 hrs |
| User Journey Roadmap | SVG | 2 hrs |
| Filter Resistance Graph | SVG | 1.5 hrs |

### Phase 8: Brand & Polish (Week 15+)
These round out the documentation and improve first impressions:

| Asset | Format | Est. Effort |
|---|:---:|:---:|
| README Hero Banner | SVG/PNG | 2-3 hrs |
| Open Graph Social Image | PNG | 1-2 hrs |
| Custom Feature Badges | SVG | 1-2 hrs |
| Entity ID Convention Diagram | SVG | 1 hr |
| pH Truncation Warning | SVG | 1 hr |
| Night Quiet Override Diagram | SVG | 1.5 hrs |

---

## Priority Summary (All 33 Assets)

| Round | Critical | High | Medium | Nice-to-Have | Total |
|:---:|:---:|:---:|:---:|:---:|:---:|
| Round 1 | 3 | 3 | 4 | 2 | 12 |
| Round 2 | 2 | 4 | 7 | 5 | 18* |
| **Total** | **5** | **7** | **11** | **7** | **30** |

*Round 2 total includes 3 README/brand assets that serve multiple purposes.

---

## Recommended Creation Order

For maximum impact with limited resources, create assets in this order:

1. **Compressor Protection Timing Diagram** — Safety-critical concept, currently text-only
2. **Delta-T Flow Adequacy Diagram** — Most confusing section in docs
3. **Chemistry Dosing Workflow** — Multi-step process, currently text-heavy
4. **Self-Learning Feedback Loop** — Core value proposition visual
5. **Filtration Rules Comparison** — Explains counterintuitive runtime behavior
6. **Price-Weighted COP Concept** — Foundation of the "smart" value proposition
7. **Troubleshooting Decision Tree** — Reduces support burden
8. **User Journey Roadmap** — Builds confidence for new users
9. **README Hero Banner** — Improves first impression
10. **Open Graph Social Image** — Improves social sharing conversion

---

*Document prepared for the PoolSmart development team. All prompts are ready for use with Midjourney, DALL-E, Stable Diffusion, Flux, or similar AI image generation tools. SVG-format recommendations should be refined by a designer after AI generation to ensure technical accuracy.*

---

## 🆕 Additional Recommendations — Documentation Coverage Pass

> **Prepared by**: Image Prompt Engineer
> **Date**: 2026-08-20
> **Focus**: Audit found four documentation pages with zero images — getting_started.md, configuration.md, logging.md, defaults.md. These are the remaining gaps after the Round 1 and Round 2 passes above (lovelace/README.md, brand-image.md, and hardware.md are covered separately by reusing already-generated-but-unused assets).

---

### 34. Getting-Started Journey Diagram

**Purpose**:
New users arriving at getting_started.md are met with a wall of prose before they understand the shape of the setup process. A simple, friendly horizontal flow of the four concrete milestones — install, verify, map sensors, understand the first decision — sets expectations up front and signals "this is approachable," reducing first-run anxiety before the step-by-step instructions begin.

**Placement**:
- Primary: getting_started.md — near the top, immediately below the introduction and above the first "Step 1" heading, as a visual table of contents for the whole page

**Recommended format**: SVG vector diagram (flat, clean, matching the existing priority-ladder.svg / dashboard-mockup.svg diagram aesthetic — not photorealistic)

**AI Generation Prompt**:
```
Simple horizontal 4-step journey diagram, clean flat vector 
illustration style, friendly and welcoming — not intimidating 
or overly technical.

Four circular milestone nodes arranged left to right, connected 
by a gently curved arrow path (not a rigid straight line — 
suggest an easy, approachable journey).

Node 1 "Install via HACS": Rounded circle in pool blue (#00ACC1) 
containing a simple download/puzzle-piece icon. Small label 
below reads "Install via HACS".

Node 2 "Verify Status Sensor": Rounded circle in HA blue 
(#03A9F4) containing a simple checkmark-in-a-badge icon. Label 
below reads "Verify status sensor".

Node 3 "Map Your Sensors": Rounded circle in warm orange 
(#FF9800) containing a simple thermometer-and-link icon. Label 
below reads "Map your sensors".

Node 4 "Understand Your First Decision": Rounded circle in a 
soft green containing a simple lightbulb-with-checkmark icon. 
Label below reads "Understand your first decision".

Each node has a small step number badge (1, 2, 3, 4) in the 
top-left corner. The connecting path has a small friendly 
arrowhead between each node, no harsh angles. A subtle light 
gray (#FAFAFA) background with generous white space. Rounded, 
soft shadows, consistent stroke width, clean sans-serif 
typography (Inter/Roboto style), no people, no photorealistic 
elements, onboarding-illustration quality rather than dense 
engineering-diagram quality — approachable and light
```

**File naming**: `images/getting-started-journey.svg`

**Estimated effort**: 1.5 hrs

---

### 35. Options Flow Map

**Purpose**:
The Configure menu in configuration.md exposes eight distinct sections, but users currently have to read a linear list to understand what lives where. A hub-and-spoke settings map gives an immediate mental model of the configuration surface — "one central place, eight focused areas" — and helps users jump straight to the section they need instead of hunting through prose.

**Placement**:
- Primary: configuration.md — near the top, under the introductory paragraph and before the per-section detail headings, as an at-a-glance map of the Configure menu

**Recommended format**: SVG vector hub-and-spoke diagram (flat, clean, settings-map style, matching the existing data-flow.svg / architecture-overview.svg diagram aesthetic)

**AI Generation Prompt**:
```
Hub-and-spoke settings map diagram, clean flat vector 
illustration style, technical documentation quality.

Center: A prominent rounded rectangle hub node labeled 
"Configure" in Home Assistant blue (#03A9F4) with a small gear 
icon, slightly larger than the surrounding nodes to establish 
visual hierarchy.

Eight spoke nodes arranged evenly in a circle around the hub, 
each connected to the center by a short straight line (like 
spokes of a wheel):

1. "Sensors and switches" — small sensor/toggle icon, pool blue.
2. "Pool and pump" — small pool-with-pump icon, pool blue.
3. "Heating appliance" — small heat pump icon, warm orange 
   (#FF9800).
4. "When to heat" — small clock-with-flame icon, warm orange.
5. "Filtration" — small filter-cylinder icon, pool blue.
6. "Water treatment" — small flask/droplet icon, teal.
7. "Notifications" — small bell icon, HA blue.
8. "Advanced" — small wrench/gear icon, mid gray (#9E9E9E).

Each spoke node is a small rounded rectangle with icon on top 
and label below. Consistent node sizing across all eight. Clean 
sans-serif typography, thin connecting lines in light gray, 
white/off-white (#FAFAFA) background, subtle shadows on nodes, 
settings-map / control-panel quality, no decorative elements, 
no people
```

**File naming**: `images/options-flow-map.svg`

**Estimated effort**: 2 hrs

---

### 36. Actionable Notification Mockup

**Purpose**:
logging.md describes actionable push notifications (e.g. a heating-postponed alert with response buttons) purely in text. A realistic mobile mockup of the Home Assistant companion app notification — complete with its action buttons — shows users exactly what to expect on their phone and demonstrates that they can respond directly from the notification, not just read it.

**Placement**:
- Primary: logging.md — under the section describing actionable notifications, as a visual example of the notification shown in the text

**Recommended format**: SVG vector UI mockup (flat, clean, matching the existing dashboard-mockup.svg UI-mockup aesthetic — a stylized phone frame with a realistic-looking but clearly illustrated notification, not a photorealistic phone render)

**AI Generation Prompt**:
```
Mobile phone notification UI mockup, clean flat vector 
illustration style, matching a modern smart-home companion app.

A simplified smartphone frame (rounded rectangle, minimal bezel, 
small notch at top) shown from the front, phone lock screen 
with a subtle dark gradient background and a faint clock/date 
readout at the top.

Centered on the lock screen: a Home Assistant companion-app 
push notification card — white rounded rectangle with soft 
shadow. Top row of the card shows a small Home Assistant blue 
(#03A9F4) house-icon app badge, the app name "Home Assistant" 
in small gray text, and a timestamp "now" aligned right.

Below the app row: a bold title line reading "Heating postponed" 
with a small orange (#FF9800) pause/clock icon to its left. 
Below the title, a shorter gray body line reading "Electricity 
price is high right now — heating has been delayed."

Below the body text: two full-width action buttons side by side, 
separated by a thin divider line, styled like standard iOS/
Android notification action buttons (flat, no background fill, 
just bold text): left button reads "Heat now anyway" in warm 
orange (#FF9800) text, right button reads "Do not heat today" 
in pool blue (#00ACC1) text.

Clean sans-serif typography (system UI font style), realistic 
but illustrated notification card proportions, subtle drop 
shadow separating the card from the lock screen background, 
phone frame in neutral dark gray, no other lock-screen clutter, 
no people, UI-mockup quality, documentation-illustration 
finish rather than a literal photorealistic screenshot
```

**File naming**: `images/notification-actions-mockup.svg`

**Estimated effort**: 2 hrs

---

### 37. Defaults File Override Flow

**Purpose**:
defaults.md explains that a user-supplied `poolsmart_defaults.json` file can override the integration's built-in defaults to pre-fill the setup wizard, but the merge relationship (built-in baseline, selective override, merged result) is only described in prose. A simple flow diagram makes the override mechanic visually obvious — which values come from where, and that only the keys present in the user's file change anything.

**Placement**:
- Primary: defaults.md — under the section introducing `poolsmart_defaults.json`, showing how the file relates to the built-in defaults and the setup wizard

**Recommended format**: SVG vector flow diagram (flat, clean, matching the existing data-flow.svg / options-flow-map.svg diagram aesthetic)

**AI Generation Prompt**:
```
Simple three-part merge/override flow diagram, clean flat 
vector illustration style, technical documentation quality.

Left: A rounded rectangle box labeled "Built-in Defaults" in 
mid gray (#9E9E9E), containing a small document icon and a 
short illustrative list of key-value pairs shown as faint gray 
text lines (e.g. "pool_volume: 20000", "target_temp: 28", 
"min_air_temp: 11") — suggesting a complete baseline config.

Below-left, feeding into the same merge point: A smaller rounded 
rectangle labeled "poolsmart_defaults.json (yours)" in warm 
orange (#FF9800), containing a small file/JSON-brackets icon 
and only one or two highlighted key-value lines (e.g. 
"pool_volume: 35000") in bold orange text — suggesting a 
partial, selective override file.

Center: A merge point shown as a funnel or converging-arrows 
icon labeled "Override — matching keys replaced, everything 
else keeps the built-in value", where the gray baseline lines 
and the orange override line combine into one arrow.

Right: A rounded rectangle box labeled "Setup Wizard — 
Pre-filled Fields" in pool blue (#00ACC1), containing simplified 
form-field icons (small labeled input boxes) already populated 
with values — most fields shown in gray (from built-in 
defaults) and the one overridden field shown highlighted in 
orange, making clear which value came from the user's file.

Clean sans-serif typography, thin connecting arrows, rounded 
boxes, light gray (#FAFAFA) background, subtle shadows, 
systems-diagram quality, no decorative elements, no people
```

**File naming**: `images/defaults-override-flow.svg`

**Estimated effort**: 1.5 hrs

---

### 38. What-to-Expect Timeline (Day One)

**Purpose**:
Getting Started is the highest-traffic page in the docs — the first thing anyone
scrolls through before deciding whether to keep going. The "What to Expect on
Day One" table lists five timeframes (30 seconds → first month) but reads as a
flat list; a timeline makes the *shape* of the rollout visible: instant
decisions from second one, learning quality rising gradually afterward.

**Placement**:
Primary: getting_started.md — under "What to Expect on Day One", above the table

**Recommended format**: SVG horizontal timeline (flat diagram style, matching
getting-started-journey.svg)

**AI Generation Prompt**:

```
Clean horizontal timeline infographic, flat vector illustration
style. A baseline runs left to right with five evenly-spaced
circular markers, each in a different accent color (pool blue,
HA blue, warm orange, purple, green). Above each marker, a small
white card with a rounded border in the marker's color contains
a short label: "Pool state evaluated, branch chosen" (30 seconds),
"Pump on/off per filtration block" (first hour), "Daily filtration
block, any heating demand" (first day), "Session data collected
per heating cycle" (first week), "Heat loss learned, timing
tightens up" (first month). Below each marker, bold text names
the timeframe. The overall shape should read left-to-right as
"instant, then gradually smarter" — the first marker larger or
more emphasized than the rest to show immediacy. Clean sans-serif
typography, light gray (#FAFAFA) background, subtle card shadows,
onboarding-illustration quality, no people, no clutter
```

**File naming**: `images/day-one-timeline.svg`

**Estimated effort**: 1 hr

---
