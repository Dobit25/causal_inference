# P1-v3 sentence-ID semantic evidence prompt v1

Use only the numbered public story. Do not use general world knowledge.

For every requested pair:

1. Return `DIRECTED` only when the story directly supports one requested public variable causing the other. Return the public names verbatim as `cause` and `effect`.
2. Return `PROCESSING_UNCERTAIN` when the story directly connects the pair but leaves direction ambiguous or contains conflicting directions. Return null `cause` and `effect`.
3. Return `NO_DIRECT_DIRECTION_EVIDENCE` when the story supplies no direct evidence for the requested pair. Return null `cause` and `effect`.
4. For `DIRECTED` or `PROCESSING_UNCERTAIN`, cite one to three unique `evidence_sentence_ids` in story order. The selected sentences may jointly provide the evidence; their combined text must mention both requested variables.
5. For `NO_DIRECT_DIRECTION_EVIDENCE`, return an empty `evidence_sentence_ids` array.

Association, indirect paths, variable order, requested-pair order and general knowledge cannot establish a direct direction. Candidate adjacency does not itself establish direction. Return every `pair_id` exactly once and only the registered JSON schema.

The six fixed query variants change inspection order or wording only. Pair IDs, pair anchors, numbered story sentences and output semantics remain invariant.
