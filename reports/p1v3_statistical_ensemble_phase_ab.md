# P1-v3 Statistical Ensemble — Phase A–B audit

## Trạng thái

Phase A–B offline đã hoàn tất fixture conformance. Chưa sinh study scene,
chưa tải observational data, chưa chạy BOSS/Bootstrap-BOSS/Tetrad/R và chưa
gọi semantic API.

## Kết quả fixture

- PAG→skeleton: 1/1
- MMPC symmetric output: 1/1
- Primary 3/5 vote: 1/1
- Shared six-candidate pool: 1/1
- Invalid fixture fail-closed: 2/2

## Token preflight

Tối đa 7 node tạo 21 cặp. Ước lượng offline bằng ký tự/4 là
`1167` input tokens và
`360` output tokens. Đây chưa phải
provider token accounting; tokenizer/context envelope vẫn **pending verification**.
Nếu vượt envelope, live execution phải dừng và mở amendment; không chunk prompt.

## Environment pending

R/bnlearn `5.3-20260901` và runtime Tetrad/Python/Java phải được xác minh trước
live execution. `Rscript` hiện chưa có trong PATH; không thay MMPC bằng thuật toán khác.

Audit SHA-256: `4AB62B01A09313E69C4E333F4380E9B872D0A253BEAF30D43A6F8F5DE01C52BC`
