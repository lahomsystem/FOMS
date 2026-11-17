"""운영 AI · 일정 AI 훑기 — **모델을 부르지 않는 규칙**이 할 일 제안을 만든다(설계서 2026-11-14-foms-graft 3.10 · D207 · D214).

규칙(이름 → 함수 표 :data:`RULES` — 뒤 일감이 줄을 더한다. 예: T15 의 ``O4``):

- ``S1`` 일정: 협력사가 바란 시공일이 있고(``partner_intake.requested_construction``) 우리 시공일이 비었고 요청이 열려 있음
  → ``schedule_construction``(그 날 · 그 시간대 — 시간대가 정한 넷이 아니면 '정하지 않음').
- ``O1`` 운영: 실측일이 내일인데 지금 실측 일정으로 **나간** 실측 예약 알림톡 기록(``structured_data.alimtalk_measurement``)이
  없음 → ``send_measure_alimtalk``(:func:`foms.services.erp_actions.measure_notice.measure_sent` — 실패 · 건너뜀 기록과 옛 일정의
  자동 발송 기록은 '안 보냄', 승인 막는 조건과 같은 판정). 직접 실측 · 협력사 주문은 빼고, 알림톡은 **보내지 않는다**(제안만 —
  사람이 승인해야 나간다). 제안 기간은 실측일이 끝나는 때까지, 실측 일정이 바뀌면 옛 제안은 낡은 것으로 닫힌다(점검 2차 w6-01).
- ``O2`` 운영(D214 — 처음 수준 0): 지금 단계의 현재 작업이 모두 승인됐는데 단계가 2일 넘게 그대로 → ``advance_stage``.
  도면 단계(전용 명령으로만 넘어간다)와 고객컨펌 도면 문지기에 걸린 주문은 뺀다.
- ``O3`` 운영: 단계가 도면인데 도면 담당이 2일 넘게 비어 있음 → ``assign_draftsman``(담당 칸은 비워 둔다 — 승인자가 고른다).
- ``O4`` 운영(D208 · D214 — 처음 수준 0): 시공일이 내일인데 그 시공일의 시공일 안내 알림톡 기록
  (``structured_data.alimtalk_construction``)이 없음 → ``send_construction_alimtalk``. 시공일 안내가 쓸 수 있는 상태일 때만 —
  스위치(``FOMS_GRAFT_CONSTRUCTION_ALIMTALK``)가 꺼져 있으면 후보도 읽지 않고, 주문마다(브랜드 서식 번호 · 전화 · 협력사)는
  제안 만들기의 막는 조건이 거른다. 알림톡은 **보내지 않는다**(제안만).

- 후보는 납작 칸(``erp_stage_code`` · ``erp_construction_date`` · ``erp_stage_updated_at`` · ``partner_org_id``)과
  ``order_schedule_dates`` 색인으로 고르고, 후보만 ``structured_data`` 를 읽는다(JSONB 를 글자로 바꿔 찾지 않는다).
  같은 할 일 제안이 이미 걸린 주문(열림 · 실행 중 · 실패 — 값이 정해진 규칙은 거절도)은 같은 질의 안 ``NOT EXISTS`` 로 빼고,
  새 주문부터(``id`` · 단계 바뀐 때 내림차순) :data:`SCAN_LIMIT` 개를 읽는다 — 옛 주문이 자리를 차지해 새 주문에 못 닿지 않게.
- 제안은 :func:`foms.services.erp_actions.lifecycle.propose` 로만 만든다(겹침 · 거절된 적 · 막는 조건은 그 함수가 거른다).
  한 번 훑기에 :data:`MAX_PROPOSALS` 개까지. 직원 · 할 일 수준이 0(또는 못 함)이면 그 규칙은 후보도 고르지 않는다.
  후보 하나(판정 · 제안)는 저장점 안에서 돈다 — 그 후보가 터지면 그 저장점만 되감고 코드만 로그에 남긴 뒤 다음 후보로 간다.
- 상한 나누기(운영 첫 밤 — 앞 규칙이 24개를 먼저 써 시공 잡기 11개가 다음 밤으로 밀렸다): 켜진 규칙마다 **제 몫**(상한 ÷ 켜진 규칙 수)을
  먼저 주고, 남은 자리는 오늘 밤을 놓치면 소용없는 규칙(:attr:`Rule.due` — 내일 실측 · 내일 시공)부터 규칙 차례로 채운다. 밀린 일이
  많은 규칙 하나가 다른 규칙의 자리를 다 쓰지 못한다.
- 꺼진 규칙 거두기(D245 — 도면 담당 맡기기 · 협력사 시공 잡기를 끈 날 운영에 열린 제안 43개가 남아 있었다): 수준이 0(또는 못 함)인
  규칙은 그 직원이 훑기로 만든 열린 · 실패한 제안을 '낡은 것'(``superseded``)으로 닫는다. 사람이 결정한 것 · 상담에서 나온 제안은
  건드리지 않고, 승인 중이라 잠긴 줄은 건너뛴다. 다시 켜면 그 밤부터 새로 만든다(거절이 아니라 막지 않는다).
- ``FOMS_GRAFT_PROPOSERS`` 가 꺼져 있으면(:func:`foms.services.graft_flags.enabled_global`) **아무것도 읽지도 쓰지도 않고**
  ``enabled`` 거짓으로 끝난다(지금과 같다).
- 직원마다 실행 기록 한 줄(``ai_agent_runs`` — 규칙마다 후보 고르기 · 제안 만들기 단계와 걸린 시간). 커밋은 부르는 쪽.
- **폰 알림**: 훑기는 알림톡을 보내지 않지만, 폰 알림 스위치(``FOMS_GRAFT_PUSH_ENABLED`` — 이 훑기가 도는 서비스의 env)가 켜져
  있으면 새로 만든 제안마다 받는 사람(:func:`foms.services.erp_actions.notify.recipients` — 담당 → 관리자 → 팀)에게 커밋 뒤 폰
  알림이 간다(밤 단계라 한국 02:00 무렵). 꺼져 있으면(처음 값) 알림 줄도 만들지 않는다.
- 제안 기간 7일은 훑은 날부터 7일째 되는 날 0시(한국)에 끝난다(:attr:`SweepContext.week_end`) — 그 밤 단계 '끝남 닫기'가 닫고 이어 도는
  훑기가 같은 밤 다시 만든다(만든 때 + 7일이면 몇 분 차이로 그 밤을 비껴가 하루를 비운다 — 점검 2차 w6-12).
- 날짜는 한국 날짜(:func:`get_today_kst`). 이유 글은 코드가 정한 말뿐(손님 글 · 이름 없음).
"""

