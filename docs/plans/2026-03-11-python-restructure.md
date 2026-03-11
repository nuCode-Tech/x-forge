# Python Adapter Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure `adapters/python` to mirror the Dart adapter layout — `src/xforge_python/precompiled/` for source, `tool/commands/` for CLI commands, matching `lib/src/precompiled/` and `tool/commands/` in Dart.

**Architecture:** Pure rename/move — zero logic changes. The public import name changes from `xforge` to `xforge_python`. All implementation files move from `src/xforge/` to `src/xforge_python/precompiled/`. The monolithic `cli.py` splits into `tool/commands/keygen.py`, `tool/commands/validate_precompiled.py`, `tool/commands/generate_loader.py`, and a `tool/cli.py` dispatcher — mirroring Dart's `tool/commands/` and `tool/cli.dart`. A `bin/xforge_python.py` entry point mirrors `bin/xforge_dart.dart`.

**Tech Stack:** Python 3.9+, setuptools src layout, same dependencies as before.

---

## Target layout (mirrors Dart exactly)

```
adapters/dart/                          adapters/python/
  lib/                                    src/
    xforge_dart.dart          →             xforge_python/
    src/precompiled/          →               precompiled/
      artifacts_provider.dart →                 artifacts_provider.py
      crate_hash.dart         →                 crate_hash.py
      loader.dart (new)       →                 loader.py
      options.dart            →                 options.py
      resolver.dart (new)     →                 resolver.py
      target.dart             →                 target.py
      util.dart               →                 util.py
  bin/                                    bin/
    xforge_dart.dart          →             xforge_python.py
  tool/                                   tool/
    cli.dart                  →             cli.py
    commands/                 →             commands/
      keygen.dart             →               keygen.py
      validate_precompiled.dart →             validate_precompiled.py
      (new)                   →               generate_loader.py
  test/                                   tests/
  pubspec.yaml                            pyproject.toml
```

---

### Task 1: Create new directory structure and move source files

**Files:**
- Create: `adapters/python/src/xforge_python/__init__.py`
- Create: `adapters/python/src/xforge_python/precompiled/__init__.py`
- Create: `adapters/python/src/xforge_python/precompiled/artifacts_provider.py`
- Create: `adapters/python/src/xforge_python/precompiled/crate_hash.py`
- Create: `adapters/python/src/xforge_python/precompiled/loader.py`
- Create: `adapters/python/src/xforge_python/precompiled/options.py`
- Create: `adapters/python/src/xforge_python/precompiled/resolver.py`
- Create: `adapters/python/src/xforge_python/precompiled/target.py`
- Create: `adapters/python/src/xforge_python/precompiled/util.py`
- Delete: `adapters/python/src/xforge/` (entire directory)

**Step 1: Create the new directory structure**

```bash
cd adapters/python
mkdir -p src/xforge_python/precompiled
```

**Step 2: Copy each implementation file with updated imports**

For each file, the only change is replacing `from xforge.` with `from xforge_python.precompiled.` and `from xforge import` with `from xforge_python.precompiled import` (or `from xforge_python import` for the barrel).

**`src/xforge_python/precompiled/util.py`** — copy from `src/xforge/util.py` verbatim (no internal xforge imports):

```python
"""
Hex encode/decode, HTTP with retry, atomic write, Ed25519 verify.
"""
import os
import time
from pathlib import Path

import requests
from nacl.encoding import RawEncoder
from nacl.signing import VerifyKey

def decode_hex(hex_str: str) -> bytes:
    normalized = hex_str.strip().lower()
    if len(normalized) % 2 != 0:
        raise ValueError("Invalid hex length")
    return bytes.fromhex(normalized)


def hex_encode(data: bytes) -> str:
    return data.hex()


def http_get_with_retry(
    url: str,
    *,
    headers: dict | None = None,
    max_attempts: int = 4,
    timeout: float = 30.0,
    retry_delay: float = 1.0,
) -> requests.Response:
    for attempt in range(1, max_attempts + 1):
        try:
            return requests.get(url, headers=headers or {}, timeout=timeout)
        except (requests.RequestException, requests.Timeout):
            if attempt == max_attempts:
                raise
            time.sleep(retry_delay)
    raise RuntimeError("Unreachable")


def write_bytes_atomically(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{time.time_ns()}.tmp")
    tmp.write_bytes(data)
    try:
        tmp.replace(path)
    except OSError:
        if path.exists():
            path.unlink()
        tmp.replace(path)


def read_or_download_bytes(
    path: Path,
    url: str,
    *,
    headers: dict | None = None,
) -> bytes:
    if path.is_file():
        return path.read_bytes()
    response = http_get_with_retry(url, headers=headers)
    response.raise_for_status()
    data = response.content
    write_bytes_atomically(path, data)
    return data


def verify_ed25519_signature(
    *,
    public_key: bytes,
    message: bytes,
    signature: bytes,
) -> bool:
    if len(public_key) != 32:
        raise ValueError("public_key must be 32 bytes")
    try:
        key = VerifyKey(public_key, encoder=RawEncoder)
        key.verify(signature + message)
        return True
    except Exception:
        return False
```

