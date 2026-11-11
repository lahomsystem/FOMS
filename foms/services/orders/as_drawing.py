"""완료 주문 AS 도면 차수(round) — 순수 계산·``commit`` 없음.

설계서 ``docs/specs/2026-11-11-as-drawing-after-completion_SPEC.md``.

시공이 끝난 주문(main stage ``CS``·``COMPLETED``)에 AS 가 오면 도면팀이 원래 최종 도면을 건드리지
않고 AS 도면만 따로 그려 보낸다. 이 모듈은 그 차수를 ``structured_data['as_drawing']`` 아래에
쌓는 규칙의 정본이다.

- 원래 최종 도면 키(``drawing_current_files``·``drawing_status``·``drawing_transfer_history`` 등)는
  여기서 절대 쓰지 않는다.
- 차수 안에서는 최종본만 남긴다 — 같은 시트의 새 판은 옛 판을 그 자리에서 바꾼다.
- AS 단계에서 마법사 저장은 원래 시트(차수 표시 없음)와 지난 차수 시트를 **저장된 그대로 지킨다**
  (:func:`apply_sheet_lock`). 보낸 값은 버리고 무엇을 지켰는지 돌려준다 — 자동 저장을 409 로 막으면
  도면팀 화면이 저장 실패를 반복한다.

호출자가 잠근 행의 ``structured_data`` 사본을 넘기고, 쓰기·``flag_modified``·commit 은 호출자가 한다.
"""
from __future__ import annotations

import copy
import uuid
from typing import Any, Iterable, Mapping, Optional

from foms.services.orders.as_cycle_service import AS_COMPLETED, AS_NONE, current_cycle, cycle_status
from foms.services.orders.drawing_key_safety import as_drawing_keys
from foms.services.orders.state_axes import read_as_status, read_main_stage

AS_DRAWING_KEY = "as_drawing"
#: 목록 SQL 이 단순 같음 비교로 읽는 평평한 키(현재·마지막 차수 상태).
AS_DRAWING_STATUS_KEY = "as_drawing_status"
#: 마법사 시트에 다는 차수 표시. 없으면 원래 시트다.
SHEET_ROUND_KEY = "as_round_id"

#: AS 도면을 그리는 main stage — 시공이 끝난 뒤.
AS_DRAWING_STAGES = frozenset({"CS", "COMPLETED"})

STATUS_WAITING = "WAITING"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_TRANSFERRED = "TRANSFERRED"
STATUS_RETURNED = "RETURNED"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_CANCELLED = "CANCELLED"
OPEN_STATUSES = (STATUS_WAITING, STATUS_IN_PROGRESS, STATUS_TRANSFERRED, STATUS_RETURNED)

SOURCE_AS_REQUEST = "AS_REQUEST"
SOURCE_DRAWING_FIRST = "DRAWING_FIRST"

_MAX_MEMO = 500
_MAX_NOTE = 500
_MAX_HISTORY = 200


class ASDrawingError(ValueError):
    """차수 규칙 위반. ``code`` 는 화면이 가르는 값, ``status`` 는 HTTP 상태."""

    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def is_as_drawing_stage(order: Any) -> bool:
    """AS 도면을 그리는 주문인가 — 시공이 끝난 main stage, 또는 main stage 가 AS 표기로만 남은 옛 주문."""
    stage = read_main_stage(order)
    if stage in AS_DRAWING_STAGES:
        return True
    return stage is None and read_as_status(order) not in ("", AS_NONE)


def _block(sd: Mapping) -> dict:
    block = sd.get(AS_DRAWING_KEY) if isinstance(sd, Mapping) else None
    return block if isinstance(block, dict) else {}


def rounds(sd: Mapping) -> list[dict]:
    """차수 목록(오래된 것부터). dict 가 아닌 항목은 뺀다."""
    items = _block(sd).get("rounds")
    return [r for r in items if isinstance(r, dict)] if isinstance(items, list) else []


def current_round(sd: Mapping) -> Optional[dict]:
    """열린 차수(WAITING·IN_PROGRESS·TRANSFERRED·RETURNED). 없으면 None."""
    block = _block(sd)
    rid = block.get("current_round_id")
    if not rid:
        return None
    for r in rounds(sd):
        if r.get("round_id") == rid and r.get("status") in OPEN_STATUSES:
            return r
    return None


