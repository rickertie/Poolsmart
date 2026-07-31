"""Minimal test runner, so the acceptance suite can run without pytest."""
import importlib
import sys
import traceback

MODULES = ["test_acceptance", "test_planning"]

passed, failed = 0, []
for module_name in MODULES:
    module = importlib.import_module(module_name)
    tests = [
        (n, f)
        for n, f in sorted(vars(module).items())
        if n.startswith("test_") and callable(f) and f.__module__ == module_name
    ]
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception:
            print(f"FAIL  {name}")
            traceback.print_exc(limit=3)
            failed.append(name)

total = passed + len(failed)
print(f"\n{passed}/{total} passed")
sys.exit(1 if failed else 0)
