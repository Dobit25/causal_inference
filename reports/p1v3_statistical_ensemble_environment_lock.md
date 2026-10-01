# P1-v3 environment lock (Phase A-B)

Verified from repository metadata:

- Tetrad implementation: `7.6.11-SNAPSHOT`
- Tetrad JAR SHA-256: `5A3BA56ADECE35DA8A209B39DB8B8BF29D4037FB79ED56C4B63F8D3B4C1A7051`
- py-tetrad commit: `092a8cf13a9b31809d4256fd9aa3c98c52b88002`
- BOSS score: `BasisFunctionBicScore`, penalty `1.0`, truncation `3`

Pending verification before live execution:

- R runtime and exact `bnlearn 5.3-20260901` package
- the activated Python 3.10.20 / Java 21.0.10 runtime pair
- the validated semantic context/token envelope for 21 pairs

The current shell could not resolve `Rscript`; this is recorded as an
environment blocker, not silently replaced with another MMPC implementation.
