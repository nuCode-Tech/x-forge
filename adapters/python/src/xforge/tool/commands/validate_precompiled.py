"""
validate-precompiled command: download and verify manifest + artifact.
"""
import argparse
import sys
from pathlib import Path

from xforge.precompiled.artifacts_provider import PrecompiledArtifactsProvider
from xforge.precompiled.crate_hash import compute_release_hash
from xforge.precompiled.options import XforgeOptions
from xforge.precompiled.target import detect_host_target_triple


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
