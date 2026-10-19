# Isolated PC replay — execution audit

The captured parsed PC graph has one undirected edge, `X002 -- X003`. Exhaustive
checking gives two possible orientations:

- `X002 → X003` forms the directed cycle `X003 → X000 → X001 → X002 → X003`.
- `X003 → X002` introduces the unshielded collider `X001 → X002 ← X003`.

Thus the captured parsed PC output has no consistent DAG extension. The frozen
validator rejection is mathematically supported by the captured graph; there is no
evidence of a validator-only error. This does not change PC parameters or repair
the graph. Phase D remains suspended until a separate registered handling policy
for invalid PC outputs is approved.
