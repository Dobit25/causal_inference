"""Command-line interface for the fourgraph package."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from fourgraph import __version__
from fourgraph.config import load_config
from fourgraph.graph_contract import GraphArtifact, VariableMap


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
    validate_graph = subparsers.add_parser(
        "validate-graph", help="Validate a canonical graph artifact and its hashes."
    )
    validate_graph.add_argument("path", help="Path to the canonical graph JSON file.")
    validate_map = subparsers.add_parser(
        "validate-variable-map",
        help="Validate a canonical variable-map artifact and its hash.",
    )
    validate_map.add_argument("path", help="Path to the variable-map JSON file.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-config":
        load_config(args.path)
        print(f"Valid config: {args.path}")
    elif args.command == "validate-graph":
        artifact = GraphArtifact.load(args.path)
        print(
            f"Valid graph: {args.path} "
            f"method={artifact.graph_method} view={artifact.graph_view} "
            f"graph_sha256={artifact.graph_sha256}"
        )
    elif args.command == "validate-variable-map":
        mapping = VariableMap.load(args.path)
        print(
            f"Valid variable map: {args.path} "
            f"mapping_sha256={mapping.mapping_sha256}"
        )

    return 0
