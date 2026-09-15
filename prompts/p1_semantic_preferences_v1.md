You estimate causal direction preferences using only a public synthetic-process story.

For every pair in REQUESTED_PAIRS, return exactly one probability that the public variable named `left` directly causes the public variable named `right`. Use the story's explicit directional wording as evidence. Association-only wording does not establish either direction and should normally receive probability 0.5. Do not invent indirect or unlisted relations. Treat all requested pairs jointly, but do not add, remove, or rename a pair.

Probability must be between 0.001 and 0.999. Give one concise evidence statement. Preserve the supplied endpoint spelling and order. Return exactly one JSON object, without Markdown or commentary, containing only `schema_version` and `preferences`. Set `schema_version` to `fourgraph.p1_semantic_preferences_response.v1`.

REQUESTED_PAIRS:
{{PAIRS_JSON}}

PUBLIC STORY:
{{STORY}}
