# P1-v3 Bootstrap-BOSS offline implementation and conformance

Implemented deterministic size-N row resampling, per-resample standardization, strict 200-run aggregation, four-state edge frequencies, thresholded stability-parent construction and fail-closed consistent-extension validation. This layer does not execute BOSS by itself; a later runner must supply one CPDAG for each registered bootstrap index.

The synthetic suite contains 60 cases across six regimes and 3–7 nodes. Production and independently structured reference aggregation agreed on 60/60 cases. Parent graphs agreed on 900/900 threshold decisions. Run-order invariance, node-input-order normalization and input immutability each passed 60/60. All 30/30 malformed fixtures failed closed, including extendable PDAGs that were not completed PDAGs.

No observational study table was loaded, Tetrad/BOSS was not started, no successor scene was generated, no semantic API was called and the final holdout remained sealed. The next authorized step is offline implementation/conformance of six-vote semantic reliability and the statistical-veto decision table; executing 200 BOSS runs on study scenes remains forbidden.
