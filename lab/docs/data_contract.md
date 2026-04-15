# Data contract — Lab Day 10

> Đồng bộ với `contracts/data_contract.yaml`. Cập nhật cả hai khi thêm nguồn mới.

---

## 1. Nguồn dữ liệu (source map)

| Nguồn | Phương thức ingest | Failure mode chính | Metric / alert |
|-------|-------------------|--------------------|----------------|
| `policy_refund_v4` — Chính sách hoàn tiền CS | Export CSV từ CMS (mô phỏng bằng `data/raw/*.csv`) | Chunk stale với cửa sổ 14 ngày từ policy-v3 lọt vào export | `expectation[refund_no_stale_14d_window]` FAIL; `quarantine_records` tăng bất thường |
| `hr_leave_policy` — Chính sách nghỉ phép HR | Export CSV (tích hợp từ HRIS) | Bản 2025 (10 ngày phép) và bản 2026 (12 ngày) cùng xuất hiện trong export — conflict version | `quarantine_records` tăng; `expectation[hr_leave_no_stale_10d_annual]` FAIL nếu lọt qua |
| `sla_p1_2026` — SLA ticket IT | Export từ ticketing system | Chunk thiếu `exported_at` → không đo được freshness | Rule `missing_exported_at` bắt; `quarantine_records` tăng |
| `it_helpdesk_faq` — FAQ IT Helpdesk | Export CSV từ knowledge base portal | Ngày `effective_date` format dd/mm/yyyy thay vì ISO → parse lỗi | Rule `invalid_effective_date_format` bắt; auto-normalize nếu hợp lệ |

---

## 2. Schema cleaned

| Cột | Kiểu | Bắt buộc | Constraints | Ghi chú |
|-----|------|----------|-------------|---------|
| `chunk_id` | string | Có | unique, format: `{doc_id}_{seq}_{hash16}` | Sinh bởi `_stable_chunk_id()` — dùng làm Chroma vector ID (idempotent) |
| `doc_id` | string | Có | trong `ALLOWED_DOC_IDS` | Khóa logic nguồn tài liệu |
| `chunk_text` | string | Có | len >= 30 sau strip | Sau cleaning, không còn BOM hay cửa sổ stale |
| `effective_date` | date | Có | format YYYY-MM-DD | Được normalize từ dd/mm/yyyy nếu cần |
| `exported_at` | datetime | Có | parseable ISO 8601 | Dùng để đo freshness; thiếu → quarantine |

---

## 3. Quy tắc quarantine vs drop

| Lý do (reason) | Hành động | Approve lại? |
|----------------|-----------|--------------|
| `unknown_doc_id` | Quarantine CSV | Phải xác nhận catalog, thêm vào `ALLOWED_DOC_IDS` nếu hợp lệ |
| `missing_exported_at` | Quarantine CSV | Yêu cầu upstream re-export với timestamp đầy đủ |
| `missing_effective_date` | Quarantine CSV | Back-fill từ nguồn chính nếu có |
| `invalid_effective_date_format` | Auto-normalize nếu dd/mm/yyyy khớp pattern; otherwise quarantine | Không cần approve nếu đã normalize thành công |
| `stale_hr_policy_effective_date` | Quarantine CSV | Không merge lại; bản 2025 đã obsolete |
| `hr_stale_content_10d_annual` | Quarantine CSV | Cập nhật nội dung lên 12 ngày rồi re-export |
| `chunk_too_short` | Quarantine CSV | Review thủ công; thường là artifact lỗi export |
| `missing_chunk_text` | Quarantine CSV | Lỗi export — yêu cầu source re-generate |
| `duplicate_chunk_text` | Quarantine CSV (giữ bản đầu tiên) | Không cần merge; dedupe tự động |

**Không có "drop"** — mọi record bị loại đều ghi vào quarantine CSV để audit. Team data/compliance có thể review và quyết định có cần re-ingest hay không.

---

## 4. Phiên bản & canonical

| Tài liệu | Source of truth | Version hiện tại |
|----------|----------------|-----------------|
| Policy hoàn tiền | `data/docs/policy_refund_v4.txt` | v4 — cửa sổ **7 ngày** làm việc |
| Chính sách nghỉ phép HR | `data/docs/hr_leave_policy.txt` | 2026 — **12 ngày** phép năm cho < 3 năm kinh nghiệm |
| SLA IT Helpdesk | `data/docs/sla_p1_2026.txt` | 2026 — P1 phản hồi **15 phút**, resolution **4 giờ** |
| FAQ IT Helpdesk | `data/docs/it_helpdesk_faq.txt` | 2026 — khóa sau **5 lần** sai |

**Policy cutoff HR**: `hr_leave_min_effective_date = 2026-01-01` (đọc từ `contracts/data_contract.yaml` → `policy_versioning.hr_leave_min_effective_date`). Không hard-code trong `cleaning_rules.py`.
