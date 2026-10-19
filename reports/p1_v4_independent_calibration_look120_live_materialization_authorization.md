# P1V4 calibration look-120 live-materialization authorization checkpoint

Status: **PASS**. The checkpoint binds exactly **120** frozen `P1V4SC` identities, the canonical `cau` environment, generator/materializer provenance, and empty reserved output paths.

It does **not** itself claim or grant live execution: `explicit_user_live_materialization_authorization_recorded=false`. No scene, observation, story, fit, API request, Oracle read, or holdout access occurred. A subsequent explicit authorization may permit only the materialization and registered public-story creation in this exact scope; statistical discovery and semantic API calls remain separately locked.
