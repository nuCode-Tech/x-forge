import textwrap
from pathlib import Path

import pytest

from xforge.tool.commands.generate_loader import run_generate_loader


def _make_crate(tmp_path: Path, rel: str = ".") -> Path:
    """Create a minimal valid crate at tmp_path/rel."""
    crate = tmp_path / rel
    crate.mkdir(parents=True, exist_ok=True)
    (crate / "xforge.yaml").write_text(textwrap.dedent("""\
        precompiled_binaries:
          repository: owner/repo
          public_key: "0000000000000000000000000000000000000000000000000000000000000000"
    """))
    (crate / "Cargo.toml").write_text("[package]\nname = \"demo\"\nversion = \"0.1.0\"\n")
    return crate


def test_generate_loader_creates_file(tmp_path):
    """generate-loader writes _xforge_loader.py with expected content."""
    crate = _make_crate(tmp_path)
    out = tmp_path / "_xforge_loader.py"

    code = run_generate_loader(["--crate-dir", str(crate), "--out", str(out)])

    assert code == 0
    assert out.is_file()
    content = out.read_text()
    assert "AUTO-GENERATED" in content
    assert "load_or_raise" in content
    assert "LIBRARY" in content


def test_generate_loader_default_out(tmp_path, monkeypatch):
    """Without --out, writes _xforge_loader.py in cwd."""
    crate = _make_crate(tmp_path)
    monkeypatch.chdir(tmp_path)

    code = run_generate_loader(["--crate-dir", str(crate)])

    assert code == 0
    assert (tmp_path / "_xforge_loader.py").is_file()


def test_generate_loader_no_xforge_yaml(tmp_path):
    """Exits with code 2 if xforge.yaml is missing."""
    empty = tmp_path / "empty"
    empty.mkdir()
    out = tmp_path / "out.py"

    code = run_generate_loader(["--crate-dir", str(empty), "--out", str(out)])

    assert code == 2
    assert not out.exists()


def test_generate_loader_no_precompiled_binaries(tmp_path):
    """Exits with code 2 if xforge.yaml has no precompiled_binaries block."""
    crate = tmp_path / "crate"
    crate.mkdir()
    (crate / "xforge.yaml").write_text("{}")
    out = tmp_path / "out.py"

    code = run_generate_loader(["--crate-dir", str(crate), "--out", str(out)])

    assert code == 2
    assert not out.exists()


def test_generate_loader_autodetect_crate_dir(tmp_path, monkeypatch):
    """Auto-detects crate dir when xforge.yaml is in cwd."""
    crate = _make_crate(tmp_path)
    monkeypatch.chdir(crate)
    out = tmp_path / "out.py"

    code = run_generate_loader(["--out", str(out)])

    assert code == 0
    assert out.is_file()


def test_generate_loader_autodetect_native_subdir(tmp_path, monkeypatch):
    """Auto-detects crate dir when xforge.yaml is in ./native."""
    _make_crate(tmp_path, rel="native")
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out.py"

    code = run_generate_loader(["--out", str(out)])

    assert code == 0
    content = out.read_text()
    assert "native" in content


def test_generated_file_contains_rerun_comment(tmp_path):
    """Generated file contains a re-run comment with the --out path."""
    crate = _make_crate(tmp_path)
    out = tmp_path / "pkg" / "_xforge_loader.py"
    out.parent.mkdir()

    run_generate_loader(["--crate-dir", str(crate), "--out", str(out)])

    content = out.read_text()
    assert "generate-loader" in content
    assert "_xforge_loader.py" in content
