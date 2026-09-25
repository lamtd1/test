# Spec: Retrieval & ranking

**Trạng thái:** Implemented (`src/services/retrieval.py`)

## Mục tiêu
`retrieve(criteria, envelope, conn) -> list[ScoredUnit]`: lọc cứng bằng SQL, chấm điểm
bằng Python. Không nhận `business_priority` làm tham số — kiểm bằng
`tests/test_retrieval.py::test_match_score_does_not_accept_business_priority`.

## Lọc cứng (SQL, JOIN `unit` + `project` để lấy `district`)
`status='available'`, `price_vnd <= price_cap` (ưu tiên `hard_constraints.price_max_vnd`,
fallback `envelope.price_max_vnd`), `bedrooms >= bedrooms_min`, và các `deal_breakers`
(`balcony_dir`, `handover_year` qua `project.handover_date`).

## Chấm điểm (Python, trên tập đã lọc)
- `near_poi`: `clamp(1 - (d - ideal)/(max - ideal), 0, 1)`, `d` từ
  `project_poi_distance`, `ideal`/`max` lấy từ `params` của `soft_preference` (mặc định
  500m/2000m).
- `airiness`: `0.4·(floor/total_floors) + 0.4·dir_bonus + 0.2·(n_open_sides/3)`.
- `view`: 1.0 nếu `view_type` là ưu tiên #1 trong danh sách `preferred`, giảm dần theo
  thứ hạng, 0 nếu không có trong danh sách.
- `match_score = Σ(weight × score) / Σweight`; `confidence: low` nhân weight × 0.7.

## Field có thể NULL (theo `docs/schemas.md`)
`balcony_dir`, `n_open_sides`, `is_corner`, `view_type`, `furnishing` có thể `NULL`
(chưa biết, khác với "không có"). Khi tính `airiness`/`view` mà field liên quan là
`NULL`, thành phần đó bị loại khỏi trung bình có trọng số (không tính là 0) — tránh
phạt oan căn có mô tả ngắn. Dữ liệu mock hiện tại luôn điền đủ 4 field này
(`provenance: synthetic`), nên nhánh NULL chưa có ca thực tế để test — cần bổ sung khi
có dữ liệu crawl thật.

## Chưa làm
- pgvector similarity trên `canonical_text` (Phần 3 của `docs/schemas.md`) — chỉ bật khi
  đo được cải thiện precision@3, hiện chưa đo.
