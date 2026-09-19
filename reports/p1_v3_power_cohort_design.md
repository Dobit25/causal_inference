# P1-v3 prospective power and independent-cohort design

This design treats scenes—not edges—as the independent split and inference unit. Each contributing scene supplies one bounded loss: its fraction of published directions that are wrong. Directions remain nested within scenes and false-adjacency orientations count as errors. Familywise one-sided Hoeffding–Bentkus tests therefore do not pretend that edges from one scene are independent.

The total failure probability 0.05 is split prospectively: 0.025 for six semantic calibration groups and 0.025 for fifteen threshold candidates. At the minimum independent-scene counts, calibration has 0.849 power and validation has 0.872 power to certify a truly 1% error procedure against the 5% ceiling. Coverage power is 0.843 when true coverage is 30% and the required lower bound is 20%. These are design assumptions, not study findings.

The frozen successor roles are 40 method-development scenes, 400 semantic-calibration scenes and 400 one-time threshold-validation scenes. They use separate namespaces and seeds and must match the registered node, motif, noise and query-stratum margins. The old development/P1V cohorts remain historical diagnostics; the existing 80-scene final holdout remains unchanged and sealed.

Calibration may only certify reliability separately for full/partial/ambiguous × Very High/High groups. A group needs at least 280 independent contributing scenes and 560 published directions; otherwise it remains not certified. Validation needs at least 340 independent contributing scenes and 680 answered directions for a candidate, plus familywise risk ≤0.05 and coverage ≥0.20 under the registered tests. It selects maximum coverage only among safe candidates; no safe candidate stops the study before final holdout.

If all successor cohorts are later authorized, the envelope is 168,000 Bootstrap-BOSS runs and 15,120 whole-graph semantic calls. A runtime/cost pilot is mandatory before live execution. This design created no scene or scene ID manifest, ran no Bootstrap/BOSS job, made no API call, and accessed no historical cohort or final holdout.
