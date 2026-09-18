You estimate the direction of a direct causal relation using only the public synthetic-process story.

For every pair in REQUESTED_PAIRS, return the probability that the variable written as `left` directly causes the variable written as `right`.

Apply this mapping exactly:

1. If the story states that `left` directly influences `right`, return a probability close to 1 (use 0.999 when the statement is explicit).
2. If the story states that `right` directly influences `left`, return a probability close to 0 (use 0.001 when the reverse statement is explicit). A reverse-direction statement is evidence against `left` causing `right`; it is not missing evidence.
3. If the story establishes only a direct association/connection and explicitly does not establish direction, return exactly 0.5.
4. If the story says that an unlisted pair has no direct connection, do not use indirect paths to invent a direct relation.

Examples:

- Requested pair `{left: "Amber index", right: "Beryl index"}` and story “Amber index directly influences Beryl index” → `probability_left_causes_right: 0.999`.
- The same requested pair and story “Beryl index directly influences Amber index” → `probability_left_causes_right: 0.001`.
- The same requested pair and story “Amber index and Beryl index are directly connected, but direction is not established” → `probability_left_causes_right: 0.5`.

Do not add, remove, reorder, or rename requested pairs. Probability must be within [0.001, 0.999]. Give one concise evidence statement. Return exactly one JSON object without Markdown or commentary, containing only `schema_version` and `preferences`. Set `schema_version` to `fourgraph.p1_semantic_preferences_response.v1`.

REQUESTED_PAIRS:
{{PAIRS_JSON}}

PUBLIC STORY:
{{STORY}}
