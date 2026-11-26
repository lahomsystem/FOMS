"""밤 배우기 지식 목록 아껴 보내기(설계 글 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 6절 — 처음 끔).

밤 배우기(:mod:`.handoff_learning`)는 한 밤에 열 몇 번 모델을 부르고, 그때마다 회사 지식 · 온톨로지 목록 전체를 다시 보낸다(입력의
약 9할). 켜면 **한 밤 처음 부르기 때 목록 줄을 한 번 만들어 굳히고**(:func:`night_lists`), 그 밤 부르기마다 같은 글을 ``system``
둘째 블록(1시간 캐시 표시)으로 보낸다(:func:`.handoff_learning_prompt.build_params`). 그 밤에 새로 들어가거나 바뀐 항목은 사용자
글의 꼬리 줄로 간다 — 지금 목록 줄 가운데 굳힌 목록에 없는 줄이라, 그 밤 방금 넣은 지식을 다음 부르기가 보는 '그 밤 두 벌 막기'는
그대로다.

- **굳힌 글을 DB 한 줄에 둔다**(SystemSetting :data:`STORE_KEY` — ``{"day": KST 날, "knowledge": [줄], "ontology": [줄]}``):
  밤 배우기는 15분 바퀴마다 한 번씩 부르고(바퀴 사이 15분 + 바퀴 시간), 재배포 · 두 컨테이너가 겹치면 프로세스가 바뀐다.
  메모리에만 두면 새 프로세스가 그 밤 넣은 지식까지 든 목록을 새로 만들어 캐시를 다시 쓴다. 날이 같으면 어느 프로세스든 같은 글을
  읽는다(다음 날 첫 부르기가 덮어쓴다 — 한 줄뿐).
- **차례 고정**: 굳힐 때 항목을 파이썬 글자 차례로 다시 줄 세운다(:func:`ordered` — 고칠 수 있는 라홈 사실 · 정책 먼저, 그다음
  키). DB 정렬 규칙(한글 정렬 무게)에 기대지 않는다.
- **끔**: 패널 :data:`.handoff_learn_settings.CACHE_FIELD` 가 꺼져 있으면 ``None`` — 표를 읽지도 쓰지도 않고 요청 꼴이 예전과
  글자까지 같다.
- **캐시는 모델마다 따로다**: 어려운 묶음(Opus) · 쉬운 묶음(Sonnet)을 섞어 부르면 한 밤에 첫 쓰기가 모델마다 한 번씩이다. 같은
  모델 부르기 사이가 1시간을 넘으면 그 모델은 다시 쓴다(값은 보통 입력의 2배 — 상한 예약 셈
  :func:`.brain_prompt.worst_case_cost` 는 캐시를 믿지 않고 늘 이 값으로 잡는다).

글(회사 지식 줄)은 로그에 싣지 않는다. 줄은 개인정보 꼴을 뺀 목록 줄(:func:`.handoff_learning_prompt.knowledge_lines` ·
:func:`.photo_learning_prompt.knowledge_lines`) 그대로다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.cs_agent import photo_learning_prompt as onto_prompt
from foms.services.cs_agent.handoff_learn_settings import CACHE_FIELD
from foms.services.cs_agent.handoff_learning_prompt import ITEM_TYPES, knowledge_lines
from foms.services.cs_agent.send import SEND_BRAND
from models import SystemSetting

__all__ = ["STORE_KEY", "NightLists", "night_lists", "ordered"]

STORE_KEY = "cs_agent_handoff_learn_lists"


@dataclass(frozen=True)
class NightLists:
    """그 밤 굳힌 목록 줄 — 회사 지식(:func:`.handoff_learning_prompt.knowledge_lines`) · 온톨로지."""

    knowledge: tuple[str, ...]
    ontology: tuple[str, ...]


def ordered(rows: Sequence[Any]) -> list[Any]:
    """항목 → 굳힐 차례(고칠 수 있는 라홈 사실 · 정책이 먼저 — :func:`.handoff_learning_prompt.knowledge_rows` 와 같은 갈래, 그
    안은 키의 파이썬 글자 차례)."""
    return sorted(rows, key=lambda row: (not (row.brand == SEND_BRAND and row.item_type in ITEM_TYPES),
                                         str(row.item_key or "")))


def _lines(value: Any) -> Optional[tuple[str, ...]]:
    """저장 값의 줄 목록(꼴이 틀리면 ``None`` — 다시 굳힌다)."""
    if not isinstance(value, list) or not all(isinstance(line, str) for line in value):
        return None
    return tuple(value)


def _locked(session: Any) -> Any:
    """굳힌 목록 줄을 잠가 읽는다(없으면 먼저 만들어 커밋 — 두 컨테이너가 같이 만들면 하나만 남는다)."""
    if session.get(SystemSetting, STORE_KEY) is None:
        session.add(SystemSetting(setting_key=STORE_KEY, setting_value={},
                                  description="AI 상담팀원 밤 배우기 — 그 밤 굳힌 회사 지식 목록(캐시 앞부분)"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return session.get(SystemSetting, STORE_KEY, populate_existing=True, with_for_update=True)


def _stored(row: Any, day: str) -> Optional[NightLists]:
    """저장 줄이 그 날 굳힌 목록이면 그것(아니면 ``None``)."""
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    knowledge, ontology = _lines(value.get("knowledge")), _lines(value.get("ontology"))
    if value.get("day") != day or knowledge is None or ontology is None:
        return None
    return NightLists(knowledge, ontology)


def night_lists(session: Any, cfg: Any, day: str, rows: Sequence[Any], onto_rows: Sequence[Any]) -> Optional[NightLists]:
    """그 밤 굳힌 목록(모듈 설명) — 끔이면 ``None``(DB 에 닿지 않는다).

    같은 날 굳힌 줄이 있으면 그대로 돌려준다(읽기만). 없거나(그 밤 첫 부르기 · 켠 뒤 첫 부르기) 다른 날 것이면 지금 항목(``rows`` —
    :func:`.handoff_learning_prompt.knowledge_rows`, ``onto_rows`` — :func:`.photo_learning_prompt.knowledge_rows`)으로 새로
    굳혀 줄을 잠그고 적는다(커밋 — 그 사이 다른 컨테이너가 먼저 적었으면 그것을 쓴다)."""
    if cfg.get(CACHE_FIELD) is not True:
        return None
    kept = _stored(session.get(SystemSetting, STORE_KEY, populate_existing=True), day)
    if kept is not None:
        return kept
    fresh = NightLists(tuple(knowledge_lines(ordered(rows))),  # 잠그기 전에 — 커밋하면 항목 줄이 만료된다
                       tuple(onto_prompt.knowledge_lines(sorted(onto_rows, key=lambda row: str(row.item_key or "")))))
    row = _locked(session)
    kept = _stored(row, day)
    if kept is None:
        row.setting_value = {"day": day, "knowledge": list(fresh.knowledge), "ontology": list(fresh.ontology)}
        flag_modified(row, "setting_value")
    session.commit()
    return fresh if kept is None else kept