def round_no(sd: Mapping, rnd: Mapping) -> int:
    """화면에 쓰는 차수 번호(그만둔 차수는 세지 않는다)."""
    no = 0
    for r in rounds(sd):
        if r.get("status") != STATUS_CANCELLED:
            no += 1
        if r.get("round_id") == rnd.get("round_id"):
            return no if rnd.get("status") != STATUS_CANCELLED else int(rnd.get("no") or no or 1)
    return int(rnd.get("no") or 1)


def _sync_flat_status(sd: dict) -> None:
    items = rounds(sd)
    if not items:
        sd.pop(AS_DRAWING_STATUS_KEY, None)
        return
    cur = current_round(sd)
    sd[AS_DRAWING_STATUS_KEY] = (cur or items[-1]).get("status")


def _history_append(rnd: dict, entry: dict) -> None:
    hist = rnd.get("history")
    if not isinstance(hist, list):
        hist = []
        rnd["history"] = hist
    hist.append(entry)
    if len(hist) > _MAX_HISTORY:
        del hist[: len(hist) - _MAX_HISTORY]


def _clean_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def open_as_cycle_id(sd: Mapping) -> Optional[str]:
    """열린(접수·진행) AS cycle id. 없으면 None."""
    cycle = current_cycle(sd if isinstance(sd, dict) else {})
    if cycle is None or cycle_status(cycle) in (AS_NONE, AS_COMPLETED):
        return None
    cid = str(cycle.get("cycle_id") or "").strip()
    return cid or None


def open_round(
    sd: dict, *, source: str, status: str, memo: str, actor_id: Optional[int], actor_name: str,
    now_iso: str, cycle_id: Optional[str] = None, registered_as: bool = False,
) -> dict:
    """새 차수를 연다. 이미 열린 차수가 있으면 ``AS_DRAWING_OPEN``(409).

    Args:
        sd: 잠근 행의 structured_data 사본(이 함수가 고친다).
        source: :data:`SOURCE_AS_REQUEST`(AS 담당 부탁) · :data:`SOURCE_DRAWING_FIRST`(도면팀 시작).
        status: 처음 상태 — 부탁은 WAITING, 도면팀 시작은 IN_PROGRESS.
        memo: 무엇을 그리는지 한 줄(빈 값이면 화면이 AS 내용을 대신 보여 준다).
        actor_id / actor_name: 연 사람.
        now_iso: UTC naive ISO 시각.
        cycle_id: 묶을 AS cycle id(없으면 None).
        registered_as: 도면팀이 이 차수와 함께 AS 접수까지 했는가.

    Returns:
        새 차수 dict(``sd`` 안의 같은 객체).
    """
    if source not in (SOURCE_AS_REQUEST, SOURCE_DRAWING_FIRST):
        raise ASDrawingError("BAD_SOURCE", "알 수 없는 시작 방법입니다.", 400)
    if status not in (STATUS_WAITING, STATUS_IN_PROGRESS):
        raise ASDrawingError("BAD_STATUS", "알 수 없는 처음 상태입니다.", 400)
    if current_round(sd) is not None:
        raise ASDrawingError("AS_DRAWING_OPEN", "이미 그리고 있는 AS 도면이 있어요.")
    block = sd.get(AS_DRAWING_KEY)
    if not isinstance(block, dict):
        block = {}
        sd[AS_DRAWING_KEY] = block
    items = block.get("rounds")
    if not isinstance(items, list):
        items = []
        block["rounds"] = items
    action = "REQUEST" if source == SOURCE_AS_REQUEST else "START"
    rnd = {
        "round_id": "asd_" + uuid.uuid4().hex[:12],
        "no": sum(1 for r in items if isinstance(r, dict) and r.get("status") != STATUS_CANCELLED) + 1,
        "source": source,
        "cycle_id": cycle_id,
        "status": status,
        "memo": _clean_text(memo, _MAX_MEMO),
        "opened_at": now_iso,
        "opened_by": actor_id,
        "opened_by_name": actor_name or "",
        "registered_as": bool(registered_as),
        "files": [],
        "history": [],
    }
    _history_append(rnd, {"action": action, "at": now_iso, "by": actor_id, "by_name": actor_name or "",
                          "note": rnd["memo"]})
    items.append(rnd)
    block["current_round_id"] = rnd["round_id"]
    _sync_flat_status(sd)
    return rnd


