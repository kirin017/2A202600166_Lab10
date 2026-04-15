"""
Expectation suite đơn giản (không bắt buộc Great Expectations).

Sinh viên có thể thay bằng GE / pydantic / custom — miễn là có halt có kiểm soát.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class ExpectationResult:
    name: str
    passed: bool
    severity: str  # "warn" | "halt"
    detail: str


def run_expectations(cleaned_rows: List[Dict[str, Any]]) -> Tuple[List[ExpectationResult], bool]:
    """
    Trả về (results, should_halt).

    should_halt = True nếu có bất kỳ expectation severity halt nào fail.
    """
    results: List[ExpectationResult] = []

    # E1: có ít nhất 1 dòng sau clean
    ok = len(cleaned_rows) >= 1
    results.append(
        ExpectationResult(
            "min_one_row",
            ok,
            "halt",
            f"cleaned_rows={len(cleaned_rows)}",
        )
    )

    # E2: không doc_id rỗng
    bad_doc = [r for r in cleaned_rows if not (r.get("doc_id") or "").strip()]
    ok2 = len(bad_doc) == 0
    results.append(
        ExpectationResult(
            "no_empty_doc_id",
            ok2,
            "halt",
            f"empty_doc_id_count={len(bad_doc)}",
        )
    )

    # E3: policy refund không được chứa cửa sổ sai 14 ngày (sau khi đã fix)
    bad_refund = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "policy_refund_v4"
        and "14 ngày làm việc" in (r.get("chunk_text") or "")
    ]
    ok3 = len(bad_refund) == 0
    results.append(
        ExpectationResult(
            "refund_no_stale_14d_window",
            ok3,
            "halt",
            f"violations={len(bad_refund)}",
        )
    )

    # E4: chunk_text đủ dài
    short = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 8]
    ok4 = len(short) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_8",
            ok4,
            "warn",
            f"short_chunks={len(short)}",
        )
    )

    # E5: effective_date đúng định dạng ISO sau clean (phát hiện parser lỏng)
    iso_bad = [
        r
        for r in cleaned_rows
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", (r.get("effective_date") or "").strip())
    ]
    ok5 = len(iso_bad) == 0
    results.append(
        ExpectationResult(
            "effective_date_iso_yyyy_mm_dd",
            ok5,
            "halt",
            f"non_iso_rows={len(iso_bad)}",
        )
    )

    # E6: không còn marker phép năm cũ 10 ngày trên doc HR (conflict version sau clean)
    bad_hr_annual = [
        r
        for r in cleaned_rows
        if r.get("doc_id") == "hr_leave_policy"
        and "10 ngày phép năm" in (r.get("chunk_text") or "")
    ]
    ok6 = len(bad_hr_annual) == 0
    results.append(
        ExpectationResult(
            "hr_leave_no_stale_10d_annual",
            ok6,
            "halt",
            f"violations={len(bad_hr_annual)}",
        )
    )

    # E7 (new): chunk_min_length_60_warn — warn nếu chunk quá ngắn sau clean.
    # Cleaning rule 8 quarantine < 30 chars; expectation này cảnh báo ở ngưỡng rộng hơn (< 60)
    # để phát hiện chunk "vừa sống sót" qua quarantine nhưng vẫn quá ngắn cho retrieval.
    # metric_impact: Row 6 ("Tài khoản bị khóa sau 5 lần đăng nhập sai liên tiếp." ≈ 52 chars)
    # sẽ kích hoạt WARN trong mọi run chuẩn → short_chunks=1. Nếu inject nhiều chunk ngắn
    # hơn 60 chars → short_chunks tăng.
    short_60 = [r for r in cleaned_rows if len((r.get("chunk_text") or "")) < 60]
    ok7 = len(short_60) == 0
    results.append(
        ExpectationResult(
            "chunk_min_length_60_warn",
            ok7,
            "warn",
            f"short_chunks={len(short_60)}",
        )
    )

    # E8 (new): all_required_doc_ids_present — warn nếu thiếu bất kỳ doc_id nào trong cleaned.
    # Pipeline phải đảm bảo mọi nguồn đều có đại diện; nếu một nguồn bị loại hoàn toàn
    # (ví dụ: toàn bộ SLA bị quarantine do lỗi schema), agent sẽ mù thông tin SLA.
    # metric_impact: Normal run → PASS (4/4 doc_ids có mặt). Inject scenario: xóa toàn bộ
    # sla_p1_2026 rows → WARN (sla_p1_2026 missing). Xem group_report metric_impact table.
    required_doc_ids = frozenset(
        {"policy_refund_v4", "sla_p1_2026", "it_helpdesk_faq", "hr_leave_policy"}
    )
    present_doc_ids = {(r.get("doc_id") or "").strip() for r in cleaned_rows}
    missing_doc_ids = sorted(required_doc_ids - present_doc_ids)
    ok8 = len(missing_doc_ids) == 0
    results.append(
        ExpectationResult(
            "all_required_doc_ids_present",
            ok8,
            "warn",
            f"missing_doc_ids={missing_doc_ids}",
        )
    )

    halt = any(not r.passed and r.severity == "halt" for r in results)
    return results, halt
