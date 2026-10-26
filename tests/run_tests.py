"""Tiny pytest-free runner:  python tests/run_tests.py   (pytest also works if installed)."""
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.test_core as T
import tests.test_ui_backend as U
import tests.test_pune_system as P

bad = 0
for mod in (T, U, P):
    for n in sorted(dir(mod)):
        if n.startswith("test_"):
            try:
                getattr(mod, n)()
                print("PASS", n)
            except Exception:
                bad += 1
                print("FAIL", n)
                traceback.print_exc()
sys.exit(1 if bad else 0)