from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlalchemy import and_, or_, select

from foms.persistence.graft.models import ErpActionProposal
from foms.services import kakao_alimtalk_construction as construction_alimtalk
from foms.services.ai_staff.registry import AGENTS, level_table, proposer
from foms.services.ai_staff.runs import record_run
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions.freshness import PROPOSAL_DAYS
from foms.services.erp_actions.lifecycle import propose
from foms.services.erp_actions.measure_notice import measure_sent
from foms.services.erp_actions.registry import (
    STATUS_EXECUTING, STATUS_FAILED, STATUS_OPEN, STATUS_REJECTED, STATUS_SUPERSEDED, TIME_SLOTS,
)
from foms.services.erp_ontology.read import order_key
from foms.services.graft_flags import enabled_global
from foms.services.measurement_read_model import measurement_schedule_on_dates
from foms.services.orders.confirm_drawing_gate import confirm_exit_block, is_confirm_stage
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from foms.services.orders.erp_policy_permissions import get_assignee_ids
from foms.services.orders.erp_policy_quests import check_quest_approvals_complete
from foms.services.orders.stage_override import MAIN_PIPELINE_CODES
from foms.services.partners.schedule_request import REQUEST_CLOSED_STAGES, clean_date, pending_request
from models import Order, OrderScheduleDate

__all__ = ["MAX_PROPOSALS", "RULES", "SCAN_LIMIT", "STUCK_DAYS", "Candidate", "Rule", "SweepContext", "SweepResult",
           "run_sweep"]

logger = logging.getLogger(__name__)

