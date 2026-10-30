"""협력사 주문 화면 도면 탭 — 우리 도면 작업실 휴대폰 화면(차례 띠 · 단계 · 도면 목록 · 주고받은 기록)과 같은 모양.

사용자 요청 2026-10-30 "도면 탭도 FOMS 와 같은 방식으로". 우리 화면(``templates/drawing/partials/
workbench_mobile_handoff.html``)은 직원 이름 · 내부 메모 · 고객 발송 기록을 싣으므로 그대로 쓰지 않고, 협력사에게
보여도 되는 값만 여기서 고른다(``history.py`` 와 같은 규칙):

* 우리 직원 이름 대신 "저희 도면팀" · "저희 담당자". 도면팀 전달 메모 · 우리 쪽이 낸 수정 요청 내용은 싣지 않는다.
* 이 회사가 낸 수정 요청은 메모 · 참고 사진까지 싣는다(자기 회사 일).
"""
from __future__ import annotations

from typing import Any

from foms.services.datetime_kst import format_datetime_kst, parse_datetime_utc
from foms.services.orders.drawing_revision_files import is_revision_reference_key

OUR_DRAWING_TEAM = "저희 도면팀"
OUR_STAFF = "저희 담당자"
_PARTNER_SUFFIX = " (협력사)"
MAX_NOTE = 300
MAX_REFS = 10
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic")


def _when(value: Any) -> tuple[Any, str]:
    at = parse_datetime_utc(value)
    return at, (format_datetime_kst(at, "%m-%d %H:%M") if at else "")


def _partner_name(entry: dict[str, Any]) -> str:
    """협력사 사람이 한 일이면 그 이름(꼬리 뺌), 아니면 빈 문자열."""
    name = str(entry.get("by_user_name") or "")
    return name[: -len(_PARTNER_SUFFIX)] if name.endswith(_PARTNER_SUFFIX) else ""


def _refs(order_id: int, files: Any) -> list[dict[str, Any]]:
    """이 회사가 올린 수정 요청 참고 사진 — 이 주문 수정 요청 폴더 key 만(주소는 화면 쪽이 key 로 만든다)."""
    rows = []
    for f in (files or [])[:MAX_REFS]:
        key = str((f or {}).get("key") or "") if isinstance(f, dict) else ""
        if not key or not is_revision_reference_key(order_id, key):
            continue
        name = str(f.get("filename") or key.rsplit("/", 1)[-1])
        rows.append({"key": key, "filename": name, "is_image": name.lower().endswith(_IMAGE_EXT)})
    return rows


def _thread(order: Any, history: list[Any]) -> list[dict[str, Any]]:
    """주고받은 기록(최신이 위). 왼쪽 = 저희, 오른쪽 = 이 회사."""
    events: list[dict[str, Any]] = []
    revisions = 0
    for h in history:
        if not isinstance(h, dict):
            continue
        action = h.get("action")
        if action == "TRANSFER":
            at, at_text = _when(h.get("transferred_at") or h.get("at"))
            count = int(h.get("files_count") or len(h.get("files") or []))
            events.append({"side": "left", "who": OUR_DRAWING_TEAM, "tag": f"{revisions + 1}차 도면 올림",
                           "note": f"도면 {count}장", "refs": [], "at": at, "at_text": at_text})
        elif action == "REQUEST_REVISION":
            revisions += 1
            at, at_text = _when(h.get("at"))
            own = h.get("partner_org_id") is not None and h.get("partner_org_id") == order.partner_org_id
            events.append({
                "side": "right" if own else "left", "who": (_partner_name(h) or "협력사") if own else OUR_STAFF,
                "tag": "수정 요청", "note": str(h.get("note") or "").strip()[:MAX_NOTE] if own else "",
                "refs": _refs(order.id, h.get("files")) if own else [], "at": at, "at_text": at_text,
            })
        elif action == "CONFIRM_RECEIPT":
            at, at_text = _when(h.get("at"))
            name = _partner_name(h)
            events.append({"side": "right" if name else "left", "who": name or OUR_STAFF,
                           "tag": "도면 확인했어요" if name else "도면 확정", "note": "", "refs": [],
                           "at": at, "at_text": at_text})
    events.sort(key=lambda e: (e["at"] is None, e["at"]), reverse=True)
    return events


def _turn(stage: str, finals: list, status: str, flags: dict[str, bool]) -> dict[str, str]:
    """차례 띠 — tone mine(이 회사 차례) · other(저희 차례) · done(확정 뒤)."""
    if flags["can_receive"]:
        return {"tone": "mine", "label": "내 차례 · 도면 확인", "sub": "도면을 보고 '도면 확인했어요' 또는 '수정 요청'을 눌러 주세요."}
    if flags["can_approve"]:
        return {"tone": "mine", "label": "내 차례 · 고객 확인",
                "sub": "고객과 확인한 뒤 '이대로 만들어 주세요'를 누르면 제작을 시작합니다."}
    if status == "RETURNED" and stage in ("DRAWING", "CONFIRM"):
        return {"tone": "other", "label": "저희 도면팀 차례 · 고치는 중", "sub": "고친 도면을 다시 보내면 알림이 갑니다."}
    if stage in ("RECEIVED", "MEASURE", "DRAWING", "CONFIRM", ""):
        if not finals:
            return {"tone": "other", "label": "저희 도면팀 차례 · 그리는 중", "sub": "도면이 올라오면 알림이 갑니다."}
        return {"tone": "other", "label": "저희 차례 · 확인 중", "sub": "저희가 도면을 확인하고 있습니다."}
    return {"tone": "done", "label": "도면 확정", "sub": "이 도면대로 제작합니다."}


def _steps(stage: str, finals: list, status: str, sd: dict[str, Any]) -> list[dict[str, str]]:
    """도면 올라옴 → 도면 확인 → 제작 요청("이대로 만들어 주세요"). 상태 done · now · todo."""
    received = status == "CONFIRMED" or stage not in ("RECEIVED", "MEASURE", "DRAWING", "CONFIRM", "")
    approved = bool((sd.get("blueprint") or {}).get("customer_confirmed")) and stage not in ("DRAWING", "CONFIRM")
    sent = bool(finals) and status in ("TRANSFERRED", "CONFIRMED") or received
    marks = [sent, received, approved]
    now = next((i for i, done in enumerate(marks) if not done), None)
    labels = ("도면 올라옴", "도면 확인", "제작 요청")
    return [{"label": label, "state": "done" if marks[i] else ("now" if i == now else "todo")}
            for i, label in enumerate(labels)]


def build_partner_drawing_tab(order: Any, finals: list[dict[str, Any]], *, can_receive: bool,
                              can_approve: bool) -> dict[str, Any]:
    """도면 탭 값 — 차례 띠 · 단계 · 주고받은 기록 · 도면 장수."""
    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    stage = (order.erp_stage_code or "").upper()
    status = str(sd.get("drawing_status") or "")
    flags = {"can_receive": can_receive, "can_approve": can_approve}
    return {
        "turn": _turn(stage, finals, status, flags),
        "steps": _steps(stage, finals, status, sd),
        "thread": _thread(order, list(sd.get("drawing_transfer_history") or [])),
        "count": len(finals),
    }