**`src/xforge_python/precompiled/target.py`** — copy from `src/xforge/target.py` verbatim (no internal xforge imports):

```python
"""
Detect host Rust target triple (e.g. aarch64-apple-darwin, x86_64-unknown-linux-gnu).
"""
import platform
import sys


def detect_host_target_triple() -> str:
    machine = platform.machine().lower()
    system = sys.platform

    arch = "x86_64"
    if "aarch64" in machine or "arm64" in machine:
        arch = "aarch64"
    elif "x86_64" in machine or "amd64" in machine or "x64" in machine:
        arch = "x86_64"
    elif "i686" in machine or "i386" in machine or "x86" in machine:
        arch = "x86"
    elif "arm" in machine:
        arch = "arm"

    if system == "darwin":
        return f"{arch}-apple-darwin"
    if system == "linux":
        return f"{arch}-unknown-linux-gnu"
    if system == "win32":
        return f"{arch}-pc-windows-msvc"
    return "x86_64-unknown-linux-gnu"
```

**`src/xforge_python/precompiled/options.py`** — update import `from xforge.util` → `from xforge_python.precompiled.util`:

```python
"""
Parse xforge.yaml precompiled_binaries: repository, public_key, url_prefix, mode.
"""
import re
from enum import Enum
from pathlib import Path

import yaml

from xforge_python.precompiled.util import decode_hex
# ... rest of file identical to src/xforge/options.py
```

**`src/xforge_python/precompiled/crate_hash.py`** — no internal xforge imports, copy verbatim.

**`src/xforge_python/precompiled/artifacts_provider.py`** — update imports:
- `from xforge.options import` → `from xforge_python.precompiled.options import`
- `from xforge.util import` → `from xforge_python.precompiled.util import`

**`src/xforge_python/precompiled/resolver.py`** — update imports:
- `from xforge.artifacts_provider import` → `from xforge_python.precompiled.artifacts_provider import`
- `from xforge.crate_hash import` → `from xforge_python.precompiled.crate_hash import`
- `from xforge.options import` → `from xforge_python.precompiled.options import`
- `from xforge.target import` → `from xforge_python.precompiled.target import`

**`src/xforge_python/precompiled/loader.py`** — update import:
- `from xforge.resolver import` → `from xforge_python.precompiled.resolver import`

**`src/xforge_python/precompiled/__init__.py`** — empty (internal package marker):

```python
```

**`src/xforge_python/__init__.py`** — barrel file, update all imports from `xforge.*` → `xforge_python.precompiled.*`:

```python
"""
xforge_python — Python adapter for XForge precompiled binaries.

Exposes get_library_path, load_native_library, PrecompiledResolver, and helpers
for computing build_id and loading xforge.yaml config.
"""
from xforge_python.precompiled.artifacts_provider import (
    ArtifactNotFoundException,
    ArtifactResolution,
    ArtifactSignatureException,
    ManifestSignatureException,
    PlatformNotFoundException,
    PrecompiledArtifactsProvider,
)
from xforge_python.precompiled.crate_hash import compute_release_hash
from xforge_python.precompiled.options import PrecompiledBinaryMode, XforgeOptions
from xforge_python.precompiled.resolver import (
    get_library_path,
    load_native_library,
    PrecompiledResolver,
)
from xforge_python.precompiled.loader import load_or_raise
from xforge_python.precompiled.target import detect_host_target_triple

__all__ = [
    "ArtifactNotFoundException",
    "ArtifactResolution",
    "ArtifactSignatureException",
    "ManifestSignatureException",
    "PlatformNotFoundException",
    "PrecompiledArtifactsProvider",
    "PrecompiledBinaryMode",
    "PrecompiledResolver",
    "XforgeOptions",
    "compute_release_hash",
    "detect_host_target_triple",
    "get_library_path",
    "load_native_library",
    "load_or_raise",
]
```

