> [← Back to README](../README.md) | [Getting Started](GETTING_STARTED.MD) | [Architecture](ARCHITECTURE.MD) | [Configuration](CONFIGURATION.MD) | [Troubleshooting](TROUBLESHOOTING.MD)

---

# Development

This document covers how to run the test suite and contribute to PoolSmart.
For the architecture of the decision core, see [ARCHITECTURE.MD](ARCHITECTURE.MD).

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
module covers pH and chlorine but not alkalinity or hardness

---

## Contributing

Feedback and issues welcome — especially from anyone whose pool is nothing like
the one this was built for, since that is exactly where untested assumptions show
up.

---

## See Also

- [ARCHITECTURE.MD](ARCHITECTURE.MD) — Architecture & decision core
- [CHANGELOG.md](../CHANGELOG.md) — Full changelog
- [HARDWARE.MD](HARDWARE.MD) — Hardware & wiring guide