MAX_PROPOSALS = 30
SCAN_LIMIT = 200  # 규칙 하나가 읽는 후보 주문 수(구조 칸까지 읽는 수의 천장)
STUCK_DAYS = 2
#: 단계 넘기기 규칙이 보지 않는 단계 — 도면은 전용 명령(도면 전달 · 수령 확정)으로만 넘어가고, 마지막 단계는 넘길 곳이 없다.
_NO_ADVANCE = frozenset({"DRAWING", MAIN_PIPELINE_CODES[-1]})
_KST = datetime.timedelta(hours=9)
#: 후보에서 빼는 제안 상태 — 이미 걸려 있어 :func:`propose` 가 어차피 만들지 않는 것(값이 늘 같은 규칙은 거절까지).
_HELD = (STATUS_OPEN, STATUS_EXECUTING, STATUS_FAILED)
_HELD_OR_REJECTED = (*_HELD, STATUS_REJECTED)


@dataclass(frozen=True)
class SweepContext:
    """훑기 한 번의 때 — 지금(UTC naive) · 한국 오늘."""

    now: datetime.datetime
    today: datetime.date

    @property
    def tomorrow(self) -> str:
        """한국 내일 'YYYY-MM-DD'."""
        return (self.today + datetime.timedelta(days=1)).isoformat()

    @property
    def week_end(self) -> datetime.datetime:
        """훑기 제안 기간의 끝 — 한국 오늘부터 7일째 되는 날 0시(한국)를 UTC naive 로(그 밤 단계가 닫고 다시 만든다)."""
        return datetime.datetime.combine(self.today + datetime.timedelta(days=PROPOSAL_DAYS), datetime.time()) - _KST

    @property
    def stuck_before(self) -> datetime.datetime:
        """이때보다 앞에 단계가 바뀐 주문은 '2일 넘게 그대로'(UTC naive — ``erp_stage_updated_at`` 과 같은 꼴)."""
        return self.now - datetime.timedelta(days=STUCK_DAYS)


@dataclass(frozen=True)
class Candidate:
    """제안 하나의 재료 — 주문 · 넣을 값 · 이유(코드가 정한 말)."""

    order: Any
    params: dict[str, Any]
    reason: str
    scope: Optional[str] = None  # 넣을 값이 없는 규칙의 상황(겹침 열쇠 — 원장 F-08). 바뀌면 거절 뒤에도 다시 제안된다.
    # 실측 예약 · 시공일 안내 알림톡은 할 일 쪽 상황(:func:`foms.services.erp_actions.preview.scope`)이 먼저다(같은 값).


@dataclass(frozen=True)
class Rule:
    """훑기 규칙 하나 — 이름 · 직원 · 할 일 · 화면 말 · 후보 고르는 도구 · 후보 고르기(질의) · 주문 하나 판정."""

    key: str
    agent: str
    action: str
    label: str
    tool: str
    pick: Callable[[Any, SweepContext, str, int], list[Any]]
    judge: Callable[[Any, SweepContext], Optional[Candidate]]
    due: bool = False  # 오늘 밤을 놓치면 소용없는 규칙(내일 일) — 남은 자리를 먼저 받는다


@dataclass
class SweepResult:
    """훑기 결과 — 켜졌나 · 만든 제안 수 · 규칙마다 수 · 거둔 수 · 실행 기록 번호."""

    enabled: bool
    created: int = 0
    by_rule: dict[str, int] = field(default_factory=dict)
    withdrawn: dict[str, int] = field(default_factory=dict)  # 꺼진 규칙이 거둔 열린 제안 수(규칙 이름 → 수)
    runs: list[int] = field(default_factory=list)


def _aliases(code: str) -> tuple[str, ...]:
    """단계 코드와 한글 이름(옛 줄은 ``erp_stage_code`` 에 한글이 남아 있을 수 있다)."""
    return tuple(dict.fromkeys(name for name in (code, STAGE_LABELS.get(code, "")) if name))


