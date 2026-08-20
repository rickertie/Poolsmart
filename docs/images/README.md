# PoolSmart Visual Assets

This directory contains visual assets for the PoolSmart documentation.
All paths use forward slashes for cross-platform compatibility.

## Image Inventory

| # | File | Status | Used In | Description |
|---|------|--------|---------|-------------|
| 1 | `architecture-overview.svg` | Generated | index.md | System architecture overview: ESPHome → HA → Decision Engine |
| 2 | `priority-ladder.svg` | Generated | architecture.md | 10-branch priority ladder flowchart |
| 3 | `dashboard-mockup.svg` | Generated | index.md, lovelace/README.md | Three-tab pool management panel mockup |
| 4 | `cop-curve.svg` | Generated | learning.md | COP vs outdoor temperature curve |
| 5 | `heating-timeline.svg` | Generated | planning.md | Maintenance vs seasonal heating timeline |
| 6 | `turnover-infographic.svg` | Generated | filtration.md | Cumulative filtration effectiveness chart |
| 7 | `operating-envelope.svg` | Generated | troubleshooting.md | Heat pump temperature thresholds |
| 8 | `solar-surplus.svg` | Generated | planning.md | Solar surplus heating diagram |
| 9 | `data-flow.svg` | Generated | entities.md | Data flow and entity relationship map |
| 10 | `chemistry-intervals.svg` | Generated | chemistry.md | Test intervals by water temperature |
| 11 | `heat-loss-comparison.svg` | Generated | heating.md | Pool cover vs no cover heat loss |
| 12 | `bucket-test-calibration.svg` | Placeholder | esphome.md | Flow meter calibration procedure |
| 13 | `getting-started-journey.svg` | Placeholder | getting_started.md | 4-step onboarding journey: install, verify, map sensors, first decision |
| 14 | `options-flow-map.svg` | Placeholder | configuration.md | Configure menu hub-and-spoke map of the 8 settings sections |
| 15 | `notification-actions-mockup.svg` | Placeholder | logging.md | Mobile mockup of an actionable HA companion-app notification |
| 16 | `defaults-override-flow.svg` | Placeholder | defaults.md | poolsmart_defaults.json override flow into the setup wizard |
| 17 | `cop-weighted-cost.svg` | Generated | planning.md | Price × COP weighting behind heating hour selection |
| 18 | `chemistry-dosing-workflow.svg` | Generated | chemistry.md | pH reading → dosing instruction workflow |
| 19 | `delta-t-flow-adequacy.svg` | Generated | filtration.md | Delta-T flow adequacy zones (healthy/marginal/starved) |
| 20 | `filter-resistance-graph.svg` | Generated | filtration.md | Flow decline over time as the filter fouls |
| 21 | `filtration-rules-comparison.svg` | Generated | filtration.md | Turnover rule vs daily-minimum rule, side by side |
| 22 | `heating-sources-comparison.svg` | Generated | heating.md | Efficiency and operating characteristics per heating source |
| 23 | `learning-feedback-loop.svg` | Generated | learning.md | Session → learned parameter feedback loop |
| 24 | `panel-overview.svg` | Generated | panel.md | Management panel — Overview tab |
| 25 | `panel-planning.svg` | Generated | panel.md | Management panel — Planning tab |
| 26 | `panel-sessions.svg` | Generated | panel.md | Management panel — Sessions tab |
| 27 | `panel-learning.svg` | Generated | panel.md | Management panel — Learning tab |
| 28 | `panel-settings.svg` | Generated | panel.md | Management panel — Settings tab |
| 29 | `panel-diagnostics.svg` | Generated | panel.md, logging.md | Management panel — Diagnostics tab (full ladder trace) |
| 30 | `Sensors.svg` | Generated | sensors.md | Sensor array overview photo |
| 31 | `esp32c6_wiring_overview.svg` | Generated | hardware.md | ESP32-C6 wiring overview photo |
| 32 | `Bestway_pump.svg` | Generated | hardware.md | Bestway Flowclear filter pump photo |
| 33 | `Flow_meter.svg` | Generated | hardware.md | DN50 flow meter installation photo |
| 34 | `Pipe_clamp.svg` | Generated | hardware.md | DS18B20 probe pipe-clamp mount photo |
| 35 | `w_eau_mini_power_3kw_warmtepomp.svg` | Generated | hardware.md | W'eau Mini Power 3 kW heat pump photo |
| 36 | `DS18B20.svg` | Generated | hardware.md | DS18B20 probe close-up photo |
| 37 | `Pool.svg` | Generated | getting_started.md, hardware.md | The above-ground pool PoolSmart automates |
| 38 | `HeatPump.svg` | Generated | heating.md | Installed heat pump unit photo |
| 39 | `3wayValve.svg` | Generated | heating.md | Manual three-way valve photo |
| 40 | `3wayValve-schema.svg` | Generated | heating.md | Three-way valve plumbing/wiring schema |
| 41 | `waterPump.svg` | Generated | filtration.md | Circulation pump installed in the filtration loop |

## Status Legend

- **Placeholder** — Minimal SVG with title text, ready to replace with generated image
- **Generated** — Final AI-generated image in place

## Generating Final Images

Each placeholder was created using the template defined in `VISUAL_ASSETS_RECOMMENDATIONS.MD`.
That document contains detailed AI generation prompts for each image, optimized for tools like
Midjourney, DALL-E, Stable Diffusion, or Flux.

### Brand Color Palette

| Color | Hex | Usage |
|-------|-----|-------|
| Pool Blue | `#00ACC1` | Primary brand, headings, accents |
| HA Blue | `#03A9F4` | Home Assistant integration elements |
| Warm Orange | `#FF9800` | Solar/heat highlights |
| Light Gray | `#FAFAFA` | Backgrounds |
| Mid Gray | `#9E9E9E` | Secondary text |

### Replacement Guidelines

When replacing placeholders:
1. Keep the same filename and path
2. Maintain the aspect ratio (800×400 for most diagrams)
3. Use the brand color palette for consistency
4. Include the diagram title as a visible heading
5. Export as SVG (preferred) or PNG at 2× resolution for retina displays

## License Note

All visual assets created for PoolSmart are released under the same AGPL-3.0 license as the
project code. Hardware photos remain property of their respective photographers.
