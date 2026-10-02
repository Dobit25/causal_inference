# Phase E v2 execution stop

Checkpoint V2 passed and the live execution was explicitly authorized. Before the first study call, the runner found a missing frozen rule: the protocol retains six Bootstrap-BOSS candidates but defines only one singular `primary_ensemble` condition. It does not specify which Bootstrap skeleton is the method-level vote, nor whether the six candidates may be unioned/intersected for that vote.

The runner therefore stopped without calling the semantic provider. Choosing C1, choosing another candidate, or inventing a union/intersection rule would be post-freeze protocol modification.

- Planned study calls: 0
- Actual study calls: 0
- Provider attempts: 0
- Oracle/holdout access: 0
- Downstream reasoner calls: 0
- Provider preflight: previously passed and remains valid.

Required next step: a small scientific amendment that freezes the deterministic construction of the single Bootstrap-BOSS method-level skeleton used by the 3/5 ensemble (or removes `primary_ensemble` from the Phase E semantic pool). After that amendment is hash-frozen, a new Phase E live authorization is required.