def _orders(session: Any, action: str, *conds: Any, limit: int, held: tuple[str, ...] = _HELD_OR_REJECTED,
            newest: tuple[Any, ...] = ()) -> list[Any]:
    """지워지지 않고 초안이 아닌 ERP 주문 가운데 조건에 맞고 ``action`` 제안이 걸리지 않은 것 — 새것부터 ``limit`` 개.

    Args:
        session: DB 세션. action: 규칙의 할 일 이름(이 할 일 제안이 ``held`` 상태로 있는 주문은 같은 질의에서 뺀다).
        conds: 납작 칸 조건. limit: 읽을 주문 수. held: 빼는 제안 상태.
        newest: 번호보다 먼저 볼 내림차순 칸(예: 단계 바뀐 때).

    Returns:
        주문 목록(질의 한 번).
    """
    taken = select(ErpActionProposal.id).where(ErpActionProposal.order_id == Order.id,
                                               ErpActionProposal.action == action,
                                               ErpActionProposal.status.in_(held))
    query = (select(Order).where(Order.active_filter(), Order.is_erp_order.is_(True), *conds, ~taken.exists())
             .order_by(*(column.desc() for column in newest), Order.id.desc()))
    return list(session.execute(query.limit(limit)).scalars())


def _sd(order: Any) -> dict[str, Any]:
    data = getattr(order, "structured_data", None)
    return data if isinstance(data, dict) else {}


# ── 규칙 ─────────────────────────────────────────────────────────────────
def _pick_partner_requests(session: Any, ctx: SweepContext, action: str, limit: int) -> list[Any]:
    """S1 후보 — 협력사 주문 · 우리 시공일 빔 · 시공 전(거절은 빼지 않는다 — 희망 날이 바뀌면 열쇠가 달라진다)."""
    return _orders(session, action, Order.partner_org_id.isnot(None),
                   or_(Order.erp_construction_date.is_(None), Order.erp_construction_date == ""),
                   or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(REQUEST_CLOSED_STAGES)),
                   limit=limit, held=_HELD)


def _judge_partner_request(order: Any, ctx: SweepContext) -> Optional[Candidate]:
    """S1 — 열린 희망 시공일이 오늘이거나 뒤면 그 날 · 시간대(정한 넷이 아니면 '정하지 않음')."""
    request = pending_request(_sd(order), order.erp_stage_code or "")
    day = clean_date((request or {}).get("date"))
    if not day or datetime.date.fromisoformat(day) < ctx.today:
        return None
    slot = str((request or {}).get("time") or "").strip()
    return Candidate(order, {"date": day, "time": slot if slot in TIME_SLOTS else ""},
                     "협력사가 바란 시공일이 있는데 우리 시공일이 아직 비었어요.")


def _pick_measure_alimtalk(session: Any, ctx: SweepContext, action: str, limit: int) -> list[Any]:
    """O1 후보 — 내일 실측(납작 칸 · 일정 색인) · 직접 실측 · 협력사 주문 빼고."""
    tomorrow = ctx.tomorrow
    return _orders(session, action, Order.partner_org_id.is_(None),
                   or_(Order.is_self_measurement.is_(None), Order.is_self_measurement.is_(False)),
                   or_(Order.erp_measurement_date == tomorrow, measurement_schedule_on_dates([tomorrow])),
                   limit=limit, held=_HELD)  # 거절은 빼지 않는다 — 실측 일정이 바뀌면 열쇠가 달라진다(F-08)


def _judge_measure_alimtalk(order: Any, ctx: SweepContext) -> Optional[Candidate]:
    """O1 — 지금 일정으로 나간 실측 예약 알림톡이 없으면 제안."""
    if measure_sent(int(order.id), _sd(order)):
        return None
    return Candidate(order, {}, "내일 실측인데 실측 예약 알림톡을 보낸 기록이 없어요.")  # 상황 = 실측 일정(할 일 쪽)


def _pick_stuck_stage(session: Any, ctx: SweepContext, action: str, limit: int) -> list[Any]:
    """O2 후보 — 도면 · 마지막 단계가 아닌 단계로 2일 넘게 그대로(방금 그 선을 넘은 주문부터)."""
    stages = [name for code in MAIN_PIPELINE_CODES if code not in _NO_ADVANCE for name in _aliases(code)]
    return _orders(session, action, Order.erp_stage_code.in_(stages), Order.erp_stage_updated_at.isnot(None),
                   Order.erp_stage_updated_at <= ctx.stuck_before, limit=limit, held=_HELD,
                   newest=(Order.erp_stage_updated_at,))  # 거절은 빼지 않는다 — 단계가 바뀌면 열쇠가 달라진다(F-08)


