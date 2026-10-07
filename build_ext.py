#!/usr/bin/env python3
"""
build_ext.py — One-shot helper to compile the Cython matching-engine extension.

Usage::

    python build_ext.py

This is equivalent to::

    python setup.py build_ext --inplace

but adds friendly diagnostics and can auto-detect MinGW on Windows.
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent

# ---------------------------------------------------------------------------
# 1. Verify Cython is installed
# ---------------------------------------------------------------------------
try:
    import Cython
    print(f"[OK] Cython {Cython.__version__} found")
except ImportError:
    print("[ERROR] Cython is not installed.  Run:  pip install cython>=3.0")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 2. Locate a C compiler on Windows (prefer MinGW in MSYS2)
# ---------------------------------------------------------------------------
MINGW_CANDIDATES = [
    r"C:\msys64\mingw64\bin",
    r"C:\msys64\ucrt64\bin",
    r"C:\msys2\mingw64\bin",
    r"C:\MinGW\bin",
]

if sys.platform == "win32":
    # Add known MinGW locations to PATH if found
    for candidate in MINGW_CANDIDATES:
        if Path(candidate).is_dir() and candidate not in os.environ["PATH"]:
            print(f"[INFO] Adding MinGW to PATH: {candidate}")
            os.environ["PATH"] = candidate + os.pathsep + os.environ["PATH"]
            break

    gcc = shutil.which("gcc")
    if gcc:
        print(f"[OK] GCC found: {gcc}")
        # Tell distutils to use mingw32 compiler
        os.environ.setdefault("DISTUTILS_COMPILER", "mingw32")
    else:
        print(
            "[WARNING] No GCC found on PATH.  MSVC will be tried.\n"
            "          If build fails, install MSYS2 from https://www.msys2.org\n"
            "          then run:  C:\\msys64\\msys2_shell.cmd -defterm -here -no-start\n"
            "          inside it: pacman -S --noconfirm mingw-w64-x86_64-gcc"
        )

# ---------------------------------------------------------------------------
# 3. Build
# ---------------------------------------------------------------------------
cmd = [
    sys.executable,
    str(ROOT / "setup.py"),
    "build_ext",
    "--inplace",
]

print(f"\n[BUILD] Running: {' '.join(cmd)}\n")
result = subprocess.run(cmd, cwd=ROOT)

if result.returncode != 0:
    print("\n[FAILED] Build failed — see errors above.")
    sys.exit(result.returncode)

# ---------------------------------------------------------------------------
# 4. Quick import smoke test
# ---------------------------------------------------------------------------
print("\n[VERIFY] Attempting import of compiled extension …")
try:
    # Force fresh import outside any cached module
    sys.path.insert(0, str(ROOT))
    import importlib, importlib.util
    spec = importlib.util.find_spec("chronos.matching_engine.order_book")
    if spec is None or spec.origin is None:
        raise ImportError("Module spec not found — .pyd may not be on sys.path")
    if spec.origin.endswith(".py"):
        raise ImportError(
            f"Loaded pure-Python fallback instead of compiled extension: {spec.origin}"
        )
    mod = importlib.import_module("chronos.matching_engine.order_book")
    lob = mod.LimitOrderBook(symbol_id=1001)
    assert lob.symbol_id == 1001
    assert lob.best_bid is None
    lob.add_order(1, 1_000_000_000, 150.25, 100, 1, 1)
    assert lob.total_bid_orders == 1
    print(f"[OK] Import successful — {spec.origin}")
    print(f"[OK] LimitOrderBook smoke test passed: {lob!r}")
except Exception as exc:
    print(f"[FAILED] Import/smoke test failed: {exc}")
    sys.exit(1)

print("\n✓ Cython extension built and verified successfully.\n")
print("  Run the full test suite with:  pytest tests/test_order_book.py -v")
