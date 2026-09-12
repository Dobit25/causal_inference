# T12 v2 GPT-5.4 Mini candidate audit

## Mục tiêu

Nhánh này thay đúng một yếu tố của lần kiểm tra Gemma: model/provider. Prompt `reasoner_cpdag_conservative_v2`, canonical JSON edge list, nhãn `X000...`, năm schema theo task, 150 synthetic cases, strict scorer và các ngưỡng prospective đều được giữ nguyên. Không story, semantic name, gold answer hoặc graph provenance nào được đưa vào model.

Candidate được khóa ở `gpt-5.4-mini-2026-03-17`, Responses API, `reasoning_effort=high`, `max_output_tokens=4096`, `service_tier=default`, `store=false`, OpenAI SDK 3.6.0. Temperature không được gửi.

## Measurement audit không tốn API

Một solver độc lập dùng active-simple-path d-separation và exhaustive CPDAG orientation đã tái tạo đúng 150/150 targets của generator. Panel 20 cases gồm bốn strata cho từng task: DAG có/không có `no_backdoor`, CPDAG invariant và CPDAG undetermined. Các giá trị `[]`, `[[]]`, `0`, `no_backdoor` và `undetermined` được giữ khác nhau. Semantic-equivalent scorer chỉ là diagnostic; strict scorer vẫn là primary.

## Engineering preflight

OpenAI strict Structured Outputs từ chối `oneOf` và `uniqueItems`. Adapter chỉ chuyển schema gửi provider sang tập con tương đương (`oneOf` thành `anyOf`; bỏ các validation-only keyword không được hỗ trợ), sau đó vẫn dùng nguyên strict local parser để kiểm ID, uniqueness và số không âm. Hai lỗi HTTP 400 này xảy ra trước model inference.

Một preflight sau đó hoàn tất `SYN001`, nhưng backend cũ dừng khi `SYN024` trả `incomplete`. Raw/cache của preflight được bảo tồn riêng dưới ignored `results/raw/t12_v2_openai_mini/preflight_*`. Response incomplete này xảy ra trước khi logger được sửa nên không truy hồi được request ID; đây không phải một phần của official smoke audit.

## Official smoke và verdict

Official smoke dừng sau bốn captured calls:

- `SYN001`: completed, parse được và strict-correct.
- `SYN024`: cả ba attempts đều `incomplete/max_output_tokens`.
- Mỗi attempt lỗi dùng đúng 4096 output tokens, toàn bộ là reasoning tokens, và tạo 0 ký tự visible output.
- Captured usage: 2,484 input tokens; 12,718 output tokens, trong đó 12,694 reasoning tokens.
- Chi phí standard ước tính cho bốn captured calls: USD 0.059094. OpenAI Usage là nguồn quyết toán chính thức; preflight nằm ngoài con số này.
- Snapshot, usage logging, reasoning-token logging, cache/resume và chặn holdout đều hoạt động.

`smoke_technical_passed: false`. Vì vậy không chạy đủ 150 cases, không chạy 35 Oracle-development calls, không chạy ma trận development 175 records và không truy cập holdout. Kết quả này chưa đo được accuracy/capability của Mini; nó bác bỏ riêng cấu hình candidate `high + 4096` như một measurement instrument khả dụng.

Muốn tiếp tục phải đăng ký một candidate mới và chỉ đổi một yếu tố, chẳng hạn tăng output/reasoning budget hoặc giảm reasoning effort. Không được âm thầm sửa candidate hiện tại hay tự động chuyển sang GPT-5.4 tiêu chuẩn.

## Reproducibility

```powershell
conda run -n cau python scripts/audit_t12_v2_measurement.py --check
conda run -n cau python scripts/build_t12_v2_conformance.py --check
conda run -n cau python scripts/run_t12_v2_openai_mini.py --smoke --check
conda run -n cau python -m pytest
```

Tracked smoke-audit SHA-256: `A7204E59C4B8865840124F1F83682656C40BBA7E05FB03198C9DB534BCB1A125`.
