# P1-v3 semantic reliability and statistical-veto offline conformance

Implemented strict whole-graph response parsing, exact-story directional-quote validation, deterministic normalization, six-vote agreement classes, empirical-reliability group records and the frozen statistical-veto decision table.

The suite contains 90 synthetic whole-graph cases and 180 edge records. Production classifications agreed with an independent reference on 180/180 edges. Across the six prompts, the validator accepted 810 exact directional quotes and 270 correctly null evidence fields; 48/48 malformed responses failed closed. Nine reliability groups reproduced expected correct/total counts, included false adjacencies as errors and remained `pending_risk_control`; diagnostic point estimates never self-certified a group. The production/reference veto table agreed on 36/36 cases.

No model/API call, Bootstrap/BOSS run, study observation, historical cohort, successor scene, Oracle loader or final holdout was accessed. The next authorized step is prospective power and cohort design; study execution remains forbidden.
