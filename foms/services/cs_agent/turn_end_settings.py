"""관리 패널 '말 끝남 판단' 칸 묶음 — 빠른 길 모아 받기의 기다림을 손님 말 모양으로 줄이고 늘린다(사장님 요청 11-11).

칸은 :mod:`.settings` 의 ``FIELDS`` 끝에 붙는다(같은 읽기 · 쓰기 · 수정 기록 길). 처음 값은 **끔**이다 — 끄면 기다림은 예전
그대로(조용 기다림 · 최대 기다림)다. '기록만'은 작은 모델이 판단만 하고 남기며 기다림은 바꾸지 않는다(맞히는 비율을 운영
글로 먼저 잰다). '켬'이면 말이 끝났다고 본 글은 :data:`FAST_FIELD` 초만, 이어질 것 같다고 본 글은 :data:`SLOW_FIELD` 초까지
기다린다 — 둘 다 최대 기다림(첫 미답 글부터)을 넘지 않는다. 판단을 못 하면(모델 오류 · 가림 검사 · 돈 상한) 예전 기다림이다.
"""

from __future__ import annotations

from typing import Any

from foms.services.cs_agent.settings_field import KIND_CHOICE, KIND_INT, Field

__all__ = [
    "FAST_FIELD", "GROUP_TURN_END", "MODE_FIELD", "MODE_OFF", "MODE_ON", "MODE_SHADOW", "MODES", "SLOW_FIELD",
    "TURN_END_FIELDS", "turn_end_mode",
]

GROUP_TURN_END = "말 끝남 판단(작은 AI — 빠른 길 기다림)"
MODE_FIELD, FAST_FIELD, SLOW_FIELD = "turn_end_mode", "turn_end_fast_wait_s", "turn_end_slow_wait_s"
MODE_OFF, MODE_SHADOW, MODE_ON = "off", "shadow", "on"
MODES: tuple[str, ...] = (MODE_OFF, MODE_SHADOW, MODE_ON)
_MODE_CHOICES = ((MODE_OFF, "끔"), (MODE_SHADOW, "기록만"), (MODE_ON, "켬"))

TURN_END_FIELDS: tuple[Field, ...] = (
    Field(MODE_FIELD, "말 끝남 판단", KIND_CHOICE, MODE_OFF, GROUP_TURN_END, _MODE_CHOICES,
          help="작은 AI(Haiku)가 손님 말이 끝났는지 봐요. 끝났으면 조금만, 이어질 것 같으면 더 기다렸다 초안을 써요. "
               "'기록만'은 판단만 남기고 기다림은 그대로예요(맞히는 비율을 먼저 재요). 판단을 못 하면 예전 기다림이에요"),
    Field(FAST_FIELD, "말이 끝났을 때 기다림", KIND_INT, 4, GROUP_TURN_END, low=3, high=15, unit="초",
          help="마지막 손님 글 뒤 이만큼 새 글이 없으면 판단해요. 끝났다고 보면 바로 초안을 써요"),
    Field(SLOW_FIELD, "말이 이어질 때 기다림", KIND_INT, 40, GROUP_TURN_END, low=15, high=120, unit="초",
          help="이어질 것 같다고 보면 마지막 글 뒤 이만큼 기다려요. 그래도 최대 기다림을 넘지는 않아요"),
)


def turn_end_mode(cfg: Any) -> str:
    """설정의 판단 방식(모르는 값은 끔)."""
    mode = cfg.get(MODE_FIELD)
    return mode if mode in MODES else MODE_OFF
