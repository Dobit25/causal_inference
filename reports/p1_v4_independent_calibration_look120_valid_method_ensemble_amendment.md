# Valid-method ensemble amendment — calibration look 120

This post-incident technical amendment preserves all five registered ensemble
methods while making invalid-output handling symmetric. A graph that is parsed
and persisted but fails its registered graph contract is `INVALID_NO_VOTE`; it
is neither repaired nor treated as an absence vote.

- five valid methods: retain adjacencies with at least 3/5 votes;
- exactly one invalid method: retain adjacencies with at least 3/4 votes;
- two or more invalid methods: fail closed for the scene.

Bootstrap-BOSS is valid only when all 200 registered bootstrap runs are valid.
Runtime/adapter failures remain execution-stopping errors. The amendment itself
executes no fit and authorizes no resume, API, Oracle, or holdout access.
