-- ═══════════════════════════════════════════════════════════════════
-- HomeMatch — schema dữ liệu
-- Một database duy nhất: PostgreSQL. Không Mongo, không vector DB riêng.
--
-- Nguyên tắc:
--   1. DB lưu FACT gốc (toạ độ, tầng, hướng...), KHÔNG lưu nhãn mềm
--      kiểu is_airy / near_school. Điểm "thoáng", "gần trường" tính lúc truy vấn.
--   2. Thông tin kinh doanh nằm ở BẢNG RIÊNG. API của khách không bao giờ
--      join tới bảng đó → chống rò rỉ business_priority bằng cấu trúc,
--      không phải bằng việc nhớ xoá field.
--   3. Không lưu thu nhập / tiết kiệm thô của khách. Chỉ lưu bucket và
--      kết quả đã dẫn xuất.
--
-- Phần 1–2: MVP. Phần 3: thêm sau khi happy case chạy.
-- ═══════════════════════════════════════════════════════════════════


-- ───────────────────────────────────────────────────────────────────
-- PHẦN 1 — KHO HÀNG (dữ liệu tĩnh, seed một lần)
-- ───────────────────────────────────────────────────────────────────

-- Dự án. Thuộc tính VỊ TRÍ nằm ở đây, không nằm ở từng căn:
-- geocode ~6–50 dự án thay vì hàng nghìn căn.
CREATE TABLE project (
    project_id      TEXT PRIMARY KEY,                  -- 'matrix-one'
    name            TEXT NOT NULL,                     -- 'The Matrix One'
    developer       TEXT,
    district        TEXT NOT NULL,                     -- 'Nam Từ Liêm'
    ward            TEXT,
    lat             DOUBLE PRECISION NOT NULL,
    lng             DOUBLE PRECISION NOT NULL,
    -- Toạ độ đến từ đâu. 'ward_centroid' = chỉ biết phường, sai số vài trăm mét
    -- → KHÔNG được dùng để nói "cách trường 600m" trong lời giải thích.
    geo_source      TEXT NOT NULL DEFAULT 'geocoded'
                    CHECK (geo_source IN ('listing_field','geocoded','manual','ward_centroid')),
    handover_date   DATE,                              -- NULL = đã bàn giao
    amenities       TEXT[] NOT NULL DEFAULT '{}',      -- {'pool','gym','park'}
    is_synthetic    BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (lat BETWEEN 20.5 AND 21.5 AND lng BETWEEN 105.3 AND 106.2)  -- Hà Nội
);
CREATE INDEX idx_project_district ON project (district);


