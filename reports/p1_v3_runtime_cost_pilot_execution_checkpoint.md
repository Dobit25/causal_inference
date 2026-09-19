# P1-v3 runtime/cost pilot execution-authorization checkpoint

OpenAI's official pricing page was checked and frozen for `gpt-5.4-nano` Standard processing: USD 0.20 per million input tokens, USD 0.02 per million cached-input tokens and USD 1.25 per million output tokens. The official model page confirms snapshot `gpt-5.4-nano-2026-03-17`.

The official organization costs endpoint requires an Admin API key. The repository environment contains only the project-scoped API key; a read-only costs request returned HTTP 403. It made no model request and consumed zero tokens. Therefore current spend/balance cannot be established from the available credential, and the checkpoint must deny pilot execution.

A separate budget-guarded semantic adapter is hash-frozen. It reserves worst-case cost before every call, requires provider usage telemetry, accounts actual token cost and fails closed at the USD 1.50 pilot cap. The guarded entrypoint rejects execution under this checkpoint before any workload starts.

Decision: `DENY_PENDING_BALANCE_VERIFICATION`. The next permissible action is a balance-attestation amendment using a current Platform Usage/Limits reading or an Admin API key kept outside Git. Pilot observations, BOSS runs, semantic calls, successor generation and holdout access remain zero/forbidden.
