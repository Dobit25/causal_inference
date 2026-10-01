# P1-v3 ensemble normalization specification

This specification is an offline contract. It does not run any discovery
algorithm. Nodes are canonicalized lexicographically. Directed edges are stored
as `(source, target)` and undirected edges as sorted pairs. Self-loops,
unknown nodes, duplicate conflicting adjacencies and invalid endpoint states
fail closed. A failed parent graph is not repaired or silently projected.

GFCI is normalized only from PAG adjacency: any edge between two valid observed
nodes counts as one undirected adjacency regardless of endpoint marks. PAG
endpoint marks are never converted into CPDAG directions.
