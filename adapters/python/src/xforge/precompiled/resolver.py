"""
PrecompiledResolver: resolve (download + extract) precompiled library; loader API for generated code.
"""
from __future__ import annotations

import logging
import os
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

from xforge.precompiled.artifacts_provider import (
    PrecompiledArtifactsProvider,
)
from xforge.precompiled.crate_hash import compute_release_hash
from xforge.precompiled.options import PrecompiledBinaryMode, XforgeOptions
from xforge.precompiled.target import detect_host_target_triple

_log = logging.getLogger("xforge.precompiled.resolver")


def _library_extension_for_target(target: str) -> str:
    if "windows" in target or "msvc" in target:
        return ".dll"
    if "darwin" in target or "apple" in target:
        return ".dylib"
    return ".so"


def _rust_available() -> bool:
    import shutil
    return shutil.which("cargo") is not None or shutil.which("rustup") is not None


def _extract_library_from_archive(
    archive_path: Path,
    build_id: str,
    target_triple: str,
    crate_dir: Path,
    lib_name: str = "xforge",
) -> Path:
    ext = _library_extension_for_target(target_triple)
    cache_root = crate_dir / ".xforge" / "extracted" / build_id / target_triple
    cache_root.mkdir(parents=True, exist_ok=True)

    for f in cache_root.iterdir():
        if f.is_file() and f.suffix == ext:
            return f

    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            entry = _select_library_entry(zf, ext)
            if entry is None:
                raise ValueError(
                    f'No library with extension "{ext}" found in {archive_path}'
                )
            out_path = cache_root / Path(entry).name
            data = zf.read(entry)
        out_path.write_bytes(data)
    elif archive_path.suffix == ".gz" or ".tar.gz" in archive_path.name:
        with tarfile.open(archive_path, "r:*") as tf:
            entry = _select_library_entry_tar(tf, ext)
            if entry is None:
                raise ValueError(
                    f'No library with extension "{ext}" found in {archive_path}'
                )
            out_path = cache_root / Path(entry).name
            for m in tf.getmembers():
                if Path(m.name).name == Path(entry).name:
                    f = tf.extractfile(m)
                    out_path.write_bytes(f.read() if f else b"")
                    break
            else:
                raise ValueError(f"Tar entry {entry} not found")
    else:
        raise ValueError(f"Unsupported archive type: {archive_path}")
    return out_path


def _select_library_entry(zf: zipfile.ZipFile, expected_ext: str) -> str | None:
    fallback = None
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        if not Path(name).suffix == expected_ext:
            continue
        if "lib" in Path(name).parts:
            return name
        fallback = fallback or name
    return fallback


def _select_library_entry_tar(tf: tarfile.TarFile, expected_ext: str) -> str | None:
    fallback = None
    for member in tf.getmembers():
        if not member.isfile():
            continue
        if not Path(member.name).suffix == expected_ext:
            continue
        if "lib" in Path(member.name).parts:
            return member.name
        fallback = fallback or member.name
    return fallback


class PrecompiledResolver:
    """
    Resolves the precompiled native library: downloads and verifies when possible,
    optionally falls back to local build per precompiled_binaries.mode.
    """

    def __init__(
        self,
        crate_dir: str | Path,
        *,
        lib_name: str = "xforge",
        fallback_builder: Callable[[Path, str], Path] | None = None,
    ):
        self.crate_dir = Path(crate_dir)
        self.lib_name = lib_name
        self.fallback_builder = fallback_builder

    def resolve(
        self,
        target: str | None = None,
        mode: PrecompiledBinaryMode | None = None,
    ) -> Path:
        """
        Resolve the native library path. Downloads and extracts if precompiled
        config is present and artifact is available; otherwise raises or calls
        fallback_builder if provided.
        """
        env_path = os.environ.get("XFORGE_NATIVE_LIB_PATH")
        if env_path:
            p = Path(env_path)
            if p.is_file():
                return p
            raise FileNotFoundError(
                f"XFORGE_NATIVE_LIB_PATH set but not a file: {env_path}"
            )

        options = XforgeOptions.load(self.crate_dir)
        config = options.precompiled_binaries
        if config is None:
            return self._do_fallback_or_raise(
                "No precompiled_binaries config in xforge.yaml."
            )

        effective_mode = mode or config.mode
        if effective_mode == PrecompiledBinaryMode.NEVER:
            return self._do_fallback_or_raise(
                "Precompiled binaries disabled (mode=never)."
            )

        target_triple = target or detect_host_target_triple()
        build_id = compute_release_hash(self.crate_dir)
        _log.info("Resolving precompiled binary for %s", target_triple)
        _log.debug("build_id: %s", build_id)
        provider = PrecompiledArtifactsProvider(
            crate_dir=self.crate_dir,
            config=config,
        )
        rust_available = _rust_available()

        resolution = provider.resolve_artifact(
            build_id=build_id,
            target=target_triple,
            mode=effective_mode,
            rust_available=rust_available,
        )

        if resolution.downloaded and resolution.artifact is not None:
            _log.info("Using precompiled binary for %s", target_triple)
            return _extract_library_from_archive(
                resolution.artifact,
                build_id=build_id,
                target_triple=target_triple,
                crate_dir=self.crate_dir,
                lib_name=self.lib_name,
            )

        _log.info("Falling back for %s: %s", target_triple, resolution.reason)
        return self._do_fallback_or_raise(
            resolution.reason or "Failed to resolve precompiled artifact."
        )

    def _do_fallback_or_raise(self, reason: str) -> Path:
        if self.fallback_builder is not None:
            return self.fallback_builder(self.crate_dir, reason)
        raise RuntimeError(reason)


def get_library_path(
    crate_dir: str | Path,
    target: str | None = None,
    *,
    mode: PrecompiledBinaryMode | None = None,
    fallback_builder: Callable[[Path, str], Path] | None = None,
) -> Path:
    """
    Resolve and return the path to the precompiled native library.
    Use this from generated bindings or at runtime to load the lib (e.g. ctypes.CDLL(path)).
    """
    resolver = PrecompiledResolver(
        crate_dir,
        fallback_builder=fallback_builder,
    )
    return resolver.resolve(target=target, mode=mode)


def load_native_library(
    crate_dir: str | Path,
    target: str | None = None,
    *,
    mode: PrecompiledBinaryMode | None = None,
    fallback_builder: Callable[[Path, str], Path] | None = None,
):
    """
    Resolve the library and return a ctypes.CDLL (or compatible) handle.
    """
    import ctypes
    path = get_library_path(
        crate_dir,
        target=target,
        mode=mode,
        fallback_builder=fallback_builder,
    )
    return ctypes.CDLL(str(path))
