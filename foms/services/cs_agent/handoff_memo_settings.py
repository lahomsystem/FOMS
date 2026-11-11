"""관리 패널 '넘김 메모' 칸 — AI 가 초안을 안 쓰고 사람에게 넘긴 차례에 까닭 메모를 남길지(처음 끔).

칸은 :mod:`.settings` 의 ``FIELDS`` 끝에 붙는다(같은 읽기 · 쓰기 · 수정 기록 길). 끄면 예전 그대로 넘김 · 검사 걸림은 기록만
하고 채널톡에 아무것도 쓰지 않는다. 켜도 초안 스위치가 '메모'일 때만 올린다(메모 길은 :mod:`.handoff_memo`).
:mod:`.settings` 가 이 모듈을 부르므로 여기서는 칸 꼴(:mod:`.settings_field`)만 가져온다.
"""

from __future__ import annotations

from typing import Any

from foms.services.cs_agent.settings_field import KIND_BOOL, Field

__all__ = ["GROUP_HANDOFF_MEMO", "HANDOFF_MEMO_FIELD", "HANDOFF_MEMO_FIELDS", "handoff_memo_on"]

GROUP_HANDOFF_MEMO = "넘김 메모(AI 가 초안을 안 쓴 상담)"
HANDOFF_MEMO_FIELD = "handoff_memo_enabled"

HANDOFF_MEMO_FIELDS: tuple[Field, ...] = (
    Field(HANDOFF_MEMO_FIELD, "넘김 메모", KIND_BOOL, False, GROUP_HANDOFF_MEMO,
          help="켜면 AI 가 초안을 안 쓰고 넘긴 상담(회사 지식에 없음 · 불만 · 검사에 걸림 등)에 '직원이 직접 답해 주세요' "
               "메모를 한 번 남겨요. 왜 안 썼는지 쉬운 말로 적고, 손님에게는 안 보여요. 초안 스위치가 메모일 때만 올라가요"),
)


def handoff_memo_on(cfg: Any) -> bool:
    """설정의 넘김 메모 스위치(참일 때만 켬)."""
    return cfg.get(HANDOFF_MEMO_FIELD) is True