def _sheets(sd: Mapping) -> list[dict]:
    wiz = sd.get("drawing_wizard") if isinstance(sd, Mapping) else None
    items = wiz.get("sheets") if isinstance(wiz, Mapping) else None
    return [s for s in items if isinstance(s, dict)] if isinstance(items, list) else []


def round_sheet_ids(sd: Mapping, round_id: str) -> list[str]:
    """이 차수 시트 id(마법사 시트 순서)."""
    return [str(s.get("id")) for s in _sheets(sd)
            if s.get("id") and s.get(SHEET_ROUND_KEY) == round_id]


def as_sheet_ids(sd: Mapping) -> set[str]:
    """차수 표시가 붙은 시트 id 전부(어느 차수든)."""
    return {str(s.get("id")) for s in _sheets(sd) if s.get("id") and s.get(SHEET_ROUND_KEY)}


def apply_sheet_lock(order: Any, sd: dict, saved_sheets: Any, incoming_sheets: Any,
                     *, actor_id: Optional[int] = None, actor_name: str = "",
                     now_iso: str = "") -> tuple[list, dict]:
    """AS 단계 마법사 저장에서 원래 시트·지난 차수 시트를 저장된 그대로 지킨다.

    AS 단계가 아니면 ``incoming_sheets`` 를 그대로 돌려준다(지금 동작 그대로).

    AS 단계면:

    - 잠긴 시트(열린 차수 표시가 없는 저장된 시트)는 저장된 사본으로 되돌리고, 빠졌으면 다시 넣는다.
    - 열린 차수가 있으면 새 시트와 그 차수 시트를 받아들이고 차수 표시를 서버가 붙인다.
      부탁(WAITING) 차수에 첫 AS 시트가 생기면 작업중(IN_PROGRESS)으로 바꾼다.
    - 열린 차수가 없으면 새 시트는 버린다.
    - 순서: 잠긴 시트(저장된 순서) 다음에 AS 시트(보낸 순서). 원래 도면 번호가 밀리지 않는다.

    Args:
        order: 대상 주문(단계 판정).
        sd: 잠근 행의 structured_data 사본(차수 상태가 바뀔 수 있다).
        saved_sheets: 저장돼 있던 시트 목록.
        incoming_sheets: 화면이 보낸 시트 목록(검증 통과).

    Returns:
        ``(저장할 시트 목록, 보고)``. 보고는 ``{"kept": [...], "dropped": [...], "tagged": [...]}``.
    """
    report: dict = {"kept": [], "dropped": [], "tagged": []}
    incoming = [s for s in incoming_sheets if isinstance(s, dict)] if isinstance(incoming_sheets, list) else []
    saved = [s for s in saved_sheets if isinstance(s, dict)] if isinstance(saved_sheets, list) else []
    if not is_as_drawing_stage(order):
        # 차수 표시는 서버만 붙인다 — 화면이 보낸 표시는 저장돼 있던 값으로 되돌린다.
        saved_tags = {str(s.get("id")): s.get(SHEET_ROUND_KEY) for s in saved if s.get("id")}
        out = []
        for sheet in incoming:
            tag = saved_tags.get(str(sheet.get("id") or ""))
            if sheet.get(SHEET_ROUND_KEY) != tag:
                sheet = copy.deepcopy(sheet)
                if tag:
                    sheet[SHEET_ROUND_KEY] = tag
                else:
                    sheet.pop(SHEET_ROUND_KEY, None)
            out.append(sheet)
        return out, report
    cur = current_round(sd)
    open_id = cur.get("round_id") if cur else None
    saved_by_id = {str(s.get("id")): s for s in saved if s.get("id")}
    locked_ids = [sid for sid, s in saved_by_id.items() if not open_id or s.get(SHEET_ROUND_KEY) != open_id]
    incoming_by_id = {str(s.get("id")): s for s in incoming if s.get("id")}

    result: list = []
    for sid in locked_ids:
        kept = copy.deepcopy(saved_by_id[sid])
        if incoming_by_id.get(sid) != saved_by_id[sid]:
            report["kept"].append(sid)
        result.append(kept)
    locked_set = set(locked_ids)
    for sheet in incoming:
        sid = str(sheet.get("id") or "")
        if sid in locked_set:
            continue
        if not open_id:
            report["dropped"].append(sid)
            continue
        accepted = copy.deepcopy(sheet)
        if accepted.get(SHEET_ROUND_KEY) != open_id:
            accepted[SHEET_ROUND_KEY] = open_id
            report["tagged"].append(sid)
        result.append(accepted)

    if cur is not None and cur.get("status") == STATUS_WAITING and any(
        s.get(SHEET_ROUND_KEY) == open_id for s in result
    ):
        cur["status"] = STATUS_IN_PROGRESS
        _history_append(cur, {"action": "START", "at": now_iso, "by": actor_id, "by_name": actor_name,
                              "note": "AS 시트를 만들었어요"})
        _sync_flat_status(sd)
    return result, report


