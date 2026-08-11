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

*Document prepared for the PoolSmart development team. All prompts are ready for use with Midjourney, DALL-E, Stable Diffusion, Flux, or similar AI image generation tools. SVG-format recommendations should be refined by a designer after AI generation to ensure technical accuracy.*
