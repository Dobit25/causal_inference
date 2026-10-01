# P1-v3 shared semantic reuse specification

For each scene, the semantic universe is the union of eligible undirected
edges from Single-BOSS, all six Bootstrap-BOSS candidates and the 3/5 primary
ensemble. With at most seven observed nodes this is bounded by 21 pairs.

The whole-story, six-prompt response is cached once and reused byte-for-byte
across graph conditions. Each condition applies its own eligibility filter,
orientation selection and closure. A global closure shared between conditions
is forbidden. If the offline token preflight exceeds the validated context
envelope, execution stops and requests an amendment; automatic chunking is
forbidden.
