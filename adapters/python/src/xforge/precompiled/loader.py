"""
load_or_raise: download, verify, extract, and ctypes-load the native library.
Called from generated _xforge_loader.py at import time.
"""
from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path
from typing import Callable

from xforge.precompiled.resolver import PrecompiledResolver

_log = logging.getLogger("xforge.precompiled.loader")


def load_or_raise(
    crate_dir: str | Path,
    crate_rel_path: str = ".",
    *,
    fallback_builder: Callable[[Path, str], Path] | None = None,
) -> ctypes.CDLL:
    """
    Resolve, download, and load the native library.

    crate_dir: path to the file calling this (pass __file__ from the generated loader),
               or a directory. If it's a file, its parent directory is used as the base
               for resolving crate_rel_path.
    crate_rel_path: path from crate_dir's parent (or crate_dir if it's a dir) to the
                    Rust crate root that contains xforge.yaml.
    fallback_builder: optional callable(crate_dir: Path, reason: str) -> Path.
                      Called when the precompiled binary cannot be resolved.
                      Must return the path to the native library.
    """
    env_path = os.environ.get("XFORGE_NATIVE_LIB_PATH")
    if env_path:
        p = Path(env_path)
        if not p.is_file():
            raise FileNotFoundError(
                f"XFORGE_NATIVE_LIB_PATH is set but not a file: {env_path}"
            )
        _log.info("Using XFORGE_NATIVE_LIB_PATH override: %s", p)
        return ctypes.CDLL(str(p))

    base = Path(crate_dir)
    if base.is_file():
        base = base.parent
    resolved_crate_dir = (base / crate_rel_path).resolve()

    _log.info("Resolving precompiled library from crate: %s", resolved_crate_dir)

    resolver = PrecompiledResolver(crate_dir=resolved_crate_dir)
    try:
        lib_path = resolver.resolve()
    except Exception as exc:
        if fallback_builder is not None:
            _log.warning("Resolver failed, trying fallback_builder: %s", exc)
            lib_path = fallback_builder(resolved_crate_dir, str(exc))
            if lib_path is None or not Path(lib_path).is_file():
                raise RuntimeError(
                    f"fallback_builder returned an invalid path: {lib_path!r}"
                ) from exc
        else:
            _log.error("Failed to resolve precompiled library: %s", exc)
            raise

    _log.info("Loading library: %s", lib_path)
    try:
        return ctypes.CDLL(str(lib_path))
    except OSError as e:
        raise OSError(f"Failed to load native library at {lib_path}: {e}") from e
