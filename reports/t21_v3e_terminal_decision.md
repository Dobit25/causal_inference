# T21 v3-E — Terminal stop/freeze decision

T21 v3-E closes P1-v2 without opening the final holdout. The preregistered validation gate failed: the best candidate correctly oriented 83/97 answered edges (`0.8557` precision) at `0.4554` coverage, below the required `0.95` precision.

No threshold was selected. The selected-graph manifest remains empty, T22 is unauthorized, and the existing 80-scene final holdout remains sealed. The validation result is retained as a negative result; its gate will not be lowered and the same validation cohort will not be retuned.

This closure made zero API calls and accessed no downstream task answer or final-holdout method result. It hash-pins 70 versioned T21 v2/v3 artifacts without modifying them.

The only authorized successor action is design-only work for `P1-v3 Evidence-Selective Hybrid`. The user-frozen starting decisions are GPT-5.4 Nano, whole-graph semantic calls, Bootstrap-BOSS as the primary statistical method, and deferral of the multi-algorithm ensemble to a later robustness study. Bootstrap execution, semantic API calls, new cohort generation and final-holdout access remain unauthorized until that successor protocol is independently frozen.
