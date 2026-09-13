# T19 — Deterministic semantic-story variants and blinded audit

## Kết quả

T19 đã sinh ba story variants cho toàn bộ 100 SCM T18 mà không gọi API hay chạy bất kỳ phương pháp nghiên cứu nào.

- Public stories: 300 = 100 scenes × 3 variants.
- Alias maps: 100; mỗi map dùng một lexicon trung tính và seed độc lập với graph.
- Full directional claims: 684/684.
- Partial directional claims: 367/684; số cạnh mỗi scene dùng round-half-up.
- Ambiguous directional claims: 0/684.
- Automated truth audit: không false direction, không nonedge claim, không canonical ID/arrow/generator metadata trong story.
- Internal blinded text audit: 20/20 scenes, 60/60 evidence classifications, minimum naturalness 4/5.

## Blinding và giới hạn

Panel chỉ dùng 20 development scenes. Mỗi scene có ba slot A/B/C được shuffle; panel không chứa scene/study ID, split, variant label, canonical mapping, truth edge hay seed. Kết quả trên là internal implementation-quality review, không phải independent external human validation; giới hạn này phải được giữ khi báo cáo và nên bổ sung reviewer độc lập trước publication nếu claim mở rộng sang natural-language realism.

## Evidence boundary

Holdout stories được sinh và kiểm tra tự động theo protocol, nhưng không story holdout nào được mở trong manual panel. T19 gọi 0 API, không chạy SCD, LLM, reasoner, H1 hoặc H2, không đọc method result và không chấm holdout.

## Quyền tiếp theo

T19 chỉ cấp quyền T20 triển khai và kiểm thử H2 offline về consistent-extension constraints, global optimization và abstention. Live model calls và P1 holdout evaluation vẫn bị khóa.
