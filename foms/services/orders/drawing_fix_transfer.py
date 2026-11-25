"""생산 · 시공 단계 수정본 보내기 규칙(설계서 2026-11-25 D2 — §2-3 · §3-4 ~ §3-7 · §4-2 · §5 C1 · C2 순서).

두 길(작업실 ``transfer-drawing`` · 마법사 · 작업실 일괄 ``transfer-pending``)이 모두 ``perform_drawing_transfer`` 하나를 거치고, 그
함수가 이 모듈을 같은 차례로 부른다:

1. 권한(``can_fix_production_drawing`` — 부르는 쪽) → :func:`precheck`(메모 400 → 파일 바꿀 도면 400 → [반영 완료] · [요청 반려]
   안 된 공장 요청 400)
2. 지금 검사들(반영 안 한 영업 요청 400 · 자리 계산 400) → :func:`worked_refusal`(시공 단계 409 ``ORDER_MADE`` — ``ack_order_made``
   면 지나감 · 작업이 닿은 도면 409 ``WORKED_DRAWING`` — 그 도면 열쇠가 모두 ``ack_worked`` 목록에 있을 때만 지나감)
3. 쓰기(같은 JSON 사본) → :func:`apply_fix_writes` — 고치는 중 풀림 · 건드린 도면의 열린 공장 요청 닫기 · 파일 이어받기 · 손 처리
   풀기(생산 단계) · 패킹 줄 체크 풀기.

[반영 완료](``checked``)는 막힘을 풀지 않는다 — 수정본이 가서 그 도면을 건드려야 요청이 ``done`` 이 된다(설계서 §3-2 · §3-4). 그 밖
단계는 이 모듈을 부르지 않는다(지금 그대로).
"""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import insert

from foms.services.datetime_kst import now_utc_naive, parse_datetime_utc
from foms.services.drawing_fix_progress import order_made_warning, worked_warnings
from foms.services.orders.drawing_factory import hand_checked_parts
from foms.services.orders.drawing_fix import (
    close_requests_on_transfer,
    inherit_file_successors,
    release_fixing_on_transfer,
    unhandled_requests,
)
from foms.services.orders.drawing_transfer import is_drawing_hotfix_stage
from foms.services.orders.drawing_transfer_plan import (
    NEW_TARGET,
    FilePlan,
    changed_old_entries,
    is_manual_file,
    touched_idents,
)
from foms.services.orders.erp_policy_permissions import can_set_sheet_factory
from foms.services.orders.state_axes import read_main_stage
from foms.services.production.part_mark_write import actor_name
from foms.services.production.part_steps_sync import (
    TRIGGER_TRANSFER,
    StepChange,
    apply_part_step_changes,
    step_event_rows,
)
from foms.services.production.step_expand import expand_hand_step
from foms.services.production.steps import step_done_map
from foms.services.shipment.packing_factory import release_packing_checks
from models import OrderEvent, ProductionPartMark

NOTE_REQUIRED = "NOTE_REQUIRED"
PICK_TARGET = "PICK_TARGET"
FACTORY_REQUEST_OPEN = "FACTORY_REQUEST_OPEN"
WORKED_DRAWING = "WORKED_DRAWING"
ORDER_MADE = "ORDER_MADE"
MESSAGES = {
    NOTE_REQUIRED: "공장에 남길 메모를 적어 주세요.",
    PICK_TARGET: "바꿀 도면을 골라 주세요.",
    FACTORY_REQUEST_OPEN: "공장 수정 요청을 [반영 완료]나 [요청 반려]로 처리한 뒤에 보낼 수 있어요.",
}
STAGE_CONSTRUCTION = "CONSTRUCTION"
STAGE_PRODUCTION = "PRODUCTION"