def _require_open(sd: Mapping, allowed: Iterable[str], message: str) -> dict:
    cur = current_round(sd)
    if cur is None:
        raise ASDrawingError("NO_OPEN_ROUND", "열린 AS 도면이 없어요.")
    if cur.get("status") not in tuple(allowed):
        raise ASDrawingError("BAD_ROUND_STATUS", message)
    return cur


def transfer_round(sd: dict, *, actor_id: Optional[int], actor_name: str, now_iso: str,
                   note: str = "") -> dict:
    """이번 차수 시트의 대기함 그림을 차수 파일로 옮긴다(작업중·수정 요청됨·확정 대기에서).

    같은 시트의 옛 판은 그 자리에서 바꾸고, 다른 시트는 남긴다. 옮긴 대기함 항목은 지운다
    (그 key 는 이제 차수 파일이 쓴다). 원래 최종 도면 키는 건드리지 않는다.

    Returns:
        ``{"round": 차수, "files": 이번에 보낸 파일, "replaced": 바뀐 시트 id}``.
    """
    cur = _require_open(sd, (STATUS_IN_PROGRESS, STATUS_RETURNED, STATUS_TRANSFERRED),
                        "아직 AS 시트가 없어요. 마법사에서 AS 시트를 먼저 만들어 주세요.")
    sheet_order = round_sheet_ids(sd, cur["round_id"])
    wiz = sd.get("drawing_wizard") if isinstance(sd.get("drawing_wizard"), dict) else {}
    pending = wiz.get("pending") if isinstance(wiz.get("pending"), dict) else {}
    sent: list[dict] = []
    for sid in sheet_order:
        entry = pending.get(sid)
        if not isinstance(entry, dict) or not str(entry.get("key") or "").strip():
            continue
        item = {
            "key": str(entry["key"]).strip(),
            "filename": entry.get("filename") or str(entry["key"]).rsplit("/", 1)[-1],
            "name": entry.get("sheet_name") or sid,
            "sheet_id": sid,
            "at": now_iso,
        }
        if entry.get("sig"):
            item["sig"] = entry["sig"]
        sent.append(item)
    if not sent:
        raise ASDrawingError("NOTHING_TO_SEND",
                             "보낼 AS 도면이 없어요. 마법사에서 [저장]을 먼저 눌러 주세요.", 400)

    previous = copy.deepcopy(cur.get("files") or [])
    files = [f for f in previous if isinstance(f, dict)]
    replaced: list[str] = []
    for item in sent:
        for i, old in enumerate(files):
            if old.get("sheet_id") == item["sheet_id"]:
                files[i] = item
                replaced.append(item["sheet_id"])
                break
        else:
            files.append(item)
    # 마법사 시트 순서로 줄 세운다(도면 장 번호 = 시트 순서).
    rank = {sid: i for i, sid in enumerate(sheet_order)}
    files.sort(key=lambda f: rank.get(f.get("sheet_id"), len(rank)))
    cur["files"] = files
    for item in sent:
        pending.pop(item["sheet_id"], None)
    cur["status"] = STATUS_TRANSFERRED
    _history_append(cur, {"action": "TRANSFER", "at": now_iso, "by": actor_id, "by_name": actor_name,
                          "note": _clean_text(note, _MAX_NOTE), "files": copy.deepcopy(sent),
                          "previous_files": previous})
    _sync_flat_status(sd)
    return {"round": cur, "files": sent, "replaced": replaced}


