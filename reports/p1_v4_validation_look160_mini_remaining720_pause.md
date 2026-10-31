# P1V4 look-160 Mini remaining-720 pause

Status: **PAUSED_BY_USER_BEFORE_SCOPE_COMPLETION**.

The runner was interrupted safely at the user's request. It recorded 307 of the authorized 720 new logical calls, leaving 413 authorized IDs pending. The raw cache is preserved; no response was deleted or rewritten. Because the runner was interrupted before finalization, no completion audit was written.

New-slice status:

- `completed_valid`: 268
- `completed_pair_invalid`: 33
- `provider_error`: 6

No Oracle, holdout, response freeze, re-score, closure, or metric calculation occurred. Resumption requires explicit authorization and must use cache/idempotency.
