"""Tiny pytest-free runner:  python tests/run_tests.py   (pytest also works if installed)."""
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.test_core as T
bad = 0
for n in sorted(dir(T)):
    if n.startswith("test_"):
        try: getattr(T, n)(); print("PASS", n)
        except Exception: bad += 1; print("FAIL", n); traceback.print_exc()
sys.exit(1 if bad else 0)
