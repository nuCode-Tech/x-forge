"""
CLI: keygen, validate-precompiled. Entry point for the xforge script.
"""
import argparse
import sys
from pathlib import Path

from nacl.encoding import RawEncoder
from nacl.signing import SigningKey

from xforge import (
    XforgeOptions,
    compute_release_hash,
    detect_host_target_triple,
)
from xforge.artifacts_provider import PrecompiledArtifactsProvider
from xforge.util import hex_encode


def main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("--help", "-h"):
        print("xforge commands: keygen, validate-precompiled")
        print("Run with --help for command options.")
        sys.exit(0 if argv and argv[0] in ("--help", "-h") else 2)

    parser = argparse.ArgumentParser(
        prog="xforge",
        description="xforge-python CLI: keygen, validate-precompiled",
    )
    parser.add_argument(
        "command",
        choices=["keygen", "validate-precompiled"],
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
    parser.print_help()
    sys.exit(2)


def run_keygen(rest: list[str]) -> int:
    if rest and rest != ["--help"] and rest != ["-h"]:
        print("Unknown arguments: " + " ".join(rest), file=sys.stderr)
        _print_keygen_usage()
        return 2
    if rest and rest[0] in ("--help", "-h"):
        _print_keygen_usage()
        return 0

    signing_key = SigningKey.generate()
    seed = signing_key.encode(encoder=RawEncoder)
    verify_key = signing_key.verify_key
    public = verify_key.encode(encoder=RawEncoder)
    # xforge expects private_key = seed (32) + public (32)
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


def _print_keygen_usage() -> None:
    print("Usage: xforge keygen")
    print("Outputs:")
    print("  public_key=<32-byte hex>")
    print("  private_key=<64-byte hex (seed + public)>")


def run_validate_precompiled(rest: list[str]) -> int:
    p = argparse.ArgumentParser(prog="xforge validate-precompiled")
    p.add_argument(
        "--crate-dir",
        default=None,
        help="Crate directory (default: cwd)",
    )
    p.add_argument(
        "--build-id",
        default=None,
        help="Build id override",
    )
    p.add_argument(
        "--target",
        default=None,
        help="Rust target triple (default: host)",
    )
    parsed, _ = p.parse_known_args(rest)

    crate_dir = Path(parsed.crate_dir) if parsed.crate_dir else Path.cwd()

    options = XforgeOptions.load(crate_dir)
    config = options.precompiled_binaries
    if config is None:
        print("xforge.yaml is missing precompiled_binaries config.", file=sys.stderr)
        return 2

    build_id = parsed.build_id or compute_release_hash(crate_dir)
    target = parsed.target or detect_host_target_triple()

    provider = PrecompiledArtifactsProvider(
        crate_dir=crate_dir,
        config=config,
    )

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
