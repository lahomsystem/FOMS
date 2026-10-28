"""PARTNER-FOMS 3-2: 협력사 주문 목록 — 우리 ERP 대시보드 모양(프로세스 맵 · 필터 줄 · 작업 큐).

스펙 docs/specs/2026-10-19-partner-foms-mode_SPEC.md §3.2.

* 프로세스 맵은 협력사 쉬운 단계 7칸이다(:data:`PARTNER_PIPELINE`). "도면 확인 대기"가 협력사 차례다.
* 필터: 검색(고객 · 연락처 · 주소 · 주문 번호) · 단계 · 담당 · 내 차례만 · 내 담당.
* 자기 회사의 운영 주문만 읽는다(삭제 · 초안 제외). structured_data(JSONB)는 고객컨펌 단계 주문의 도면 확정
  여부만 읽는다(그 단계 주문 몇 건 — PARTNER-FOMS 6 §1-9). 나머지는 평면 칸.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_

from foms.services.partners.orders import partner_stage_label
from foms.services.partners.schedule_request import pending_request_texts
from models import Order, OrderAssignment

PARTNER_PIPELINE = ("접수 확인 중", "도면 작업 중", "도면 확인 대기", "생산 중", "시공 예정", "완료", "AS 진행 중")
TURN_LABEL = "도면 확인 대기"
# 진행 막대 칸(주문 화면 진행 단계 6칸과 같은 순서). AS 는 끝 칸.
_STEP_OF_LABEL = {label: min(i, 5) for i, label in enumerate(PARTNER_PIPELINE)}
_WORK = {
    "접수 확인 중": "저희 CS 가 보낸 내용을 확인하고 있습니다",
    "도면 작업 중": "저희 도면팀이 도면을 그리고 있습니다",
    "도면 확인 대기": "고객과 도면을 확인한 뒤 승인 또는 수정 요청",
    "생산 중": "공장에서 만들고 있습니다",
    "완료": "끝났습니다 · 완공 사진을 볼 수 있습니다",
    "AS 진행 중": "저희 AS 팀이 처리하고 있습니다",
}
MAX_ROWS = 200
_PHONE_DIGITS_MIN = 4
_SCAN_LIMIT = 2000


def partner_list_filters(args: Any) -> dict[str, str]:
    """요청 인자에서 쓸 수 있는 필터만 고른다(모르는 값은 버린다)."""
    stage = str(args.get("stage") or "").strip()
    manager = str(args.get("manager") or "").strip()
    return {
        "q": str(args.get("q") or "").strip()[:50],
        "stage": stage if stage in PARTNER_PIPELINE else "",
        "manager": manager if manager.isdigit() else "",
        "turn": "1" if args.get("turn") == "1" else "",
        "mine": "1" if args.get("mine") == "1" else "",
    }


def _work_text(label: str, construction_date: Any) -> str:
    if label == "시공 예정":
        return f"시공 {construction_date}" if construction_date else "저희가 시공일을 잡고 있습니다"
    return _WORK.get(label, "")


def _matches_query(row: dict[str, Any], q: str) -> bool:
    if not q:
        return True
    digits = re.sub(r"\D", "", q)
    if digits and digits == str(row["id"]):
        return True
    # 연락처는 4자리 이상일 때만 — 짧은 숫자(주문 번호)가 모든 연락처에 걸리지 않게.
    if len(digits) >= _PHONE_DIGITS_MIN and digits in re.sub(r"\D", "", row["phone"] or ""):
        return True
    needle = q.lower()
    return any(needle in str(row[key] or "").lower() for key in ("customer_name", "address", "product"))


def _drawing_confirmed(db, order_ids: set[int]) -> dict[int, bool]:
    """고객컨펌 단계 주문만 도면 확정 여부를 읽는다(주문 데이터 JSONB — 그 단계 주문 몇 건뿐)."""
    if not order_ids:
        return {}
    rows = db.query(Order.id, Order.structured_data).filter(Order.id.in_(order_ids)).all()
    return {r.id: isinstance(r.structured_data, dict) and r.structured_data.get("drawing_status") == "CONFIRMED"
            for r in rows}


def _rows(db, org_id: int, names: dict[int, str]) -> list[dict[str, Any]]:
    result = (
        db.query(
            Order.id, Order.customer_name, Order.phone, Order.address, Order.product, Order.received_date,
            Order.erp_stage_code, Order.erp_construction_date, Order.as_axis_status, OrderAssignment.user_id,
        )
        .outerjoin(OrderAssignment, (OrderAssignment.order_id == Order.id) & (OrderAssignment.domain == "SALES")
                   & OrderAssignment.active.is_(True))
        .filter(Order.partner_org_id == org_id, Order.active_filter())
        .order_by(Order.id.desc())
        .limit(_SCAN_LIMIT)
        .all()
    )
    confirmed = _drawing_confirmed(db, {r.id for r in result if (r.erp_stage_code or "").upper() == "CONFIRM"})
    # 시공일 칸: 우리 시공일이 없으면 보낸 희망 시공일을 "(희망)"으로(사용자 2026-10-28).
    requested = pending_request_texts(db, {r.id for r in result if not r.erp_construction_date})
    rows: dict[int, dict[str, Any]] = {}
    for r in result:
        if r.id in rows:
            continue
        label = partner_stage_label(r.erp_stage_code, r.as_axis_status, confirmed.get(r.id))
        rows[r.id] = {
            "id": r.id, "customer_name": r.customer_name, "phone": r.phone, "address": r.address,
            "product": r.product, "received_date": r.received_date, "construction_date": r.erp_construction_date,
            "requested_construction": requested.get(r.id, ""),
            "stage_label": label, "turn": label == TURN_LABEL, "work": _work_text(label, r.erp_construction_date),
            "step": _STEP_OF_LABEL.get(label, 0), "manager_id": r.user_id, "manager_name": names.get(r.user_id, ""),
        }
    return list(rows.values())


def partner_order_board(db, org_id: int, user_id: int, filters: dict[str, str],
                        names: dict[int, str]) -> dict[str, Any]:
    """목록 화면 값 — 프로세스 맵 칸별 수(필터 전), 내 차례 수, 거른 작업 큐(최근 200건)."""
    rows = _rows(db, org_id, names)
    counts = {label: 0 for label in PARTNER_PIPELINE}
    for row in rows:
        counts[row["stage_label"]] = counts.get(row["stage_label"], 0) + 1
    picked = [
        row for row in rows
        if (not filters["stage"] or row["stage_label"] == filters["stage"])
        and (not filters["turn"] or row["turn"])
        and (not filters["mine"] or row["manager_id"] == user_id)
        and (not filters["manager"] or str(row["manager_id"]) == filters["manager"])
        and _matches_query(row, filters["q"])
    ]
    picked.sort(key=lambda row: not row["turn"])  # 내 차례를 맨 위로(그 안에서는 최신순 그대로)
    return {
        "pipeline": [{"label": label, "count": counts[label], "turn": label == TURN_LABEL} for label in PARTNER_PIPELINE],
        "turn_count": counts[TURN_LABEL],
        "orders": picked[:MAX_ROWS],
        "total": len(picked),
    }


def partner_turn_count(db, org_id: int) -> int:
    """머리 메뉴 "도면 확인 N" — 협력사 차례(고객컨펌 단계 · 도면 확정 · AS 건 열림 제외)."""
    ids = {
        r.id for r in db.query(Order.id).filter(
            Order.partner_org_id == org_id, Order.active_filter(), Order.erp_stage_code == "CONFIRM",
            or_(Order.as_axis_status.is_(None), ~Order.as_axis_status.in_(("RECEIVED", "IN_PROGRESS"))),
        )
    }
    return sum(1 for ok in _drawing_confirmed(db, ids).values() if ok)