def confirm_round(sd: dict, *, actor_id: Optional[int], actor_name: str, now_iso: str) -> dict:
    """확정 대기 → 확인함. 영업 담당·AS 담당 중 한 명이면 끝(사용자 11-11)."""
    cur = _require_open(sd, (STATUS_TRANSFERRED,), "확인할 AS 도면이 아직 오지 않았어요.")
    cur["status"] = STATUS_CONFIRMED
    cur["confirmed_at"] = now_iso
    cur["confirmed_by"] = actor_id
    cur["confirmed_by_name"] = actor_name
    _history_append(cur, {"action": "CONFIRM", "at": now_iso, "by": actor_id, "by_name": actor_name,
                          "files": copy.deepcopy(cur.get("files") or [])})
    _block(sd)["current_round_id"] = None
    _sync_flat_status(sd)
    return cur


def request_revision(sd: dict, *, actor_id: Optional[int], actor_name: str, now_iso: str,
                     reason: str) -> dict:
    """확정 대기 → 수정 요청됨. 사유는 꼭 받는다."""
    text = _clean_text(reason, _MAX_NOTE)
    if not text:
        raise ASDrawingError("REASON_REQUIRED", "무엇을 고쳐야 하는지 적어 주세요.", 400)
    cur = _require_open(sd, (STATUS_TRANSFERRED,), "고쳐 달라고 할 AS 도면이 아직 오지 않았어요.")
    cur["status"] = STATUS_RETURNED
    _history_append(cur, {"action": "REQUEST_REVISION", "at": now_iso, "by": actor_id,
                          "by_name": actor_name, "note": text})
    _sync_flat_status(sd)
    return cur


def cancel_round(sd: dict, *, actor_id: Optional[int], actor_name: str, now_iso: str,
                 reason: str = "") -> dict:
    """한 번도 안 보낸 차수를 그만둔다. AS 시트는 남기고(이후 잠김), AS 접수는 건드리지 않는다."""
    cur = _require_open(sd, (STATUS_WAITING, STATUS_IN_PROGRESS),
                        "이미 보낸 AS 도면은 그만둘 수 없어요.")
    if any(h.get("action") == "TRANSFER" for h in cur.get("history") or [] if isinstance(h, dict)):
        raise ASDrawingError("ALREADY_SENT", "이미 보낸 AS 도면은 그만둘 수 없어요.")
    cur["status"] = STATUS_CANCELLED
    _history_append(cur, {"action": "CANCEL", "at": now_iso, "by": actor_id, "by_name": actor_name,
                          "note": _clean_text(reason, _MAX_NOTE)})
    _block(sd)["current_round_id"] = None
    _sync_flat_status(sd)
    return cur


def round_view(sd: Mapping, rnd: Optional[Mapping]) -> Optional[dict]:
    """응답·화면용 요약(파일 key 포함, 이력 제외)."""
    if not isinstance(rnd, Mapping):
        return None
    return {
        "round_id": rnd.get("round_id"),
        "no": round_no(sd, rnd),
        "source": rnd.get("source"),
        "status": rnd.get("status"),
        "memo": rnd.get("memo") or "",
        "cycle_id": rnd.get("cycle_id"),
        "registered_as": bool(rnd.get("registered_as")),
        "opened_at": rnd.get("opened_at"),
        "opened_by_name": rnd.get("opened_by_name") or "",
        "files": copy.deepcopy(rnd.get("files") or []),
    }


__all__ = [
    "AS_DRAWING_KEY", "AS_DRAWING_STATUS_KEY", "AS_DRAWING_STAGES", "SHEET_ROUND_KEY",
    "STATUS_WAITING", "STATUS_IN_PROGRESS", "STATUS_TRANSFERRED", "STATUS_RETURNED",
    "STATUS_CONFIRMED", "STATUS_CANCELLED", "OPEN_STATUSES",
    "SOURCE_AS_REQUEST", "SOURCE_DRAWING_FIRST", "ASDrawingError",
    "is_as_drawing_stage", "rounds", "current_round", "round_no", "open_as_cycle_id", "open_round",
    "round_sheet_ids", "as_sheet_ids", "apply_sheet_lock", "transfer_round", "confirm_round",
    "request_revision", "cancel_round", "as_drawing_keys", "round_view",
]