def can_fix_production_drawing(user: Any, order: Any) -> bool:
    """생산 · 시공 단계 주문의 수정본 보내기 권한 — 도면팀 누구나 + 관리자(설계서 2026-11-25 §4-1, 사장님 답 4).

    단계가 생산 · 시공(``is_drawing_hotfix_stage`` — 전달 API 의 바로 반영 판정과 같은 함수)이고
    ``erp_policy_permissions.can_set_sheet_factory``(도면팀 STAFF · MANAGER + 관리자)와 같은 사람이면 참 — 그 주문 도면 담당이
    아니어도, 담당이 없어도 된다. 그 밖 단계는 늘 거짓(전달 권한은 지금 그대로 ``can_transfer_drawing``). 전달 API · 작업실 전달
    단추 · 마법사 '도면 발송' 칸이 같은 술어를 쓴다(화면 == 서버). ``erp_policy_permissions`` 에 두면 단계 읽기 모듈과 import 가
    돌아 여기 둔다.

    Args:
        user: 사용자(None 허용). order: 주문(None 허용).
    """
    if not user or not order or not is_drawing_hotfix_stage(order):
        return False
    return can_set_sheet_factory(user)


def refusal(status: int, code: str, message: str, **data: Any) -> tuple[dict[str, Any], int]:
    """거절 본문 — ``{success: False, data: {code, …}, error: 글}`` + 지금 화면이 읽는 ``message``(같은 글)."""
    return {"success": False, "message": message, "error": message, "data": {"code": code, **data}}, status


def collect_picks(raw_files: Iterable[Any]) -> dict[str, str]:
    """요청 파일 목록의 ``replace_of``(파일마다 바꿀 도면 key 또는 ``"NEW"``) → ``{새 key: 고른 값}``(빈 값은 뺌)."""
    out = {}
    for f in raw_files or []:
        if isinstance(f, dict):
            key, pick = str(f.get("key") or "").strip(), str(f.get("replace_of") or "").strip()
            if key and pick:
                out[key] = pick
    return out


def ack_idents(raw: Any) -> set[str]:
    """``ack_worked`` = 보내기 전 확인 창에서 물어본 도면 열쇠 목록(``sheet:…`` · ``file:…``). 목록이 아니면 빈 것(참 · 거짓은 받지 않음)."""
    return {x.strip() for x in raw if isinstance(x, str) and x.strip()} if isinstance(raw, list) else set()


def precheck(sd: Any, *, note: str, new_files: list[dict[str, Any]], picks: dict[str, str],
             old_files: list[Any]) -> Optional[tuple[dict[str, Any], int]]:
    """생산 · 시공 단계 앞 검사(§5 순서) — 메모 → 파일 바꿀 도면 → 열린 공장 요청. 통과면 None.

    Args:
        sd: 주문 ``structured_data``(읽기만). note: 전달 메모(공백만은 빈 글).
        new_files: 이번 파일(시트 신원이 없는 것이 직접 올린 파일). picks: :func:`collect_picks`.
        old_files: 지금 확정 도면(고른 값이 이 key 중 하나 또는 ``"NEW"`` 여야 한다).
    """
    if not str(note or "").strip():
        return refusal(400, NOTE_REQUIRED, MESSAGES[NOTE_REQUIRED])
    old_keys = {str((f or {}).get("key") or "") for f in old_files if isinstance(f, dict)}
    for entry in new_files:
        if is_manual_file(entry) and picks.get(entry["key"]) not in old_keys | {NEW_TARGET}:
            return refusal(400, PICK_TARGET, MESSAGES[PICK_TARGET])
    if unhandled_requests(sd):
        return refusal(400, FACTORY_REQUEST_OPEN, MESSAGES[FACTORY_REQUEST_OPEN])
    return None


def manual_picks(new_files: list[dict[str, Any]], picks: dict[str, str]) -> dict[str, str]:
    """직접 올린 파일의 고른 값만(시트 파일 · 고르지 않은 값은 뺌) — 자리 계산(``plan_transfer_files``)에 넘긴다."""
    return {e["key"]: picks[e["key"]] for e in new_files if is_manual_file(e) and e["key"] in picks}