def _judge_stuck_stage(order: Any, ctx: SweepContext) -> Optional[Candidate]:
    """O2 — 현재 작업이 모두 승인됐고 고객컨펌 문지기(승인 길과 같은)에 걸리지 않으면 제안."""
    sd, stage = _sd(order), order.erp_stage_code or ""
    if not check_quest_approvals_complete(sd, stage)[0]:
        return None
    if is_confirm_stage(stage) and confirm_exit_block(sd) is not None:
        return None
    return Candidate(order, {}, "지금 단계의 현재 작업이 모두 승인됐는데 단계가 2일 넘게 그대로예요.", scope=stage)


def _pick_no_draftsman(session: Any, ctx: SweepContext, action: str, limit: int) -> list[Any]:
    """O3 후보 — 도면 단계로 2일 넘게 있는 주문(방금 그 선을 넘은 주문부터)."""
    return _orders(session, action, Order.erp_stage_code.in_(_aliases("DRAWING")),
                   Order.erp_stage_updated_at.isnot(None), Order.erp_stage_updated_at <= ctx.stuck_before,
                   limit=limit, newest=(Order.erp_stage_updated_at,))


def _judge_no_draftsman(order: Any, ctx: SweepContext) -> Optional[Candidate]:
    """O3 — 도면 담당이 비었으면 제안(담당 칸은 비워 둔다 — 승인자가 고른다)."""
    if get_assignee_ids(order, "DRAWING_DOMAIN"):
        return None
    return Candidate(order, {}, "도면 단계인데 도면 담당이 2일 넘게 비어 있어요.")


def _pick_construction_alimtalk(session: Any, ctx: SweepContext, action: str, limit: int) -> list[Any]:
    """O4 후보 — 내일 시공(납작 칸 · 일정 색인) · 협력사 주문 빼고. 스위치가 꺼져 있으면 읽지도 않는다."""
    if not enabled_global("construction_alimtalk"):
        return []
    tomorrow = ctx.tomorrow
    on_tomorrow = Order.schedule_dates.any(and_(OrderScheduleDate.kind == "construction",
                                                OrderScheduleDate.date == tomorrow))
    return _orders(session, action, Order.partner_org_id.is_(None),
                   or_(Order.erp_construction_date == tomorrow, on_tomorrow), limit=limit,
                   held=_HELD)  # 거절은 빼지 않는다 — 시공일이 바뀌면 열쇠가 달라진다(F-08)


def _judge_construction_alimtalk(order: Any, ctx: SweepContext) -> Optional[Candidate]:
    """O4 — 그 시공일로 나간 시공일 안내가 없으면 제안(실패 기록 · 옛 시공일 기록은 안 보냄)."""
    sd = _sd(order)
    day = construction_alimtalk.construction_day(sd)
    if construction_alimtalk.sent_for(sd, day):
        return None
    return Candidate(order, {}, "내일 시공인데 시공일 안내 알림톡을 보낸 기록이 없어요.")  # 상황 = 시공일(할 일 쪽)


#: 규칙 이름 → 규칙(차례대로 돈다). 뒤 일감은 여기 줄을 더한다.
RULES: dict[str, Rule] = {rule.key: rule for rule in (
    Rule("S1", "schedule", "schedule_construction", "협력사 희망 시공일 있음 · 우리 시공일 빔", "erp.visit.list",
         _pick_partner_requests, _judge_partner_request),
    Rule("O1", "ops", "send_measure_alimtalk", "내일 실측 · 알림톡 기록 없음", "erp.order.list",
         _pick_measure_alimtalk, _judge_measure_alimtalk, due=True),
    Rule("O2", "ops", "advance_stage", "현재 작업 모두 승인 · 단계 2일 그대로", "erp.order.list",
         _pick_stuck_stage, _judge_stuck_stage),
    Rule("O3", "ops", "assign_draftsman", "도면 단계 · 담당 2일 비어 있음", "erp.order.list",
         _pick_no_draftsman, _judge_no_draftsman),
    Rule("O4", "ops", "send_construction_alimtalk", "내일 시공 · 시공일 안내 기록 없음", "erp.order.list",
         _pick_construction_alimtalk, _judge_construction_alimtalk, due=True),
)}


