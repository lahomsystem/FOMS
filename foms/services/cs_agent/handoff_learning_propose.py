"""넘김 학습 — '더함' 대상이 넘김 학습이 고칠 수 없는 유형일 때(설계서 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md``
4.1 · 비평 종합 ``docs/plans/2026-11-26-brain-ontology-deep-critique.md`` 3.1).

놓을 자리 판정자가 '더함'(``adds``)이라 답했는데 대상이 가격 규칙 · 규격 · 용어처럼 넘김 학습이 고치지 않는 유형이면
(:func:`.handoff_learning_prompt.updatable` 은 라홈 사실 · 정책만) 예전에는 대상 키를 버리고 같은 내용의 새 사실을 만들었다 —
두 벌 지식 · 가짜 엇갈림 카드가 여기서 나왔다. 이제는 새 사실을 만들지 않고 **그 항목의 고침 제안**(열린 제안 — 지금 글 + 더할
말)을 올린다. 금액이 걸린 유형이라 **사람이 승인한다** — 바로 반영은 이 제안을 넣지 않는다(:func:`human_only`).

- 대상(:func:`proposable`): 살아 있는 라홈 · 모두가 보는 항목인데 **유형만** 고칠 수 없는 공통 바탕 유형(:data:`PROPOSE_TYPES` —
  가격 규칙 · 규격 · 용어 · 제작 조건 · 사장님 결정 · 브랜드). 다른 까닭으로 못 고치는 대상은 예전 그대로(부르는 쪽이 새 지식으로):
  브랜드(공통 — 하우드 문서에도 들어간다) · 보기 범위 · 상담 층 유형(기준 답은 주간 고침 안 몫 · 상황은 온톨로지 안 길) · 도면 층 ·
  빈 설명 칸 · 에이전트 일 · 관찰.
- 관문: 더할 말의 가림 · 한자(``mask``) · 숫자 출처(회사 지식 + 그 항목 지금 글 + 근거 직원 답 — 아니면 ``numbers``). 걸리면 새
  지식으로도 넣지 않는다. 그 항목에 누구든 열린 제안이 있으면 ``open_proposal``, 넘김 학습이 낸 비슷한 안이 거절됐으면
  ``rejected_before``. 제안 길의 글 · 근거 · 평가 관문은 그대로 탄다(부딪침은 판정자가 했으니 결과만 적는다 — :data:`SKIP`).
- 셈 이름 :data:`PROPOSED`.
"""

from __future__ import annotations

from typing import Any, Callable, NamedTuple, Optional

from foms.services.brain.ai_gates import STUB_TYPES
from foms.services.brain.constants import COMMON_TYPES, SCOPE_ALL, STATUS_ACTIVE
from foms.services.brain.gates import FAIL, text_gates
from foms.services.brain.proposals import propose_update
from foms.services.cs_agent.handoff_learning_gates import _duplicate, _numbers_ok, _open_on
from foms.services.cs_agent.handoff_learning_prompt import ITEM_TYPES
from foms.services.cs_agent.send import SEND_BRAND

__all__ = ["PROPOSED", "PROPOSE_TYPES", "Proposal", "human_only", "proposable", "propose_added"]

#: 셈 이름 — 더함 대상 고침 제안을 올림(사람 승인 대기).
PROPOSED = "placed_proposed"
#: 막지 않을 제안 길 관문(:data:`.handoff_learning_route.SKIP` 와 같다 — 시험이 맞춘다).
SKIP = ("conflict",)
#: 고침 제안으로 올리는 대상 유형 — 공통 바탕 유형에서 넘김 학습이 고치는 유형(사실 · 정책)과 빈 설명 칸을 뺀 것.
PROPOSE_TYPES: frozenset[str] = frozenset(COMMON_TYPES) - {*ITEM_TYPES, *STUB_TYPES}
_HEAD = "넘긴 상담 배우기 · "


class Proposal(NamedTuple):
    """고침 제안 갈래 답 — (막힌 까닭 코드, 넣는 함수). 부르는 쪽은 이 꼴이면 :data:`PROPOSED` 로 센다."""

    code: Optional[str]
    make: Optional[Callable[[], Any]]


def proposable(row: Any) -> bool:
    """'더함' 대상을 고침 제안으로 올릴 항목인가 — 살아 있는 라홈 · 모두가 보는 항목이고 유형만 고칠 수 없는 것(모듈 설명)."""
    return (row is not None and row.status == STATUS_ACTIVE and row.brand == SEND_BRAND and row.visibility == SCOPE_ALL
            and row.item_type in PROPOSE_TYPES)


def human_only(change: Any) -> bool:
    """사람이 승인해야 하는 넘김 학습 제안인가 — 사실 · 정책 밖 유형(이 갈래의 고침 제안). 바로 반영하지 않는다."""
    return getattr(change, "item_type", None) not in ITEM_TYPES


def propose_added(session: Any, target: Any, card: dict[str, Any], added: str, *, known: str,
                  replies: dict[str, list[str]]) -> Optional[Proposal]:
    """대상(``target``)이 :func:`proposable` 이면 지금 글 끝에 ``added`` 를 붙인 고침 제안(모듈 설명), 아니면 ``None``(부르는 쪽
    예전 길). ``card`` 는 부르는 쪽 안 꾸러미(``common`` — 제안 까닭 · 제안한 이 · 근거 · 시각 · 숫자 허용 글, ``seen``)."""
    if not proposable(target):
        return None
    gates = text_gates([added], "")
    if FAIL in (gates["mask"], gates["hanja"]):
        return Proposal("mask", None)
    if not _numbers_ok([added], f"{known}\n{target.text or ''}", replies):  # 지금 그 항목 글의 숫자는 이미 지식이다
        return Proposal("numbers", None)
    joined = f"{(target.text or '').rstrip()} {added}"
    dup = _duplicate(joined, card["seen"])
    if dup is not None or _open_on(session, target.item_key):
        return Proposal(dup or "open_proposal", None)
    common = card["common"]
    reason = common["reason"].replace(_HEAD, f"{_HEAD}지금 지식에 더할 말 · 사람 승인 · ", 1)[:500]
    fields = {**common, "reason": reason, "known": f"{common['known']}\n{target.text or ''}"}
    return Proposal(None, lambda: propose_update(session, key=target.item_key, base_version=target.version,
                                                 after={"text": joined}, skip_gates=SKIP, **fields))
