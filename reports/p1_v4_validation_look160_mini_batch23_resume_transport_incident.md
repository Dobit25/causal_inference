# P1V4 validation look-160 Mini: second transport incident

The separately authorized retry of `P1V4SV303/ambiguous/P5` succeeded. The runner then recorded 212 additional calls before `P1V4SV475/ambiguous/P2` remained in transport without a response, request ID, or provider usage.

The client had a 180-second timeout configuration, but it did not return control before the process was stopped after an extended no-output interval. No additional retry was made because the sole retry authorization had already been consumed by the first incident.

The cache now contains 877/2,640 immutable responses. This resume segment contributed 311,856 provider-reported tokens; the raw cache, metadata, and ledger hashes are recorded in the partial execution audit. Oracle, holdout, closure, and metrics remain untouched.

Before another resume, the protocol requires an explicit user decision for the second call and, if desired, a separately frozen external transport-watchdog mechanism. No pending response should be silently replaced.
