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

from foms.services.datetime_kst import now_utc_naive
from foms.services.drawing_confirm_cleanup import resolve_final_drawing_files
from foms.services.orders.confirm_drawing_gate import normalize_stage_code
from foms.services.orders.drawing_factory import DRAWING_FIX_KEY, NOT_CURRENT_MESSAGE
from foms.services.orders.drawing_fix import FIX_LOG_CAP, fix_ident, number_topic
from foms.services.orders.drawing_fix_requests import close_on_stage_exit, open_requests
from foms.services.orders.drawing_transfer import clean_sheet_id
from foms.services.orders.erp_policy_permissions import can_set_sheet_factory
from foms.services.orders.state_axes import read_main_stage
from models import OrderEvent, User

#: 이벤트(``OrderEvent.event_type``) — 생산 '바뀐 것' 줄이 읽는다(``production_change_alerts``).
FIX_STARTED_EVENT = "DRAWING_FIX_STARTED"
FIX_STOPPED_EVENT = "DRAWING_FIX_STOPPED"
LOG_START = "start"
LOG_STOP = "stop"
#: 단계가 생산 밖으로 나가며 저절로 풀린 줄(``OrderEvent`` payload ``via`` · ``log`` 의 ``via``).
VIA_STAGE_EXIT = "stage_exit"
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


def clear_fixing_on_stage_exit(sd: dict[str, Any], *, from_stage: Any, to_stage: Any, by_name: str,
                               at: str) -> list[dict[str, Any]]:
    """주문이 **생산 단계에서 다른 단계로** 가는 쓰기 안에서 [수정 시작] 표시를 모두 지운다(제자리 — 사장님 답 "둘 다", 2026-11-25).

    생산 → 시공(제작 완료) · 고객컨펌 등 되돌림 · 강제 단계 변경 모두 "나감"이다. 생산 → 생산 · 그 밖 → 생산(수정 제작 · 완료 취소)은
    아무것도 안 한다(나갈 때 이미 지웠다). 지운 것이 있으면 ``log`` 에 ``stop`` 한 줄(``via: stage_exit``). 공장 요청(``requests``)은
    여기서 건드리지 않는다(:func:`release_on_stage_exit` 가 ``drawing_fix_requests.close_on_stage_exit`` 로 따로 닫는다). ``drawing_fix`` 칸은 새 dict 로 바꿔 끼운다 — 셸 복사(``dict(sd)``)로 넘기는 자리의 옛 값을 건드리지 않게.

    Args:
        sd: 쓰는 쪽 ``structured_data`` 사본(부르는 쪽이 재대입 · ``flag_modified``).
        from_stage · to_stage: 바뀌기 전 · 뒤 단계(영문 코드 · 한글 이름 모두).
        by_name: 그 쓰기를 한 사람 이름. at: 그 때(UTC iso).

    Returns:
        풀린 장 ``[{no, ident}]``(지금 도면 번호 — 없는 장은 적힌 번호). 지운 것이 없으면 빈 목록.
    """
    if normalize_stage_code(from_stage) != STAGE_PRODUCTION or normalize_stage_code(to_stage) == STAGE_PRODUCTION:
        return []
    rows = [{"no": r["no"], "ident": r["ident"]} for r in fixing_rows(sd)]
    if not rows:
        return []
    table = dict(sd.get(DRAWING_FIX_KEY) or {})
    table["fixing"] = {}
    log = [row for row in table.get("log") or [] if isinstance(row, dict)]
    log.append({"act": LOG_STOP, "idents": [r["ident"] for r in rows], "numbers": [r["no"] for r in rows],
                "by_name": by_name, "at": at, "via": VIA_STAGE_EXIT})
    table["log"] = log[-FIX_LOG_CAP:]
    sd[DRAWING_FIX_KEY] = table
    return rows


