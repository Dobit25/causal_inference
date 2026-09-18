# T21 Amendment v2 — development-only result

Semantic-preference conformance passed 120/120, but the preregistered 0.95 precision threshold gate did not pass on 20 development scenes. The best candidate achieved 0.7368421053 precision at 0.0945273632 coverage.

Standalone LLM partial directed F1: 0.703861385; ambiguous: 0.4705637255. Oracle-skeleton diagnostics are non-primary and were not used for threshold selection. An overlapping-process incident produced 18 extra successful development preference responses; the original log is retained and a deterministic first-seen rule excluded all duplicates. No holdout scene, downstream task, answer, or reasoner was accessed.
