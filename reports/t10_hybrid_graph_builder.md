# T10 — Hybrid H1 development graph builder

## Outcome

T10 is complete on the eight frozen graph-development scenes. It produced 8/8 canonical `G_HYBRID` DAGs and audited all 27 unresolved T09 CPDAG edges. Holdout, observational tables, T08 `G_LLM` artifacts, T09 projected DAGs, tasks, answers, grading, and Oracle data were not accessed.

## Frozen H1 intervention

Each scene begins with its raw T09 CPDAG. The Hybrid builder keeps its node set, skeleton, and compelled directions fixed. The semantic LLM sees only that CPDAG structure, the public story, and the public variable glossary/schema types; it returns one direction, confidence, and rationale for every unresolved edge. It cannot return `no_edge`.

The semantic transport exactly reuses T08's OpenAI configuration: Responses API, immutable snapshot `gpt-5.4-nano-2026-03-17`, SDK `3.6.0`, `reasoning_effort=none`, `temperature=0`, `service_tier=default`, `store=false`, strict JSON Schema, 6,000 maximum output tokens, null seed, two transport retries, and at most two validation retries.

The builder never consumes the T08 graph. Reusing the semantic model means reusing its model/configuration, not merging or voting with `G_LLM`.

## Validation

Every output is validated by the T06 parent-child contract:

- same scene and canonical node universe;
- exact parent artifact hash;
- unchanged skeleton;
- unchanged compelled directions;
- acyclic final DAG;
- no incompatible new unshielded collider;
- membership in the parent CPDAG's Markov equivalence class;
- exactly one non-arbitrary semantic audit record per unresolved edge.

Invalid model output triggers a complete-response retry with the validator error. There is no heuristic repair and no deterministic projected-DAG fallback.

## Live execution and reproducibility

The hardest development scene, `scene_000511`, was run first because it has nine unresolved edges. It passed in one call. Resume mode replayed that call and made exactly seven additional calls for the remaining development scenes.

Final results:

- scenes: 8/8;
- unresolved edges oriented and audited: 27/27;
- live API calls: 8;
- validation retries: 0;
- input tokens: 7,350;
- output tokens: 1,857;
- skeleton changes: 0;
- compelled-direction changes: 0;
- valid parent hashes/equivalence classes: 8/8;
- holdout scenes accessed: 0/25.

The raw log is ignored at `results/raw/t10_hybrid/gpt-5.4-nano-2026-03-17_dev.jsonl`. Replaying it regenerates both versioned T10 artifacts byte-for-byte:

```powershell
conda run -n cau python scripts/audit_causalds_t10.py <extracted-causalds-source-root> --replay-log results/raw/t10_hybrid/gpt-5.4-nano-2026-03-17_dev.jsonl
conda run -n cau python scripts/audit_causalds_t10.py <extracted-causalds-source-root> --replay-log results/raw/t10_hybrid/gpt-5.4-nano-2026-03-17_dev.jsonl --check
```

Freeze hashes:

- config: `EE6ABDF6C4819F19570BAA01F10C4F459D7CB72022F6522974E1F504F7B13A93`;
- raw replay log: `07E597FE5C772C32D8D3B5263C816A0DF5CA9F7565C788819C82FC9BE654AA68`;
- development Hybrid graph set: `BD16C234E6B1B6AA261FA505E5F357C5160D61AB0768515C5116577AA0ADF18A`.

T10 establishes construction readiness, not graph accuracy. Oracle-based structural evaluation belongs to T11; downstream reasoning belongs to T12; holdout graph generation remains deferred to T14.
