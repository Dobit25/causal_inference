# P1V4 canonical `cau` transition — completion record

## Decision

`cau` is the sole authorized runtime for P1V4 from the environment-correction
amendment onward. The previous `p1v3_py31020` Stage-3D result is retained as a
historical technical artifact and is not overwritten.

This transition changes no scientific parameter: cohort identities, SCM
generator, observational sample size, algorithms, Bootstrap repetitions,
thresholds, semantic model, prompt and schema are unchanged. It grants no
provider/API, Oracle or holdout access.

## Frozen runtime

- Python `3.10.21`: `D:/Coding/Anaconda/envs/cau/python.exe`
- OpenAI SDK `3.6.0`; `jiter 0.16.0`
- Java `21.0.10`; R `4.4.3`; bnlearn `5.3-20260901`
- Tetrad JAR SHA-256: `5A3BA56ADECE35DA8A209B39DB8B8BF29D4037FB79ED56C4B63F8D3B4C1A7051`
- Complete Python package lock: `configs/p1_v4_cau_environment.lock`

Environment amendment: `1DD68013E7EF9149B004081E98B41280EE2B08F79B6121609E20420413D1F642`.

## Official statistical rerun

The `cau` namespace contains the official Stage-3D statistical layer:

| Algorithm | Fits |
|---|---:|
| Single-BOSS | 30 |
| Bootstrap-BOSS | 6,000 |
| PC | 30 |
| MMPC | 30 |
| FGES | 30 |
| Constrained-BOSS | 30 |
| Constrained-FGES | 30 |
| **Total** | **6,180** |

The audit reports 6,180 planned, raw and normalized artifacts; 30 ensemble
aggregates; and zero error artifacts. Audit replay is byte-stable.

## Deterministic comparison with the retained historical run

For all 6,180 `(scene, algorithm, repetition)` records:

- input observation-hash mismatches: `0`;
- normalized graph mismatches: `0`.

The historical run is retained only for provenance. The distinct `cau` output
namespace is the artifact eligible for later P1V4 semantic work.

## Boundary

Semantic API calls: `0`; provider preflight: not run; Oracle access: `0`;
holdout access: `0`. The next step, if separately authorized, is a new provider
preflight using the canonical `cau` runtime and the frozen P1V4 semantic
contract.

## Hashes

- authorization: `DEBAC95D316F62437205827AD97193E517C6FA530228D7C3493286D9AEB5137F`
- execution config: `FD65009807B47A4217A6CF9C040B4585A0C8373F104EA04F2C5471CF02D26CEE`
- execution plan: `B32E7B212A6675409D89E33C1FB5356051575DE72300D6B4186137382CACDF4A`
- execution audit: `43FFA32C0BED1DDD0531B5ED8F62C6F192890456699BE547AB976E1192BB66ED`
