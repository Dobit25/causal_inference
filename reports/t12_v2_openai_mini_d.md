# T12 v2 GPT-5.4 Mini-D: medium reasoning với 10240 tokens

## Thiết kế đối chứng

Mini-D kiểm tra giả thuyết `reasoning_effort=high` góp phần gây reasoning runaway. Đây là đối chứng một biến với Mini-C: giữ nguyên snapshot `gpt-5.4-mini-2026-03-17`, prompt v2, graph/query/glossary contract, schemas, strict scorer, retry policy và `max_output_tokens=10240`; chỉ đổi effort từ `high` sang `medium`.

Headroom gate đăng ký trước vẫn là maximum output-token utilization không quá 0.80 trên mọi provider call, kể cả retry. Raw prompt/response và cache nằm trong namespace Mini-D riêng ngoài Git. Cache identity chứa reasoning effort nên không thể tái sử dụng nhầm response của Mini-C.

## Kết quả smoke

- 10/10 cases completed và parsed ở attempt đầu; không retry hoặc incomplete.
- Maximum utilization: 3713/10240 = 0.36259766, qua gate 0.80.
- Reasoning-token min/median/max: 286/1248.5/3689.
- Tổng reasoning tokens: 16999; estimated cost: USD 0.082014.
- Strict accuracy 7/10, chỉ mang tính diagnostic.

So với Mini-C `high + 10240`, Mini-D dùng ít hơn khoảng 52.6% reasoning tokens, không còn call 10240/10240 và không cần retry. Đây là bằng chứng có kiểm soát phù hợp với giả thuyết high effort gây runaway trong lượt smoke đã quan sát, nhưng không chứng minh high luôn gây runaway vì API có tính biến thiên.

## Kết quả 150-case conformance

Sau quyết định GO riêng, Mini-D được resume trên nguyên suite mà không thay prompt hoặc contract:

- 150/150 responses completed, parsed và đúng schema ngay attempt đầu; 0 retry, 0 incomplete.
- Strict accuracy: 105/150 = 0.700; semantic-equivalent diagnostic cũng 0.700.
- DAG answered: 42/75 = 0.560.
- CPDAG answered/invariant: 37/40 = 0.925.
- CPDAG undetermined: 26/35 = 0.7429.
- Theo task: one-valid 26/30; all-minimal 25/30; minimal-size 24/30; count-valid 23/30; forbidden-controls 7/30.
- Maximum utilization: 5168/10240 = 0.5046875, qua headroom gate 0.80.
- Reasoning-token min/median/max: 117/369/5146; latency min/median/max: 1566/3627/31129 ms.
- Tổng usage: 83400 input tokens, 107391 output tokens, gồm 103855 reasoning tokens; estimated cost USD 0.5458095.

Mini-D chỉ qua các gate parse success, first-attempt schema compliance và CPDAG-answered accuracy. Nó trượt overall accuracy, DAG accuracy, CPDAG-undetermined accuracy và per-task gate. Lỗi lớn nhất là `forbidden_controls_list` với 23/30 sai; đây là systematic task-semantics failure, không phải format failure.

## Verdict

Mini-D qua engineering/headroom gate nhưng không qua scientific conformance gate. Vì vậy `causalds_oracle_development_eligible: false`: không chạy 35 Oracle-development tasks, full development matrix hoặc holdout. Medium đã xử lý runaway/truncation nhưng chưa đạt semantic reliability. Bước kế tiếp phải là candidate/prompt version mới được đăng ký trước, không điều chỉnh Mini-D sau khi xem kết quả.

## Reproducibility

```powershell
conda run -n cau python scripts/run_t12_v2_openai_mini.py --config configs/t12_v2_openai_mini_d.yaml --smoke --check
conda run -n cau python scripts/run_t12_v2_openai_mini.py --config configs/t12_v2_openai_mini_d.yaml --check
conda run -n cau python -m pytest
```

Smoke audit SHA-256: `5D0B2750E758248C0A379ED675AF93E590A9A41F9FDEF395B00AADED46E93A12`.

Conformance records SHA-256: `DD0F3D5604CA682C44939BF63C6FA4DD1013970459319C106977146264B62E62`.

Conformance audit SHA-256: `FCDF82156F88AE355D6A50E6C60C888FCC88BE70DCD7E8C09FC332E02F4C770A`.
