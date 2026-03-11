# xforge-python

`xforge-python` is the Python adapter for XForge precompiled binaries. It computes the same `build_id` as the CLI, downloads and verifies signed manifest and artifacts from `xforge.yaml`, and exposes `get_library_path` / `load_native_library` so generated bindings (UniFFI, PyO3, ctypes) can load the native library without rebuilding the Rust crate.

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

## Integrating with your project

### Prerequisites

- The Rust crate (or repo) that ships precompiled artifacts must have:
  - `xforge.yaml` with a `precompiled_binaries` block: `repository`, `public_key`, and optionally `url_prefix`, `mode`.
  - `rust-toolchain.toml` (so `build_id` can be computed).
- Your Python environment has `xforge-python` installed: `pip install xforge-python` (or install from this repo).

### Option A — Use from generated bindings (runtime resolution)

Resolve the native library at runtime and load it (e.g. with ctypes or your binding’s loader):

```python
from xforge import get_library_path
import ctypes

# Crate root: directory that contains Cargo.toml and xforge.yaml
crate_dir = "/path/to/rust/crate"
path = get_library_path(crate_dir)
lib = ctypes.CDLL(str(path))
# Use lib.* as needed
```

Or use the helper that returns a loaded library:

```python
from xforge import load_native_library

lib = load_native_library("/path/to/rust/crate")
# lib is a ctypes.CDLL
```

To force a specific target triple (e.g. in CI):

```python
path = get_library_path(crate_dir, target="x86_64-unknown-linux-gnu")
```

**Environment override:** set `XFORGE_NATIVE_LIB_PATH` to the full path to the native library file. The resolver will use it and skip download (useful for CI or vendored builds).

### Option B — Install-time resolution

To have the library available at a fixed path after `pip install`, run the resolver in your package’s install step and copy the result into your package data (e.g. under `lib/` next to your Python package). Your generated code can then assume the library is at that relative path and load it without calling the resolver at runtime.

Example pattern in `setup.py` or a custom install script:

```python
from pathlib import Path
from xforge import get_library_path

def install_native_lib():
    crate_dir = Path(__file__).resolve().parent / "native"  # or your crate path
    lib_path = get_library_path(crate_dir)
    dest = Path(__file__).resolve().parent / "my_package" / "lib"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(lib_path, dest / lib_path.name)
```

### Configuration

`get_library_path`, `load_native_library`, and the CLI read the `precompiled_binaries` block from `xforge.yaml`:

```yaml
precompiled_binaries:
  repository: owner/repo
  public_key: "<32-byte hex>"
  url_prefix: "https://github.com/owner/repo/releases/download/"
  mode: auto
```

- `repository` and `public_key` are required.
- `mode`: `auto` (prefer download, fall back to local build if possible), `always` (fail if precompiled not available), `never` (always use fallback). Aliases: `download`→`always`, `build`/`off`/`disabled`→`never`.
- `url_prefix` overrides the default GitHub release download URL.

They also rely on `rust-toolchain.toml` in the crate (or repo) for deterministic `build_id`. For full config and CLI usage, see the sections below.

---

## PrecompiledResolver and API

- **`get_library_path(crate_dir, target=None, mode=None, fallback_builder=None)`** — Resolves (download + verify + extract) the precompiled library and returns its path. Use from generated bindings or at install time.
- **`load_native_library(crate_dir, target=None, ...)`** — Same resolution, then returns a `ctypes.CDLL` (or compatible) handle.
- **`PrecompiledResolver(crate_dir, lib_name="xforge", fallback_builder=None)`** — Resolver instance; call `.resolve(target=..., mode=...)` to get the library path. Optional `fallback_builder(crate_dir, reason)` can build locally and return a path when download is not used.
- **`compute_release_hash(crate_dir)`** — Computes the deterministic `build_id` (e.g. `b1-<sha256>`) matching the xforge CLI.
- **`detect_host_target_triple()`** — Returns the host Rust target triple (e.g. `x86_64-apple-darwin`).
- **`XforgeOptions.load(crate_dir)`** — Loads `xforge.yaml`; `.precompiled_binaries` is the config or `None`.

## CLI

### validate-precompiled

Download and verify the manifest and artifact for the current (or given) target:

```bash
xforge validate-precompiled \
  --crate-dir path/to/crate \
  --build-id b1-abc123 \
  --target aarch64-apple-darwin
```

- Exit `0` on success, `1` if verification fails, `2` on argument/configuration errors.
- `--crate-dir` defaults to the current directory; `--build-id` and `--target` default to computed build_id and host triple.

### keygen

Generate a new Ed25519 keypair in the same format as `xforge keygen` (Rust):

```bash
xforge keygen
```

Outputs:

- `public_key=<32-byte hex>`
- `private_key=<64-byte hex (seed + public)>`

## Caching and logging

Downloaded manifests, artifacts, and extracted libraries are stored under the crate directory as `.xforge/` (e.g. `.xforge/manifests/<build_id>/`, `.xforge/artifacts/<build_id>/`, `.xforge/extracted/<build_id>/<target>/`). Signatures are verified with PyNaCl (Ed25519); HTTP downloads use retries. Set `XFORGE_PYTHON_PRECOMPILED_VERBOSE=1` for verbose output where supported.