def stage_exit_event(order_id: int, rows: list[dict[str, Any]], *, by_user_id: Optional[int], by_name: str,
                     to_stage: Any) -> OrderEvent:
    """단계가 나가며 풀린 [수정 시작]의 이벤트 — [수정 취소]와 같은 ``DRAWING_FIX_STOPPED``(공장 '바뀐 것' "도면 수정 취소" 한 줄,
    폰 알림 없음). 누가 = 그 단계 쓰기를 한 사람."""
    return OrderEvent(order_id=order_id, event_type=FIX_STOPPED_EVENT, created_by_user_id=by_user_id,
                      payload={"numbers": [r["no"] for r in rows], "idents": [r["ident"] for r in rows], "by_name": by_name,
                               "via": VIA_STAGE_EXIT, "to": normalize_stage_code(to_stage)})


def written_by_current_stage_move(payload: Any, stage_now: Any) -> bool:
    """이 이벤트가 **주문의 지금 단계를 만든 단계 쓰기**가 같이 남긴 줄인가 — 적어 둔 표지(``via`` · ``to``)로 읽는다(시각 아님).

    단계 쓰기는 단계 시각을 먼저 읽고, 같이 남기는 이 줄은 그 뒤(flush 때) 찍힌다. 시계 눈금이 그 사이보다 굵으면 두 시각이 같아져
    "창 시작 뒤인가"를 시각으로는 못 가린다(2026-11-28 — '바뀐 것'에서 "도면 수정 취소" 줄이 가끔 빠짐). 표지가 있으면 같은 때여도 '뒤'다.
    """
    stage = normalize_stage_code(stage_now)
    return isinstance(payload, dict) and payload.get("via") == VIA_STAGE_EXIT and bool(stage) and payload.get("to") == stage


def release_on_stage_exit(session: Any, order_id: int, sd: Any, *, from_stage: Any, to_stage: Any, user_id: Any,
                          at: Optional[str] = None, by_name: Optional[str] = None) -> list[dict[str, Any]]:
    """단계를 바꾸는 쓰기 자리마다 부르는 한 함수 — 생산 밖으로 나가면 [수정 시작] 표시를 같은 사본에서 지우고(제자리)
    '바뀐 것' "도면 수정 취소" 이벤트를 같은 세션에 더한다. 열린 공장 요청도 같은 사본에서 닫는다(D4 — 사장님 답 "둘 다",
    ``drawing_fix_requests.close_on_stage_exit``: ``done`` + ``via: stage_exit``, 알림 · '바뀐 것' 줄 없음). 부르는 쪽이 사본 재대입 ·
    ``flag_modified`` · 커밋을 한다.

    지울 것이 없으면(생산 → 생산 · 그 밖 → 생산 · 고치는 중 · 열린 요청 없음 · 사본이 dict 아님) 아무것도 안 하고 쿼리 0.
    이름(``by_name``)을 안 주면 지울 것이 있을 때만 그 사람 행을 읽는다(보통 같은 세션에 이미 있어 쿼리 0). ``at`` 을 안 주면 지금(UTC).

    Returns:
        풀린 [수정 시작] 장 ``[{no, ident}]``(없으면 빈 목록).
    """
    if normalize_stage_code(from_stage) != STAGE_PRODUCTION or normalize_stage_code(to_stage) == STAGE_PRODUCTION:
        return []
    if not isinstance(sd, dict) or not (fixing_rows(sd) or open_requests(sd)):
        return []
    at = at or now_utc_naive().replace(microsecond=0).isoformat() + "Z"
    if by_name is None:
        actor = session.get(User, int(user_id)) if isinstance(user_id, int) or str(user_id or "").isdigit() else None
        by_name = (getattr(actor, "name", None) or getattr(actor, "username", None) or "") if actor is not None else ""
    rows = clear_fixing_on_stage_exit(sd, from_stage=from_stage, to_stage=to_stage, by_name=by_name, at=at)
    if rows:
        session.add(stage_exit_event(order_id, rows, by_user_id=int(user_id) if str(user_id or "").isdigit() else None,
                                     by_name=by_name, to_stage=to_stage))
    close_on_stage_exit(sd, by_name=by_name, at=at, to_stage=normalize_stage_code(to_stage) or str(to_stage or ""))
    return rows


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
    "MESSAGES", "VIA_STAGE_EXIT", "clear_fixing_on_stage_exit", "confirm_text", "fixing_rows", "numbers_note", "refusal_for",
    "release_on_stage_exit", "resolve_targets", "stage_exit_event", "start_fixing", "stop_fixing",
    "written_by_current_stage_move",
]
