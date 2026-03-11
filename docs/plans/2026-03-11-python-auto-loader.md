# Python Auto-Loader Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `xforge.loader.load_or_raise()` and `xforge generate-loader` CLI command so plugin authors can ship a generated `_xforge_loader.py` that transparently downloads and loads the native library on first import.

**Architecture:** A new `loader.py` runtime module wraps `PrecompiledResolver` and `ctypes.CDLL`. A new `generate-loader` CLI command auto-detects the crate dir and writes a small generated file the plugin author commits. The generated file calls `load_or_raise()` at module level so import triggers the download.

**Tech Stack:** Python 3.9+, `ctypes` (stdlib), `logging` (stdlib), existing `xforge.resolver.PrecompiledResolver`, `xforge.options.XforgeOptions`.

---

### Task 1: `xforge.loader` — `load_or_raise()`

**Files:**
- Create: `adapters/python/src/xforge/loader.py`
- Test: `adapters/python/tests/test_loader.py`

**Step 1: Write the failing tests**

Create `adapters/python/tests/test_loader.py`:

```python
import ctypes
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from xforge.loader import load_or_raise


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

    with patch("xforge.loader.PrecompiledResolver", return_value=mock_resolver), \
         patch("ctypes.CDLL", return_value=mock_lib):
        result = load_or_raise(crate_dir=str(tmp_path), crate_rel_path=".")

    assert result is mock_lib


def test_resolver_failure_no_fallback_raises(tmp_path):
    """When resolver raises and no fallback_builder, RuntimeError is raised."""
    mock_resolver = MagicMock()
    mock_resolver.resolve.side_effect = RuntimeError("download failed")

    with patch("xforge.loader.PrecompiledResolver", return_value=mock_resolver):
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

    with patch("xforge.loader.PrecompiledResolver", return_value=mock_resolver), \
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

    with patch("xforge.loader.PrecompiledResolver", return_value=mock_resolver) as MockResolver, \
         patch("ctypes.CDLL", return_value=mock_lib):
        load_or_raise(crate_dir=str(caller_file), crate_rel_path="../native")

    # Verify the resolver was constructed with the resolved crate dir
    call_kwargs = MockResolver.call_args
    resolved = Path(call_kwargs[1]["crate_dir"] if call_kwargs[1] else call_kwargs[0][0])
    assert resolved.resolve() == native_dir.resolve()
```

**Step 2: Run to verify they fail**

```bash
cd adapters/python
python -m pytest tests/test_loader.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'xforge.loader'`

**Step 3: Implement `loader.py`**

Create `adapters/python/src/xforge/loader.py`:

```python
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

from xforge.resolver import PrecompiledResolver

_log = logging.getLogger("xforge.loader")


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

    resolver = PrecompiledResolver(
        crate_dir=resolved_crate_dir,
        fallback_builder=fallback_builder,
    )
    try:
        lib_path = resolver.resolve()
    except Exception as exc:
        _log.error("Failed to resolve precompiled library: %s", exc)
        raise

    _log.info("Loading library: %s", lib_path)
    return ctypes.CDLL(str(lib_path))
```

**Step 4: Run tests to verify they pass**

```bash
cd adapters/python
python -m pytest tests/test_loader.py -v
```

Expected: all 6 tests PASS.

**Step 5: Export from `__init__.py`**

In `adapters/python/src/xforge/__init__.py`, add to the imports and `__all__`:

```python
from xforge.loader import load_or_raise
```

And add `"load_or_raise"` to `__all__`.

**Step 6: Commit**

```bash
git add adapters/python/src/xforge/loader.py \
        adapters/python/src/xforge/__init__.py \
        adapters/python/tests/test_loader.py
git commit -m "feat(python): add xforge.loader.load_or_raise for auto-download on import"
```

---

### Task 2: `xforge generate-loader` CLI command

**Files:**
- Modify: `adapters/python/src/xforge/cli.py`
- Test: `adapters/python/tests/test_cli_generate_loader.py`

**Step 1: Write the failing tests**

Create `adapters/python/tests/test_cli_generate_loader.py`:

```python
import textwrap
from pathlib import Path

import pytest

from xforge.cli import run_generate_loader


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
```

