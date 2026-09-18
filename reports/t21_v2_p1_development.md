# T21 — P1 development graph construction and threshold selection

T21 completed on 20/20 frozen development scenes. It captured 60 shared semantic-preference artifacts, materialized 160 non-Oracle graph records and evaluated 20 preregistered threshold pairs.

No threshold candidate met the preregistered 0.95 orientation-precision gate. The best candidate reached precision `0.7368421053` at coverage `0.0945273632` (14/19 evaluable orientations). No threshold was selected; the protocol requires amendment while holdout remains sealed.

Forced orientation precision was full `0.776119403`, partial `0.5970149254`, and ambiguous `0.4626865672`. H1 produced valid graphs on 9/20 scenes; H2-Forced was valid on 20/20 for every variant. Mean directed F1 was projection `0.62335148`, H2-Forced-Full `0.72645678`, standalone LLM `0.8115343`, and DirectLiNGAM `0.99372549`.

Captured token usage was 63082 input and 25168 output tokens (0 reasoning). Captured live API attempts: 80; this final resume added 0. Raw call logs remain outside Git. One earlier request was rejected by the endpoint before inference because a JSON Schema const field lacked an explicit type; it created no model response or token usage and was corrected before the first scientific response. No holdout input, downstream answer, downstream ranking or reasoner output was accessed. T22 and T23 remain unauthorized.
