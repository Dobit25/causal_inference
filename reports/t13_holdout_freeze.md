# T13 — Đóng băng cấu hình thực thi holdout P0

## Kết luận

T13 hoàn thành hoàn toàn offline. Cấu hình T14 đã được khóa cho đúng 25 graph-holdout scenes, gồm 20 primary scenes và 5 supplementary scenes. Không API call nào được thực hiện, không file nội dung holdout nào được đọc, không gold answer hay Oracle edge nào được mở, và không accuracy nào được tính.

`t14_authorized: true` chỉ có nghĩa T14 được phép bắt đầu theo manifest đã đóng băng; T14 chưa tự động chạy.

## Những gì đã khóa

- Primary: 20 scenes × 5 task cố định = 100 query và 500 downstream records trên 5 graph conditions.
- Supplementary: 5 scenes và 77 task rows được lưu thành inventory exploratory; không chạy bằng fixed five-task reasoner và không gộp vào primary accuracy.
- Graph cohort: 25 scenes × 5 graph conditions = 125 structural metric records. Bốn graph phi-Oracle tạo 100 persisted artifacts; 25 Oracle DAG chỉ được load trong memory lúc grading.
- Builder: GPT-5.4 Nano snapshot/config của T08; BOSS + BasisFunctionBicScore và deterministic projection của T09; H1 semantic orientation của T10.
- Reasoner: GPT-5.4 Mini snapshot, medium reasoning, 10,240 output-token ceiling, prompt v3, five strict schemas và conservative CPDAG semantics.
- Canonical graph contract, mapping `X000...`, parser, hai scorers, retry/cache/resume/failure policy, output paths, execution order, metrics và paired scene-clustered/BH analysis.

Review trước checkpoint khóa thêm các chi tiết dễ tạo researcher degrees of freedom: thứ tự gọi deterministic với seed `13014`, bootstrap percentile 95% gồm 5.000 lần với seed `13015`, tất cả 10 cặp graph-condition, kiểm định hai phía và BH `alpha=0.05` trong từng phase/outcome family. Sau retry, reasoner/graph failure được tính là downstream incorrect và báo failure rate; structural metric của graph không tạo được là unavailable kèm completion rate, không được impute hoặc âm thầm loại khỏi báo cáo.

## Artifact

- `configs/t13_holdout_freeze.yaml`: pre-registration nguồn.
- `data/manifests/t13_primary_holdout_tasks.jsonl`: đúng 100 primary task rows.
- `data/manifests/t13_supplementary_holdout_tasks.jsonl`: đúng 77 exploratory task rows.
- `data/manifests/t13_holdout_execution.json`: bản cam kết thực thi T14 cùng hash của mọi dependency.
- `data/manifests/t13_holdout_execution_audit.json`: các gate, expected counts và bằng chứng không mở holdout.

`python scripts/freeze_t13_holdout_execution.py --check` tái tạo cả bốn output byte-for-byte từ các manifest metadata đã freeze.

## Reproducibility caveat

Các config và artifact lịch sử T08–T11 không bị sửa. Tuy nhiên, audit phát hiện source-anchor drift ở các module dùng chung: `llm_backend.py` so với anchor T08/T10, `graph_contract.py` so với anchor T10/T11, và một newline cuối `causalds_scd.py` so với anchor T09.

T13 không che giấu drift này: nó ghi allowlist cụ thể và pin byte hash hiện tại của toàn bộ implementation làm baseline cho T14. Bất kỳ drift mới nào sẽ làm `--check` thất bại. Vì source byte cũ không còn trong lịch sử Git, không được tuyên bố T08–T11 hiện replay trọn vẹn qua mọi legacy source gate; chỉ các historical artifacts/config vẫn nguyên vẹn và baseline T14 hiện tại đã được đóng băng.

## Ranh giới T14

T14 phải chạy đúng một lần theo thứ tự đã khóa. Mọi thay đổi về scene/task/model/prompt/schema/method/scorer/metric/statistics sau T13 phải tạo experiment version mới; không được sửa manifest này rồi tiếp tục dưới cùng experiment ID.
