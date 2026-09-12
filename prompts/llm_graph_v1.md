You are constructing one causal DAG from a public causal story.

Use only the story and variable glossary below. Identify direct causal relations, not correlations and not merely indirect ancestry. Do not add a transitive edge unless the story separately supports that direct effect. The final directed edges must form an acyclic graph.

For every unordered pair listed in PAIRS, return exactly one decision:

- `left_causes_right`: the left variable directly causes the right variable;
- `right_causes_left`: the right variable directly causes the left variable;
- `no_direct_edge`: the story does not support a direct edge between them.

Use only canonical IDs in `left` and `right`. Preserve the supplied lexicographic endpoint order. Confidence must be a finite number from 0 to 1. Give one concise evidence-based rationale per pair.

Return exactly one JSON object and no Markdown, code fence, preface, or trailing commentary. The object must contain only `schema_version` and `pair_decisions`, with `schema_version` equal to `fourgraph.llm_graph_response.v1`.

VARIABLES:
{{VARIABLES_JSON}}

PAIRS:
{{PAIRS_JSON}}

PUBLIC STORY:
{{STORY}}
