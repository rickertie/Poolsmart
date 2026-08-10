"""Just enough Home Assistant to import the modules that depend on it.

The decision core carries no Home Assistant imports and is exercised directly.
Everything around it -- the store, the coordinator, the platforms -- could only
ever be parsed, and parsing proves a file is grammatical while saying nothing
about whether its attributes exist. Two setup-breaking bugs shipped through that
gap: a method calling one that was never written, and a method reading fields
off the wrong object.

**Stubs are a fallback, not a preference.** When Home Assistant is genuinely
installed, these get out of the way entirely. Standing a fake package in front
of a real one gives a single process two answers to the same import, and the
failure that produces lands nowhere near the cause: on a runner with the real
package present, this file's own `from unittest.mock import ...` line reported a
circular import inside `asyncio`.

So: use the real thing when it is there, stub only when it is not, and never
replace a module that already exists.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"

#: Whether a real Home Assistant is importable. Decided once, by asking rather
#: than by guessing from the environment.
HAVE_REAL_HA = importlib.util.find_spec("homeassistant") is not None

_INSTALLED = False


def _module(name: str) -> types.ModuleType:
    """A stub module, unless one is already there.

    Never overwrites: an existing entry is either the real package or a stub
    from an earlier call, and both are better than a fresh empty one.
    """
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


def install() -> None:
    """Put stub Home Assistant modules on the import path, if needed.

    Called at the bottom of this module as well as by callers, because a module
    importing this one may have Home Assistant imports of its own at the top
    level. Doing it lazily left a window whose size depended on test ordering.
    """
    global _INSTALLED
    if _INSTALLED or HAVE_REAL_HA:
        return
    _INSTALLED = True

    # Imported here rather than at module level: on a runner with the real
    # package installed this module is imported but stubs nothing, and there is
    # no reason to drag mock in for that.
    from unittest.mock import MagicMock

    for name in (
        "homeassistant",
        "homeassistant.core",
        "homeassistant.config_entries",
        "homeassistant.const",
        "homeassistant.helpers",
        "homeassistant.helpers.storage",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.entity_registry",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.util",
        "homeassistant.util.dt",
    ):
        _module(name)

    core = _module("homeassistant.core")
    core.HomeAssistant = object
    core.State = object
    core.callback = lambda func: func

    storage = _module("homeassistant.helpers.storage")
    storage.Store = MagicMock

    config_entries = _module("homeassistant.config_entries")
    config_entries.ConfigEntry = object

    const_module = _module("homeassistant.const")
    const_module.ATTR_NAME = "name"
    const_module.ATTR_DEVICE_ID = "device_id"

    util_dt = _module("homeassistant.util.dt")
    util_dt.utcnow = datetime.utcnow
    util_dt.now = datetime.now
    util_dt.parse_datetime = lambda value: None

    coordinator = _module("homeassistant.helpers.update_coordinator")
    coordinator.DataUpdateCoordinator = object
    coordinator.CoordinatorEntity = object


def load(module_name: str, relative_path: str):
    """Import one integration module under a package rooted at the component."""
    install()

    package = sys.modules.get("poolsmart")
    if package is None:
        package = types.ModuleType("poolsmart")
        package.__path__ = [str(ROOT)]
        sys.modules["poolsmart"] = package

    full = f"poolsmart.{module_name}"
    if full in sys.modules:
        return sys.modules[full]

    spec = importlib.util.spec_from_file_location(full, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


def load_store():
    """The storage layer, with its dependencies loaded in order."""
    install()
    load("const", "const.py")
    load("core", "core/__init__.py")
    load("core.learning", "core/learning.py")
    return load("store", "store.py")


# Installed on import rather than on first use: see install(). A no-op when the
# real Home Assistant is present.
install()
