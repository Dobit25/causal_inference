# Isolated PC replay amendment

This amendment freezes exactly one forensic PC replay for `P1V4SC307`. It uses the
original frozen PC configuration and data. The replay runner writes the parsed graph
before calling the CPDAG validator, so it can distinguish an invalid Tetrad/PC graph
from a parser/validator disagreement.

This checkpoint is **not** live authorization. It permits no statistical execution,
semantic API call, Oracle/holdout access, or Phase-D resume. A separate explicit
authorization is required to invoke `--execute`.
