"""
keygen command: generate an Ed25519 keypair.
"""
import sys

from nacl.encoding import RawEncoder
from nacl.signing import SigningKey

from xforge.precompiled.util import hex_encode


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
