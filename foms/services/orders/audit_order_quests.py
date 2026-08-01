"""QUEST-BACKFILL-00 — read-only quest single-ness audit/classifier.

각 주문 ``structured_data.quests`` 를 검사해 **stage별 current(active) quest 단일성**
위반을 ``SAFE`` / ``AMBIGUOUS`` / ``MANUAL`` / ``CLEAN`` 으로 분류한다. 이 모듈은
**아무 것도 쓰지 않으며**(read-only), lazy-create 도 하지 않는다(GET/approve 복구 금지 계약과
정합; :func:`~foms.services.orders.state_axes.read_current_quest` 의 read-only 계약을 따른다).

quest 스키마·stage/team 매핑·active 판정 규칙은 다음을 **import 재사용**한다(무변경):

* :mod:`foms.services.orders.erp_policy_quests` — dynamic required approval teams.
* :mod:`foms.services.erp_quest_display` — ``ACTIVE_QUEST_STATUSES`` (OPEN/IN_PROGRESS).
* :mod:`foms.services.orders.erp_policy_constants` — ``STAGE_NAME_TO_CODE`` (label→code).

분류 규칙(§5.2 QUEST-BACKFILL-00):

* 한 stage code 에 active(non-terminal) quest 가 2개 이상 = 단일성 위반.
* 위반 stage 의 active 중복 중 approval 을 가진 quest 가 **2개 이상** → ``AMBIGUOUS``
  (어느 하나를 supersede 하면 approval 손실 → 자동 선택 금지 → manual CSV).
* approval 보유가 **0 또는 1개** → ``SAFE`` (approval 보유분을 survivor 로, 없으면 최신을
  survivor 로 두고 나머지 approval-0 중복만 supersede — approval 손실 0).
* quests 컨테이너가 list 아님 / entry 가 dict 아님 / stage 해석 불가 = ``MANUAL``.
* 위반·malformed 없음 = ``CLEAN``.

우선순위 ``AMBIGUOUS > MANUAL > SAFE > CLEAN`` — 사람이 봐야 하는 주문(ambiguous·malformed)은
절대 자동 backfill 하지 않는다. dynamic required team 정합은 report-only finding 이다
(단일성 정규화는 required_approvals 를 재작성하지 않는다).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from foms.services.erp_quest_display import ACTIVE_QUEST_STATUSES
from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE
from foms.services.orders.erp_policy_quests import (
    get_required_approval_teams_for_stage,
)

PACKET_ID = "QUEST-BACKFILL-00"
PHASE = "QUEST"
TOOL_VERSION = 1

CLEAN = "CLEAN"
SAFE = "SAFE"
AMBIGUOUS = "AMBIGUOUS"
MANUAL = "MANUAL"

CLASSIFICATIONS: Tuple[str, ...] = (CLEAN, SAFE, AMBIGUOUS, MANUAL)

_TERMINAL_TRANSITION = "SUPERSEDED"


# --------------------------------------------------------------------------- #
# quest predicates (readers 계약과 일치)
# --------------------------------------------------------------------------- #
def stage_code_of(raw_stage: Any) -> Optional[str]:
    """quest.stage(라벨 또는 코드)를 canonical stage code 로 정규화(해석 불가 시 None)."""
    text = str(raw_stage or "").strip()
    if not text:
        return None
    return STAGE_NAME_TO_CODE.get(text, text)


def is_superseded(quest: Dict[str, Any]) -> bool:
    """quest 가 terminal(마지막 transition ``to==SUPERSEDED`` 또는 status SUPERSEDED)인가."""
    transitions = quest.get("transitions")
    if isinstance(transitions, list) and transitions:
        last = transitions[-1]
        if isinstance(last, dict) and str(last.get("to") or "").upper() == _TERMINAL_TRANSITION:
            return True
    return str(quest.get("status") or "").upper() == _TERMINAL_TRANSITION


def is_active(quest: Dict[str, Any]) -> bool:
    """quest 가 current(active, non-terminal)인가 — display/read model 과 동일 판정."""
    if is_superseded(quest):
        return False
    return str(quest.get("status", "OPEN")).upper() in ACTIVE_QUEST_STATUSES


def has_approval(quest: Dict[str, Any]) -> bool:
    """quest 가 실제 approval(team 승인·assignee 승인·COMPLETED)을 보유하는가."""
    team_approvals = quest.get("team_approvals")
    if isinstance(team_approvals, dict):
        for value in team_approvals.values():
            if isinstance(value, dict):
                if value.get("approved"):
                    return True
            elif bool(value):
                return True
    assignee = quest.get("assignee_approval")
    if isinstance(assignee, dict) and assignee.get("approved"):
        return True
    return str(quest.get("status") or "").upper() == "COMPLETED"


def _newest_index(quests: List[Any], indexes: List[int]) -> int:
    """created_at/updated_at 가 가장 최신인 quest index(동률이면 뒤 index) — display 규칙 일치."""
    def sort_key(idx: int) -> Tuple[str, int]:
        quest = quests[idx]
        stamp = quest.get("created_at") or quest.get("updated_at") or "1970-01-01T00:00:00"
        return (str(stamp), idx)

    return max(indexes, key=sort_key)


def _expected_required_teams(stage_code: str, sd: Dict[str, Any]) -> List[str]:
    """stage 의 dynamic required approval teams(라홈 발주사 CS override 포함)."""
    teams = list(get_required_approval_teams_for_stage(stage_code))
    if stage_code in ("MEASURE", "CONFIRM"):
        orderer = (((sd.get("parties") or {}).get("orderer") or {}).get("name") or "").strip()
        if orderer and "라홈" in orderer:
            return ["CS"]
    return teams


# --------------------------------------------------------------------------- #
# audit result types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StageResolution:
    """단일성 위반 stage 의 결정적 정규화 plan(SAFE 전용).

    Attributes:
        stage_code: canonical stage code.
        active_indexes: sd['quests'] 내 active(중복) quest index 들.
        survivor_index: 유지할 quest index(approval 보유분 우선, 없으면 최신).
        superseded_indexes: terminal 처리할 approval-0 중복 index 들.
    """

    stage_code: str
    active_indexes: Tuple[int, ...]
    survivor_index: int
    superseded_indexes: Tuple[int, ...]


@dataclass(frozen=True)
class OrderQuestAudit:
    """한 주문의 quest 단일성 분류 결과.

    Attributes:
        order_id: 주문 id.
        classification: CLEAN/SAFE/AMBIGUOUS/MANUAL 중 하나.
        resolutions: SAFE 일 때 stage별 정규화 plan(그 외 빈 튜플).
        ambiguous_stages: 승인 충돌로 자동 결정 불가한 stage code 들.
        manual_reasons: malformed 구조 사유(quests_not_list 등).
        required_team_drift: required_approvals 가 dynamic 기대와 다른 stage code 들(report-only).
        source_sha: 이 주문 quests 소스의 fingerprint(backfill drift 감지용).
    """

    order_id: int
    classification: str
    resolutions: Tuple[StageResolution, ...] = ()
    ambiguous_stages: Tuple[str, ...] = ()
    manual_reasons: Tuple[str, ...] = ()
    required_team_drift: Tuple[str, ...] = ()
    source_sha: str = ""


def _quests_source_sha(raw_quests: Any) -> str:
    """주문 quests 소스의 결정적 sha256(canonical JSON, drift 감지)."""
    payload = json.dumps(raw_quests, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_quests(order_id: int, structured_data: Any) -> OrderQuestAudit:
    """한 주문의 structured_data 를 읽어 quest 단일성 분류 결과를 반환한다(read-only).

    Args:
        order_id: 주문 id.
        structured_data: 주문 structured_data(dict 아니면 빈 dict 취급).

    Returns:
        OrderQuestAudit — CLEAN/SAFE/AMBIGUOUS/MANUAL 분류 + SAFE plan.
    """
    sd = structured_data if isinstance(structured_data, dict) else {}
    raw = sd.get("quests")
    source_sha = _quests_source_sha(raw)

    if raw is None or (isinstance(raw, list) and not raw):
        return OrderQuestAudit(order_id, CLEAN, source_sha=source_sha)
    if not isinstance(raw, list):
        return OrderQuestAudit(
            order_id, MANUAL, manual_reasons=("quests_not_list",), source_sha=source_sha
        )

    manual_reasons: List[str] = []
    active_by_stage: Dict[str, List[int]] = {}
    for idx, quest in enumerate(raw):
        if not isinstance(quest, dict):
            manual_reasons.append(f"quest[{idx}]_not_dict")
            continue
        stage_code = stage_code_of(quest.get("stage"))
        if stage_code is None:
            manual_reasons.append(f"quest[{idx}]_unresolved_stage")
            continue
        if is_active(quest):
            active_by_stage.setdefault(stage_code, []).append(idx)

    ambiguous_stages: List[str] = []
    resolutions: List[StageResolution] = []
    for stage_code in sorted(active_by_stage):
        indexes = active_by_stage[stage_code]
        if len(indexes) < 2:
            continue
        approved = [i for i in indexes if has_approval(raw[i])]
        if len(approved) >= 2:
            ambiguous_stages.append(stage_code)
            continue
        survivor = approved[0] if approved else _newest_index(raw, indexes)
        superseded = tuple(i for i in indexes if i != survivor)
        resolutions.append(
            StageResolution(stage_code, tuple(indexes), survivor, superseded)
        )

    drift = tuple(_required_team_drift(raw, sd, active_by_stage))

    if ambiguous_stages:
        classification = AMBIGUOUS
        resolutions = []  # ambiguous 주문은 어떤 stage 도 자동 정규화하지 않는다.
    elif manual_reasons:
        classification = MANUAL
        resolutions = []
    elif resolutions:
        classification = SAFE
    else:
        classification = CLEAN

    return OrderQuestAudit(
        order_id=order_id,
        classification=classification,
        resolutions=tuple(resolutions),
        ambiguous_stages=tuple(ambiguous_stages),
        manual_reasons=tuple(manual_reasons),
        required_team_drift=drift,
        source_sha=source_sha,
    )


def _required_team_drift(
    raw_quests: List[Any], sd: Dict[str, Any], active_by_stage: Dict[str, List[int]]
) -> List[str]:
    """active quest 의 required_approvals 가 dynamic 기대와 다른 stage code 목록(report-only)."""
    drift: List[str] = []
    for stage_code in sorted(active_by_stage):
        expected = set(_expected_required_teams(stage_code, sd))
        for idx in active_by_stage[stage_code]:
            declared = raw_quests[idx].get("required_approvals")
            declared_set = {str(t) for t in declared} if isinstance(declared, list) else set()
            if declared_set != expected:
                drift.append(stage_code)
                break
    return drift


# --------------------------------------------------------------------------- #
# whole-table audit report
# --------------------------------------------------------------------------- #
@dataclass
class AuditReport:
    """전체 주문 quest 단일성 audit 요약(coverage 100% 증명 원장)."""

    total: int = 0
    counts: Dict[str, int] = field(default_factory=lambda: {c: 0 for c in CLASSIFICATIONS})
    safe_audits: List[OrderQuestAudit] = field(default_factory=list)
    ambiguous_audits: List[OrderQuestAudit] = field(default_factory=list)
    manual_audits: List[OrderQuestAudit] = field(default_factory=list)
    required_team_drift_ids: List[int] = field(default_factory=list)

    @property
    def unclassified(self) -> int:
        """어느 bucket 에도 들어가지 않은 주문 수(coverage 100% 이면 0)."""
        return self.total - sum(self.counts[c] for c in CLASSIFICATIONS)

    def manifest_sha256(self) -> str:
        """run identity 용 manifest sha256(packet/phase/tool/source composite)."""
        from foms.services.security.backfill.manifest import compute_manifest_sha256

        return compute_manifest_sha256(self._manifest_dict())

    def mapping_sha256(self) -> str:
        """SAFE 결정 목록의 canonical mapping sha256(order_id → NORMALIZE_SINGLETON)."""
        from foms.services.security.backfill.manifest import compute_mapping_sha256

        entries = [
            {
                "identity_fields": {"order_id": audit.order_id},
                "decision": "NORMALIZE_SINGLETON",
                "target_ids": [audit.order_id],
                "reason_code": "QUEST_SINGLETON",
            }
            for audit in self.safe_audits
        ]
        return compute_mapping_sha256(entries)

    def source_composite_sha256(self) -> str:
        """SAFE 주문 소스 fingerprint 의 결정적 합성 sha256(전체 drift 감지)."""
        payload = json.dumps(
            [[a.order_id, a.source_sha] for a in self.safe_audits],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _manifest_dict(self) -> Dict[str, Any]:
        return {
            "packet_id": PACKET_ID,
            "phase": PHASE,
            "tool_version": TOOL_VERSION,
            "total_rows": self.total,
            "safe_rows": self.counts[SAFE],
            "ambiguous_rows": self.counts[AMBIGUOUS],
            "manual_rows": self.counts[MANUAL],
            "source_composite_sha256": self.source_composite_sha256(),
        }


def iter_order_quests(session, *, batch_size: int = 1000) -> Iterable[Tuple[int, Any]]:
    """모든 주문의 ``(id, structured_data)`` 를 스트리밍(read-only, 전수 coverage)."""
    from models import Order

    query = session.query(Order.id, Order.structured_data).order_by(Order.id)
    for row in query.yield_per(batch_size):
        yield row[0], row[1]


def audit_orders(session, *, batch_size: int = 1000) -> AuditReport:
    """전체 주문을 분류해 coverage 100% audit 원장을 만든다(mutation 0).

    Args:
        session: SQLAlchemy Session(read-only 로만 사용).
        batch_size: 스트리밍 yield_per 크기.

    Returns:
        AuditReport — 총계·bucket 카운트·SAFE plan·ambiguous/manual/drift 목록.
    """
    report = AuditReport()
    for order_id, sd in iter_order_quests(session, batch_size=batch_size):
        audit = classify_quests(order_id, sd)
        report.total += 1
        report.counts[audit.classification] += 1
        if audit.classification == SAFE:
            report.safe_audits.append(audit)
        elif audit.classification == AMBIGUOUS:
            report.ambiguous_audits.append(audit)
        elif audit.classification == MANUAL:
            report.manual_audits.append(audit)
        if audit.required_team_drift:
            report.required_team_drift_ids.append(order_id)
    return report


__all__ = [
    "PACKET_ID",
    "PHASE",
    "CLEAN",
    "SAFE",
    "AMBIGUOUS",
    "MANUAL",
    "CLASSIFICATIONS",
    "StageResolution",
    "OrderQuestAudit",
    "AuditReport",
    "stage_code_of",
    "is_active",
    "is_superseded",
    "has_approval",
    "classify_quests",
    "audit_orders",
    "iter_order_quests",
]
