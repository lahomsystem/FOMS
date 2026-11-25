"""[수정 시작] · [수정 취소] 쓰기 — 도면팀이 고치는 도면을 공장에서 그 도면만 막는다(설계서 2026-11-25 §3-2 · §4-1 · §4-2 · N1 · N2, D3).

자료는 주문 JSON 의 서버 소유 칸 ``structured_data.drawing_fix``(:mod:`foms.services.orders.drawing_fix`)의 ``fixing`` · ``log`` 다.
이 모듈은 순수 함수(쿼리 0) — 라우트(``foms/api/drawing/erp_orders_drawing_fix.py``)가 잠근 주문의 사본(deepcopy)에 부르고 재대입 ·
``flag_modified`` 한다.

* 열쇠 = :func:`~foms.services.orders.drawing_fix.fix_ident`(지금 확정 도면 항목) — 요청의 ``{sheet_id}`` · ``{key}`` 를 지금 도면에서
  찾아 그 항목의 열쇠로 쓴다(시트 도면은 key 로 골라도 ``sheet:…`` 열쇠). 지금 도면에 없는 장이면 409 ``FIX_NOT_CURRENT``.
* 누가: 도면팀 STAFF · MANAGER + 관리자(``can_set_sheet_factory`` — ``can_fix_production_drawing`` 의 사람 쪽 판정과 같다), 누가 시작했든
  [수정 취소]도 같다(사장님 답 Q2 · Q3). 그 밖 403 ``FIX_FORBIDDEN``.
* 언제: [수정 시작]은 생산 단계만(시공 대기 포함 그 밖 409 ``FIX_STAGE`` — 지휘 풀이 "시공 대기에는 [수정 시작] 없음"). [수정 취소]는
  설계서 표에 단계 조건이 없어 두지 않는다.
* 멱등: 이미 그 상태인 도면은 건너뛴다 — 바뀐 장이 없으면 쓰지 않는다(라우트가 200 ``changed:false``).
* ``log`` 는 누가 언제 눌렀나 최근 :data:`~foms.services.orders.drawing_fix.FIX_LOG_CAP` 줄(전체 기록은 ``OrderEvent``).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.drawing_factory import DRAWING_FIX_KEY, NOT_CURRENT_MESSAGE
from foms.services.orders.drawing_fix import FIX_LOG_CAP, fix_ident, number_topic
from foms.services.orders.drawing_transfer import clean_sheet_id
from foms.services.orders.erp_policy_permissions import can_set_sheet_factory
from foms.services.orders.state_axes import read_main_stage

#: 이벤트(``OrderEvent.event_type``) — 생산 '바뀐 것' 줄이 읽는다(``production_change_alerts``).
FIX_STARTED_EVENT = "DRAWING_FIX_STARTED"
FIX_STOPPED_EVENT = "DRAWING_FIX_STOPPED"
LOG_START = "start"
LOG_STOP = "stop"
#: 거절 code(§4-2).
FIX_FORBIDDEN = "FIX_FORBIDDEN"
FIX_STAGE = "FIX_STAGE"
FIX_NOT_CURRENT = "FIX_NOT_CURRENT"
MESSAGES = {
    FIX_FORBIDDEN: "도면 수정은 도면팀이나 관리자만 표시할 수 있어요.",
    FIX_STAGE: "생산 중인 주문만 수정 시작을 표시할 수 있어요.",
    FIX_NOT_CURRENT: NOT_CURRENT_MESSAGE,
}
STAGE_PRODUCTION = "PRODUCTION"
#: 한 번에 고르는 도면 수 상한(몸이 커지지 않게).
MAX_TARGETS = 100


class FixRefusal(Exception):
    """[수정 시작] · [수정 취소] 거절 — ``status`` · ``code`` · ``message``(§4-2 글)."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = MESSAGES[code]


def refusal_for(user: Any, order: Any, *, starting: bool) -> Optional[FixRefusal]:
    """권한 · 단계 거절(통과면 None) — 권한(403) 먼저, 그다음 [수정 시작]만 생산 단계(409).

    Args:
        user: 사용자(None 허용). order: 주문. starting: [수정 시작]이면 True, [수정 취소]면 False.
    """
    if not can_set_sheet_factory(user):
        return FixRefusal(403, FIX_FORBIDDEN)
    if starting and read_main_stage(order) != STAGE_PRODUCTION:
        return FixRefusal(409, FIX_STAGE)
    return None


def _target_of(raw: Any) -> tuple[str, str]:
    if not isinstance(raw, dict):
        return "", ""
    key = raw.get("key")
    return clean_sheet_id(raw.get("sheet_id")), key.strip()[:500] if isinstance(key, str) else ""


def resolve_targets(sd: Any, raw_targets: Any) -> list[tuple[int, dict[str, Any]]]:
    """요청 ``targets`` (``[{sheet_id} | {key}]``) → 지금 확정 도면 ``(번호, 항목)`` — 도면 번호 순, 같은 장은 한 번.

    Raises:
        FixRefusal: 고른 장이 없거나 하나라도 지금 확정 도면에 없으면 409 ``FIX_NOT_CURRENT``(화면을 다시 열면 된다).
    """
    rows = list(enumerate(resolve_final_drawing_files(sd), 1))
    if not isinstance(raw_targets, list) or not 1 <= len(raw_targets) <= MAX_TARGETS:
        raise FixRefusal(409, FIX_NOT_CURRENT)
    picked: dict[int, dict[str, Any]] = {}
    for raw in raw_targets:
        sheet_id, key = _target_of(raw)
        hit = next(((no, entry) for no, entry in rows
                    if (sheet_id and clean_sheet_id(entry.get("sheet_id")) == sheet_id) or (key and entry.get("key") == key)), None)
        if hit is None:
            raise FixRefusal(409, FIX_NOT_CURRENT)
        picked[hit[0]] = hit[1]
    return sorted(picked.items())