def load_marks(db: Any, order_id: int) -> list[Any]:
    """그 주문 파트 표시 줄(쿼리 1 — 잠금 아래)."""
    return db.query(ProductionPartMark).filter(ProductionPartMark.order_id == int(order_id)).all()


def worked_refusal(db: Any, order: Any, sd: Any, plan: FilePlan, old_files: list[Any], *, acked: set[str],
                   ack_order_made: bool) -> tuple[Optional[tuple[dict[str, Any], int]], Optional[list[Any]]]:
    """보내기 전 확인(§2-3) — 시공 단계면 409 ``ORDER_MADE``, 생산 단계에서 바뀌는 도면에 작업이 닿았으면 409 ``WORKED_DRAWING``.

    시공 단계는 ``ack_order_made`` 면 지나간다. 생산 단계는 작업이 닿은 도면 열쇠가 **모두** ``acked``(물어본 도면 목록)에 있을
    때만 지나가고, 하나라도 빠지면 빠진 도면 글로 다시 409 — 저장 전 예측으로 물은 뒤 보낼 시트가 늘어도 안 물은 도면은 못 지나간다
    (D2 검토 I). 생산 단계에서 표시 줄을 읽었으면 그 줄을 돌려준다(손 처리 풀기가 다시 쓴다 — 한 번만 읽음).

    Returns:
        (거절 또는 None, 읽은 표시 줄 또는 None).
    """
    stage = read_main_stage(order)
    if stage == STAGE_CONSTRUCTION:
        warnings = order_made_warning()
        return (None if ack_order_made else refusal(409, ORDER_MADE, warnings[0]["text"], warnings=warnings)), None
    changed = changed_old_entries(old_files, plan.updated_files)
    if stage != STAGE_PRODUCTION or not changed:
        return None, None
    marks = load_marks(db, order.id)
    missing = [w for w in worked_warnings(sd, marks, changed) if w["ident"] not in acked]
    if not missing:
        return None, marks
    return refusal(409, WORKED_DRAWING, " ".join(w["text"] for w in missing), warnings=missing), marks


def _step_rows(sd: Any) -> dict[str, dict[str, Any]]:
    production = sd.get("production") if isinstance(sd, dict) else None
    steps = production.get("steps") if isinstance(production, dict) else None
    return {str(s.get("key")): s for s in steps or [] if isinstance(s, dict)}


def _naive_utc(raw: Any) -> Optional[datetime.datetime]:
    aware = parse_datetime_utc(raw) if raw else None
    return aware.replace(tzinfo=None) if aware is not None else None


def expand_hand_parts(db: Any, order: Any, sd: dict[str, Any], marks: list[Any], *, new_keys: set[str],
                      user: Any) -> list[str]:
    """손 처리 파트를 도면별 표시로 풀어 적는다(§3-6 ② — 사장님 답 Q13 "고친 도면만 다시 할 일로").

    카드를 한 장도 안 쓴 채 칸이 켜진 파트마다, 이번에 **안 바뀐** 지금 도면을 ``DONE`` 으로 쓴다 — 완료한 사람 = 칸을 켠 사람(칸
    ``by_name``) · 시각 = 칸 시각(장별 기록 이벤트의 ``by_name`` 도 같은 사람 — ``expand_hand_step``). 칸에 이름이 없으면 이름은 빈 채
    (보낸 도면팀원을 완료한 사람으로 적지 않는다 — D2 검토 F), 칸 시각도 없으면 지금. 그 뒤 동기화가 새 판(줄 없음)을
    보고 칸을 끈다. 안 바뀐 도면이 하나도 없으면(모든 장을 고침) 쓸 줄이 없어 동기화가 그 파트를 못 보므로 칸을 여기서 끈다(같은
    칸 바꾸기 함수 · 같은 이벤트). 검수 준비 문(``INSPECT_NOT_READY``)은 걸지 않는다 — 이미 손으로 끝낸 일을 장마다 옮겨 적을 뿐이고
    전달이 중간에 막히면 안 된다.

    Returns:
        풀어 적은 파트 key 들(없으면 빈 목록).
    """
    steps = _step_rows(sd)
    done, off = [], []
    for part in hand_checked_parts(sd, marks):
        step = steps.get(part) or {}
        writes = expand_hand_step(db, order, sd, marks, part, exclude_keys=new_keys, user=user,
                                  done_by_name=str(step.get("by_name") or "").strip(),
                                  done_at=_naive_utc(step.get("at")) or now_utc_naive())
        done.append(part)
        if not writes:
            off.append(StepChange(part, False))
    if off:
        apply_part_step_changes(sd, off, at_iso=datetime.datetime.now(datetime.timezone.utc).isoformat())
        db.execute(insert(OrderEvent), step_event_rows(order.id, off, actor_user_id=getattr(user, "id", None),
                                                       trigger=TRIGGER_TRANSFER, actor_name=actor_name(user)))
    if done:
        # 한 문장 넣기 · 고치기는 세션 사본을 모른다 — 뒤 동기화(``sync_steps_in_drawing_write``)가 다시 읽을 때 새 값을 보게
        for mark_row in marks:
            db.expire(mark_row)
    return done


