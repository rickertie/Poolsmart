# PoolSmart

An intelligent swimming pool controller for Home Assistant. ESPHome measures,
Home Assistant decides, and every decision comes from a single priority ladder.

Works with any pool: volume, pump flow and heat pump specification are entered at
setup, and filtration duration, heating time and the energy budget are derived
from them. A 1000 litre inflatable and a 30000 litre in-ground pool both work
without touching code.

## Why it is built this way

The design solves four problems that YAML automations cannot:

| Problem | How PoolSmart handles it |
|---|---|
| A running timer is lost on restart | Filtration runtime is stored as closed intervals, not a counter |
| Learned values get corrupted by odd sessions | Updates are capped per step and outliers are skipped |
| Threshold comparisons oscillate | Blocks are states with an end time, not thresholds |
| "Why is it doing that?" | The reason is recorded at the moment of deciding, not reconstructed |

## The decision ladder

Every 30 seconds the ladder is walked from the top. The first branch that matches
wins, and lower branches are not evaluated.

| # | Branch | Ignores night quiet |
|---|---|---|
| 0 | Emergency stop | yes |
| 1 | Frost and minimum-temperature protection | yes |
| 2 | Manual control | yes |
| 3 | Chemistry cycle | yes |
| 4 | Filtration deadline | yes |
| 5 | Free electricity (price below zero) | yes |
| 6 | Heating session | no |
| 7 | Scheduled filtration block | no |
| 8 | Pump rundown | no |
| 9 | Idle | — |

Modes do not carry their own logic; they enable or disable branches. Branches 1
and 4 stay active in every mode including OFF, because an off switch must not be
able to cause damage.

In front of branches 5 and 6 sits a gate: the heat pump's operating envelope.
Below its minimum air temperature nothing can heat the pool, not even a negative
price and not even the minimum-temperature protection. That protection can only
circulate, which is enough, because moving water does not freeze.

## Installation

1. Add this repository to HACS as a custom repository and install PoolSmart.
2. Restart Home Assistant.
3. Settings → Devices & Services → Add Integration → PoolSmart.
4. Work through the five steps. Only the last two ask for entities, and only
   three of those are required.

Every optional entity may be left blank. The matching capability is switched off
and listed in diagnostics rather than failing.

| Left blank | What stops working |
|---|---|
| Outdoor temperature | Operating envelope check; falls back to the weather entity |
| Heat pump inlet or outlet | Delta-T and COP learning |
| Flow meter | Flow protection and self-correcting block duration |
| Power sensors | Energy, cost and measured COP |
| Price sensor | Price optimisation, including the free-electricity branch |
| Solar sensors | Solar optimisation |

### A recommendation about the heat pump thermostat

Set the heat pump's own thermostat to the highest temperature you would ever want
plus about two degrees. If your maximum is 32 °C, set it to 34 °C. Below that you
keep full software control over any target, and above it the hardware intervenes
if the software ever fails to switch off. The setup wizard shows this suggestion
with your own numbers filled in.

## Filtration

The daily requirement is calculated, not entered:

```
daily runtime = pool volume x turnover factor / effective pump flow
block duration = daily runtime / number of blocks
```

Manufacturers specify pump flow without a filter installed; with one in line
roughly 60-75% remains and it drops as the filter fouls. If you tick "measured"
the figure is used as it is; otherwise it is derated. With a flow meter connected
the block duration corrects itself as the filter ages, and a sustained decline
raises a service notification.

Heating sessions run the pump too, so that runtime counts towards the quota.
Without that credit the system would filter far more than needed on heating days.

## Development

The decision core in `custom_components/poolsmart/core/` has no Home Assistant
imports, so it runs and is tested standalone:

```bash
cd tests && python run_tests.py
```

The suite covers the twelve acceptance cases from the design documents, including
regression tests for the two bugs that prompted this rewrite: the pump sitting
idle while the filtration window closed, and the pump oscillating once the daily
quota was met.

## Status

| Work package | State |
|---|---|
| WP1 Foundation: config flow, storage, models | done |
| WP2 Control core: coordinator, ladder, filtration, safety, entities | done |
| WP3 Planning and learning: optimizer, session recorder, COP curve | heating estimate done, optimizer and learning pending |
| WP4 Notifications and Lovelace | example page included, notification routing pending |
| WP5 Sidebar management panel | pending |
| WP6 AI advisor, chemistry and cover modules | placeholders in place |

## Licence

AGPL-3.0-or-later.
