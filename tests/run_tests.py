"""Minimal test runner, so the acceptance suite can run without pytest."""
import sys, traceback
import test_acceptance as m

tests = [(n, f) for n, f in sorted(vars(m).items()) if n.startswith("test_") and callable(f)]
passed, failed = 0, []
for name, fn in tests:
    try:
        fn()
        print(f"PASS  {name}")
        passed += 1
    except Exception:
        print(f"FAIL  {name}")
        traceback.print_exc(limit=3)
        failed.append(name)
print(f"\n{passed}/{len(tests)} passed")
sys.exit(1 if failed else 0)
