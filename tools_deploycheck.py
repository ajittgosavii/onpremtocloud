"""Deployment guard: the failures that only appear on a hosted Streamlit server.

Local development never reproduces these, because locally the modules stay in
sys.modules, the filesystem is writable, and whatever happens to be installed is
installed. Each check below corresponds to a real failure observed on Streamlit
Community Cloud.

Run with:  python tools_deploycheck.py     (exit code 1 on any failure)
"""

import pathlib
import sys
import tempfile

FUTURE = "from __future__ import annotations"
CORE = pathlib.Path("core")


def check_no_future_annotations() -> list[str]:
    """`from __future__ import annotations` + @dataclass is a crash under a reloader.

    With it, annotations are strings, so dataclasses calls _is_type(), which does
    sys.modules.get(cls.__module__).__dict__ -- None when the module has been
    purged from sys.modules, which is what a reloader does.
    """
    bad = []
    for p in sorted(pathlib.Path(".").rglob("*.py")):
        if "__pycache__" in p.parts or ".cache" in p.parts:
            continue
        if p.name == pathlib.Path(__file__).name:
            continue
        if FUTURE in p.read_text(encoding="utf-8"):
            bad.append(f"{p} still has '{FUTURE}'")
    return bad


def check_dataclasses_survive_reload() -> list[str]:
    """Re-execute each core module with itself absent from sys.modules.

    This is exactly what a module reloader does, and exactly what crashed on
    Streamlit Cloud at core/tco.py.
    """
    bad = []
    for path in sorted(CORE.glob("*.py")):
        if path.name == "__init__.py":
            continue
        modname = f"core.{path.stem}"
        src = path.read_text(encoding="utf-8")
        saved = sys.modules.pop(modname, None)
        try:
            ns = {"__name__": modname, "__file__": str(path), "__package__": "core"}
            exec(compile(src, str(path), "exec"), ns)
        except Exception as exc:
            bad.append(f"{modname} failed on reload: {type(exc).__name__}: {exc}")
        finally:
            if saved is not None:
                sys.modules[modname] = saved
    return bad


def check_no_scipy() -> list[str]:
    """SciPy is not in requirements, so nothing may depend on it.

    pandas needs SciPy for corr(method='spearman'), which the tornado chart used
    to call. Blocking the import proves nothing has crept back in.
    """
    blocked = {}
    for name in list(sys.modules):
        if name == "scipy" or name.startswith("scipy."):
            blocked[name] = sys.modules.pop(name)
    sys.modules["scipy"] = None          # makes `import scipy` raise ImportError
    try:
        from core import montecarlo
        det = montecarlo.Deterministic(
            migration_cost=1e6, effort_hours=1e4, team_hours_per_day=48,
            elapsed_days=300, replication_days=100, engineering_days=200,
            azure_monthly_cost=1e5, onprem_monthly_cost=2e5,
            expected_rollbacks=20, vm_count=547, cost_per_vm=2000)
        sim = montecarlo.run(det, montecarlo.SimulationInputs(iterations=400))
        tor = montecarlo.tornado(sim)
        if tor.empty or tor["correlation"].isna().all():
            return ["tornado() produced no usable correlations without SciPy"]
        return []
    except ImportError as exc:
        return [f"something still imports SciPy: {exc}"]
    finally:
        sys.modules.pop("scipy", None)
        sys.modules.update(blocked)


def check_cache_read_only() -> list[str]:
    """A read-only application directory must degrade, not crash."""
    from core import pricing
    original = pricing.CACHE_DIR
    try:
        pricing.CACHE_DIR = pathlib.Path("/nonexistent-read-only-path/cache")
        pricing._write_cache("probe-key", [{"a": 1}])       # must not raise
        got = pricing._read_cache("probe-key")
        # It may legitimately fall back to the temp directory and read back.
        if got is not None and got[0] != [{"a": 1}]:
            return ["cache fell back but returned the wrong payload"]
        return []
    except Exception as exc:
        return [f"cache raised on a read-only path: {type(exc).__name__}: {exc}"]
    finally:
        pricing.CACHE_DIR = original


def check_requirements_cover_imports() -> list[str]:
    """Every third-party top-level import must appear in requirements.txt."""
    req = pathlib.Path("requirements.txt").read_text(encoding="utf-8").lower()
    mapping = {"dotenv": "python-dotenv", "openai": "openai", "plotly": "plotly",
               "pandas": "pandas", "numpy": "numpy", "requests": "requests",
               "streamlit": "streamlit", "openpyxl": "openpyxl"}
    bad = []
    for mod, pkg in mapping.items():
        used = any(f"import {mod}" in p.read_text(encoding="utf-8")
                   for p in pathlib.Path(".").rglob("*.py")
                   if "__pycache__" not in p.parts)
        if used and pkg not in req:
            bad.append(f"{mod} is imported but {pkg} is not in requirements.txt")
    return bad


CHECKS = [
    ("no `from __future__ import annotations`", check_no_future_annotations),
    ("dataclasses survive a module reload", check_dataclasses_survive_reload),
    ("no hidden SciPy dependency", check_no_scipy),
    ("read-only filesystem degrades gracefully", check_cache_read_only),
    ("requirements.txt covers every import", check_requirements_cover_imports),
]


def main() -> int:
    print(f"Python {sys.version.split()[0]}\n")
    failures = 0
    for name, fn in CHECKS:
        try:
            problems = fn()
        except Exception as exc:
            problems = [f"check itself raised: {type(exc).__name__}: {exc}"]
        if problems:
            failures += len(problems)
            print(f"FAIL  {name}")
            for p in problems:
                print(f"      {p}")
        else:
            print(f"ok    {name}")
    print()
    if failures:
        print(f"{failures} problem(s) found.")
        return 1
    print("Ready to deploy.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
