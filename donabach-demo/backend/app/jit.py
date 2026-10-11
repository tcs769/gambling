"""Numba shim for the scalar kernels (tax engine, simulator).

With numba installed the kernels are JIT-compiled; without it the identical source runs as
plain Python (correct but slow), so tests and the API still work on a machine without numba.

numba's on-disk cache only tracks the file a function lives in. Our kernels call each other
across files (the simulator inlines the tax kernel), so editing one file would be served stale
from the cache. The cache directory is therefore keyed on a hash of every kernel source file.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    import numba
except ImportError:  # pragma: no cover - exercised only on machines without numba
    numba = None

HAVE_NUMBA = numba is not None

_APP_DIR = Path(__file__).resolve().parent
_CACHE_ROOT = _APP_DIR.parent / ".numba_cache"
_KERNEL_DIRS = ("tax", "sim")
_KEEP_CACHE_DIRS = 3


def _source_hash() -> str:
    digest = hashlib.sha256()
    digest.update(Path(__file__).read_bytes())
    for sub in _KERNEL_DIRS:
        for path in sorted((_APP_DIR / sub).glob("*.py")):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _configure_cache() -> None:
    if numba is None or os.environ.get("NUMBA_CACHE_DIR"):
        return
    current = _CACHE_ROOT / _source_hash()
    current.mkdir(parents=True, exist_ok=True)
    numba.config.CACHE_DIR = str(current)
    stale = sorted(
        (p for p in _CACHE_ROOT.iterdir() if p.is_dir() and p != current),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in stale[_KEEP_CACHE_DIRS - 1 :]:
        shutil.rmtree(old, ignore_errors=True)


_configure_cache()


def jit(fn: Callable | None = None, **options: Any) -> Callable:
    """`numba.njit` with project defaults, or the plain function when numba is missing."""
    if numba is None:
        return fn if fn is not None else (lambda f: f)
    options.setdefault("cache", True)
    options.setdefault("error_model", "numpy")  # no ZeroDivisionError checks in hot loops
    decorator = numba.njit(**options)
    return decorator(fn) if fn is not None else decorator


prange = numba.prange if numba is not None else range
