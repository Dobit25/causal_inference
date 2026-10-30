# P1V4 validation Mini: watchdog retry and resume authorization

Status: **PASS_WATCHDOG_RETRY_AND_RESUME_AUTHORIZATION**. The user authorized one retry of `P1V4SV475/ambiguous/P2` and continuation of the 562 remaining IDs in the original batch-2/3 scope. Each request uses a separate worker with a 120-second SDK attempt timeout and a 210-second parent deadline. On any future deadline, the worker is terminated, a provider-error record is written, and no retry occurs automatically.
