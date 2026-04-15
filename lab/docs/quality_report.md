# Quality report — Lab Day 10

**run_id:** sprint2-clean  
**Ngày:** 2026-04-15

---

## 1. Tóm tắt số liệu

| Chỉ số | Sprint 1 (baseline+new rules) | inject-bad (no refund fix) | Sprint 2 clean | Ghi chú |
|--------|-------------------------------|---------------------------|----------------|---------|
| raw_records | 13 | 13 | 13 | CSV có 10 row gốc + 3 row test mới |
| cleaned_records | 6 | 6 | 6 | inject-bad giữ cùng số cleaned |
| quarantine_records | 7 | 7 | 7 | 3 rule mới bắt thêm 3 row (11, 12, 13) |
| Expectation halt? | Không | **WARN** (E3 fail, tiếp tục vì --skip-validate) | Không | E3 = refund_no_stale_14d_window |

**Quarantine breakdown (sprint1/sprint2-clean):**

| Row # | doc_id | Reason |
|-------|--------|--------|
| 2 | policy_refund_v4 | duplicate_chunk_text |
| 5 | policy_refund_v4 | missing_effective_date |
| 7 | hr_leave_policy | stale_hr_policy_effective_date (2025-01-01 < 2026-01-01) |
| 9 | legacy_catalog_xyz_zzz | unknown_doc_id |
| 11 | policy_refund_v4 | chunk_too_short (3 chars) ← **Rule 8 mới** |
| 12 | sla_p1_2026 | missing_exported_at ← **Rule 7 mới** |
| 13 | hr_leave_policy | hr_stale_content_10d_annual (2026-03-01 nhưng "10 ngày") ← **Rule 9 mới** |

**Expectation E7 (new) — chunk_min_length_60_warn:**
- short_chunks=1 mỗi run chuẩn: Row 6 `it_helpdesk_faq` "Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp." (52 chars < 60)
- Severity: warn (không halt pipeline)

---

## 2. Before / after retrieval

**File before (inject-bad):** `artifacts/eval/after_inject_bad.csv`  
**File after (clean):** `artifacts/eval/before_after_eval.csv`

### Câu hỏi then chốt: refund window (`q_refund_window`)

| Scenario | contains_expected | hits_forbidden | top1_preview |
|----------|-------------------|----------------|--------------|
| **inject-bad** (no-refund-fix) | yes | **yes** ← FAIL | "Yêu cầu được gửi trong vòng 7 ngày..." (top-1 OK nhưng top-k còn chunk 14 ngày) |
| **sprint2-clean** | yes | **no** ✓ | "Yêu cầu được gửi trong vòng 7 ngày làm việc kể từ thời điểm xác nhận đơn hàng." |

**Phân tích:** Khi `--no-refund-fix`, Row 3 không bị thay "14 ngày" → chunk "14 ngày làm việc" xuất hiện trong top-3 → `hits_forbidden=yes`. Sau khi pipeline chuẩn (fix + prune), chunk stale bị thay bởi version "7 ngày" → hits_forbidden=no.

### Merit: leave version (`q_leave_version`)

| Scenario | contains_expected | hits_forbidden | top1_doc_expected |
|----------|-------------------|----------------|-------------------|
| **inject-bad** | yes | no | yes |
| **sprint2-clean** | yes | no | yes |

**Phân tích:** Cả hai run đều đúng cho `q_leave_version` vì Rule 9 (hr_stale_content_10d_annual) quarantine Row 13 trong cả hai scenario. Nếu Rule 9 bị tắt và Row 13 được embed → "10 ngày phép năm" xuất hiện trong top-k → `hits_forbidden=yes` (xem phần 4).

---

## 3. Freshness & monitor

**SLA:** 24 giờ (`FRESHNESS_SLA_HOURS=24` trong `.env`)  
**Kết quả trên manifest sprint2-clean:**

```
freshness_check=FAIL
latest_exported_at=2026-04-10T08:00:00
age_hours=121.033
sla_hours=24.0
reason=freshness_sla_exceeded
```

**Giải thích:**
- CSV mẫu có `exported_at` cố định là `2026-04-10T08:00:00` (ngày tạo file).
- Lab chạy ngày `2026-04-15` → data đã 5 ngày = 121 giờ > SLA 24h → FAIL là **hợp lý**.
- Trong production: upstream phải cập nhật `exported_at` theo mỗi batch export thực tế.
- Giải pháp tạm thời: đặt `FRESHNESS_SLA_HOURS=200` hoặc cập nhật exported_at trong CSV nếu muốn PASS. Lab này giữ nguyên FAIL và ghi rõ trong runbook.

---

## 4. Corruption inject (Sprint 3)

**Kịch bản inject:**
```bash
python etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```

**Cơ chế:**
- `--no-refund-fix`: Bỏ qua bước thay "14 ngày làm việc" → "7 ngày làm việc" trong Row 3.
- `--skip-validate`: Tiếp tục embed dù E3 (`refund_no_stale_14d_window`) FAIL.
- Kết quả: chunk stale "14 ngày làm việc" được embed vào Chroma.

**Phát hiện bằng eval:**
- `q_refund_window`: `hits_forbidden=yes` — top-3 chunks chứa "14 ngày làm việc" lẫn "7 ngày".
- Log inject-bad: `expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=1`

**Recovery:** Chạy pipeline chuẩn → prune xoá chunk stale → hits_forbidden=no.

---

## 5. Hạn chế & việc chưa làm

- Freshness chỉ đo ở 1 boundary (`latest_exported_at`). Distinction yêu cầu đo ở 2 boundary (ingest + publish). Run_timestamp có trong manifest nhưng chưa được compare với ingest time.
- Eval 4 câu (test_questions.json). Grading questions (gq_d10_01-03) chưa public; sẽ chạy `grading_run.py` sau 17:00.
- E7 (`chunk_min_length_60_warn`) luôn WARN vì lockout FAQ chunk (52 chars) không thể thay đổi — cân nhắc hạ ngưỡng xuống 50 hoặc accept WARN như một "known issue".
- Không có LLM-judge; chỉ dùng keyword-based retrieval eval.
