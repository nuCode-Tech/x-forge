import pytest
from pathlib import Path

from xforge.precompiled.crate_hash import canonical_json_without_target, compute_release_hash


def test_canonical_json_field_order():
    """Canonical JSON sorts fields by name for stable hash."""
    out = canonical_json_without_target(
        cargo_toml="[package]\nname = \"x\"",
        cargo_lock="[[package]]",
        rust_toolchain="[toolchain]\ntargets = [\"x86_64-unknown-linux-gnu\"]",
        xforge_yaml=None,
        uniffi_udl=None,
    )
    assert "version" in out
    assert "b1" in out
    assert "inputs" in out
    # Field names must be sorted: cargo.lock before cargo.toml
    idx_lock = out.index("cargo.lock")
    idx_toml = out.index("cargo.toml")
    assert idx_lock < idx_toml


def test_compute_release_hash_requires_cargo_toml(tmp_path):
    (tmp_path / "rust-toolchain.toml").write_text("[toolchain]\ntargets = [\"x86_64-unknown-linux-gnu\"]\ncomponents = []")
    (tmp_path / "Cargo.lock").write_text("[[package]]\nname = \"x\"")
    with pytest.raises(FileNotFoundError, match="Cargo.toml"):
        compute_release_hash(tmp_path)


def test_compute_release_hash_requires_cargo_lock(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"x\"")
    (tmp_path / "rust-toolchain.toml").write_text("[toolchain]\ntargets = [\"x86_64-unknown-linux-gnu\"]\ncomponents = []")
    with pytest.raises(FileNotFoundError, match="Cargo.lock"):
        compute_release_hash(tmp_path)


def test_compute_release_hash_requires_rust_toolchain(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"x\"")
    (tmp_path / "Cargo.lock").write_text("[[package]]\nname = \"x\"")
    with pytest.raises(FileNotFoundError, match="rust-toolchain.toml"):
        compute_release_hash(tmp_path)


def test_compute_release_hash_returns_b1_prefix(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"demo\"\nversion = \"0.1.0\"")
    (tmp_path / "Cargo.lock").write_text("[[package]]\nname = \"demo\"")
    (tmp_path / "rust-toolchain.toml").write_text(
        "[toolchain]\nchannel = \"stable\"\ntargets = [\"x86_64-unknown-linux-gnu\"]\ncomponents = [\"rustfmt\"]"
    )
    build_id = compute_release_hash(tmp_path)
    assert build_id.startswith("b1-")
    assert len(build_id) == 3 + 64  # b1- (3) + 64 hex chars
