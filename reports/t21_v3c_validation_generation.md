# T21 v3-C — Frozen validation SCM cohort

V3-C đã sinh và đóng băng một cohort validation mới, độc lập với 20 development và 80 holdout scenes hiện hữu.

- SCMs: 20/20, IDs `P1V000–P1V019`.
- Observational datasets: 20 raw + standardized pairs at N=2000.
- Tasks: 100/100; production/reference solver agreements 100/100.
- Semantic story stimuli: 60/60 across full/partial/ambiguous; generated deterministically, not by an LLM.
- Oracle CPDAG unresolved-edge minimum: 2.

SCM truth, expected answers, alias mappings and story truth remain in the ignored generated tree. Versioned manifests contain exact IDs, queries, hashes and non-semantic inventory metadata.

V3-C made zero API calls, did not run BOSS/SCD/H1/H2/reasoner, did not select a threshold, and accessed no existing development or holdout scene artifact. Only T21 v3-D validation semantic calls and the preregistered twenty-candidate gate are authorized next; the 80 final holdout scenes remain sealed.
