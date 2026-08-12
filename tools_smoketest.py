"""Headless smoke test of every Streamlit page using streamlit.testing.

Run with:  py -3.12 tools_smoketest.py
Exits non-zero if any page raises.
"""

import sys
import time

from streamlit.testing.v1 import AppTest

PAGES = [
    "views/overview.py",
    "views/assumptions.py",
    "views/inventory.py",
    "views/assess.py",
    "views/cost.py",
    "views/effort.py",
    "views/plan.py",
    "views/simulate.py",
    "views/azure_migrate.py",
    "views/provider.py",
    "views/platform_options.py",
    "views/tooling.py",
    "views/business_case.py",
    "views/advisor.py",
]


def main() -> int:
    failures = []
    for page in PAGES:
        t0 = time.time()
        at = AppTest.from_file(page, default_timeout=300)
        try:
            at.run()
        except Exception as exc:
            failures.append((page, f"{type(exc).__name__}: {exc}"))
            print(f"FAIL  {page}  ({time.time() - t0:.1f}s)  {type(exc).__name__}: {exc}")
            continue

        if at.exception:
            for e in at.exception:
                failures.append((page, str(e.value)))
                print(f"FAIL  {page}  ({time.time() - t0:.1f}s)")
                print(f"      {e.value}")
                if getattr(e, "stack_trace", None):
                    print("      " + "\n      ".join(e.stack_trace[-14:]))
        else:
            warns = len(at.warning) if hasattr(at, "warning") else 0
            print(f"ok    {page}  ({time.time() - t0:.1f}s)  "
                  f"{len(at.markdown)} markdown, {len(at.dataframe)} tables, {warns} warnings")

    print()
    if failures:
        print(f"{len(failures)} failure(s) across {len({f[0] for f in failures})} page(s).")
        return 1
    print(f"All {len(PAGES)} pages rendered without error.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