**Step 3: Delete the old `src/xforge/` directory**

```bash
cd adapters/python
rm -rf src/xforge
```

**Step 4: Update `pyproject.toml`**

Change the entry point script from `xforge.cli:main` to `xforge_python.tool.cli:main`, and update the package name:

```toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "xforge-python"
version = "0.1.0"
description = "Python adapter for XForge precompiled artifacts."
readme = "README.md"
requires-python = ">=3.9"
license = { text = "MIT" }
dependencies = [
    "PyYAML>=6.0",
    "requests>=2.28.0",
    "PyNaCl>=1.5.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[project.scripts]
xforge = "xforge_python.tool.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

**Step 5: Update `_LOADER_TEMPLATE` in `tool/commands/generate_loader.py`** (Task 2) — the generated `_xforge_loader.py` must import from `xforge_python.precompiled.loader` not `xforge.loader`.

**Step 6: Verify the package is importable**

```bash
cd adapters/python
python3 -c "from xforge_python import load_or_raise, XforgeOptions, compute_release_hash; print('OK')"
```

Expected: `OK`

**Step 7: Run tests (they will fail — fixed in Task 3)**

```bash
cd adapters/python
python3 -m pytest tests/ -v 2>&1 | head -20
```

Expected: `ImportError: No module named 'xforge'` — this is expected, tests are fixed in Task 3.

**Step 8: Commit**

```bash
cd /Users/sambaby/Development/@stax/nucode/xforge/x-forge
git add adapters/python/src/
git commit -m "refactor(python): restructure src/xforge/ → src/xforge_python/precompiled/ to mirror Dart layout"
```

---

### Task 2: Split CLI into `tool/commands/` (mirrors Dart's `tool/commands/`)

**Files:**
- Create: `adapters/python/tool/__init__.py`
- Create: `adapters/python/tool/cli.py`
- Create: `adapters/python/tool/commands/__init__.py`
- Create: `adapters/python/tool/commands/keygen.py`
- Create: `adapters/python/tool/commands/validate_precompiled.py`
- Create: `adapters/python/tool/commands/generate_loader.py`
- Create: `adapters/python/bin/xforge_python.py`
- Delete: `adapters/python/src/xforge_python/precompiled/cli.py` (if it exists — cli was in old xforge package)

**Step 1: Create `tool/commands/keygen.py`**

Extract `run_keygen` and `_print_keygen_usage` from the old `cli.py`. Update imports to use `xforge_python`:

```python
"""
keygen command: generate an Ed25519 keypair.
"""
import sys

from nacl.encoding import RawEncoder
from nacl.signing import SigningKey

from xforge_python.precompiled.util import hex_encode


def run_keygen(rest: list[str]) -> int:
    if rest and rest != ["--help"] and rest != ["-h"]:
        print("Unknown arguments: " + " ".join(rest), file=sys.stderr)
        _print_usage()
        return 2
    if rest and rest[0] in ("--help", "-h"):
        _print_usage()
        return 0

    signing_key = SigningKey.generate()
    seed = signing_key.encode(encoder=RawEncoder)
    verify_key = signing_key.verify_key
    public = verify_key.encode(encoder=RawEncoder)
    private = seed + public

    if len(public) != 32 or len(private) != 64:
        print(
            "Key generation failed: expected 32-byte public key and "
            "64-byte private key.",
            file=sys.stderr,
        )
        return 1

    print(f"public_key={hex_encode(public)}")
    print(f"private_key={hex_encode(private)}")
    return 0


def _print_usage() -> None:
    print("Usage: xforge keygen")
    print("Outputs:")
    print("  public_key=<32-byte hex>")
    print("  private_key=<64-byte hex (seed + public)>")
```

**Step 2: Create `tool/commands/validate_precompiled.py`**

Extract `run_validate_precompiled` from old `cli.py`. Update imports:

```python
"""
validate-precompiled command: download and verify manifest + artifact.
"""
import argparse
import sys
from pathlib import Path

from xforge_python.precompiled.artifacts_provider import PrecompiledArtifactsProvider
from xforge_python.precompiled.crate_hash import compute_release_hash
from xforge_python.precompiled.options import XforgeOptions
from xforge_python.precompiled.target import detect_host_target_triple


