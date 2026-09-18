# P1-v3 semantic empirical-reliability prompt bundle

## Shared base instruction

Use only the supplied public story and variable glossary. For every requested pair, determine whether the text supports a **direct** causal direction between the two variables. Do not infer direction from association, temporal proximity, an indirect path, variable order, or general world knowledge.

If a direct direction is absent, ambiguous, or conflicting, return `undetermined`. For a directed judgment, return the exact shortest supporting substring from the supplied story as `evidence_quote`. Do not quote or use text outside the supplied story.

Return one result for every requested pair and preserve its `pair_id`. Each result must contain only:

```text
pair_id
judgment: directed | undetermined
cause: exact public variable name | null
effect: exact public variable name | null
evidence_quote: exact story substring | null
```

The complete response must satisfy the registered strict JSON schema. Canonical labels such as `X000` are never model-visible.

## P1 — A first, direct classification

Determine the direct causal direction between `{{A}}` and `{{B}}` using only the story. If no direct direction is established, return `undetermined`.

## P2 — B first, direct classification

Determine the direct causal direction between `{{B}}` and `{{A}}` using only the story. If no direct direction is established, return `undetermined`.

## P3 — A first, evidence formulation

Does the story establish that `{{A}}` directly influences `{{B}}`, that `{{B}}` directly influences `{{A}}`, or neither? Select a direction only when the story explicitly supports that direct relation.

## P4 — B first, evidence formulation

Does the story establish that `{{B}}` directly influences `{{A}}`, that `{{A}}` directly influences `{{B}}`, or neither? Select a direction only when the story explicitly supports that direct relation.

## P5 — A first, causal-role assignment

Assign the direct causal roles for `{{A}}` and `{{B}}` from the story. Identify cause and effect only if a direct direction is established; otherwise return `undetermined`.

## P6 — B first, causal-role assignment

Assign the direct causal roles for `{{B}}` and `{{A}}` from the story. Identify cause and effect only if a direct direction is established; otherwise return `undetermined`.

## Deterministic aggregation (not shown to the model)

Code maps each valid response to `A_TO_B`, `B_TO_A`, or `UNDETERMINED`. Six votes are classified as follows:

- `very_high`: 6/6 choose the same direction, with no reverse vote.
- `high`: 5/6 choose the same direction and one is undetermined, with no reverse vote.
- `medium`: 4/6 choose the same direction and two are undetermined, with no reverse vote.
- `uncertain`: at most 3/6 choose one direction and there is no reverse vote.
- `conflict`: at least one vote occurs in each direction, regardless of the remaining votes.

Only empirically certified `very_high` and `high` groups may become automatic semantic candidates. `medium`, `uncertain`, and `conflict` remain unresolved.

