You construct one causal DAG using only a public synthetic-process story.

For every unordered pair in PAIRS, decide whether the story explicitly supports a direct causal relation. Directional wording supports the stated direction. Association-only wording establishes adjacency but not direction; for this forced standalone-DAG condition, choose the lexicographically earlier public name as the source and mark confidence 0.5. Do not add an edge for an unlisted pair and do not add transitive edges unless directly stated. The complete set of selected directions must be acyclic.

For every pair return exactly one of `left_causes_right`, `right_causes_left`, or `no_direct_edge`. Preserve endpoint spelling/order. Confidence must be between 0 and 1 and rationale must be concise. Return exactly one JSON object without Markdown or commentary, containing only `schema_version` and `pair_decisions`. Set `schema_version` to `fourgraph.p1_llm_graph_response.v1`.

PAIRS:
{{PAIRS_JSON}}

PUBLIC STORY:
{{STORY}}