-- Căn hộ. Chỉ fact gốc — mọi field ở đây đều có thể xuất hiện trong
-- câu giải thích cho khách, nên KHÔNG có thông tin kinh doanh.
CREATE TABLE unit (
    unit_id         TEXT PRIMARY KEY,                  -- 'MO-S2-1806'
    project_id      TEXT NOT NULL REFERENCES project(project_id),
    block           TEXT,                              -- 'S2'
    floor           SMALLINT NOT NULL CHECK (floor >= 1),
    total_floors    SMALLINT NOT NULL CHECK (total_floors >= 1),
    area_sqm        NUMERIC(6,1) NOT NULL CHECK (area_sqm > 0),
    bedrooms        SMALLINT NOT NULL CHECK (bedrooms BETWEEN 0 AND 6),  -- 0 = studio
    bathrooms       SMALLINT NOT NULL DEFAULT 1,
    -- BỐN FIELD DƯỚI ĐÂY ĐƯỢC PHÉP NULL = chưa biết. Xem cột provenance.
    balcony_dir     TEXT CHECK (balcony_dir IN ('N','NE','E','SE','S','SW','W','NW')),
    n_open_sides    SMALLINT CHECK (n_open_sides BETWEEN 1 AND 3),
    is_corner       BOOLEAN,
    view_type       TEXT CHECK (view_type IN ('lake','park','river','city','internal','blocked')),
    furnishing      TEXT CHECK (furnishing IN ('bare','basic','full')),
    price_vnd       BIGINT NOT NULL CHECK (price_vnd > 0),
    status          TEXT NOT NULL DEFAULT 'available'
                    CHECK (status IN ('available','reserved','sold')),
    raw_description TEXT,                              -- mô tả gốc của người bán
    -- Văn bản CHUẨN HOÁ, sinh từ chính các field ở trên + phần chủ quan người bán
    -- viết thêm. Mọi căn có độ dài và cấu trúc tương đương → embedding so sánh
    -- được với nhau. Embed cột này, KHÔNG embed raw_description.
    canonical_text  TEXT,
    -- Xuất xứ từng field: {"balcony_dir":"extracted","view_type":"unknown",...}
    -- Giá trị: listing_field | extracted | derived | synthetic | unknown
    -- Field NULL + provenance 'unknown' nghĩa là KHÔNG BIẾT, không phải là KHÔNG CÓ.
    -- Lúc chấm điểm: bỏ thành phần unknown ra khỏi trung bình có trọng số rồi
    -- chuẩn hoá lại — nếu cho 0 thì listing viết ngắn bị phạt oan.
    provenance      JSONB NOT NULL DEFAULT '{}',
    source_url      TEXT,                              -- nguồn crawl, NULL nếu seed tay
    is_synthetic    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (floor <= total_floors)
);
-- Index phục vụ đúng câu lọc cứng: status + số PN + giá
CREATE INDEX idx_unit_hard_filter ON unit (status, bedrooms, price_vnd);
CREATE INDEX idx_unit_project ON unit (project_id);


-- Thông tin kinh doanh — BẢNG RIÊNG, chỉ API role sale được đọc.
-- Dữ liệu mock (seed có seed cố định), dùng để kiểm chứng chống thiên vị.
CREATE TABLE unit_business (
    unit_id             TEXT PRIMARY KEY REFERENCES unit(unit_id),
    days_on_market      INT NOT NULL DEFAULT 0,
    business_priority   NUMERIC(3,2) NOT NULL DEFAULT 0 CHECK (business_priority BETWEEN 0 AND 1),
    discount_pct        NUMERIC(4,2),                  -- chiết khấu
    commission_pct      NUMERIC(4,2),                  -- hoa hồng
    policy_note         TEXT                           -- 'CK 5% + HH 1,5%'
);


-- Điểm quan tâm: trường, công viên, bệnh viện, siêu thị, bến xe buýt.
-- Nguồn: OpenStreetMap / Overpass. Kể cả điểm neo khách hay nhắc (Hồ Gươm).
CREATE TABLE poi (
    poi_id      SERIAL PRIMARY KEY,
    type        TEXT NOT NULL CHECK (type IN
                ('school_primary','school_secondary','school_high','kindergarten',
                 'park','lake','hospital','supermarket','bus_stop','landmark')),
    name        TEXT NOT NULL,                         -- 'Tiểu học Nam Từ Liêm'
    lat         DOUBLE PRECISION NOT NULL,
    lng         DOUBLE PRECISION NOT NULL,
    osm_id      BIGINT                                 -- để truy lại nguồn
);
CREATE INDEX idx_poi_type ON poi (type);


-- Khoảng cách dự án → POI, TÍNH SẴN một lần lúc seed.
-- 50 dự án × 200 POI = 10.000 dòng: nhỏ, và biến "gần trường X" thành một JOIN.
-- Đây cũng là nguồn cho câu giải thích "cách Tiểu học X 600m".
CREATE TABLE project_poi_distance (
    project_id  TEXT NOT NULL REFERENCES project(project_id),
    poi_id      INT  NOT NULL REFERENCES poi(poi_id),
    distance_m  INT  NOT NULL,                         -- haversine, mét
    PRIMARY KEY (project_id, poi_id)
);
CREATE INDEX idx_ppd_poi ON project_poi_distance (poi_id, distance_m);


