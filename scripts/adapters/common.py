from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def graph_record(nodes: list[str], directed: list[list[str]], undirected: list[list[str]], *, graph_type: str = "cpdag") -> dict[str, Any]:
    canonical_nodes = sorted(set(nodes))
    if nodes != canonical_nodes:
        raise ValueError("node universe must be sorted and unique")
    d = sorted({tuple(edge) for edge in directed})
    u = sorted({tuple(sorted(edge)) for edge in undirected})
    if any(len(edge) != 2 or edge[0] == edge[1] for edge in d + u):
        raise ValueError("self-loop or malformed edge")
    if any(edge[0] not in canonical_nodes or edge[1] not in canonical_nodes for edge in d + u):
        raise ValueError("edge references unknown node")
    return {"schema_version": "fourgraph.p1v3_normalized_statistical_graph.v1", "graph_type": graph_type, "nodes": canonical_nodes, "directed": [list(edge) for edge in d], "undirected": [list(edge) for edge in u]}

