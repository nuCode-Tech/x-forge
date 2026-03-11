import pytest
from pathlib import Path

from xforge.precompiled.options import PrecompiledBinaryMode, XforgeOptions


def test_load_missing_xforge_yaml(tmp_path):
    opts = XforgeOptions.load(tmp_path)
    assert opts.precompiled_binaries is None


def test_load_empty_xforge_yaml(tmp_path):
    (tmp_path / "xforge.yaml").write_text("{}")
    opts = XforgeOptions.load(tmp_path)
    assert opts.precompiled_binaries is None


def test_load_precompiled_binaries(tmp_path):
    (tmp_path / "xforge.yaml").write_text("""
precompiled_binaries:
  repository: owner/repo
  public_key: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  mode: auto
""")
    opts = XforgeOptions.load(tmp_path)
    assert opts.precompiled_binaries is not None
    assert opts.precompiled_binaries.repository == "owner/repo"
    assert len(opts.precompiled_binaries.public_key) == 32
    assert opts.precompiled_binaries.mode == PrecompiledBinaryMode.AUTO


def test_load_mode_always(tmp_path):
    (tmp_path / "xforge.yaml").write_text("""
precompiled_binaries:
  repository: a/b
  public_key: "0000000000000000000000000000000000000000000000000000000000000000"
  mode: always
""")
    opts = XforgeOptions.load(tmp_path)
    assert opts.precompiled_binaries.mode == PrecompiledBinaryMode.ALWAYS


def test_load_mode_never(tmp_path):
    (tmp_path / "xforge.yaml").write_text("""
precompiled_binaries:
  repository: a/b
  public_key: "0000000000000000000000000000000000000000000000000000000000000000"
  mode: never
""")
    opts = XforgeOptions.load(tmp_path)
    assert opts.precompiled_binaries.mode == PrecompiledBinaryMode.NEVER


def test_file_url_default(tmp_path):
    (tmp_path / "xforge.yaml").write_text("""
precompiled_binaries:
  repository: owner/repo
  public_key: "0000000000000000000000000000000000000000000000000000000000000000"
""")
    opts = XforgeOptions.load(tmp_path)
    url = opts.precompiled_binaries.file_url("b1-abc", "xforge-manifest.json")
    assert "github.com" in url
    assert "owner/repo" in url
    assert "b1-abc" in url
    assert "xforge-manifest.json" in url