-- Hàm haversine — cho điểm neo tuỳ ý khách nhắc (nơi làm việc, Hồ Gươm)
-- không có sẵn trong bảng poi. Chỉ chạy trên ~50 dự án nên không cần PostGIS.
CREATE FUNCTION haversine_m(lat1 DOUBLE PRECISION, lng1 DOUBLE PRECISION,
                            lat2 DOUBLE PRECISION, lng2 DOUBLE PRECISION)
RETURNS INT LANGUAGE sql IMMUTABLE AS $$
    SELECT (2 * 6371000 * asin(sqrt(
        power(sin(radians(lat2 - lat1) / 2), 2) +
        cos(radians(lat1)) * cos(radians(lat2)) *
        power(sin(radians(lng2 - lng1) / 2), 2)
    )))::INT
$$;


-- ───────────────────────────────────────────────────────────────────
-- PHẦN 2 — PHIÊN LÀM VIỆC (dữ liệu chạy, ghi liên tục)
-- ───────────────────────────────────────────────────────────────────

CREATE TABLE app_user (
    user_id     SERIAL PRIMARY KEY,
    role        TEXT NOT NULL CHECK (role IN ('customer','sale')),
    display_name TEXT NOT NULL,
    phone_masked TEXT,                                 -- '0912 •••• 47' — không lưu số đầy đủ
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- Một phiên = một lần khách tìm căn.
-- criteria và envelope để JSONB: cấu trúc khớp Pydantic model,
-- đổi schema không cần migration mỗi lần.
CREATE TABLE session (
    session_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     INT NOT NULL REFERENCES app_user(user_id),
    assigned_sale_id INT REFERENCES app_user(user_id),
    state           TEXT NOT NULL DEFAULT 'draft' CHECK (state IN
                    ('draft','awaiting_review','under_review','rerank_requested','approved','sent')),
    criteria        JSONB,                             -- CriteriaSchema
    completeness    NUMERIC(3,2) NOT NULL DEFAULT 0,
    envelope        JSONB,                             -- AffordabilityEnvelope (đã dẫn xuất)
    income_bucket   TEXT,                              -- '50-60tr' — KHÔNG lưu số thô
    finance_purged_at TIMESTAMPTZ,                     -- khách bấm xoá dữ liệu tài chính
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at         TIMESTAMPTZ
);
CREATE INDEX idx_session_queue ON session (state, created_at) WHERE state IN ('awaiting_review','under_review');


-- Lịch sử hội thoại — nguồn cho raw_quote và để agent đọc lại 6 lượt gần nhất.
CREATE TABLE message (
    message_id  BIGSERIAL PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('customer','agent','system')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_message_session ON message (session_id, created_at);


-- Shortlist của một phiên. Một dòng = một căn trong danh sách.
-- reasons / tradeoffs lưu lại đúng câu đã sinh, để sale sửa và để audit.
CREATE TABLE shortlist_item (
    session_id  UUID NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
    unit_id     TEXT NOT NULL REFERENCES unit(unit_id),
    rank        SMALLINT NOT NULL,
    match_score NUMERIC(4,3) NOT NULL,                 -- 0..1, do code tính
    reasons     JSONB NOT NULL DEFAULT '[]',           -- ["Cách TH Nam Từ Liêm 600m", ...]
    tradeoffs   JSONB NOT NULL DEFAULT '[]',
    what_if     TEXT,
    origin      TEXT NOT NULL DEFAULT 'system' CHECK (origin IN ('system','sale_added')),
    is_removed  BOOLEAN NOT NULL DEFAULT FALSE,        -- sale loại → ẩn, không xoá
    over_envelope BOOLEAN NOT NULL DEFAULT FALSE,      -- căn sale thêm tay vượt trần
    PRIMARY KEY (session_id, unit_id)
);


-- ───────────────────────────────────────────────────────────────────
-- PHẦN 3 — THÊM SAU KHI HAPPY CASE CHẠY
-- ───────────────────────────────────────────────────────────────────

-- Mọi thao tác có side effect của sale.
CREATE TABLE audit_log (
    audit_id        BIGSERIAL PRIMARY KEY,
    session_id      UUID NOT NULL REFERENCES session(session_id),
    actor_id        INT NOT NULL REFERENCES app_user(user_id),
    action          TEXT NOT NULL CHECK (action IN
                    ('view','remove_unit','add_unit','update_criteria',
                     'override_rank','edit_explanation','approve_and_send')),
    unit_id         TEXT REFERENCES unit(unit_id),
    from_rank       SMALLINT,
    to_rank         SMALLINT,
    old_value       JSONB,
    new_value       JSONB,
    match_score     NUMERIC(4,3),                      -- chụp lại lúc thao tác
    business_priority NUMERIC(3,2),                    -- để hậu kiểm thiên vị
    days_on_market  INT,
    reason_code     TEXT,
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- đổi hạng và thêm căn BẮT BUỘC có lý do — chặn ở tầng DB, không chỉ ở API
    CHECK (action NOT IN ('override_rank','add_unit') OR (reason_code IS NOT NULL AND note IS NOT NULL))
);
CREATE INDEX idx_audit_session ON audit_log (session_id, created_at);


-- Phản hồi của khách sau khi xem shortlist.
CREATE TABLE feedback (
    session_id  UUID NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
    unit_id     TEXT NOT NULL REFERENCES unit(unit_id),
    intent      TEXT NOT NULL CHECK (intent IN ('want_visit','rejected')),
    reason_tag  TEXT CHECK (reason_tag IN ('price','direction_floor','location','handover','other')),
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, unit_id),
    CHECK (intent = 'want_visit' OR reason_tag IS NOT NULL)   -- loại thì phải có lý do
);


-- Chi phí LLM — nguồn cho chỉ số chi phí/phiên.
CREATE TABLE llm_usage (
    usage_id    BIGSERIAL PRIMARY KEY,
    session_id  UUID REFERENCES session(session_id) ON DELETE SET NULL,
    node        TEXT NOT NULL,                         -- 'discovery' | 'explain' | 'ingest'
    model       TEXT NOT NULL,
    tokens_in   INT NOT NULL,
    tokens_out  INT NOT NULL,
    cost_usd    NUMERIC(10,6) NOT NULL,
    latency_ms  INT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- Embedding — chỉ bật khi đo được là nó cải thiện precision@3.
-- Embed canonical_text (đã chuẩn hoá), KHÔNG embed raw_description.
-- Dùng làm ĐIỂM THƯỞNG trên tập đã lọc, không bao giờ dùng để lọc:
-- căn nào người bán viết sơ sài sẽ bị loại oan nếu dùng vector làm bộ lọc.
--   CREATE EXTENSION IF NOT EXISTS vector;
--   ALTER TABLE unit ADD COLUMN canonical_embedding vector(1536);  -- text-embedding-3-small

-- Độ phủ từng field — chạy sau khi seed để biết field nào đủ tin để chấm điểm.
-- Field nào dưới ~60% thì đừng cho trọng số cao, và đừng dùng làm lọc cứng.
CREATE VIEW v_field_coverage AS
SELECT
    count(*)                                                        AS total_units,
    round(100.0 * count(balcony_dir)  / count(*), 1)                AS pct_balcony_dir,
    round(100.0 * count(view_type)    / count(*), 1)                AS pct_view_type,
    round(100.0 * count(n_open_sides) / count(*), 1)                AS pct_open_sides,
    round(100.0 * count(furnishing)   / count(*), 1)                AS pct_furnishing,
    round(100.0 * count(canonical_text) / count(*), 1)              AS pct_canonical_text
FROM unit;