def _fixing_now(sd: Any) -> dict[str, Any]:
    table = sd.get(DRAWING_FIX_KEY) if isinstance(sd, dict) else None
    fixing = table.get("fixing") if isinstance(table, dict) else None
    return fixing if isinstance(fixing, dict) else {}


def _table(sd: dict[str, Any]) -> dict[str, Any]:
    table = sd.get(DRAWING_FIX_KEY)
    if not isinstance(table, dict):
        table = {}
        sd[DRAWING_FIX_KEY] = table
    if not isinstance(table.get("fixing"), dict):
        table["fixing"] = {}
    return table


def _append_log(table: dict[str, Any], act: str, rows: list[dict[str, Any]], *, by_name: str, at: str) -> None:
    log = [row for row in table.get("log") or [] if isinstance(row, dict)]
    log.append({"act": act, "idents": [r["ident"] for r in rows], "numbers": [r["no"] for r in rows], "by_name": by_name, "at": at})
    table["log"] = log[-FIX_LOG_CAP:]


def start_fixing(sd: dict[str, Any], picked: Iterable[tuple[int, dict[str, Any]]], *, by_user_id: Optional[int],
                 by_name: str, at: str) -> list[dict[str, Any]]:
    """[수정 시작] — 고른 도면 중 아직 고치는 중이 아닌 장을 ``fixing`` 에 적는다(제자리).

    Args:
        sd: 고칠 ``structured_data`` 사본. picked: :func:`resolve_targets` 값.
        by_user_id · by_name: 누른 사람. at: 누른 때(UTC iso, ``…Z``).

    Returns:
        새로 고치는 중이 된 장 ``[{no, ident}]``(없으면 빈 목록 — 쓰지 않았다).
    """
    current = _fixing_now(sd)
    fresh = [{"no": no, "ident": fix_ident(entry)} for no, entry in picked if fix_ident(entry) not in current]
    if not fresh:
        return []
    table = _table(sd)
    for row in fresh:
        table["fixing"][row["ident"]] = {"no": row["no"], "by_user_id": by_user_id, "by_name": by_name, "at": at}
    _append_log(table, LOG_START, fresh, by_name=by_name, at=at)
    return fresh


def stop_fixing(sd: dict[str, Any], picked: Iterable[tuple[int, dict[str, Any]]], *, by_name: str,
                at: str) -> list[dict[str, Any]]:
    """[수정 취소] — 고른 도면 중 고치는 중인 장을 ``fixing`` 에서 지운다(제자리, 누가 시작했든).

    Returns:
        고치는 중이 풀린 장 ``[{no, ident}]``(없으면 빈 목록 — 쓰지 않았다).
    """
    current = _fixing_now(sd)
    gone = [{"no": no, "ident": fix_ident(entry)} for no, entry in picked if fix_ident(entry) in current]
    if not gone:
        return []
    table = _table(sd)
    for row in gone:
        table["fixing"].pop(row["ident"], None)
    _append_log(table, LOG_STOP, gone, by_name=by_name, at=at)
    return gone


def fixing_rows(sd: Any) -> list[dict[str, Any]]:
    """지금 고치는 중인 장 ``[{no, ident, by_name, at}]`` — 번호는 지금 확정 도면 순서로 다시 센다(없는 장은 적힌 번호), 번호 순."""
    fixing = _fixing_now(sd)
    if not fixing:
        return []
    numbers = {fix_ident(entry): no for no, entry in enumerate(resolve_final_drawing_files(sd), 1)}
    out = []
    for ident, info in fixing.items():
        info = info if isinstance(info, dict) else {}
        no = numbers.get(ident, info.get("no"))
        out.append({"no": no if isinstance(no, int) else None, "ident": ident, "by_name": str(info.get("by_name") or ""),
                    "at": str(info.get("at") or "")})
    return sorted(out, key=lambda r: (r["no"] is None, r["no"] or 0, r["ident"]))


def numbers_note(rows: list[dict[str, Any]]) -> str:
    """감사 · 이벤트 글의 번호 "도면 2" · "도면 2 · 3"."""
    return "도면 " + " · ".join(str(r["no"]) for r in rows)


def confirm_text(numbers: list[int], *, starting: bool) -> str:
    """확인 창 본문(§10) — 화면 JS 와 같은 글(시험 · 서버 쪽 정본).

    시작 "도면 2를 고치는 중으로 표시할까요? 공장에서 도면 2만 작업이 막혀요." · 취소 "도면 2 수정을 취소할까요? 공장에서 도면 2를
    다시 작업할 수 있어요."(조사 을/를 = 숫자 끝소리 — :func:`~foms.services.orders.drawing_fix.number_topic` 과 같은 표).
    """
    label = " · ".join(str(n) for n in numbers)
    obj = "을" if number_topic(numbers[-1]) == "은" else "를"
    if starting:
        return f"도면 {label}{obj} 고치는 중으로 표시할까요? 공장에서 도면 {label}만 작업이 막혀요."
    return f"도면 {label} 수정을 취소할까요? 공장에서 도면 {label}{obj} 다시 작업할 수 있어요."


__all__ = [
    "FIX_FORBIDDEN", "FIX_NOT_CURRENT", "FIX_STAGE", "FIX_STARTED_EVENT", "FIX_STOPPED_EVENT", "FixRefusal", "LOG_START", "LOG_STOP",
    "MESSAGES", "confirm_text", "fixing_rows", "numbers_note", "refusal_for", "resolve_targets", "start_fixing", "stop_fixing",
]
