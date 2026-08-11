[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • [Learning](learning.md) • [Heating](heating.md) • [Filtration](filtration.md) • [Chemistry](chemistry.md) • [Hardware](hardware.md) • [ESPHome](esphome.md) • [Sensors](SENSORS.md) • [Logging](logging.md) • [Entities](entities.md) • [Panel](panel.md) • [Configuration](configuration.md) • [Troubleshooting](troubleshooting.md) • [Defaults](DEFAULTS.md) • **Community Post**

---

# PoolSmart — a pool controller that tells you why

*Post this in **Share your Projects!** on community.home-assistant.io. Add a
screenshot of the simple page and one of the diagnostics tab — the trace is the
thing people will not have seen before.*

---

## PoolSmart — a pool controller that explains itself

I have an Intex frame pool with a small heat pump, a Zigbee plug on the pump and
another on the heat pump, and a dynamic electricity tariff. I started with about
forty automations and fourteen scripts. It worked, mostly, and every time it did
something unexpected I had to reconstruct why from the logbook.

So I rebuilt it as an integration. **PoolSmart** is on GitHub, AGPL, installable
through HACS as a custom repository:

👉 https://github.com/rickertie/Poolsmart

### The idea

ESPHome measures. Home Assistant decides. Every 30 seconds a single priority
ladder is walked from the top, and the first branch that matches produces one
decision with a plain-language reason attached:

```
0  Emergency stop
1  Frost protection
2  Manual
3  Chemistry cycle
4  Filtration deadline
5  Free electricity (price below zero)
6  Heating
7  Filtration block
8  Pump rundown
9  Idle
```

Modes — Auto, Boost, Eco, Pump, Stand-by, Off — do not carry their own logic.
They enable or disable branches, so there is exactly one place where control
lives. That was the main thing forty automations could not give me.

### What it does

- Heats around dynamic prices and solar surplus, working backwards from when you
  want to swim
- Works out how many hours of filtration the pool actually needs, from volume and
  measured flow, rather than a number you type in
- Learns heat loss, heating rate and COP per outdoor temperature band from its
  own sessions
- Records the reason for every decision at the moment of deciding, and shows the
  full ladder trace: which branch won, which were rejected and why, and what
  would have to change for a different one to win
- Turns a pH reading into "add 18 ml of pH-minus", using your pool volume

Everything except two switches and a water temperature sensor is optional. Leave
a field blank and the matching feature switches off and says so.

### The part I did not expect

Building this taught me more about my pool than the pool ever did.

My flow meter reads 1.05 m³/h against a datasheet minimum of 2.0. The AI review
kept telling me to increase it. Then I opened the diverter valve and watched what
happened: flow went up 25%, delta-T dropped 19%, and thermal output stayed
exactly the same. The heat pump was never flow-limited. The datasheet figure is
written for a generic installation and takes no account of pipe length, elbows or
a valve — so the integration now judges flow by the temperature rise across the
heat pump, which measures directly what the flow number is a proxy for. A genuine
flow problem shows up as a *high* delta-T, not a low flow figure.

The other one was worse. Two of the four learned values were being recorded after
every session, stored, displayed on a dashboard — and read by no calculation at
all. Planning ran on the datasheet COP of 5.17 while the pool was measuring 3.49.
That is a 54% optimistic estimate: three hours predicted for a two degree rise
that actually takes four and a half. It started too late and the pool was cold.
Version 1.0 fixes it, and every learned value now names the decision that reads
it, because a value nobody reads is not knowledge.

### What it is not

It is not a water chemistry integration. For saturation indices, alkalinity and
calcium hardness there is already
[ha-poolchem](https://github.com/joyfulhouse/ha-poolchem), which does that
properly and works with any sensor source. PoolSmart handles the part that needs
the pool's own numbers — dosing from volume, a test interval that follows water
temperature, and running the pump afterwards. The two sit next to each other
without overlapping.

It is also version 1.0 of software running on exactly one pool. There are 85
automated tests against the decision core, which run without Home Assistant, and
most of them exist because something went wrong on my pool first. Have a look at
the changelog — every release is named after what it got wrong.

### Setup

Five steps, every field pre-filled with a help line explaining where to find the
real number. Volume, pump flow and heat pump specification are entered at setup
and everything else is derived, so it works for a 1000 litre inflatable and a
50000 litre in-ground pool alike.

There is a complete three-tab dashboard in `docs/lovelace/`, an example ESPHome
configuration in `docs/esphome/`, and a management panel that appears in the
sidebar.

Feedback and issues very welcome — especially from anyone whose pool is nothing
like mine, since that is exactly where the assumptions I have not noticed will
show up.

---

## See Also

- [README](../README.md) — Main project documentation.
- [docs/architecture.md](architecture.md) — Architecture & decision core.
- [docs/SENSORS.md](SENSORS.md) — Sensor mapping & calibration.
- [CHANGELOG.md](../CHANGELOG.md) — Full changelog.