**Step 2: Run to verify they fail**

```bash
cd adapters/python
python -m pytest tests/test_cli_generate_loader.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'run_generate_loader' from 'xforge.cli'`

**Step 3: Implement `run_generate_loader` in `cli.py`**

In `adapters/python/src/xforge/cli.py`:

Add `"generate-loader"` to the `choices` list in the main parser, add dispatch for it, and add the function:

```python
# In main(), add to choices:
choices=["keygen", "validate-precompiled", "generate-loader"],

# In main(), add dispatch:
if args.command == "generate-loader":
    sys.exit(run_generate_loader(args.extra))
```

Add the function (after `run_validate_precompiled`):

```python
_CRATE_SEARCH_PATHS = [".", "native", "rust", "../native", "../rust", "../.."]

_LOADER_TEMPLATE = '''\
# AUTO-GENERATED by xforge generate-loader. Do not edit manually.
# Re-run: xforge generate-loader --out {out_path}
"""
Auto-loader for the precompiled native library.
Imported at package init time; downloads and loads the library transparently.
"""
import ctypes
from xforge.loader import load_or_raise

LIBRARY: ctypes.CDLL = load_or_raise(
    crate_dir=__file__,
    crate_rel_path={crate_rel_path!r},
    fallback_builder=None,  # replace with your own build function if needed
)
'''


def run_generate_loader(rest: list[str]) -> int:
    p = argparse.ArgumentParser(prog="xforge generate-loader")
    p.add_argument(
        "--crate-dir",
        default=None,
        help="Crate directory containing xforge.yaml (auto-detected if omitted)",
    )
    p.add_argument(
        "--out",
        default="_xforge_loader.py",
        help="Output file path (default: ./_xforge_loader.py)",
    )
    parsed, _ = p.parse_known_args(rest)

    out_path = Path(parsed.out).resolve()

    # Resolve crate dir
    if parsed.crate_dir:
        crate_dir = Path(parsed.crate_dir).resolve()
        if not (crate_dir / "xforge.yaml").is_file():
            print(
                f"Error: xforge.yaml not found in {crate_dir}",
                file=sys.stderr,
            )
            return 2
    else:
        crate_dir = _autodetect_crate_dir()
        if crate_dir is None:
            print(
                "Error: could not find xforge.yaml. "
                f"Searched: {_CRATE_SEARCH_PATHS}. "
                "Use --crate-dir to specify the crate directory.",
                file=sys.stderr,
            )
            return 2

    # Validate precompiled_binaries block exists
    options = XforgeOptions.load(crate_dir)
    if options.precompiled_binaries is None:
        print(
            f"Error: xforge.yaml at {crate_dir} has no precompiled_binaries block.",
            file=sys.stderr,
        )
        return 2

    # Compute relative path from the output file's directory to the crate dir
    try:
        crate_rel_path = os.path.relpath(crate_dir, out_path.parent)
    except ValueError:
        # On Windows, relpath can fail across drives — fall back to absolute
        crate_rel_path = str(crate_dir)

    content = _LOADER_TEMPLATE.format(
        out_path=out_path.name,
        crate_rel_path=crate_rel_path,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"Generated: {out_path}")
    print(f"  crate_dir: {crate_dir}")
    print(f"  crate_rel_path: {crate_rel_path!r}")
    return 0


def _autodetect_crate_dir() -> Path | None:
    cwd = Path.cwd()
    for rel in _CRATE_SEARCH_PATHS:
        candidate = (cwd / rel).resolve()
        if (candidate / "xforge.yaml").is_file():
            return candidate
    return None
```

Also add `import os` at the top of `cli.py` if not already present.

**Step 4: Run tests to verify they pass**

```bash
cd adapters/python
python -m pytest tests/test_cli_generate_loader.py -v
```

Expected: all 7 tests PASS.

**Step 5: Verify full test suite still passes**

```bash
cd adapters/python
python -m pytest tests/ -v
```

Expected: all tests PASS.

**Step 6: Commit**

```bash
git add adapters/python/src/xforge/cli.py \
        adapters/python/tests/test_cli_generate_loader.py
git commit -m "feat(python): add xforge generate-loader CLI command"
```

---

### Task 3: Update `__init__.py` exports and README

