"""협력사 "도면 확인" 탭 — 확인 작업대(사용자 2026-10-30, 목업 승인).

목록이 아니라 내 차례인 건만 큰 카드: 도면 그림 줄 · 몇 차 · 언제 도착 · 지난번 내 요청 · 바로 누르는 단추
(도면 보기 · 수정 요청 · 확인했어요 / 이대로 만들어 주세요). 아래에 "도면팀이 고치는 중"(내가 수정 요청을
보낸 건)을 한 줄씩 남겨 보낸 요청을 잊지 않게 한다. 값은 협력사에게 보여도 되는 것만(drawing_tab.py 와 같은 규칙).
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from foms.services.datetime_kst import format_datetime_kst, parse_datetime_utc
from foms.services.orders.drawing_customer_send import drawing_round_info, round_text
from foms.services.partners.drawing_confirm import final_drawings_for_partner
from foms.services.partners.revision import pending_revision_for_partner
from models import Order

MAX_SHEETS = 6
MAX_NOTE = 120
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def _sheets(order: Order) -> tuple[list[dict[str, Any]], int]:
    """번호 붙은 도면 그림(그림만, 6장까지)과 전체 장수."""
    finals = final_drawings_for_partner(order)
    out = []
    for no, f in enumerate(finals, start=1):
        key = str(f.get("key") or "")
        name = str(f.get("filename") or key.rsplit("/", 1)[-1])
        if name.lower().endswith(_IMAGE_EXT) and len(out) < MAX_SHEETS:
            out.append({"no": no, "url": "/api/files/view/" + quote(key, safe="/"), "label": f"{no}번 · {name}"})
    return out, len(finals)


def _last_own_request(order: Order) -> str:
    """이 회사가 낸 마지막 수정 요청 메모(2차 이상일 때 '지난번 내 요청'으로)."""
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    for h in reversed(sd.get("drawing_transfer_history") or []):
        if isinstance(h, dict) and h.get("action") == "REQUEST_REVISION":
            if h.get("partner_org_id") is not None and h.get("partner_org_id") == order.partner_org_id:
                return str(h.get("note") or "").strip()[:MAX_NOTE]
            return ""
    return ""


def _arrived(order: Order) -> tuple[str, str]:
    """(정렬용 원문, 화면 글 'MM-DD HH:MM 도착')."""
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    last = sd.get("last_drawing_transfer") if isinstance(sd.get("last_drawing_transfer"), dict) else {}
    raw = str(last.get("transferred_at") or "")
    at = parse_datetime_utc(raw)
    return raw, (format_datetime_kst(at, "%m-%d %H:%M") + " 도착" if at else "")


def build_turn_board(db, rows: list[dict[str, Any]], sort: str) -> dict[str, Any]:
    """rows = 목록 줄(decorate_rows 뒤). 내 차례 카드 · 고치는 중 줄."""
    turn_ids = [r["id"] for r in rows if r["turn"]]
    fixing_ids = [r["id"] for r in rows if r.get("drawing_status") == "RETURNED"]
    ids = turn_ids + fixing_ids
    orders = {o.id: o for o in db.query(Order).filter(Order.id.in_(ids)).all()} if ids else {}
    by_id = {r["id"]: r for r in rows}
    cards = []
    for oid in turn_ids:
        order = orders.get(oid)
        if order is None:
            continue
        sheets, count = _sheets(order)
        raw, arrived = _arrived(order)
        info = drawing_round_info(order.structured_data or {})
        stage = (order.erp_stage_code or "").upper()
        cards.append({
            **by_id[oid], "sheets": sheets, "sheet_count": count, "arrived_raw": raw, "arrived": arrived,
            "round": round_text(info.round) if info.round else "", "kind": "approve" if stage == "CONFIRM" else "receive",
            "prev_request": _last_own_request(order) if (info.round or 0) > 1 else "",
        })
    if sort == "date":
        cards.sort(key=lambda c: (c["sort_day"] is None, str(c["sort_day"] or ""), -c["id"]))
    else:  # 도면 나온 순(기본) — 최근 도착이 위
        cards.sort(key=lambda c: c["arrived_raw"], reverse=True)
    fixing = []
    for oid in fixing_ids:
        order = orders.get(oid)
        if order is not None:
            fixing.append({**by_id[oid], "revision": pending_revision_for_partner(order)})
    return {"cards": cards, "fixing": fixing}
