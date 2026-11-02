"""관리 패널 칸 꼴 — :class:`Field` 와 칸 종류 · 모델 고르기 목록(:mod:`.settings` 가 500줄 상한에 닿아 나눴다).

:mod:`.settings` 가 이 이름들을 그대로 내보낸다(``settings.Field`` · ``settings.KIND_BOOL`` …). 칸 묶음을 따로 두는 모듈
(그림 읽기 — :mod:`.image_settings`)도 여기서 꼴을 가져온다(설정 모듈을 거꾸로 가져오지 않게).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from foms.services.cs_agent.brain_prompt import MODEL, MODEL_HAIKU, MODEL_SONNET, PRICES

__all__ = [
    "EFFORT_CHOICES", "KIND_BOOL", "KIND_CHOICE", "KIND_INT", "KIND_MONEY", "MODEL_CHOICES", "MODEL_HELP", "MODEL_NAMES",
    "Field",
]

KIND_CHOICE, KIND_INT, KIND_BOOL, KIND_MONEY = "choice", "int", "bool", "money"
MODEL_NAMES = {MODEL: "Opus 5.5", MODEL_SONNET: "Sonnet 5.5", MODEL_HAIKU: "Haiku 5.5"}
MODEL_CHOICES = tuple((model, name) for model, name in MODEL_NAMES.items())
MODEL_HELP = " · ".join(f"{MODEL_NAMES[m]} ${PRICES[m].input} / ${PRICES[m].output}" for m in MODEL_NAMES) + (
    " (백만 토큰당 입력 / 출력). Haiku 5.5 는 서버 쪽 대체가 없고, 10만 토큰 넘는 프롬프트는 5배 값이다")
EFFORT_CHOICES = (("low", "낮음"), ("medium", "보통"), ("high", "높음"), ("max", "최고"))


@dataclass(frozen=True)
class Field:
    """칸 하나. ``choices`` 는 (값, 화면 이름) 목록, 정수 칸은 ``low`` ~ ``high``. ``help`` 는 화면 설명 한 줄.

    ``locked`` 면 다음 단계 칸이다 — 화면은 값만 보이고, 바꾸는 저장은 거절하고, 읽을 때는 늘 처음 값이다.
    """

    name: str
    label: str
    kind: str
    default: Any
    group: str
    choices: tuple[tuple[Any, str], ...] = ()
    low: Optional[int] = None
    high: Optional[int] = None
    unit: str = ""
    help: str = ""
    locked: bool = False
