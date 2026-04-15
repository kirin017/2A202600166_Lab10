# Kiến trúc pipeline — Lab Day 10

**Nhóm:** 
**Cập nhật:** 2026-04-15

---

## 1. Sơ đồ luồng

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          ETL PIPELINE — DAY 10                           │
└──────────────────────────────────────────────────────────────────────────┘

  data/raw/                  transform/               quality/
  policy_export_dirty.csv    cleaning_rules.py        expectations.py
         │                          │                       │
         ▼                          ▼                       ▼
  ┌─────────────┐          ┌──────────────────┐    ┌──────────────────┐
  │  INGEST     │──────────▶  CLEAN            │───▶  VALIDATE         │
  │  load_raw   │  rows[]  │  clean_rows()    │    │  run_expectations │
  │  log raw_   │          │  Rule 1–9        │    │  E1–E8            │
  │  records    │          │  quarantine →    │    │  warn / halt      │
  └─────────────┘          │  artifacts/      │    └────────┬─────────┘
         ▲                 │  quarantine/*.csv│             │ pass
         │                 └──────────────────┘             ▼
  [freshness               artifacts/cleaned/      ┌──────────────────┐
   measured                *.csv                   │  EMBED            │
   here: exported_at]                              │  Chroma upsert   │
                                                   │  chunk_id (idem- │
                                                   │  potent)         │
                                                   │  prune stale ids │
                                                   └────────┬─────────┘
                                                            │
                                                    [freshness measured
                                                     here: run_timestamp]
                                                            │
                                                            ▼
                                                   artifacts/manifests/
                                                   manifest_<run_id>.json
                                                            │
                                                            ▼
                                                   monitoring/
                                                   freshness_check.py
                                                   PASS / WARN / FAIL
```

**Điểm đo freshness:**
- `latest_exported_at`: timestamp max của trường `exported_at` trong cleaned rows — phản ánh độ tươi dữ liệu nguồn.
- `run_timestamp`: thời điểm pipeline chạy — để tính SLA lag giữa export và publish.

**run_id** được ghi vào: log file, manifest JSON, và metadata mỗi vector trong Chroma.

**Quarantine:** các row bị cách ly ghi vào `artifacts/quarantine/quarantine_<run_id>.csv` với cột `reason`.

---

## 2. Ranh giới trách nhiệm

| Thành phần | Input | Output | File chính |
|------------|-------|--------|------------|
| Ingest | `data/raw/*.csv` | `List[Dict]` in-memory | `etl_pipeline.py::load_raw_csv` |
| Transform | `List[Dict]` raw | `(cleaned, quarantine)` | `transform/cleaning_rules.py` |
| Quality | `List[Dict]` cleaned | `(results, halt_flag)` | `quality/expectations.py` |
| Embed | `artifacts/cleaned/*.csv` | Chroma collection `day10_kb` | `etl_pipeline.py::cmd_embed_internal` |
| Monitor | `artifacts/manifests/*.json` | `PASS/WARN/FAIL` + detail | `monitoring/freshness_check.py` |

---

## 3. Idempotency & rerun

Embed sử dụng `col.upsert(ids=chunk_ids, ...)` — chạy lại 2 lần với cùng dữ liệu không tạo thêm vector.

Ngoài ra, sau mỗi run pipeline **prune** những vector ID có trong Chroma nhưng không còn trong cleaned batch hiện tại:
```python
drop = sorted(prev_ids - set(ids))
col.delete(ids=drop)
log(f"embed_prune_removed={len(drop)}")
```
Đảm bảo index = snapshot publish (không còn chunk "lạc hậu" sau khi quarantine rule thêm mới).

---

## 4. Liên hệ Day 09

Pipeline Day 10 sử dụng cùng corpus `data/docs/` với Day 09 nhưng qua một tầng ETL trung gian (CSV export → clean → validate → embed). Collection `day10_kb` được tách riêng khỏi collection Day 09 để tránh ảnh hưởng lẫn nhau khi inject corruption.

Multi-agent Day 09 có thể được cấu hình để query collection `day10_kb` sau khi pipeline Day 10 chạy xong, đảm bảo agent đọc đúng phiên bản dữ liệu đã được validate.

---

## 5. Rủi ro đã biết

- **CSV mẫu `exported_at` cũ**: Mọi row đều có `exported_at=2026-04-10T08:00:00`, cách hiện tại (~5 ngày) nên freshness FAIL với SLA 24h. Chạy `python etl_pipeline.py freshness` để xem chi tiết; giải thích trong runbook.
- **Single-file pipeline**: Nếu `policy_export_dirty.csv` bị ghi đè hoặc hỏng, pipeline không có fallback. Cần versioning raw file (thêm timestamp vào tên file trong production).
- **Embedding model offline**: `all-MiniLM-L6-v2` cần tải từ HuggingFace lần đầu. Sau đó cache tại `~/.cache/torch/sentence_transformers/`.
