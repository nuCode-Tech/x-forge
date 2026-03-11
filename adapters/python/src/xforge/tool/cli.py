"""
CLI dispatcher: keygen, validate-precompiled, generate-loader.
Entry point for the xforge script.
"""
import argparse
import sys

from xforge.tool.commands.keygen import run_keygen
from xforge.tool.commands.validate_precompiled import run_validate_precompiled
from xforge.tool.commands.generate_loader import run_generate_loader


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