def run_validate_precompiled(rest: list[str]) -> int:
    p = argparse.ArgumentParser(prog="xforge validate-precompiled")
    p.add_argument("--crate-dir", default=None, help="Crate directory (default: cwd)")
    p.add_argument("--build-id", default=None, help="Build id override")
    p.add_argument("--target", default=None, help="Rust target triple (default: host)")
    parsed, _ = p.parse_known_args(rest)

    crate_dir = Path(parsed.crate_dir) if parsed.crate_dir else Path.cwd()

    options = XforgeOptions.load(crate_dir)
    config = options.precompiled_binaries
    if config is None:
        print("xforge.yaml is missing precompiled_binaries config.", file=sys.stderr)
        return 2

    build_id = parsed.build_id or compute_release_hash(crate_dir)
    target = parsed.target or detect_host_target_triple()

    provider = PrecompiledArtifactsProvider(crate_dir=crate_dir, config=config)

    try:
        manifest = provider.fetch_verified_manifest(build_id)
        selection = provider.select_artifact(manifest=manifest, target=target)
        provider.fetch_verified_artifact(
            build_id=build_id,
            artifact_name=selection.artifact_name,
        )
        print("Validated precompiled artifact:")
        print(f"  crateDir: {crate_dir.resolve()}")
        print(f"  buildId: {build_id}")
        print(f"  target: {target}")
        print(f"  artifact: {selection.artifact_name}")
        return 0
    except Exception as e:
        print(f"Validation failed: {e}", file=sys.stderr)
        return 1
```

**Step 3: Create `tool/commands/generate_loader.py`**

Extract `run_generate_loader`, `_autodetect_crate_dir`, `_CRATE_SEARCH_PATHS`, `_LOADER_TEMPLATE` from old `cli.py`. Update the template import to use `xforge_python`:

```python
"""
generate-loader command: generate _xforge_loader.py for plugin packages.
"""
import argparse
import os
import sys
from pathlib import Path

from xforge_python.precompiled.options import XforgeOptions

_CRATE_SEARCH_PATHS = [".", "native", "rust", "../native", "../rust", "../.."]