def apply_fix_writes(db: Any, order: Any, sd: dict[str, Any], *, plan: FilePlan, old_files: list[Any],
                     picks: dict[str, str], marks: Optional[list[Any]], user: Any, by_name: str,
                     at_iso: str) -> dict[str, Any]:
    """생산 · 시공 단계 전달 쓰기(같은 JSON 사본 ``sd`` — 부르는 쪽이 재대입 · ``flag_modified``)(§3-4 ~ §3-7).

    * 건드린 열쇠(:func:`~foms.services.orders.drawing_transfer_plan.touched_idents`)의 고치는 중 표시를 지우고, 그 열쇠를 가리키는
      열린 공장 요청을 ``done`` 으로 닫는다 — 안 건드린 도면 · 요청은 그대로(막힘 그대로).
    * 파일로 올린 도면이 고른 도면의 공장 · '바뀐 도면' 짝을 이어받는다(``file_successor``).
    * 생산 단계: 손 처리 파트 풀어 쓰기(:func:`expand_hand_parts`).
    * 건드린 열쇠의 공장 꼴 패킹 줄 체크를 푼다(출발 보고 뒤는 그대로 — ``release_packing_checks``).

    Returns:
        ``{released_numbers, closed_requests, packing_released, expanded_parts}``(이벤트 · 감사에 싣는다).
    """
    touched = touched_idents(old_files, plan.updated_files)
    released = release_fixing_on_transfer(sd, touched, by_name=by_name, at=at_iso)
    closed = close_requests_on_transfer(sd, touched, by_name=by_name, at=at_iso)
    inherit_file_successors(sd, {new: old for new, old in plan.pairs.items() if picks.get(new) == old}, old_files)
    expanded: list[str] = []
    old_keys = {str((f or {}).get("key") or "") for f in old_files if isinstance(f, dict)}
    new_keys = {str(f.get("key") or "") for f in plan.updated_files if str(f.get("key") or "") not in old_keys}
    if read_main_stage(order) == STAGE_PRODUCTION and new_keys and any(step_done_map(sd).values()):
        expanded = expand_hand_parts(db, order, sd, marks if marks is not None else load_marks(db, order.id),
                                     new_keys=new_keys, user=user)
    packing = release_packing_checks(sd, touched)
    return {"released_numbers": released, "closed_requests": closed, "packing_released": packing, "expanded_parts": expanded}


__all__ = [
    "FACTORY_REQUEST_OPEN", "MESSAGES", "can_fix_production_drawing", "NOTE_REQUIRED", "ORDER_MADE", "PICK_TARGET", "WORKED_DRAWING", "apply_fix_writes",
    "ack_idents", "collect_picks", "expand_hand_parts", "load_marks", "manual_picks", "precheck", "refusal",
    "worked_refusal",
]
