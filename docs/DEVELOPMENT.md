[← Back to README](../README.md) • [Architecture](architecture.md) • [Planning](planning.md) • [Learning](learning.md) • [Heating](heating.md) • [Filtration](filtration.md) • [Chemistry](chemistry.md) • [Hardware](hardware.md) • [ESPHome](esphome.md) • [Sensors](SENSORS.md) • [Logging](logging.md) • [Entities](entities.md) • [Panel](panel.md) • [Configuration](configuration.md) • [Troubleshooting](troubleshooting.md) • [Defaults](DEFAULTS.md)

---

# Development

This document covers how to run the test suite and contribute to PoolSmart.
For the architecture of the decision core, see [architecture.md](architecture.md).

---

## Running Tests

The decision core in `custom_components/poolsmart/core/` has no Home Assistant
imports, so it runs and is tested standalone:

```bash
cd tests && python run_tests.py
```

The suite covers twenty-two acceptance cases, including regression tests for the
two bugs that prompted this rewrite: the pump sitting idle while the filtration
window closed, and the pump oscillating once the daily quota was met.

---

## Project Status

Version 1.3.2. Running daily on the installation it was built for, with 85
automated tests covering the decision core.

Still to come: pool cover support needs a sensor to learn from, and the chemistry
module covers pH and chlorine but not alkalinity or hardness —
[ha-poolchem](https://github.com/joyfulhouse/ha-poolchem) is the answer for those.

---

## Contributing

Feedback and issues welcome — especially from anyone whose pool is nothing like
the one this was built for, since that is exactly where untested assumptions show
up. See [COMMUNITY_POST.md](COMMUNITY_POST.md) for the project introduction.

---

## See Also

- [architecture.md](architecture.md) — Architecture & decision core
- [CHANGELOG.md](../CHANGELOG.md) — Full changelog
- [hardware.md](hardware.md) — Hardware & wiring guide
