"""ERP 할 일 제안 생명주기 — 만들기 · 승인(두 걸음) · 거절 · 나중에 · 기간 끝남 · 되맞추기(설계서 2026-11-14-foms-graft 3.4).

::

    propose ─▶ open ──승인──▶ executing ──성공──▶ executed
                │                 └──실패──▶ failed(카드 [다시] = 같은 승인 길)
                ├─거절(까닭)──▶ rejected   (같은 dedupe_key 는 다시 만들지 않는다)
                ├─기간 끝남──▶ expired     └─같은 주문 · 같은 할 일의 새 제안──▶ superseded

- :func:`propose` 는 커밋하지 않는다. 막힘 · 같은 열쇠 있음(열림 · 실행 중 · 실패 · 거절) · 가림 검사 걸림이면 ``None``(코드만 로그).
  새 줄을 만든 때에만 :func:`.notify.proposal_created`(승인할 사람 폰 알림 — 폰 보내기는 부르는 쪽 커밋 뒤)를 부른다.
- :func:`approve` 는 두 걸음이라 **스스로 커밋한다**: ① 제안 줄 잠금 → 볼 수 있나 · 열림 · 갈래 · 제안한 AI 직원의 지금 수준 ·
  넣을 값 · 막는 조건 · 기준 판 · 사유(사유를 물을 변경이면 꼭) → ``executing`` + 결정한 사람 + 감사 커밋 ② 실행기(감싼 기능의
  커밋 방식 그대로) ③ 결과 + 감사 커밋. 실행기가 막히면(주문이 바뀌지 않음) ``open`` 으로 되돌리고 ``ACTION_PRECONDITION``.
- :func:`reject` · :func:`snooze` · :func:`expire_due` · :func:`reconcile` 은 커밋하지 않는다(부르는 쪽).
- 결정 판정은 :func:`.access.can_decide`(사람별 화면 스위치는 화면 API 가 먼저 본다). 결정한 사람은 ``actor`` 뿐.
- 감사 ``SecurityLog``: ``ERP_ACTION_APPROVED`` · ``REJECTED`` · ``EXECUTED`` · ``FAILED`` — 번호 · 이름 · 코드만(글 없음).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Mapping, Optional

from sqlalchemy.exc import IntegrityError

from foms.persistence.graft.models import ErpActionProposal
from foms.services.ai_staff.registry import PROPOSER_PREFIX, agent_of, level_of
from foms.services.audit_writer import normalize_security_detail
from foms.services.brain.review_rules import clamp_ms
from foms.services.brain.usage_events import READER_ERP_ACTION, record_uses
from foms.services.cs_agent.masking import MaskLeak, require_masked
from foms.services.erp_actions import preview as fns
from foms.services.erp_actions.access import can_decide
from foms.services.erp_actions.notify import proposal_created
from foms.services.erp_actions.registry import (
    ACTIONS, EVIDENCE_KINDS, MAX_EVIDENCE, MAX_REASON, MODE_HUMAN, MODE_LINK, MODE_RUN, REJECT_CODES, SOURCE_KINDS,
    STATUS_EXECUTED, STATUS_EXECUTING, STATUS_EXPIRED, STATUS_FAILED, STATUS_OPEN, STATUS_REJECTED,
    STATUS_SUPERSEDED, ActionShapeError, ActionSpec, dedupe_key, get, message, parse_params,
)
from foms.services.erp_actions.runners import OUTCOME_BLOCKED, OUTCOME_EXECUTED, RunOutcome, RunRequest, Runner
from foms.services.orders.change_reason import REASON_CODES, normalize_reason
from foms.services.orders.revision import lock_order_row
from models import Order, SecurityLog

logger = logging.getLogger(__name__)

__all__ = [
    "AUDIT_APPROVED", "AUDIT_EXECUTED", "AUDIT_FAILED", "AUDIT_REJECTED", "AUDIT_SNOOZED", "ActionError",
    "DECIDED_APPROVE", "DECIDED_EDIT", "DECIDED_LINK", "DECIDED_REJECT", "LEVEL_ZERO_REASON", "PROPOSAL_DAYS",
    "RECONCILE_AFTER", "approve",
    "clean_evidence", "clean_reason_text", "expire_due", "next_morning", "propose", "reconcile", "reject", "snooze",
]

PROPOSAL_DAYS = 7
RECONCILE_AFTER = datetime.timedelta(minutes=2)
DECIDED_APPROVE, DECIDED_EDIT, DECIDED_REJECT, DECIDED_LINK = "approve", "edit_approve", "reject", "link_done"
AUDIT_APPROVED, AUDIT_REJECTED = "ERP_ACTION_APPROVED", "ERP_ACTION_REJECTED"
AUDIT_EXECUTED, AUDIT_FAILED, AUDIT_SNOOZED = "ERP_ACTION_EXECUTED", "ERP_ACTION_FAILED", "ERP_ACTION_SNOOZED"
_VERBS = {AUDIT_APPROVED: "승인", AUDIT_REJECTED: "거절", AUDIT_EXECUTED: "실행", AUDIT_FAILED: "실행 못 함",
          AUDIT_SNOOZED: "나중에"}
_DECIDABLE = (STATUS_OPEN, STATUS_FAILED)
_TAKEN = (STATUS_OPEN, STATUS_EXECUTING, STATUS_FAILED, STATUS_REJECTED)
_KST = datetime.timedelta(hours=9)
_REF_LIMIT, _LABEL_LIMIT = 120, 60
#: 제안한 AI 직원의 지금 수준이 0 이면 승인을 막는 말(수준을 내린 뒤 남은 열린 제안 — 검수 R-10).
LEVEL_ZERO_REASON = "AI 직원 수준이 0(읽기만)으로 바뀌어 승인할 수 없어요."


class ActionError(Exception):
    """생명주기 거절 — ``code`` 는 실패 표(:data:`.registry.FAILURES`)의 열쇠. ``reason`` 은 막는 까닭(정한 말) ·
    ``fields`` 는 꼴이 틀린 칸 이름 · ``proposal_id`` 는 새 카드를 돌려줄 제안(``ACTION_BASE_CHANGED``)."""

    def __init__(self, code: str, *, reason: Optional[str] = None, fields: tuple[str, ...] = (),
                 proposal_id: Optional[int] = None) -> None:
        super().__init__(code)
        self.code, self.reason, self.fields, self.proposal_id = code, reason, tuple(fields), proposal_id

    @property
    def message(self) -> str:
        """화면 말 — 막는 까닭이 있으면 그 말, 아니면 실패 표의 말."""
        return self.reason or message(self.code)


# ── 제안 칸 다듬기(가린 글만 · 상한) ─────────────────────────────────────
def clean_reason_text(value: Any) -> Optional[str]:
    """이유 글 — 한 줄로 모아 :data:`.registry.MAX_REASON` 자까지 · 가림 검사 0 이면 그 글, 걸리면 ``None``."""
    text = " ".join(str(value or "").split())[:MAX_REASON]
    try:
        return require_masked(text) if text else ""
    except MaskLeak:
        return None


def clean_evidence(value: Any) -> Optional[list[dict[str, str]]]:
    """근거 ``[{"kind", "ref", "label"}]`` — 여덟까지 · 종류는 정한 넷 · 이름은 가림 검사 0. 하나라도 틀리면 ``None``."""
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        return None
    out: list[dict[str, str]] = []
    for item in list(value)[:MAX_EVIDENCE]:
        if not isinstance(item, Mapping) or item.get("kind") not in EVIDENCE_KINDS:
            return None
        ref, label = str(item.get("ref") or "").strip(), " ".join(str(item.get("label") or "").split())
        if not ref or len(ref) > _REF_LIMIT or len(label) > _LABEL_LIMIT or clean_reason_text(label) is None:
            return None
        out.append({"kind": str(item["kind"]), "ref": ref, "label": label})
    return out


def _expiry(now: datetime.datetime, params: Mapping[str, Any]) -> datetime.datetime:
    """기간 끝 — 7일 뒤와 넣을 값 날짜가 끝나는 때(한국 시간 자정) 가운데 이른 쪽(UTC naive)."""
    limit = now + datetime.timedelta(days=PROPOSAL_DAYS)
    try:
        day = datetime.date.fromisoformat(str(params.get("date") or ""))
    except ValueError:
        return limit
    return min(limit, datetime.datetime.combine(day + datetime.timedelta(days=1), datetime.time()) - _KST)


def next_morning(now: datetime.datetime) -> datetime.datetime:
    """다음 날 06:00(한국 시간)을 UTC naive 로 — '나중에' 접는 끝."""
    kst_day = (now + _KST).date() + datetime.timedelta(days=1)
    return datetime.datetime.combine(kst_day, datetime.time(6)) - _KST


# ── 감사 · 잠금 도우미 ───────────────────────────────────────────────────
def _audit(session: Any, audit_action: str, row: ErpActionProposal, actor_id: Optional[int], **extra: Any) -> None:
    """감사 줄 한 줄(같은 트랜잭션) — 번호 · 이름 · 코드만(손님 글 · 이유 글을 싣지 않는다)."""
    spec, agent = ACTIONS.get(row.action), agent_of(row.proposed_by)
    detail = {"proposal_id": row.id, "action": row.action, "order_id": row.order_id,
              "agent": agent.key if agent else None, "level": row.level, "status": row.status, **extra}
    label = spec.label if spec else row.action
    session.add(SecurityLog(
        user_id=actor_id, action=audit_action, target_type="order", target_id=row.order_id,
        message=f"주문 #{row.order_id} — AI 할 일 {_VERBS[audit_action]}: {label} (제안 #{row.id})",
        detail=normalize_security_detail(detail)))


def _lock(session: Any, proposal_id: Any) -> Optional[ErpActionProposal]:
    """제안 줄을 ``FOR UPDATE`` 로 잠근 최신 값(없으면 ``None``)."""
    if isinstance(proposal_id, bool) or not isinstance(proposal_id, int):
        return None
    return (session.query(ErpActionProposal).filter(ErpActionProposal.id == proposal_id)
            .populate_existing().with_for_update().first())


def _actor_id(actor: Any) -> Optional[int]:
    value = getattr(actor, "id", None)
    return int(value) if value is not None else None


def _decidable(session: Any, proposal_id: Any, actor: Any, *, lock_order: bool) -> tuple[Any, ActionSpec, Any]:
    """잠근 제안 · 할 일 · 주문 — 없거나 결정할 수 없으면 ``ACTION_FORBIDDEN``(없는 것과 같은 404)."""
    row = _lock(session, proposal_id)
    spec = ACTIONS.get(row.action) if row is not None else None
    order = None
    if row is not None and row.order_id is not None:
        order = lock_order_row(session, row.order_id) if lock_order else session.get(Order, row.order_id)
    if row is None or spec is None or not can_decide(actor, spec, order):
        raise ActionError("ACTION_FORBIDDEN")
    return row, spec, order


def _clear_decision(row: ErpActionProposal) -> None:
    row.decided_by = row.decided_at = row.decided_action = row.view_ms = row.edited_params = None


# ── 만들기 ───────────────────────────────────────────────────────────────
def _caller_ok(spec: ActionSpec, proposed_by: Any, level: Any, source_kind: Any, source_ref: Any) -> bool:
    """부르는 쪽 약속 — 틀리면 :class:`ValueError`(코드 실수). 수준 0 이면 거짓(만들지 않음)."""
    if spec.mode == MODE_HUMAN:
        raise ActionShapeError(("action",))
    if agent_of(proposed_by) is None:
        raise ValueError("proposed_by")
    if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= spec.level_cap:
        raise ValueError("level")
    if source_kind is not None and source_kind not in SOURCE_KINDS:
        raise ValueError("source_kind")
    if source_ref is not None and (not isinstance(source_ref, str) or not 0 < len(source_ref) <= 64):
        raise ValueError("source_ref")
    return level > 0


def _skip(action: str, order: Any, code: str) -> None:
    logger.info("[ERP-ACTION] 제안 안 만듦 action=%s order=%s code=%s", action, getattr(order, "id", None), code)


def _taken(session: Any, row: ErpActionProposal) -> bool:
    """새 줄과 같은 열쇠의 제안이 열림 · 실행 중 · 실패 · 거절로 있나.

    열쇠에는 주문 번호가 들어 있다(:func:`.registry.dedupe_key`). 주문 번호 조건을 같이 걸어 ``(order_id, status)`` 색인
    (``ix_erp_action_proposals_order_status``)을 탄다 — 부분 유일 색인은 ``open`` 만 덮어 실행 중 · 실패 · 거절은 못 찾는다.
    """
    return session.query(ErpActionProposal.id).filter(
        ErpActionProposal.order_id == row.order_id, ErpActionProposal.dedupe_key == row.dedupe_key,
        ErpActionProposal.status.in_(_TAKEN)).first() is not None


def _insert(session: Any, row: ErpActionProposal) -> bool:
    """같은 주문 · 같은 할 일의 열린 · 실패한 옛 제안(다른 값)을 밀어내고 새 줄 — 저장점 안.

    같은 열쇠의 동시 만들기는 밀어내지 않고 부분 유일 색인(``status = 'open'``)에 걸려 이 저장점만 되감긴다(``False``).
    """
    try:
        with session.begin_nested():
            for old in session.query(ErpActionProposal).filter(
                    ErpActionProposal.action == row.action, ErpActionProposal.order_id == row.order_id,
                    ErpActionProposal.dedupe_key != row.dedupe_key,
                    ErpActionProposal.status.in_(_DECIDABLE)).all():
                old.status = STATUS_SUPERSEDED
            session.add(row)
            session.flush()
    except IntegrityError:
        return False
    return True


def propose(session: Any, *, action: str, proposed_by: str, order: Any, params: Optional[Mapping[str, Any]],
            reason: Any, evidence: Any, source_kind: Optional[str], source_ref: Optional[str], level: int,
            now: datetime.datetime, dedupe_scope: Optional[str] = None) -> Optional[ErpActionProposal]:
    """AI 직원의 할 일 제안 하나를 만든다(커밋은 부르는 쪽).

    Args:
        action: 할 일 이름(``run`` · ``link``). proposed_by: ``'agent:<열쇠>'``. order: 대상 주문.
        params: 넣을 값(:func:`.registry.parse_params`). reason: 가린 이유 글. evidence: 근거 ``[{"kind", "ref", "label"}]``.
        source_kind · source_ref: ``cs_turn`` · ``sweep`` 과 그 번호. level: 지금 수준(0 이면 만들지 않는다). now: UTC naive.
        dedupe_scope: 겹침 열쇠의 '상황'(:func:`.registry.dedupe_key` ``scope`` — 넣을 값이 없는 훑기 규칙이 준다).

    Returns:
        새 제안 줄, 또는 ``None``(수준 0 · 주문 없음 · 꼴 · 가림 · 막힘 · 이미 있음 · 거절된 적 있음).

    Raises:
        ActionShapeError: 모르는 할 일 · 사람만 할 일. ValueError: 제안자 · 수준 · 출처 꼴(부르는 쪽 코드 실수).
    """
    spec = get(action)
    if not _caller_ok(spec, proposed_by, level, source_kind, source_ref) or order is None:
        return None
    try:
        clean = parse_params(action, params or {})
    except ActionShapeError:
        _skip(action, order, "ACTION_SHAPE")
        return None
    text, proofs = clean_reason_text(reason), clean_evidence(evidence)
    if text is None or proofs is None:
        _skip(action, order, "MASK_OR_SHAPE")
        return None
    if fns.check(action, order, clean):
        _skip(action, order, "ACTION_PRECONDITION")
        return None
    key = dedupe_key(action, int(order.id), clean, dedupe_scope)
    row = ErpActionProposal(
        action=action, proposed_by=proposed_by, order_id=int(order.id), params=clean,
        preview=fns.preview(action, order, clean), reason=text, evidence=proofs, level=level, status=STATUS_OPEN,
        base_version=getattr(order, "mutation_version", None), dedupe_key=key, source_kind=source_kind,
        source_ref=source_ref, created_at=now, expires_at=_expiry(now, clean))
    if _taken(session, row) or not _insert(session, row):
        return None
    keys = [proof["ref"] for proof in proofs if proof["kind"] == "brain"]
    record_uses(session, keys, READER_ERP_ACTION, "proposal", row.id, now)
    proposal_created(session, row)  # 새 줄일 때만 — 승인할 사람 폰 알림(설계서 3.14 · 스위치 끔이면 아무것도 안 함)
    return row


# ── 승인(두 걸음) ────────────────────────────────────────────────────────
def _effective(spec: ActionSpec, row: ErpActionProposal, edits: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """실행할 넣을 값 · 고친 값 — 꼴만 본다(지난 날짜는 막는 조건이 409 로 가른다)."""
    edits = {} if edits is None else edits
    known = {param.name for param in spec.params}
    if not isinstance(edits, Mapping) or any(name not in known for name in edits):
        raise ActionError("ACTION_SHAPE", fields=("edits",))
    stored = dict(row.params or {})
    try:
        clean = parse_params(spec.name, {**stored, **edits}, today=datetime.date.min)
    except ActionShapeError as exc:
        raise ActionError("ACTION_SHAPE", fields=exc.fields) from exc
    return clean, {name: clean[name] for name in edits if clean.get(name) != stored.get(name)}


def _change_reason(code: Any, note: Any) -> tuple[Optional[str], Optional[str]]:
    """승인 창 사유(지금 사유 원장 코드) — 없으면 (None, None), 틀리면 ``ACTION_SHAPE``."""
    if code in (None, ""):
        return None, None
    if code not in REASON_CODES:
        raise ActionError("ACTION_SHAPE", fields=("reason_code",))
    try:
        return normalize_reason(code, note)
    except ValueError as exc:
        raise ActionError("ACTION_SHAPE", fields=("reason_note",)) from exc


def _base_check(session: Any, row: ErpActionProposal, order: Any, base_version: Any) -> None:
    """기준 판 — 미리 보기를 지금 주문으로 다시 계산해 '지금' 값이 바뀌었으면 새 값 · 판으로 갱신 · 커밋하고 409.

    판 번호를 올리지 않는 쓰기(시공일 쓰기 길)도 있어 판 번호가 아니라 '지금' 값을 견준다. 받은 판이 제안의 판과 다르면
    (낡은 카드를 보고 누름) 값이 같아도 409 다.
    """
    fresh = fns.preview(row.action, order, row.params or {})
    if [(r.get("field"), r.get("before")) for r in fresh] != [(r.get("field"), r.get("before")) for r in row.preview or []]:
        row.preview, row.base_version = fresh, getattr(order, "mutation_version", None)
        session.commit()
        raise ActionError("ACTION_BASE_CHANGED", proposal_id=row.id)
    if base_version != row.base_version:
        raise ActionError("ACTION_BASE_CHANGED", proposal_id=row.id)


def _level_check(session: Any, row: ErpActionProposal) -> None:
    """제안한 AI 직원(``agent:<열쇠>``)의 지금 수준이 0 이면 막는다 — 수준을 내린 뒤 남은 열린 제안이 실행되지 않게.

    수준은 수준 표(:func:`foms.services.ai_staff.registry.level_of`)를 승인 때 다시 읽는다. 모르는 직원 · 그 직원에게 없는
    할 일도 0 이다. 제안은 ``open`` 그대로(거절 · 기간 끝남은 된다). 막으면 409 ``ACTION_PRECONDITION`` + :data:`LEVEL_ZERO_REASON`.
    """
    proposer = str(row.proposed_by or "")
    if proposer.startswith(PROPOSER_PREFIX) and level_of(session, proposer[len(PROPOSER_PREFIX):], row.action) <= 0:
        raise ActionError("ACTION_PRECONDITION", reason=LEVEL_ZERO_REASON)


def _begin(session: Any, proposal_id: Any, *, actor: Any, runners: Mapping[str, Runner], base_version: Any,
           edits: Any, reason: tuple[Optional[str], Optional[str]], view_ms: Any,
           now: datetime.datetime) -> RunRequest:
    """① 잠금 → 볼 수 있나(404) → 열림(409) → 갈래 · 실행기(400) → AI 직원 수준(409) → 넣을 값(400) → 막는 조건 · 기준 판(409)
    → 사유(사유를 물을 변경인데 사유 코드가 없으면 400 ``reason_code`` — 변경 원장 사유가 비지 않게) → executing 커밋."""
    row, spec, order = _decidable(session, proposal_id, actor, lock_order=True)
    if row.status not in _DECIDABLE or (row.expires_at is not None and row.expires_at <= now):
        raise ActionError("ACTION_NOT_OPEN")  # 기간이 지난 제안은 밤 정리(expire_due) 전이라도 실행하지 않는다(F-13)
    if spec.mode != MODE_RUN or row.action not in runners:
        raise ActionError("ACTION_SHAPE", fields=("action",))
    _level_check(session, row)
    params, changed = _effective(spec, row, edits)
    blocked = fns.check(row.action, order, params)
    if blocked:
        raise ActionError("ACTION_PRECONDITION", reason=blocked)
    _base_check(session, row, order, base_version)
    if reason[0] is None and fns.reason_required(row.action, order, params):
        raise ActionError("ACTION_SHAPE", fields=("reason_code",))
    actor_id = _actor_id(actor)
    row.status, row.decided_by, row.decided_at = STATUS_EXECUTING, actor_id, now
    row.decided_action = DECIDED_EDIT if changed else DECIDED_APPROVE
    row.view_ms, row.edited_params, row.result, row.error_code = clamp_ms(view_ms), changed or None, None, None
    _audit(session, AUDIT_APPROVED, row, actor_id, edited=bool(changed))
    request = RunRequest(proposal_id=row.id, action=row.action, order_id=int(row.order_id), params=params,
                         actor=actor, reason_code=reason[0], reason_note=reason[1], now=now)
    session.commit()
    return request


def _execute(session: Any, runner: Runner, request: RunRequest) -> RunOutcome:
    """② 실행기 — 예외면 되감고 주문에 이 제안의 흔적(:func:`.preview.ran`)이 있는지로 실행 · 실패를 가른다."""
    try:
        return runner(session, request)
    except Exception as exc:  # noqa: BLE001 — 되감고 흔적으로 판정한다(로그에는 번호 · 예외 이름만)
        session.rollback()
        logger.warning("[ERP-ACTION] 실행 오류 proposal=%s action=%s error=%s",
                       request.proposal_id, request.action, type(exc).__name__)
    order = session.query(Order).filter(Order.id == request.order_id).populate_existing().first()
    if order is not None and fns.ran(request.action, order, request.params, request.proposal_id):
        return RunOutcome.executed("실행됐어요 — 주문에서 확인했어요.", verified=True)
    return RunOutcome.failed()


def _finish(session: Any, request: RunRequest, outcome: RunOutcome) -> dict[str, Any]:
    """③ 결과 · 감사 커밋. 막힘이면 ``open`` 으로 되돌리고 ``ACTION_PRECONDITION``."""
    row = _lock(session, request.proposal_id)
    if row is not None and row.status != STATUS_EXECUTED:
        if outcome.status == OUTCOME_BLOCKED:
            row.status, row.result, row.error_code = STATUS_OPEN, None, None
            _clear_decision(row)
            _audit(session, AUDIT_FAILED, row, request.actor_id, outcome=OUTCOME_BLOCKED, code=outcome.code)
        else:
            done = outcome.status == OUTCOME_EXECUTED
            row.status, row.result = (STATUS_EXECUTED if done else STATUS_FAILED), dict(outcome.result)
            row.error_code = None if done else outcome.code
            _audit(session, AUDIT_EXECUTED if done else AUDIT_FAILED, row, request.actor_id, code=outcome.code)
        session.commit()
    if outcome.status == OUTCOME_BLOCKED:
        raise ActionError("ACTION_PRECONDITION", reason=outcome.message)
    return {"status": STATUS_EXECUTED if outcome.status == OUTCOME_EXECUTED else STATUS_FAILED,
            "code": outcome.code, "message": outcome.message, "result": dict(outcome.result)}


def approve(session: Any, proposal_id: Any, *, actor: Any, runners: Mapping[str, Runner], base_version: Any,
            edits: Any = None, reason_code: Any = None, reason_note: Any = None, view_ms: Any = None,
            now: datetime.datetime) -> dict[str, Any]:
    """제안을 승인하고 실행한다(두 걸음 — 스스로 커밋).

    Args:
        proposal_id: 제안 번호. actor: 승인하는 로그인 사용자. runners: 할 일 이름 → 실행기(화면 ``RUNNERS`` · 작은 창
            ``SERVICE_RUNNERS``). base_version: 카드에 보인 기준 판. edits: 고친 넣을 값. reason_code · reason_note: 지금
            사유 원장 코드 · 메모. view_ms: 본 시간(밀리초). now: UTC naive.

    Returns:
        ``{"status": "executed" | "failed", "code", "message", "result"}``.

    Raises:
        ActionError: 404 ``ACTION_FORBIDDEN`` · 409 ``ACTION_NOT_OPEN`` · ``ACTION_BASE_CHANGED`` · ``ACTION_PRECONDITION``(막는
            조건 · 제안한 AI 직원 수준 0) · 400 ``ACTION_SHAPE``(``link`` · ``human`` 갈래 · 실행기 없음 · 넣을 값 · 사유 꼴 ·
            사유를 물을 변경인데 사유 없음 — 칸 ``reason_code``).
    """
    reason = _change_reason(reason_code, reason_note)
    request = _begin(session, proposal_id, actor=actor, runners=runners, base_version=base_version, edits=edits,
                     reason=reason, view_ms=view_ms, now=now)
    return _finish(session, request, _execute(session, runners[request.action], request))


# ── 거절 · 나중에 ────────────────────────────────────────────────────────
def reject(session: Any, proposal_id: Any, *, actor: Any, code: Any, view_ms: Any = None,
           now: datetime.datetime) -> ErpActionProposal:
    """거절(까닭 하나) — 같은 열쇠의 제안은 다시 만들지 않는다. 커밋은 부르는 쪽. 404 · 409 · 400 은 :class:`ActionError`."""
    row, _spec, _order = _decidable(session, proposal_id, actor, lock_order=False)
    if row.status not in _DECIDABLE:
        raise ActionError("ACTION_NOT_OPEN")
    if code not in REJECT_CODES:
        raise ActionError("ACTION_SHAPE", fields=("code",))
    actor_id = _actor_id(actor)
    row.status, row.reject_code, row.decided_by, row.decided_at = STATUS_REJECTED, code, actor_id, now
    row.decided_action, row.view_ms = DECIDED_REJECT, clamp_ms(view_ms)
    _audit(session, AUDIT_REJECTED, row, actor_id, reject_code=code)
    session.flush()
    return row


def snooze(session: Any, proposal_id: Any, *, actor: Any, now: datetime.datetime) -> ErpActionProposal:
    """나중에 — 다음 날 06:00(한국 시간)까지 접는다(상태 그대로). 커밋은 부르는 쪽. 404 · 409 는 :class:`ActionError`."""
    row, _spec, _order = _decidable(session, proposal_id, actor, lock_order=False)
    if row.status not in _DECIDABLE:
        raise ActionError("ACTION_NOT_OPEN")
    row.snoozed_until, row.snoozed_by = next_morning(now), _actor_id(actor)
    _audit(session, AUDIT_SNOOZED, row, row.snoozed_by)
    session.flush()
    return row


# ── 기간 끝남 · 되맞추기(밤 단계 · 승인 대기 읽기) ─────────────────────────
def expire_due(session: Any, now: datetime.datetime) -> int:
    """기간이 끝난(날짜가 지났거나 7일) 열린 · 실패한 제안을 ``expired`` 로. 커밋은 부르는 쪽. 바꾼 줄 수를 돌려준다."""
    rows = session.query(ErpActionProposal).filter(
        ErpActionProposal.status.in_(_DECIDABLE), ErpActionProposal.expires_at.isnot(None),
        ErpActionProposal.expires_at <= now).all()
    for row in rows:
        row.status = STATUS_EXPIRED
    session.flush()
    return len(rows)


def _settle_stuck(session: Any, row: ErpActionProposal) -> None:
    """실행 중으로 멈춘 줄 — 이 제안의 흔적이 주문에 있으면 executed, 아니면 open 으로 되돌린다."""
    order = session.get(Order, row.order_id) if row.order_id is not None else None
    if order is not None and fns.ran(row.action, order, row.params or {}, row.id):
        row.status, row.result, row.error_code = STATUS_EXECUTED, {"code": "RECONCILED"}, None
        _audit(session, AUDIT_EXECUTED, row, row.decided_by, code="RECONCILED")
        return
    row.status, row.result = STATUS_OPEN, None
    _audit(session, AUDIT_FAILED, row, row.decided_by, code="RECONCILED_REOPENED")
    _clear_decision(row)


def _close_link(session: Any, row: ErpActionProposal, now: datetime.datetime) -> bool:
    """바로가기(link) 제안 — 사람이 지금 화면에서 처리해 끝난 조건이 참이면 닫는다(실행한 사람 없음)."""
    order = session.get(Order, row.order_id) if row.order_id is not None else None
    if order is None or not fns.verify(row.action, order, row.params or {}):
        return False
    row.status, row.decided_action, row.decided_at = STATUS_EXECUTED, DECIDED_LINK, now
    row.result = {"code": "DONE_ON_ORDER"}
    _audit(session, AUDIT_EXECUTED, row, None, code="DONE_ON_ORDER")
    return True


def reconcile(session: Any, now: datetime.datetime) -> int:
    """되맞추기 — ``executing`` 으로 2분 넘게 남은 줄과 끝난 바로가기 제안을 맞춘다. 커밋은 부르는 쪽. 바꾼 줄 수."""
    stuck = (session.query(ErpActionProposal)
             .filter(ErpActionProposal.status == STATUS_EXECUTING, ErpActionProposal.decided_at < now - RECONCILE_AFTER)
             .with_for_update(skip_locked=True).all())
    for row in stuck:
        _settle_stuck(session, row)
    links = [name for name, spec in ACTIONS.items() if spec.mode == MODE_LINK]
    open_links = (session.query(ErpActionProposal)
                  .filter(ErpActionProposal.status == STATUS_OPEN, ErpActionProposal.action.in_(links))
                  .with_for_update(skip_locked=True).all()) if links else []
    closed = sum(1 for row in open_links if _close_link(session, row, now))
    session.flush()
    return len(stuck) + closed
