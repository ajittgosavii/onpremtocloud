"""Report the interpreter and which runtime dependencies are importable.

Run under each Python you intend to deploy on:  py -3.14 tools_env_check.py
"""
import sys

MODULES = ["streamlit", "pandas", "numpy", "plotly", "requests", "scipy",
           "dotenv", "openpyxl"]


def main() -> None:
    print(sys.version)
    print(sys.executable)
    print()
    for m in MODULES:
        try:
            mod = __import__(m)
            print(f"{m:12s} {getattr(mod, '__version__', 'installed')}")
        except ImportError:
            print(f"{m:12s} MISSING")
    print()
    try:
        from core import scenario  # noqa: F401
        print("core package imports cleanly")
    except Exception as exc:
        print(f"core package FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
