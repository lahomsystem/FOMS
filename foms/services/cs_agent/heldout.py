"""시험용으로 떼어 둔 상담 — 새 상담 일부를 배우기에서 빼 상담 AI 시험(⑪ 'AI 시험')의 '지난 상담' 문제로 쓴다(사용자 결정 D219).

- **칸**(:data:`HELD_OUT_FIELD`): 관리 패널 '시험용으로 떼어 둘 상담' 비율(0 ~ 100 %, 처음 값 10). 0 이면 떼어 두지 않는다 —
  차례 줄은 지금과 똑같이 ``held_out = false`` 이고 DB 를 더 읽지도 않는다.
- **규칙**(:func:`rule_holds`): 상담 단위로 정해진다 — (브랜드, 상담 id) 글자의 SHA-256 앞 8바이트를 100 으로 나눈 나머지가 비율보다
  작으면 떼어 둔다. 같은 상담은 늘 같은 결과다(바퀴 · 프로세스 · 서버가 달라도).
- **상담 안에서 섞이지 않게**(:func:`held_out_for`): 그 상담에 이미 차례가 있으면 그 상담의 첫 차례 값을 따른다 — 비율을 바꿔도
  이어지는 상담은 쪽을 바꾸지 않는다(배우기 · 시험이 같은 상담의 앞뒤 대화를 나눠 갖지 않게). 이 기능 전 차례(모두 false)로
  시작한 상담은 계속 배우기 쪽이다 — 옛 차례는 바꾸지 않는다.
- 값은 차례를 처음 만들 때(:func:`.turns.claim_turn` 의 넣기) 한 번 적는다. 실패 줄 다시 집기는 그 값을 그대로 둔다.
- 떼어 둔 상담도 손님 응대(초안 · 보내기 · 화면)는 똑같다. 빠지는 곳은 배우기 길뿐이다 — 사례 고르기(:mod:`.case_material` ·
  :mod:`.case_meaning`) · 사례 벡터(:mod:`foms.services.brain.embed_sources`) · 넘김 배우기(:mod:`.handoff_learning`) · 사진 배우기
  (:mod:`.photo_learning`) · 주간 고침 안(:mod:`.weekly_fix`) · 사진 설명 뽑기(:mod:`.photo_desc`). 직원 답 붙이기
  (:mod:`.case_memory`)는 떼어 둔 차례에도 한다 — 시험의 정답이다.

:mod:`.settings` 가 이 모듈을 부르므로 여기서는 칸 꼴(:mod:`.settings_field`)만 가져온다.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select

from foms.persistence.main.models import CsAgentTurn
from foms.services.cs_agent.settings_field import KIND_INT, Field

__all__ = ["GROUP_HELD_OUT", "HELD_OUT_DEFAULT", "HELD_OUT_FIELD", "HELD_OUT_FIELDS", "chat_bucket", "held_out_for",
           "held_out_percent", "rule_holds"]

GROUP_HELD_OUT = "AI 시험용 떼어 두기"
HELD_OUT_FIELD = "held_out_percent"
HELD_OUT_DEFAULT = 10
_BUCKETS = 100

HELD_OUT_FIELDS: tuple[Field, ...] = (
    Field(HELD_OUT_FIELD, "시험용으로 떼어 둘 상담", KIND_INT, HELD_OUT_DEFAULT, GROUP_HELD_OUT, low=0, high=_BUCKETS,
          unit="%",
          help="새 상담 가운데 이만큼을 AI 가 배우지 않게 떼어 두고, AI 시험 칸의 '지난 상담' 문제로 써요. 한 상담의 글은 "
               "모두 같은 쪽으로 가요. 떼어 둔 상담도 손님께 답하는 건 똑같아요. 이미 있던 상담은 바뀌지 않아요. 0 이면 "
               "떼어 두지 않아요(예전 그대로)"),
)


def held_out_percent(cfg: Any) -> int:
    """패널 값 → 떼어 둘 비율(0 ~ 100). 꼴이 틀리면 0(떼어 두지 않음).

    Args:
        cfg: :func:`.settings.read_settings` 값(``get`` 이 되는 것).

    Returns:
        0 ~ 100 정수.
    """
    value = cfg.get(HELD_OUT_FIELD)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(0, min(_BUCKETS, value))


def chat_bucket(brand: str, chat_id: str) -> int:
    """상담 하나의 자리(0 ~ 99) — (브랜드, 상담 id) 글자의 SHA-256 앞 8바이트를 100 으로 나눈 나머지.

    Args:
        brand: 상담 브랜드.
        chat_id: 채널톡 상담 id.

    Returns:
        0 ~ 99 정수(같은 상담은 늘 같은 값).
    """
    digest = hashlib.sha256(f"{brand}\x1f{chat_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % _BUCKETS


def rule_holds(brand: str, chat_id: str, percent: int) -> bool:
    """규칙만으로 이 상담을 떼어 두나 — 자리가 비율보다 작을 때(0 이면 늘 거짓, 100 이면 늘 참).

    Args:
        brand: 상담 브랜드.
        chat_id: 채널톡 상담 id.
        percent: 떼어 둘 비율(0 ~ 100).

    Returns:
        떼어 두면 True.
    """
    return percent > 0 and chat_bucket(brand, chat_id) < percent


def held_out_for(session: Any, brand: str, chat_id: str, percent: int) -> bool:
    """새 차례에 적을 ``held_out`` — 비율 0 이면 거짓(DB 를 읽지 않음), 그 상담에 차례가 있으면 첫 차례 값, 없으면 규칙.

    Args:
        session: DB 세션.
        brand: 상담 브랜드.
        chat_id: 채널톡 상담 id.
        percent: 떼어 둘 비율(:func:`held_out_percent`).

    Returns:
        떼어 두면 True.
    """
    if percent <= 0:
        return False
    first = session.execute(select(CsAgentTurn.held_out)
                            .where(CsAgentTurn.brand == brand, CsAgentTurn.chat_id == chat_id)
                            .order_by(CsAgentTurn.id).limit(1)).scalar()
    if first is not None:
        return bool(first)
    return rule_holds(brand, chat_id, percent)