# ── 돌리기 ───────────────────────────────────────────────────────────────
def _elapsed(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _propose_one(session: Any, rule: Rule, order: Any, level: int, ctx: SweepContext, run_id: int) -> bool:
    """주문 하나 — 판정 → 제안을 저장점 안에서. 만들었으면 참. 터지면 이 저장점만 되감고 코드만 로그에 남긴다(거짓)."""
    try:
        with session.begin_nested():
            candidate = rule.judge(order, ctx)
            if candidate is None:
                return False
            evidence = [{"kind": "order", "ref": order_key(int(order.id)), "label": f"주문 #{order.id}"}]
            row = propose(session, action=rule.action, proposed_by=proposer(rule.agent), order=order,
                          params=candidate.params, reason=candidate.reason, evidence=evidence, source_kind="sweep",
                          source_ref=str(run_id), level=level, now=ctx.now, dedupe_scope=candidate.scope)
            if row is not None and row.expires_at is not None:
                row.expires_at = min(row.expires_at, ctx.week_end)  # 7일째 0시(한국) — 그 밤 단계가 닫고 다시 만든다(w6-12)
            return row is not None
    except Exception as exc:  # 후보 하나의 실패가 그 밤의 다른 제안을 되돌리지 않게 — 코드만 남긴다
        logger.warning("[AI-STAFF] 훑기 후보 실패 rule=%s order=%s code=%s", rule.key, getattr(order, "id", None),
                       type(exc).__name__)
        return False


@dataclass
class _Turn:
    """켜진 규칙 하나의 차례 — 후보(처음 받을 때 한 번 고른다) · 어디까지 봤나 · 만든 수 · 걸린 시간."""

    rule: Rule
    level: int
    run_id: int
    orders: Optional[list[Any]] = None  # ``None`` = 자리가 없어 후보도 고르지 않음
    at: int = 0
    made: int = 0
    picked_ms: int = 0
    made_ms: int = 0

    def steps(self, limit: int) -> list[dict[str, Any]]:
        """실행 기록 단계 — 후보 고르기 · 제안 만들기(자리가 없었으면 건너뜀 한 줄)."""
        rule = self.rule
        if self.orders is None:
            return [{"tool": rule.tool, "what": f"건너뜀 — {rule.key}", "detail": f"한 번에 {limit}개까지", "ms": 0}]
        return [{"tool": rule.tool, "what": f"후보 고르기 — {rule.key}", "detail": f"후보 {len(self.orders)}개",
                 "ms": self.picked_ms},
                {"tool": "actions.propose", "what": f"제안 만들기 — {rule.key}", "detail": f"제안 {self.made}개",
                 "ms": self.made_ms}]


def _take(session: Any, turn: _Turn, ctx: SweepContext, room: int) -> int:
    """이 규칙이 ``room`` 개까지 더 만든다 — 후보는 처음 한 번만 고르고(질의 한 번) 본 데부터 이어 간다. 만든 수."""
    if room <= 0:
        return 0
    if turn.orders is None:
        started = time.perf_counter()
        turn.orders = turn.rule.pick(session, ctx, turn.rule.action, SCAN_LIMIT)
        turn.picked_ms = _elapsed(started)
    started, made = time.perf_counter(), 0
    while turn.at < len(turn.orders) and made < room:
        order = turn.orders[turn.at]
        turn.at += 1
        made += _propose_one(session, turn.rule, order, turn.level, ctx, turn.run_id)
    turn.made += made
    turn.made_ms += _elapsed(started)
    return made


def _withdraw(session: Any, rule: Rule) -> int:
    """꺼진 규칙이 훑기로 만든 열린 · 실패한 제안을 '낡은 것'으로 닫는다(잠긴 줄은 건너뜀). 닫은 수."""
    rows = (session.query(ErpActionProposal)
            .filter(ErpActionProposal.action == rule.action, ErpActionProposal.proposed_by == proposer(rule.agent),
                    ErpActionProposal.source_kind == "sweep", ErpActionProposal.status.in_((STATUS_OPEN, STATUS_FAILED)))
            .with_for_update(skip_locked=True).all())
    for row in rows:
        row.status = STATUS_SUPERSEDED
    return len(rows)


def _close_run(session: Any, run: Any, rules: list[Rule], turns: dict[str, _Turn], limit: int,
               withdrawn: dict[str, int]) -> None:
    """직원 하나의 실행 기록을 채운다 — 규칙 차례대로 단계 · 걸린 시간 · 만든 수. 꺼진 규칙은 열린 제안을 거둔다."""
    steps: list[dict[str, Any]] = []
    for rule in rules:
        turn = turns.get(rule.key)
        if turn:
            steps.extend(turn.steps(limit))
            continue
        steps.append({"tool": rule.tool, "what": f"건너뜀 — {rule.key}", "detail": "수준 0 — 제안 안 만듦", "ms": 0})
        started, closed = time.perf_counter(), _withdraw(session, rule)
        if closed:
            steps.append({"tool": "actions.propose", "what": f"열린 제안 닫기 — {rule.key}", "detail": f"닫음 {closed}개",
                          "ms": _elapsed(started)})
            withdrawn[rule.key] = closed
    mine = [turns[rule.key] for rule in rules if rule.key in turns]
    run.steps = steps
    run.total_ms = sum(turn.picked_ms + turn.made_ms for turn in mine)
    run.proposals = sum(turn.made for turn in mine)
    run.outcome = "done" if mine else "level_zero"
    session.flush()


def run_sweep(session: Any, *, now: Optional[datetime.datetime] = None, today: Optional[datetime.date] = None,
              limit: int = MAX_PROPOSALS) -> SweepResult:
    """훑기 한 번 — 규칙마다 제 몫을 먼저 만들고 남은 자리를 채운다(커밋은 부르는 쪽).

    Args:
        session: DB 세션.
        now: 지금(UTC naive — 없으면 :func:`now_utc_naive`).
        today: 한국 오늘(없으면 :func:`get_today_kst`).
        limit: 한 번에 만들 제안 수 상한(처음 30).

    Returns:
        :class:`SweepResult` — 스위치가 꺼져 있으면 ``enabled`` 거짓 · 0 개(아무것도 읽지도 쓰지도 않음).
    """
    if not enabled_global("proposers"):
        return SweepResult(enabled=False)
    ctx = SweepContext(now=now or now_utc_naive(), today=today or get_today_kst())
    result = SweepResult(enabled=True)
    table = level_table(session)
    staff: list[tuple[Any, list[Rule]]] = []
    turns: dict[str, _Turn] = {}
    for agent in AGENTS:
        rules = [rule for rule in RULES.values() if rule.agent == agent]
        if not rules:
            continue
        # 실행 기록 한 줄을 먼저 만든다(번호가 제안 출처) — 단계 · 시간 · 수는 끝에 채운다
        run = record_run(session, agent, [], started_at=ctx.now, total_ms=0, source_kind="sweep", source_ref=None)
        staff.append((run, rules))
        for rule in rules:
            level = table.get(agent, {}).get(rule.action) or 0
            if level > 0:
                turns[rule.key] = _Turn(rule, level, run.id)
    share = max(1, limit // len(turns)) if turns else 0
    for turn in turns.values():  # ① 규칙마다 제 몫
        result.created += _take(session, turn, ctx, min(share, limit - result.created))
    for turn in sorted(turns.values(), key=lambda item: not item.rule.due):  # ② 남은 자리 — 내일 일부터
        result.created += _take(session, turn, ctx, limit - result.created)
    for run, rules in staff:
        _close_run(session, run, rules, turns, limit, result.withdrawn)
        result.runs.append(run.id)
        result.by_rule.update({rule.key: turns[rule.key].made if rule.key in turns else 0 for rule in rules})
    return result
