"""공장 [도면 수정 요청] · 도면팀 [반영 완료] · [요청 반려] — 누가 · 글 · 쓰기(설계서 2026-11-25 §3-2 · §4-1 · §4-2 · N3 ~ N5, D4).

자료는 주문 JSON 서버 소유 칸 ``structured_data.drawing_fix.requests``(:mod:`foms.services.orders.drawing_fix`) — 요청 한 건 모양은 D2 가
읽는 꼴 그대로다::

    {id, from: "factory", targets, numbers, note, photos, factory, by_user_id, by_name, at, state: open|done|rejected,
     checked, checked_by_name, checked_at, resolved, done_at, rejected_by_user_id, rejected_by_name, rejected_at, reject_note}

이 모듈은 순수 함수(쿼리 0)다 — 라우트(``foms/api/production/drawing_request.py`` · ``foms/api/drawing/erp_orders_drawing_fix.py``)가
잠근 주문의 사본(deepcopy)에 부르고 재대입 · ``flag_modified`` 한다.

* 누가(§4-1 ``can_request_drawing_fix``): 관리자는 모든 도면, 반장 · 파트 계정은 자기 공장 도면만(사장님 2026-11-25 답 — ``factory_gate``
  와 같은 판정 ``part_access.can_write_sheet``), 단계가 생산일 때만. [반영 완료] · [요청 반려]는 ``can_fix_production_drawing``(부르는 쪽).
* 막힘: 열린 요청의 남은 대상(``drawing_fix.request_left``)이 그 도면을 막는다 — 보낸 순간부터(사장님 "요청하면 바로 막기").
  [반영 완료]는 ``checked`` 만 참(막힘 그대로 — 수정본이 가야 ``done``), [요청 반려]는 ``rejected``(막힘 풀림).
* 단계가 생산 밖으로 나가면(:func:`close_on_stage_exit`) 열린 요청을 ``done`` + ``via: stage_exit`` 로 닫는다 — 수정본도 반려도 아니라서
  닫힌 까닭을 요청 줄 · ``log`` 줄의 ``via`` 에 남긴다(D3 [수정 시작] 표시가 단계를 나가며 풀릴 때 쓰는 ``via`` 와 같은 낱말).
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Iterable, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.confirm_drawing_gate import normalize_stage_code
from foms.services.orders.drawing_factory import DRAWING_FIX_KEY, sheet_factory
from foms.services.orders.drawing_fix import (
    FIX_LOG_CAP,
    LOG_DONE,
    REQUEST_OPEN,
    fix_ident,
    numbers_text,
    request_left,
)
from foms.services.orders.drawing_transfer import clean_sheet_id
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.part_access import VIEW_ADMIN, VIEW_PART, VIEW_SUB, can_write_sheet, part_view_mode
from foms.services.production.factory_scope import other_factory_message
from foms.services.production.part_card_state import BLOCK_REVISE, order_block

#: 이벤트(``OrderEvent.event_type``) — 반려는 생산 '바뀐 것' 한 줄(``production_change_alerts``)이 읽는다.
REQUEST_EVENT = "PRODUCTION_DRAWING_REQUESTED"
REJECT_EVENT = "DRAWING_FIX_REQUEST_REJECTED"
CHECK_EVENT = "DRAWING_FIX_REQUEST_CHECKED"
STATE_DONE = "done"
STATE_REJECTED = "rejected"
LOG_REQUEST = "request"
LOG_REJECT = "reject"
#: 단계가 생산 밖으로 나가며 닫힌 요청(요청 줄 · ``log`` 줄의 ``via``) — ``drawing_fix_marks.VIA_STAGE_EXIT`` 와 같은 값.
VIA_STAGE_EXIT = "stage_exit"
STAGE_PRODUCTION = "PRODUCTION"
#: 사진 상한(사장님 답 Q4 "있으면 올리기" 3장까지).
MAX_PHOTOS = 3

#: 거절 code(§4-2) · 생산 단계 아님(§4-2 에 글이 없어 공장 완료 API 의 지금 글을 그대로 쓴다).
REQUEST_FORBIDDEN = "REQUEST_FORBIDDEN"
REQUEST_NOTE_REQUIRED = "REQUEST_NOTE_REQUIRED"
REQUEST_PICK = "REQUEST_PICK"
REQUEST_PHOTOS = "REQUEST_PHOTOS"
REJECT_NOTE_REQUIRED = "REJECT_NOTE_REQUIRED"
REQUEST_CLOSED = "REQUEST_CLOSED"
REQUEST_NOT_FOUND = "REQUEST_NOT_FOUND"
#: 이미 막힌 도면(고치는 중 · 영업 요청 · 열린 공장 요청)이 낀 요청 — 글은 그 막힘의 지금 글(``order_block`` 의 ``why``).
REQUEST_BLOCKED = "REQUEST_BLOCKED"
INVALID_STAGE = "INVALID_STAGE"
PHOTOS_TOO_MANY = "사진은 3장까지 올릴 수 있어요."
PHOTOS_BAD = "사진을 다시 올려 주세요."
MESSAGES = {
    REQUEST_FORBIDDEN: "도면 수정 요청은 반장이나 그 도면 파트 담당만 할 수 있어요.",
    REQUEST_NOTE_REQUIRED: "사유를 적어 주세요.",
    REQUEST_PICK: "수정할 도면을 골라 주세요.",
    REQUEST_PHOTOS: PHOTOS_BAD,
    REJECT_NOTE_REQUIRED: "반려 사유를 적어 주세요.",
    REQUEST_CLOSED: "이미 처리된 요청이에요. 화면을 다시 열어 주세요.",
    # 없는 요청 번호(손으로 만든 주소 · 지워진 줄)도 "다시 열어 주세요"가 맞는 답이라 같은 글을 쓴다(새 글 없음).
    REQUEST_NOT_FOUND: "이미 처리된 요청이에요. 화면을 다시 열어 주세요.",
    INVALID_STAGE: "생산 단계 주문이 아니에요. [다시 받기]를 눌러 주세요.",
}


class RequestRefusal(Exception):
    """공장 요청 · 반려 · 반영 완료 거절 — ``status`` · ``code`` · ``message``(§4-2 글)."""

    def __init__(self, status: int, code: str, message: Optional[str] = None) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message or MESSAGES[code]


# --------------------------------------------------------------------------- #
# 누가(§4-1)
# --------------------------------------------------------------------------- #
def can_request_people(user: Any) -> bool:
    """[도면 수정 요청]을 누를 수 있는 사람인지(주문 · 도면과 상관없는 몫) — 관리자 · 반장 · 파트 계정."""
    return part_view_mode(user) in (VIEW_ADMIN, VIEW_SUB, VIEW_PART)


def can_request_entry(user: Any, sd: Any, entry: dict[str, Any]) -> bool:
    """그 도면에 요청할 수 있는지 — 관리자는 모든 도면, 반장 · 파트 계정은 자기 공장 도면만(사장님 2026-11-25 답 "자기 공장 도면만" —
    카드 쓰기 ``factory_gate`` 와 같은 ``can_write_sheet``). 창 고르기 · 판 단추 · 사진 길 주문 문 · 서버 판정이 모두 이 함수다."""
    mode = part_view_mode(user)
    if mode == VIEW_ADMIN:
        return True
    return mode in (VIEW_SUB, VIEW_PART) and can_write_sheet(user, sheet_factory(sd, entry))


def forbidden_message(user: Any, sd: Any, entries: Iterable[dict[str, Any]]) -> str:
    """403 글 — 고른 도면 중 남의 공장 도면이 있으면 카드 쓰기가 남의 공장에서 쓰는 지금 글("2공장에서 작업하는 도면이에요. 위
    [다시 받기]를 눌러 주세요."), 없으면 ``REQUEST_FORBIDDEN`` 지금 글."""
    if can_request_people(user):
        for entry in entries:
            if not can_request_entry(user, sd, entry):
                return other_factory_message(sheet_factory(sd, entry))
    return MESSAGES[REQUEST_FORBIDDEN]


def can_request_drawing_fix(user: Any, order: Any, entries: Iterable[dict[str, Any]]) -> bool:
    """공장 요청 술어(§4-1) — 단계가 생산이고, 사람이 되고, 고른 도면이 모두 그 사람 몫인지(고른 도면이 없으면 사람 · 단계만).

    Args:
        user: 누른 사람(이미 읽은 행). order: 주문. entries: 고른 확정 도면 항목.
    """
    if order is None or read_main_stage(order) != STAGE_PRODUCTION or not can_request_people(user):
        return False
    sd = getattr(order, "structured_data", None)
    return all(can_request_entry(user, sd, entry) for entry in entries)


def entry_block(sd: Any, entry: dict[str, Any]) -> Optional[dict[str, str]]:
    """그 도면이 이미 '도면 고치는 중'으로 막혔는지 — 도면 판 카드와 같은 함수(``part_card_state.order_block`` 의 도면 막힘,
    보류는 보지 않는다 — 판도 보류 카드에는 단추를 그린다). 막혔으면 ``{kind, text, why, code}``, 아니면 None."""
    block = order_block({"structured_data": sd}, entry)
    return block if block and block.get("kind") == BLOCK_REVISE else None


def has_requestable_drawing(user: Any, sd: Any) -> bool:
    """그 주문에 이 사람이 요청할 수 있는 도면이 한 장이라도 있는지 — 사람 · 공장만 본다(막힘은 안 본다, 사진 길 문)."""
    return can_request_people(user) and any(can_request_entry(user, sd, e) for e in resolve_final_drawing_files(sd))


def requestable_entries(user: Any, sd: Any) -> list[dict[str, Any]]:
    """창의 '어느 도면인가요?' 고르기 — 지금 확정 도면 중 이 사람이 요청할 수 있고 아직 안 막힌 장(번호 순).

    이미 막힌 장(:func:`entry_block` — 판에서 단추 대신 '도면 고치는 중'이 서는 그 카드)은 뺀다(서버도 409 ``REQUEST_BLOCKED``).
    한 장 = ``{no, sheet_id}``(마법사 시트) 또는 ``{no, key}``(직접 올린 파일) — 번호를 뺀 나머지가 그대로 N3 ``targets`` 한 칸이다
    (판 카드마다 싣는 글이라 짧게).
    """
    if not can_request_people(user):
        return []
    out = []
    for no, entry in enumerate(resolve_final_drawing_files(sd), 1):
        if can_request_entry(user, sd, entry) and entry_block(sd, entry) is None:
            sid = clean_sheet_id(entry.get("sheet_id"))
            out.append({"no": no, "sheet_id": sid} if sid else {"no": no, "key": entry["key"]})
    return out


def board_request_options(user: Any, rows: Iterable[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """도면 판 [도면 수정 요청] 창의 고르기 — 생산 단계 주문마다 :func:`requestable_entries`(이미 든 주문 JSON — 쿼리 0).

    요청할 수 없는 사람(읽기 전용 등)은 빈 사전 — 판에 단추 · 창이 없다. 시공 대기 등 생산 밖 주문은 빠진다(서버도 409).
    """
    if not can_request_people(user):
        return {}
    return {int(row["id"]): requestable_entries(user, row.get("structured_data") or {}) for row in rows
            if normalize_stage_code(row.get("raw_stage")) == STAGE_PRODUCTION}


# --------------------------------------------------------------------------- #
# 몸 읽기
# --------------------------------------------------------------------------- #
def clean_note(raw: Any) -> str:
    """사유 · 반려 사유 — 공백만은 빈 글."""
    return raw.strip() if isinstance(raw, str) else ""


def request_id(user_id: Any, idem_key: Optional[str]) -> str:
    """요청 번호 — 멱등 열쇠가 있으면 (사람, 열쇠)에서 늘 같은 값(다시 보낸 요청이 같은 줄을 가리킨다), 없으면 새 값."""
    if idem_key:
        return "fr_" + hashlib.sha256(f"{user_id}:{idem_key}".encode("utf-8")).hexdigest()[:12]
    return "fr_" + uuid.uuid4().hex[:12]


def photo_rows(files: list[dict[str, Any]]) -> list[dict[str, str]]:
    """검사를 지난 사진(``drawing_revision_files.normalize_revision_files`` 값) → 저장 모양 ``[{key, filename}]``."""
    return [{"key": f["key"], "filename": f["filename"]} for f in files]


# --------------------------------------------------------------------------- #
# 쓰기(제자리 — 부르는 쪽이 사본 재대입 · flag_modified)
# --------------------------------------------------------------------------- #
def _table(sd: dict[str, Any]) -> dict[str, Any]:
    table = sd.get(DRAWING_FIX_KEY)
    if not isinstance(table, dict):
        table = {}
        sd[DRAWING_FIX_KEY] = table
    if not isinstance(table.get("requests"), list):
        table["requests"] = []
    return table


def _log(table: dict[str, Any], row: dict[str, Any]) -> None:
    log = [r for r in table.get("log") or [] if isinstance(r, dict)]
    log.append(row)
    table["log"] = log[-FIX_LOG_CAP:]


def add_request(sd: dict[str, Any], picked: list[tuple[int, dict[str, Any]]], *, rid: str, note: str,
                photos: list[dict[str, str]], user_id: Optional[int], by_name: str, at: str) -> dict[str, Any]:
    """공장 요청 한 건을 적는다(열림 — 고른 도면이 바로 막힌다) + ``log`` 에 ``request`` 한 줄.

    Args:
        sd: 고칠 사본. picked: ``drawing_fix_marks.resolve_targets`` 값(번호, 확정 도면 항목) — 번호 순.
        rid: :func:`request_id`. note: 사유(빈 글 아님). photos: :func:`photo_rows`.
        user_id · by_name: 누른 사람. at: 누른 때(UTC iso ``…Z``).

    Returns:
        적은 요청(사본 안의 그 dict). ``factory`` = 고른 첫 도면의 공장(파트 계정은 자기 공장 도면만 고른다).
    """
    targets = [fix_ident(entry) for _no, entry in picked]
    numbers = [no for no, _entry in picked]
    request = {"id": rid, "from": "factory", "targets": targets, "numbers": numbers, "note": note, "photos": photos,
               "factory": sheet_factory(sd, picked[0][1]), "by_user_id": user_id, "by_name": by_name, "at": at,
               "state": REQUEST_OPEN, "checked": False, "checked_by_name": None, "checked_at": None, "resolved": [],
               "done_at": None, "rejected_by_user_id": None, "rejected_by_name": None, "rejected_at": None, "reject_note": None}
    table = _table(sd)
    table["requests"].append(request)
    _log(table, {"act": LOG_REQUEST, "idents": targets, "numbers": numbers, "requests": [rid], "by_name": by_name, "at": at})
    return request


def find_request(sd: Any, rid: Any) -> Optional[dict[str, Any]]:
    """요청 번호로 공장 요청 한 건(사본 안의 그 dict) — 없으면 None."""
    table = sd.get(DRAWING_FIX_KEY) if isinstance(sd, dict) else None
    requests = table.get("requests") if isinstance(table, dict) else None
    wanted = str(rid or "")
    return next((r for r in requests or [] if isinstance(r, dict) and wanted and str(r.get("id") or "") == wanted), None)


def left_numbers(sd: Any, request: dict[str, Any]) -> list[int]:
    """요청이 아직 막는 도면(``request_left``)의 번호 — 지금 도면으로 다시 센다(못 세면 적힌 번호 중 그 열쇠 몫), 번호 순."""
    left = request_left(request)
    current = {fix_ident(entry): no for no, entry in enumerate(resolve_final_drawing_files(sd), 1)}
    stored = dict(zip(request.get("targets") or [], request.get("numbers") or []))
    numbers = {current.get(ident, stored.get(ident)) for ident in left}
    return sorted(n for n in numbers if isinstance(n, int) and not isinstance(n, bool))


def reject_request(sd: dict[str, Any], request: dict[str, Any], *, note: str, user_id: Optional[int], by_name: str,
                   at: str) -> list[int]:
    """[요청 반려] — ``rejected`` + 반려한 사람 · 때 · 사유(막힘 풀림) + ``log`` 에 ``reject`` 한 줄.

    Returns:
        풀린 도면 번호(반려 전 남은 대상).
    """
    numbers = left_numbers(sd, request)
    idents = request_left(request)
    request.update(state=STATE_REJECTED, rejected_by_user_id=user_id, rejected_by_name=by_name, rejected_at=at,
                   reject_note=note)
    _log(_table(sd), {"act": LOG_REJECT, "idents": idents, "numbers": numbers, "requests": [request.get("id")],
                      "by_name": by_name, "at": at})
    return numbers


def check_request(request: dict[str, Any], checked: bool, *, by_name: str, at: str) -> None:
    """[반영 완료] · [완료 해제] — ``checked`` 와 누른 사람 · 때(해제면 비움). 상태(``open``)와 막힘은 그대로."""
    request.update(checked=checked, checked_by_name=by_name if checked else None, checked_at=at if checked else None)


def open_requests(sd: Any) -> list[dict[str, Any]]:
    """열린 공장 요청(``state == "open"``)."""
    table = sd.get(DRAWING_FIX_KEY) if isinstance(sd, dict) else None
    requests = table.get("requests") if isinstance(table, dict) else None
    return [r for r in requests or [] if isinstance(r, dict) and r.get("state") == REQUEST_OPEN]


def close_on_stage_exit(sd: dict[str, Any], *, by_name: str, at: str, to_stage: str) -> list[str]:
    """단계가 생산 밖으로 나가는 쓰기 안에서 열린 공장 요청을 모두 닫는다(사장님 답 "둘 다" — 저절로 풂).

    상태는 설계서 값 안에서 ``done``(닫힘)으로 두고, 수정본으로 닫힌 것이 아니라는 까닭을 요청 줄 ``via: stage_exit`` · ``done_at`` 과
    ``log`` 의 ``done`` 줄(``via: stage_exit`` · ``to``)에 남긴다 — 반려가 아니므로 반려한 사람 · 사유 · 알림은 없다. ``drawing_fix`` 칸과
    요청 목록은 새 dict · list 로 바꿔 끼운다(셸 복사로 넘기는 자리의 옛 값을 건드리지 않게 — D3 ``clear_fixing_on_stage_exit`` 와 같다).

    Args:
        sd: 쓰는 쪽 ``structured_data`` 사본. by_name: 그 단계 쓰기를 한 사람. at: 그 때(UTC iso). to_stage: 나간 단계(영문 코드).

    Returns:
        닫은 요청 번호(없으면 빈 목록 — 쓰지 않았다).
    """
    table = sd.get(DRAWING_FIX_KEY) if isinstance(sd, dict) else None
    if not open_requests(sd):
        return []
    fresh = dict(table)
    fresh["requests"] = [dict(r) if isinstance(r, dict) else r for r in table.get("requests") or []]
    closed, idents, numbers = [], [], []
    for request in fresh["requests"]:
        if isinstance(request, dict) and request.get("state") == REQUEST_OPEN:
            idents += request_left(request)
            numbers += left_numbers(sd, request)
            request.update(state=STATE_DONE, done_at=at, via=VIA_STAGE_EXIT)
            closed.append(str(request.get("id") or ""))
    _log(fresh, {"act": LOG_DONE, "idents": sorted(set(idents)), "numbers": sorted(set(numbers)), "requests": closed,
                 "closed": closed, "by_name": by_name, "at": at, "via": VIA_STAGE_EXIT, "to": to_stage})
    sd[DRAWING_FIX_KEY] = fresh
    return closed


# --------------------------------------------------------------------------- #
# 글(§10)
# --------------------------------------------------------------------------- #
def numbers_label(numbers: list[int]) -> str:
    """감사 · '바뀐 것' 글의 번호 "도면 3" · "도면 2 · 3"."""
    return f"도면 {numbers_text(numbers)}"


def reject_body(numbers: list[int]) -> str:
    """[요청 반려] 창 본문(§2-2 · §10) — "반려 사유를 적어 주세요. 요청한 사람에게 알림이 가고, 도면 3 막힘이 풀려요."."""
    return f"반려 사유를 적어 주세요. 요청한 사람에게 알림이 가고, {numbers_label(numbers)} 막힘이 풀려요."


def order_label(order_id: int, customer: str) -> str:
    """알림 글의 주문 표기 — "주문 #5801 (정하늘)"(영업 수정 요청 알림과 같은 꼴)."""
    return f"주문 #{order_id}" + (f" ({customer})" if customer else "")


def request_message(order_id: int, customer: str, numbers: list[int], note: str) -> str:
    """공장 요청 알림 글(§10) — 반려 알림과 같은 말투 · 같은 번호 꼴(2026-11-26): "… 공장 도면 수정 요청이 접수됐어요. 대상: 도면 2 · 3. 사유: …"."""
    target = f" 대상: {numbers_label(numbers)}." if numbers else ""
    return f"{order_label(order_id, customer)} 공장 도면 수정 요청이 접수됐어요.{target} 사유: {note}"


def reject_message(order_id: int, customer: str, numbers: list[int], note: str) -> str:
    """반려 알림 글(§10) — "주문 #5801 (정하늘) 도면 3 수정 요청이 반려됐어요. 사유: …"."""
    return f"{order_label(order_id, customer)} {numbers_label(numbers)} 수정 요청이 반려됐어요. 사유: {note}"


def reject_detail(numbers: list[int], note: str) -> str:
    """생산 '바뀐 것' 반려 줄의 자세한 글(§2-4 · §10) — "도면 3 · 사유: …"(누가 · 언제는 화면이 앞에 붙인다)."""
    return f"{numbers_label(numbers)} · 사유: {note}" if note else numbers_label(numbers)


__all__ = [
    "CHECK_EVENT", "INVALID_STAGE", "LOG_REJECT", "LOG_REQUEST", "MAX_PHOTOS", "MESSAGES", "PHOTOS_BAD", "PHOTOS_TOO_MANY",
    "REJECT_EVENT", "REJECT_NOTE_REQUIRED", "REQUEST_CLOSED", "REQUEST_EVENT", "REQUEST_FORBIDDEN",
    "REQUEST_BLOCKED", "REQUEST_NOTE_REQUIRED", "REQUEST_NOT_FOUND", "REQUEST_PHOTOS", "REQUEST_PICK", "RequestRefusal",
    "STATE_DONE", "STATE_REJECTED", "VIA_STAGE_EXIT", "add_request", "board_request_options", "can_request_drawing_fix", "can_request_entry",
    "can_request_people", "check_request", "clean_note", "close_on_stage_exit", "entry_block", "find_request", "forbidden_message", "has_requestable_drawing", "left_numbers", "numbers_label", "open_requests", "order_label", "photo_rows", "reject_body", "reject_detail", "reject_message",
    "reject_request", "request_id", "request_message", "requestable_entries",
]
