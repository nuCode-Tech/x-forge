"""
Canonical build identity hash matching the xforge CLI and Dart adapter.
Reads Cargo.toml, Cargo.lock, rust-toolchain.toml, xforge.yaml and produces b1-<sha256>.
"""
import hashlib
import json
from pathlib import Path

_HASH_VERSION = "b1"


def _field(name: str, value: str | None) -> dict:
    return {"affects_abi": True, "name": name, "value": value}


def canonical_json_without_target(
    *,
    cargo_toml: str,
    cargo_lock: str,
    rust_toolchain: str,
    xforge_yaml: str | None = None,
    uniffi_udl: str | None = None,
) -> str:
    fields = [
        _field("cargo.lock", cargo_lock),
        _field("cargo.toml", cargo_toml),
        _field("rust.target_triple", None),
        _field("uniffi.udl", uniffi_udl),
        _field("rust-toolchain.toml", rust_toolchain),
        _field("xforge.yaml", xforge_yaml),
    ]
    fields.sort(key=lambda f: f["name"])
    root = {"inputs": fields, "version": _HASH_VERSION}
    return json.dumps(root, sort_keys=False, separators=(",", ":"))


def compute_release_hash(crate_dir: str | Path) -> str:
    """Compute the release build_id (b1-<hex>) for the crate at crate_dir."""
    crate_dir = Path(crate_dir)
    cargo_toml = _read_required(crate_dir, "Cargo.toml")
    cargo_lock = _read_required_cargo_lock(crate_dir)
    rust_toolchain = _read_required_rust_toolchain(crate_dir)
    xforge_yaml = _read_optional(crate_dir, "xforge.yaml")

    canonical = canonical_json_without_target(
        cargo_toml=cargo_toml,
        cargo_lock=cargo_lock,
        rust_toolchain=rust_toolchain,
        xforge_yaml=xforge_yaml,
        uniffi_udl=None,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_HASH_VERSION}-{digest}"


def _read_required(crate_dir: Path, filename: str) -> str:
    path = crate_dir / filename
    if not path.is_file():
        raise FileNotFoundError(f"Missing required file: {filename} at {path}")
    return path.read_text(encoding="utf-8")


def _read_optional(crate_dir: Path, filename: str) -> str | None:
    path = crate_dir / filename
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _read_required_cargo_lock(crate_dir: Path) -> str:
    current = crate_dir.resolve()
    while True:
        candidate = current / "Cargo.lock"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(f"Missing required file: Cargo.lock (searched from {crate_dir})")


def _read_required_rust_toolchain(crate_dir: Path) -> str:
    direct = crate_dir / "rust-toolchain.toml"
    if direct.is_file():
        return direct.read_text(encoding="utf-8")
    current = crate_dir.resolve()
    while True:
        lock = current / "Cargo.lock"
        if lock.is_file():
            toolchain = current / "rust-toolchain.toml"
            if toolchain.is_file():
                return toolchain.read_text(encoding="utf-8")
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    raise FileNotFoundError(
        f"Missing required file: rust-toolchain.toml (searched from {crate_dir})"
    )
