"""Command-line interface for the fourgraph package."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from fourgraph import __version__
from fourgraph.config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fourgraph",
        description="Run controlled four-graph causal reasoning experiments.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    subparsers = parser.add_subparsers(dest="command")
    validate = subparsers.add_parser(
        "validate-config", help="Validate that a YAML experiment config can be loaded."
    )
    validate.add_argument("path", help="Path to the YAML config file.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-config":
        load_config(args.path)
        print(f"Valid config: {args.path}")

    return 0

