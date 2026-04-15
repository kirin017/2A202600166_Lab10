# Runbook — Lab Day 10 (incident tối giản)

---

## Symptom

Agent trả lời sai chính sách: ví dụ nói "hoàn tiền trong **14 ngày** làm việc" (thay vì 7 ngày), hoặc "nhân viên được **10 ngày** phép năm" (thay vì 12 ngày).

Hoặc: Freshness check báo `FAIL` trên manifest sau khi pipeline chạy xong.

---

## Detection

| Tín hiệu | Nguồn kiểm tra |
|----------|----------------|
| `expectation[refund_no_stale_14d_window] FAIL` | `artifacts/logs/run_<id>.log` |
| `expectation[hr_leave_no_stale_10d_annual] FAIL` | `artifacts/logs/run_<id>.log` |
| `hits_forbidden=yes` cho câu hỏi hoàn tiền | `artifacts/eval/before_after_eval.csv` |
| `freshness_check=FAIL` | `artifacts/logs/run_<id>.log` hoặc chạy `python etl_pipeline.py freshness --manifest ...` |
| `quarantine_records` tăng bất thường | So sánh `manifest_<id>.json` với manifest lần trước |

---

## Diagnosis

| Bước | Việc làm | Kết quả mong đợi |
|------|----------|-----------------|
| 1 | `cat artifacts/manifests/manifest_<id>.json` | Tìm `no_refund_fix`, `skipped_validate`, `quarantine_records` |
| 2 | `cat artifacts/quarantine/quarantine_<id>.csv` | Xem `reason` của từng row bị cách ly |
| 3 | `cat artifacts/logs/run_<id>.log \| grep expectation` | Tìm dòng `FAIL` / `HALT` |
| 4 | `python eval_retrieval.py --out artifacts/eval/diag_eval.csv` | Kiểm tra `hits_forbidden`, `contains_expected` |
| 5 | Nếu freshness FAIL: so sánh `latest_exported_at` trong manifest với thời gian hiện tại | `age_hours > sla_hours` → data stale |

---

## Mitigation

**Trường hợp stale refund (14 ngày còn trong Chroma):**
```bash
# Re-run pipeline chuẩn (có fix)
python etl_pipeline.py run --run-id recovery-$(date +%Y%m%dT%H%M)
# Verify
python eval_retrieval.py --out artifacts/eval/post_recovery_eval.csv
# Kiểm tra hits_forbidden=no cho q_refund_window
```

**Trường hợp HR conflict (10 ngày phép lọt qua):**
- Kiểm tra `quarantine_*.csv` — nếu `hr_stale_content_10d_annual` không có trong quarantine: Rule 9 bị disable hoặc CSV source bị sửa.
- Re-run pipeline chuẩn; Rule 9 sẽ quarantine row lỗi.

**Trường hợp freshness FAIL:**
- Kiểm tra `FRESHNESS_SLA_HOURS` trong `.env` — nếu SLA đặt quá thấp so với chu kỳ export thực tế, điều chỉnh.
- CSV mẫu có `exported_at=2026-04-10T08:00:00` (cố định) → luôn FAIL sau 24h. Trong production, upstream cần cập nhật timestamp theo batch thực tế.
- Tạm thời: ghi `freshness_check=FAIL` trong runbook và thêm banner "data snapshot from YYYY-MM-DD" trong UI agent.

**Rollback embed:**
```bash
# Không có rollback tự động — Chroma upsert là idempotent.
# Để rollback về version cũ: xóa collection và re-run với CSV cũ.
python -c "
import chromadb, os
client = chromadb.PersistentClient(path=os.environ.get('CHROMA_DB_PATH','./chroma_db'))
client.delete_collection('day10_kb')
print('Collection deleted')
"
python etl_pipeline.py run --raw data/raw/policy_export_dirty_backup.csv --run-id rollback
```

---

## Prevention

1. **Thêm expectation mới** khi phát hiện failure mode chưa được cover (ví dụ: `min_chunks_per_source`).
2. **Alert tự động**: Chạy `freshness_check` sau mỗi pipeline run và gửi alert nếu FAIL (tích hợp vào CI/CD hoặc cron job).
3. **Owner rõ ràng**: Xem `contracts/data_contract.yaml` — mỗi doc_id có owner team; khi quarantine tăng, notify owner để fix upstream.
4. **Freshness SLA interpretation**:
   - `PASS`: `age_hours <= FRESHNESS_SLA_HOURS` — dữ liệu đủ tươi.
   - `WARN`: Không có trong baseline; có thể thêm ngưỡng WARN ở 80% SLA.
   - `FAIL`: `age_hours > FRESHNESS_SLA_HOURS` — data stale; agent có thể trả lời sai nếu policy đã thay đổi.
5. **Inject test định kỳ** (Sprint 3): Chạy `--no-refund-fix` và `eval_retrieval.py` mỗi sprint để đảm bảo pipeline đang bảo vệ đúng.
