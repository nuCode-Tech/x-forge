import ctypes
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from xforge.precompiled.loader import load_or_raise


def _make_mock_lib():
    """Return a mock that passes isinstance(x, ctypes.CDLL) — use MagicMock spec."""
    return MagicMock(spec=ctypes.CDLL)


def test_env_override_uses_path(tmp_path, monkeypatch):
    """XFORGE_NATIVE_LIB_PATH bypasses resolver and loads the file."""
    lib_file = tmp_path / "libfoo.so"
    lib_file.write_bytes(b"")
    monkeypatch.setenv("XFORGE_NATIVE_LIB_PATH", str(lib_file))

    mock_lib = _make_mock_lib()
    with patch("ctypes.CDLL", return_value=mock_lib) as mock_cdll:
        result = load_or_raise(crate_dir=__file__, crate_rel_path=".")
    mock_cdll.assert_called_once_with(str(lib_file))
    assert result is mock_lib


def test_env_override_missing_file_raises(tmp_path, monkeypatch):
    """XFORGE_NATIVE_LIB_PATH set but file missing raises FileNotFoundError."""
    monkeypatch.setenv("XFORGE_NATIVE_LIB_PATH", str(tmp_path / "missing.so"))
    with pytest.raises(FileNotFoundError, match="XFORGE_NATIVE_LIB_PATH"):
        load_or_raise(crate_dir=__file__, crate_rel_path=".")


def test_resolver_success_loads_library(tmp_path):
    """When resolver returns a path, ctypes.CDLL is called with it."""
    lib_file = tmp_path / "libfoo.so"
    lib_file.write_bytes(b"")

    mock_lib = _make_mock_lib()
    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = lib_file

    with patch("xforge.precompiled.loader.PrecompiledResolver", return_value=mock_resolver), \
         patch("ctypes.CDLL", return_value=mock_lib):
        result = load_or_raise(crate_dir=str(tmp_path), crate_rel_path=".")

    assert result is mock_lib


def test_resolver_failure_no_fallback_raises(tmp_path):
    """When resolver raises and no fallback_builder, RuntimeError is raised."""
    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = RuntimeError("download failed")

    with patch("xforge.precompiled.loader.PrecompiledResolver", return_value=mock_resolver):
        with pytest.raises(RuntimeError, match="download failed"):
            load_or_raise(crate_dir=str(tmp_path), crate_rel_path=".", fallback_builder=None)


def test_resolver_failure_with_fallback_calls_builder(tmp_path):
    """When resolver raises and fallback_builder is provided, it is called."""
    lib_file = tmp_path / "libfoo.so"
    lib_file.write_bytes(b"")

    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = RuntimeError("no precompiled")
    fallback = MagicMock(return_value=lib_file)
    mock_lib = _make_mock_lib()

    with patch("xforge.precompiled.loader.PrecompiledResolver", return_value=mock_resolver), \
         patch("ctypes.CDLL", return_value=mock_lib):
        result = load_or_raise(
            crate_dir=str(tmp_path),
            crate_rel_path=".",
            fallback_builder=fallback,
        )

    fallback.assert_called_once()
    assert result is mock_lib


def test_crate_rel_path_resolved_from_crate_dir(tmp_path):
    """crate_rel_path is resolved relative to crate_dir's parent when crate_dir is a file."""
    # When crate_dir is a file path (like __file__), parent is used as base.
    caller_file = tmp_path / "pkg" / "_xforge_loader.py"
    caller_file.parent.mkdir(parents=True)
    caller_file.write_text("")

    native_dir = tmp_path / "native"
    native_dir.mkdir()

    lib_file = native_dir / "libfoo.so"
    lib_file.write_bytes(b"")

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = lib_file
    mock_lib = _make_mock_lib()

    with patch("xforge.precompiled.loader.PrecompiledResolver", return_value=mock_resolver) as MockResolver, \
         patch("ctypes.CDLL", return_value=mock_lib):
        load_or_raise(crate_dir=str(caller_file), crate_rel_path="../native")

    # Verify the resolver was constructed with the resolved crate dir
    call_kwargs = MockResolver.call_args
    resolved = Path(call_kwargs[1]["crate_dir"] if call_kwargs[1] else call_kwargs[0][0])
    assert resolved.resolve() == native_dir.resolve()
