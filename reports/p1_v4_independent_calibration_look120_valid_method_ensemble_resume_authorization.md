# Valid-method ensemble resume authorization checkpoint

The frozen Phase-D plan contains 24,720 identities. The stopped run already
has 2,037 terminal raw/normalized artifact pairs; exactly 22,683
identities remain. This checkpoint permits no execution by itself.

If and only if explicit live authorization is recorded, the runner may execute the
exact missing list at concurrency one. Cached terminal identities are never rerun.
The historical PC error artifact is retained as incident evidence; the amended runner
will record any new invalid graph as `INVALID_NO_VOTE` rather than repairing it.