_LOADER_TEMPLATE = '''\
# AUTO-GENERATED by xforge generate-loader. Do not edit manually.
# Re-run: xforge generate-loader --out {out_path}
"""
Auto-loader for the precompiled native library.
Imported at package init time; downloads and loads the library transparently.
"""
import ctypes
from xforge_python.precompiled.loader import load_or_raise

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

    if parsed.crate_dir:
        crate_dir = Path(parsed.crate_dir).resolve()
        if not (crate_dir / "xforge.yaml").is_file():
            print(f"Error: xforge.yaml not found in {crate_dir}", file=sys.stderr)
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

    options = XforgeOptions.load(crate_dir)
    if options.precompiled_binaries is None:
        print(
            f"Error: xforge.yaml at {crate_dir} has no precompiled_binaries block.",
            file=sys.stderr,
        )
        return 2

    try:
        crate_rel_path = os.path.relpath(crate_dir, out_path.parent)
    except ValueError:
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

**Step 4: Create `tool/cli.py`** (mirrors `tool/cli.dart`):

```python
"""
CLI dispatcher: keygen, validate-precompiled, generate-loader.
Entry point for the xforge script.
"""
import argparse
import sys

from xforge_python.tool.commands.keygen import run_keygen
from xforge_python.tool.commands.validate_precompiled import run_validate_precompiled
from xforge_python.tool.commands.generate_loader import run_generate_loader


def main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("--help", "-h"):
        print("xforge commands: keygen, validate-precompiled, generate-loader")
        print("Run with --help for command options.")
        sys.exit(0 if argv and argv[0] in ("--help", "-h") else 2)

    parser = argparse.ArgumentParser(
        prog="xforge",
        description="xforge-python CLI: keygen, validate-precompiled, generate-loader",
    )
    parser.add_argument(
        "command",
        choices=["keygen", "validate-precompiled", "generate-loader"],
        help="Command to run",
    )
    parser.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        default=[],
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if args.command == "keygen":
        sys.exit(run_keygen(args.extra))
    if args.command == "validate-precompiled":
        sys.exit(run_validate_precompiled(args.extra))
    if args.command == "generate-loader":
        sys.exit(run_generate_loader(args.extra))
    parser.print_help()
    sys.exit(2)
```

**Step 5: Create `tool/__init__.py` and `tool/commands/__init__.py`** — both empty.

**Step 6: Create `bin/xforge_python.py`** (mirrors `bin/xforge_dart.dart`):

```python
"""CLI entry point — delegates to tool/cli.py."""
from xforge_python.tool.cli import main

if __name__ == "__main__":
    main()
```

**Step 7: Update `pyproject.toml` entry point**

The script entry point must point to `xforge_python.tool.cli:main`:

```toml
[project.scripts]
xforge = "xforge_python.tool.cli:main"
```

**Step 8: Verify CLI is importable**

```bash
cd adapters/python
python3 -c "from xforge_python.tool.cli import main; print('OK')"
```

Expected: `OK`

**Step 9: Commit**

```bash
cd /Users/sambaby/Development/@stax/nucode/xforge/x-forge
git add adapters/python/tool/ adapters/python/bin/ adapters/python/pyproject.toml
git commit -m "refactor(python): split CLI into tool/commands/ to mirror Dart layout"
```

---

### Task 3: Update tests to use new import paths

**Files:**
- Modify: `adapters/python/tests/test_artifacts_provider.py`
- Modify: `adapters/python/tests/test_crate_hash.py`
- Modify: `adapters/python/tests/test_options.py`
- Modify: `adapters/python/tests/test_target.py`
- Modify: `adapters/python/tests/test_loader.py`
- Modify: `adapters/python/tests/test_cli_generate_loader.py`

**Step 1: Update all `from xforge.` imports to `from xforge_python.precompiled.`**

In every test file, replace:
- `from xforge.artifacts_provider import` → `from xforge_python.precompiled.artifacts_provider import`
- `from xforge.options import` → `from xforge_python.precompiled.options import`
- `from xforge.crate_hash import` → `from xforge_python.precompiled.crate_hash import`
- `from xforge.target import` → `from xforge_python.precompiled.target import`
- `from xforge.loader import` → `from xforge_python.precompiled.loader import`
- `from xforge.util import` → `from xforge_python.precompiled.util import`
- `from xforge.cli import` → `from xforge_python.tool.commands.generate_loader import`
- `import xforge.loader` → `import xforge_python.precompiled.loader`

In `test_cli_generate_loader.py`:
- `from xforge.cli import run_generate_loader` → `from xforge_python.tool.commands.generate_loader import run_generate_loader`

In `test_loader.py`:
- `patch("xforge.loader.PrecompiledResolver"` → `patch("xforge_python.precompiled.loader.PrecompiledResolver"`

**Step 2: Run the full test suite**

```bash
cd adapters/python
python3 -m pytest tests/ -v
```

Expected: all 29 tests PASS.

**Step 3: Commit**

```bash
cd /Users/sambaby/Development/@stax/nucode/xforge/x-forge
git add adapters/python/tests/
git commit -m "refactor(python): update tests to use xforge_python.precompiled import paths"
```

---

### Task 4: Remove old `src/xforge/` if not already deleted, and final verification

**Step 1: Confirm old package is gone**

```bash
ls adapters/python/src/
```

Expected: only `xforge_python/` — no `xforge/` directory.

**Step 2: Confirm the egg-info is stale and reinstall**

```bash
cd adapters/python
pip install -e . --quiet
python3 -c "import xforge_python; print(xforge_python.__file__)"
```

Expected: path inside `src/xforge_python/__init__.py`.

**Step 3: Run full test suite one final time**

```bash
cd adapters/python
python3 -m pytest tests/ -v
```

Expected: 29/29 PASS.

**Step 4: Verify CLI entry point works**

```bash
cd adapters/python
python3 -m xforge_python.tool.cli --help
```

Expected: prints `xforge commands: keygen, validate-precompiled, generate-loader`

**Step 5: Final commit**

```bash
cd /Users/sambaby/Development/@stax/nucode/xforge/x-forge
git add -A adapters/python/
git commit -m "refactor(python): final cleanup — remove stale xforge_python.egg-info and old src/xforge"
```

---

## Execution Order

Tasks must run sequentially: **1 → 2 → 3 → 4**

Task 1 moves the source. Task 2 creates the tool layer. Task 3 fixes the tests. Task 4 verifies everything end-to-end.
