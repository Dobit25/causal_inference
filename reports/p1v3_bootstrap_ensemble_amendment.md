# P1-v3 Bootstrap method-level ensemble amendment

**Status:** `PASS — offline checkpoint only`

This small amendment resolves the `ebe1c0f5` blocker without changing the original statistical, semantic, threshold, or holdout protocol.

## Frozen rule

Bootstrap-BOSS contributes one method-level **adjacency** skeleton to the primary ensemble:

```text
edge included iff bootstrap adjacency stability >= 0.80
```

Direction stability is ignored for this outer adjacency vote. Therefore C1/C2, C3/C4 and C5/C6 share adjacency thresholds within each pair; C3 and C4 produce the same method-level skeleton. The six C1–C6 parent conditions remain separately retained for sensitivity semantic/hybrid analysis.

The primary ensemble remains:

```text
Single-BOSS + Bootstrap-BOSS + PC + MMPC + FGES
majority >= 3 of 5
```

No union or intersection of C1–C6 is used to construct the Bootstrap method-level vote.

## Audit

- Parent manifest hash verified.
- Deterministic threshold fixture: PASS.
- Outer 3/5 fixture: PASS.
- Semantic API calls: 0.
- Statistical fits: 0.
- Oracle/holdout access: 0.

Machine-readable audit: `data/manifests/p1v3_bootstrap_ensemble_amendment_audit.json`.

This amendment is frozen at the offline checkpoint. Phase E authorization must be requested again after this commit.
