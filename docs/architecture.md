# Architecture

This document covers how PoolSmart actually makes decisions, how filtration
is calculated, and how the configuration options work. For the high-level
pitch, see the [main README](../README.md).

## The decision ladder

Every 30 seconds the ladder is walked from the top. The first branch that
matches wins, and lower branches are not evaluated.

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

Modes do not carry their own logic; they enable or disable branches. Branches
1 and 4 stay active in every mode including OFF, because an off switch must
not be able to cause damage.

In front of branches 5 and 6 sits a gate: the heat pump's operating envelope.
Below its minimum air temperature nothing can heat the pool, not even a
negative price and not even the minimum-temperature protection. That
protection can only circulate, which is enough, because moving water does
not freeze.

## Configuration

Settings → Devices & Services → PoolSmart → **Configure** gives five
sections:

| Section | Contains |
|---|---|
| Entities | Every switch and sensor, including the required ones |
| Pool and equipment | Volume, depth, pump flow, heat pump figures |
| General settings | Turnover, hysteresis, prices, night quiet |
| Swimming times | When the pool should be at temperature |
| Notifications | Which message goes to which device |

Picking the wrong temperature sensor during setup is easy to do, so the
entity choices live in options where they can be corrected rather than in
the entry data where they could not.

Every optional entity may be left blank. The matching capability is switched
off and listed in diagnostics rather than failing.

| Left blank | What stops working |
|---|---|
| Outdoor temperature | Operating envelope check; falls back to the weather entity |
| Heat pump inlet or outlet | Delta-T and COP learning |
| Flow meter | Flow protection and self-correcting block duration |
| Power sensors | Energy, cost and measured COP |
| Price sensor | Price optimisation, including the free-electricity branch |
| Solar sensors | Solar optimisation |

### A recommendation about the heat pump thermostat

Set the heat pump's own thermostat to the highest temperature you would ever
want plus about two degrees. If your maximum is 32 °C, set it to 34 °C.
Below that you keep full software control over any target, and above it the
hardware intervenes if the software ever fails to switch off. The setup
wizard shows this suggestion with your own numbers filled in.

## Filtration

The daily requirement is calculated, not entered:

```
daily runtime = pool volume x turnover factor / effective pump flow
block duration = daily runtime / number of blocks
```

Manufacturers specify pump flow without a filter installed; with one in line
roughly 60-75% remains and it drops as the filter fouls. If you tick
"measured" the figure is used as it is; otherwise it is derated. With a flow
meter connected the block duration corrects itself as the filter ages, and a
sustained decline raises a service notification.

Heating sessions run the pump too, so that runtime counts towards the quota.
Without that credit the system would filter far more than needed on heating
days.

## The AI layer

Optional and advisory. It reads the session history, produces a summary and
at most a handful of suggested settings changes, and waits. Nothing is
applied without pressing accept.

Suggestions are validated against a fixed list of adjustable settings with
hard ranges; anything outside it is discarded. A safety limit cannot be
suggested away. If the AI is unavailable the pool behaves exactly as it
otherwise would, because this layer sits outside the control tick entirely.

## Development

The decision core in `custom_components/poolsmart/core/` has no Home
Assistant imports, so it runs and is tested standalone:

```bash
cd tests && python run_tests.py
```

The suite covers twenty-two acceptance cases, including regression tests for
the two bugs that prompted this rewrite: the pump sitting idle while the
filtration window closed, and the pump oscillating once the daily quota was
met.

## The management panel

A sidebar panel at `/poolsmart` with six tabs: overview, planning, sessions,
learning, settings and diagnostics. It is written as a plain custom element
with no build step and no external imports, so it keeps working without
internet.

The panel is for whoever maintains the system. The Lovelace page in
`docs/lovelace/` is for everyone else, and the two are deliberately not the
same thing.

## The "icon not available" placeholder

HACS and the integrations page both fetch their picture from the
`home-assistant/brands` repository, and custom integrations without an entry
there show a placeholder. It is cosmetic only; entity icons come from
`icons.json` and display normally.

Ready-made images are in `brands/custom_integrations/poolsmart/` and
`brands/README.md` has the four steps for submitting them. Once the pull
request is merged the placeholder disappears on its own, with no update to
install.
