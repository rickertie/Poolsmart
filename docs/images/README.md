# PoolSmart Visual Assets

This directory contains visual assets for the PoolSmart documentation.
All paths use forward slashes for cross-platform compatibility.

## Image Inventory

| # | File | Status | Used In | Description |
|---|------|--------|---------|-------------|
| 1 | `architecture-overview.svg` | Placeholder | README.md | System architecture overview: ESPHome → HA → Decision Engine |
| 2 | `priority-ladder.svg` | Placeholder | ARCHITECTURE.MD | 10-branch priority ladder flowchart |
| 3 | `dashboard-mockup.svg` | Placeholder | — | Three-tab pool management panel mockup |
| 4 | `cop-curve.svg` | Placeholder | LEARNING.MD | COP vs outdoor temperature curve |
| 5 | `heating-timeline.svg` | Placeholder | PLANNING.MD | Maintenance vs seasonal heating timeline |
| 6 | `turnover-infographic.svg` | Placeholder | FILTRATION.MD | Cumulative filtration effectiveness chart |
| 7 | `operating-envelope.svg` | Placeholder | TROUBLESHOOTING.MD | Heat pump temperature thresholds |
| 8 | `solar-surplus.svg` | Placeholder | — | Solar surplus heating diagram |
| 9 | `data-flow.svg` | Placeholder | ENTITIES.MD | Data flow and entity relationship map |
| 10 | `chemistry-intervals.svg` | Placeholder | CHEMISTRY.MD | Test intervals by water temperature |
| 11 | `heat-loss-comparison.svg` | Placeholder | — | Pool cover vs no cover heat loss |
| 12 | `bucket-test-calibration.svg` | Placeholder | — | Flow meter calibration procedure |

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

## Existing Hardware Photos

The directory also contains existing hardware photography:

| File | Description |
|------|-------------|
| `3wayValve Schema.PNG` | Three-way valve wiring schema |
| `3wayValve.DNG` | Three-way valve raw photo |
| `Bestway_pump.webp` | Bestway pump photo |
| `DS18B20.jpg` | DS18B20 temperature sensor |
| `esp32c6_wiring_overview.png` | ESP32-C6 wiring overview |
| `Flow_meter.jpg` | Flow meter installation |
| `HeatPump.DNG` | Heat pump raw photo |
| `IMG_3973.DNG` | Installation photo |
| `Pipe_clamp.jpg` | Pipe clamp sensor mount |
| `Pool.DNG` | Pool overview raw photo |
| `Sensors.DNG` | Sensor array raw photo |
| `w_eau_mini_power_3kw_warmtepomp.webp` | W-eau mini 3kW heat pump |

## License Note

All visual assets created for PoolSmart are released under the same AGPL-3.0 license as the
project code. Hardware photos remain property of their respective photographers.
