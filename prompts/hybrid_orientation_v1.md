You are orienting only the unresolved edges of one causal CPDAG.

The CPDAG skeleton and every compelled direction are fixed by statistical causal discovery. Use only the public causal story and variable glossary to choose a direction for each edge listed in UNRESOLVED_EDGES. You must not add or remove an adjacency, reverse a compelled direction, or use an edge not listed there.

Choose the directions jointly. Together with COMPELLED_EDGES, the final graph must be acyclic and must remain a consistent extension of the supplied CPDAG: do not create a new unshielded collider that is absent from the CPDAG. Prefer the direction directly supported by the story. The rationale must cite concise semantic evidence; it must not claim statistical, task, answer, or oracle evidence.

For every pair in UNRESOLVED_EDGES, return exactly one decision:

- `left_causes_right`: the left variable directly causes the right variable;
- `right_causes_left`: the right variable directly causes the left variable.

Use only canonical IDs in `left` and `right`, preserving the supplied lexicographic order. Confidence must be a finite number from 0 to 1.

Return exactly one JSON object and no Markdown, code fence, preface, or trailing commentary. The object must contain only `schema_version` and `orientation_decisions`, with `schema_version` equal to `fourgraph.hybrid_orientation_response.v1`.

VARIABLES:
{{VARIABLES_JSON}}

COMPELLED_EDGES:
{{COMPELLED_EDGES_JSON}}

UNRESOLVED_EDGES:
{{UNRESOLVED_EDGES_JSON}}

PUBLIC STORY:
{{STORY}}