**Files:**
- Modify: `adapters/python/src/xforge/__init__.py`
- Modify: `adapters/python/README.md`

**Step 1: Update `__init__.py`**

Add to `adapters/python/src/xforge/__init__.py`:

```python
from xforge.loader import load_or_raise
```

And add `"load_or_raise"` to `__all__`.

(This was partially done in Task 1 Step 5 — verify it's there, add if not.)

**Step 2: Update README**

Add a new section "Plugin author quickstart" near the top of `adapters/python/README.md`, before the existing "Integrating with your project" section:

```markdown
## Plugin author quickstart

If you are writing a Python plugin that wraps a Rust native library, xforge can make the binary download completely transparent to your users.

### 1. Add xforge-python as a dependency

In your plugin's `pyproject.toml`:

```toml
dependencies = [
    "xforge-python>=0.1.0",
    # ... your other deps
]
```

### 2. Generate the loader

From your plugin's root directory (where `xforge.yaml` lives, or with `--crate-dir`):

```bash
xforge generate-loader --out my_plugin/_xforge_loader.py
```

This writes a small `_xforge_loader.py` into your package. **Commit this file.**

### 3. Import the loader in your package's `__init__.py`

```python
# my_plugin/__init__.py
from . import _xforge_loader   # downloads + loads the native library on first import
_lib = _xforge_loader.LIBRARY  # ctypes.CDLL handle

# ... rest of your package
```

That's it. When your users run `import my_plugin`, xforge downloads the correct precompiled binary for their platform, verifies its signature, caches it under `.xforge/`, and loads it — all transparently.

### 4. Optional: local build fallback

If you want to fall back to building from source when no precompiled binary is available, replace `fallback_builder=None` in the generated file:

```python
# my_plugin/_xforge_loader.py
from xforge.loader import load_or_raise
from my_plugin._build import build_native  # your own Cargo wrapper

LIBRARY = load_or_raise(
    crate_dir=__file__,
    crate_rel_path="../native",
    fallback_builder=build_native,  # called with (crate_dir: Path, reason: str) -> Path
)
```

### Re-generating

If you move the crate directory or rename the output file, re-run:

```bash
xforge generate-loader --out my_plugin/_xforge_loader.py
```
```

**Step 3: Run full test suite one more time**

```bash
cd adapters/python
python -m pytest tests/ -v
```

Expected: all tests PASS.

**Step 4: Commit**

```bash
git add adapters/python/src/xforge/__init__.py \
        adapters/python/README.md
git commit -m "docs(python): add plugin author quickstart and export load_or_raise"
```

---

### Task 4: Add logging (audit fix, prerequisite for loader)

> This task should be done **before** Task 1 if not already done, since `loader.py` uses `logging`. The existing `resolver.py` and `artifacts_provider.py` have no logging — add it now so the full download path is observable.

**Files:**
- Modify: `adapters/python/src/xforge/resolver.py`

**Step 1: Add logging to `PrecompiledResolver.resolve()`**

In `adapters/python/src/xforge/resolver.py`, add at the top:

```python
import logging
_log = logging.getLogger("xforge.resolver")
```

Then add log calls in `resolve()`:

```python
def resolve(self, target=None, mode=None):
    # ... existing env override check ...

    # After computing target_triple and build_id:
    _log.info("Resolving precompiled binary for %s", target_triple)
    _log.debug("build_id: %s", build_id)

    # After resolution.downloaded:
    if resolution.downloaded and resolution.artifact is not None:
        _log.info("Using precompiled binary for %s", target_triple)
        # ...

    # Before fallback:
    _log.info("Falling back for %s: %s", target_triple, resolution.reason)
```

**Step 2: Run existing tests to verify nothing broke**

```bash
cd adapters/python
python -m pytest tests/ -v
```

Expected: all tests PASS (logging doesn't break anything).

**Step 3: Commit**

```bash
git add adapters/python/src/xforge/resolver.py
git commit -m "fix(python): add logging to PrecompiledResolver (audit gap)"
```

---

## Execution Order

Run tasks in this order: **4 → 1 → 2 → 3**

(Task 4 adds logging first so Task 1's `loader.py` can import `PrecompiledResolver` with logging already in place.)
