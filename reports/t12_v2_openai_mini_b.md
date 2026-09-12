# T12 v2 GPT-5.4 Mini-B: high reasoning với 8192 tokens

## Thiết kế chẩn đoán

Mini-B là candidate mới, không ghi đè lần 4096. Model snapshot, provider, `reasoning_effort=high`, prompt v2, graph encoding, variable labels, năm task-specific schemas, 150-case suite, strict scorer, smoke IDs và evidence boundary đều giữ nguyên. Thay đổi thực nghiệm duy nhất là:

```yaml
max_output_tokens: 4096 -> 8192
```

Raw/cache dùng namespace riêng dưới ignored `results/raw/t12_v2_openai_mini_b/`. Không có story, semantic names, provenance, gold answer hoặc holdout data đi vào request.

## Kết quả smoke

- 10/10 cases completed và parse được ở attempt đầu.
- 10 captured calls, 0 retry.
- Đúng model snapshot; usage/reasoning telemetry đầy đủ; holdout không được truy cập.
- `smoke_technical_passed: true`.
- Captured usage: 5,918 input tokens; 31,743 output tokens, trong đó 31,509 reasoning tokens.
- Chi phí standard ước tính: USD 0.147282.
- Reasoning tokens: min 447, median 2,396, max 7,937.
- Latency: min 3,395 ms, median 14,247.5 ms, max 42,404 ms.

Case chẩn đoán `SYN024`, từng cạn 4096 ở ba attempts, đã completed đúng với `{"adjust":"undetermined"}` sau 5,414 reasoning tokens. Điều này trực tiếp ủng hộ nguyên nhân token ceiling cho failure trước.

Tuy nhiên `SYN144` dùng 7,937 reasoning tokens và 7,960 total output tokens, rất gần trần 8,192. Vì vậy 8,192 đủ cho smoke lần này nhưng headroom vẫn mỏng và không bảo đảm mọi call sẽ ổn định.

## Accuracy diagnostic

Smoke đạt 9/10 strict-correct, nhưng accuracy này không phải scientific gate vì mẫu chỉ có hai cases mỗi task. Case sai là `SYN092`, task đếm số valid adjustment sets: model trả `{"n":2}` trong khi released CausalDS convention yêu cầu `no_backdoor`, do không candidate set nào chặn được path từ treatment về outcome. Đây là tín hiệu cần theo dõi ở full conformance, không phải lý do để sửa prompt giữa hai candidate.

## Quyết định

Mini-B vượt engineering smoke, nên đủ điều kiện kỹ thuật để được cân nhắc cho 150-case conformance. Theo thiết kế đã đăng ký, runner dừng tại đây để kiểm tra Usage và nhận quyết định riêng trước khi phát sinh chi phí lớn hơn. Không chạy 150 cases, Oracle-development, full development matrix hoặc holdout trong bước này.

Nếu 150-case run được phê duyệt, upper bound trước retry theo config là khoảng USD 5.61. Ngoại suy thô từ smoke là khoảng USD 2.21 cho 150 calls không retry, nhưng không phải cost guarantee.

## Reproducibility

```powershell
conda run -n cau python scripts/run_t12_v2_openai_mini.py --config configs/t12_v2_openai_mini_b.yaml --smoke --check
conda run -n cau python -m pytest
```

Tracked smoke-audit SHA-256: `08325DEFF0A3AA1B4C82298192EC0B58DC1C791F26C2FEA50E88811E0D8B5B49`.
