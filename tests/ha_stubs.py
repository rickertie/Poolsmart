"""Just enough Home Assistant to import the modules that depend on it.

The decision core carries no Home Assistant imports and is therefore exercised
directly by the tests. Everything around it -- the store, the coordinator, the
platforms -- could only ever be parsed, and parsing proves a file is
grammatical while saying nothing about whether its attributes exist. Two
setup-breaking bugs shipped through that gap: a method calling one that was
never written, and a method reading fields off the wrong object.

These stubs are deliberately thin. The aim is not to simulate Home Assistant,
which would be its own maintenance burden and would drift; it is to let the
module body execute so that names, attributes and imports are checked for real.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "poolsmart"


def _module(name: str) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    return module


def install() -> None:
    """Put stub Home Assistant modules on the import path."""
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


def load(module_name: str, relative_path: str):
    """Import one integration module under a stub package."""
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
    load("core.config", "core/config.py")
    load("core.learning", "core/learning.py")
    return load("store", "store.py")
