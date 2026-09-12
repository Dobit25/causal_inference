# T12 v2 GPT-5.4 Mini-C: high reasoning với 10240 tokens

## Thiết kế

Mini-C giữ nguyên model snapshot, provider, high reasoning effort, prompt v2, graph/query/glossary contract, năm response schemas, 150-case suite, 10 smoke IDs, strict scorer và retry policy của Mini-B. Thay đổi runtime duy nhất là `max_output_tokens: 8192 -> 10240`. Một headroom gate mới được đăng ký trước live run:

```yaml
max_output_token_utilization_max: 0.80
```

Gate được tính trên mọi billed provider call, bao gồm cả attempts incomplete bị thay thế bởi retry. Raw/cache nằm trong namespace Mini-C riêng ngoài Git.

## Kết quả

- 10/10 cases cuối cùng completed và parse được.
- 11 captured calls: 10 initial attempts và một retry.
- `SYN054` attempt 0: `incomplete/max_output_tokens`, 10240/10240 reasoning tokens, zero visible output.
- `SYN054` attempt 1: completed với 3324 reasoning tokens và đáp án đúng.
- Maximum output-token utilization trên mọi call: 1.00, vượt gate 0.80.
- `smoke_technical_passed: false` do headroom gate.
- Accepted-response reasoning min/median/max: 376/2591.5/4660; all-call maximum là 10240.
- Estimated captured cost: USD 0.1674885.
- Holdout không được truy cập.

Kết quả cho thấy tăng ceiling không bảo đảm model sẽ dừng reasoning sớm hơn. Cùng một case và cấu hình, attempt đầu dùng hết 10240 tokens nhưng retry chỉ dùng 3324 tokens. Đây là bằng chứng trực tiếp về run-to-run variability và lý do không được che incomplete attempt khi tính headroom.

## Accuracy diagnostic

Strict accuracy là 8/10, không phải scientific gate. Hai lỗi:

- `SYN024`: trả `{"adjust":"no_backdoor"}` thay vì `undetermined`; Mini-B từng trả đúng cùng case.
- `SYN092`: tiếp tục trả `{"n":2}` thay vì official `no_backdoor` convention.

Sự thay đổi của `SYN024` giữa Mini-B và Mini-C củng cố nhu cầu cache theo toàn bộ canonical input/config và không diễn giải smoke accuracy như ranking model.

## Verdict

Mini-C hoàn tất về implementation nhưng không đủ điều kiện chạy 150-case conformance theo headroom gate đã đăng ký. Không chạy Oracle-development, full development matrix hoặc holdout. Không nên tiếp tục tăng token ceiling vô hạn: candidate tiếp theo cần kiểm tra một giả thuyết khác, ưu tiên `reasoning_effort=medium` với ceiling hữu hạn hoặc một prompt v3 được version hóa và đánh giá trên sealed synthetic set.

## Reproducibility

```powershell
conda run -n cau python scripts/run_t12_v2_openai_mini.py --config configs/t12_v2_openai_mini_c.yaml --smoke --check
conda run -n cau python -m pytest
```

Tracked audit SHA-256: `CCDD368C73CD10839FBAA4412D6495372BAFDEE3DA33810EA92E574CADE02F72`.
