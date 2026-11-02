"""관리 패널 '그림 읽기' 칸 묶음 — 설계서 17.11 (i) · 사장님 결정 D89(처음 끔) · D92(Sonnet) · D96(PDF 쪽 상한).

칸은 :mod:`.settings` 의 ``FIELDS`` 끝에 붙는다(같은 읽기 · 쓰기 · 수정 기록 길). 처음 값은 모두 **끔**이거나 손님께 아무것도
닿지 않는 값이다 — '직원 참고만'은 직원 참고 줄에만 쓰고 계산 · 초안 금액에는 넣지 않는다(운영 첫 2주 — D96 의 5). 정답
읽기(학습 — 17.11 (g))는 그 길이 아직 없어 잠근다(다음 단계).
"""

from __future__ import annotations

from foms.services.cs_agent.brain_prompt import MODEL_HAIKU, MODEL_SONNET
from foms.services.cs_agent.settings_field import (
    EFFORT_CHOICES, KIND_BOOL, KIND_CHOICE, KIND_INT, MODEL_CHOICES, Field,
)

__all__ = [
    "GROUP_IMAGE", "IMAGE_FIELDS", "MODE_DRAFT", "MODE_FIELD", "MODE_NOTE", "MODE_OFF", "MODES", "image_mode",
]

GROUP_IMAGE = "그림 읽기(손님 도면 · 예시 — 견적)"
MODE_FIELD = "image_read_mode"
MODE_OFF, MODE_NOTE, MODE_DRAFT = "off", "note", "draft"
MODES: tuple[str, ...] = (MODE_OFF, MODE_NOTE, MODE_DRAFT)
_MODE_CHOICES = ((MODE_OFF, "끔"), (MODE_NOTE, "직원 참고만"), (MODE_DRAFT, "초안에 씀"))
_CONFIDENCE_CHOICES = (("medium", "보통 이상"), ("high", "높음만"))

IMAGE_FIELDS: tuple[Field, ...] = (
    Field(MODE_FIELD, "그림 읽기", KIND_CHOICE, MODE_OFF, GROUP_IMAGE, _MODE_CHOICES,
          help="견적 계산 넣기가 켜졌고 손님이 '크기는 보낸 도면 참고'라 했을 때만 손님 그림 · PDF 를 읽는다. '직원 참고만'은 "
               "직원 참고 줄에 읽은 범위만(금액 없음), '초안에 씀'은 읽은 가로 범위로 계산기 값을 낸다. 그림은 어디에도 "
               "저장하지 않고 숫자 결과만 남긴다(D89). 비상 정지 · 초안 끔이면 같이 멈춘다"),
    Field("image_model", "그림 읽기 모델", KIND_CHOICE, MODEL_SONNET, GROUP_IMAGE, MODEL_CHOICES,
          help="처음 Sonnet 5.5(D92 — 시험 1건에서 Opus 의 약 절반 값 · 더 빠름)"),
    Field("image_effort", "그림 읽기 생각 깊이", KIND_CHOICE, "high", GROUP_IMAGE, EFFORT_CHOICES),
    Field("image_max_tokens", "그림 읽기 최대 출력", KIND_INT, 8000, GROUP_IMAGE, low=2000, high=16000, unit="토큰"),
    Field("image_preread_timeout_s", "미리 읽기 시간 상한", KIND_INT, 60, GROUP_IMAGE, low=30, high=120, unit="초",
          help="손님 그림이 온 순간 따로 도는 길(WORKER)이 읽는다 — 견적 말이 있는 상담 · 첫 글 묶음 그림만(D96 의 6)"),
    Field("image_inline_timeout_s", "그 자리 읽기 시간 상한", KIND_INT, 35, GROUP_IMAGE, low=20, high=60, unit="초",
          help="초안 차례에 쓸 결과가 없을 때 그 자리에서 읽는 상한(받기 포함) — 넘으면 그림 없이 '확인 후 안내'로 간다. "
               "빠른 길 선점 만료가 이만큼 늘어난다"),
    Field("image_use_confidence", "쓸 확신", KIND_CHOICE, "medium", GROUP_IMAGE, _CONFIDENCE_CHOICES,
          help="이보다 낮은 확신의 결과는 금액에 쓰지 않고 직원 참고 줄에만"),
    Field("image_per_turn", "차례당 장수", KIND_INT, 4, GROUP_IMAGE, low=1, high=6, unit="장"),
    Field("image_per_chat_day", "상담 하나 하루 장수", KIND_INT, 8, GROUP_IMAGE, low=1, high=20, unit="장"),
    Field("image_per_day", "전체 하루 장수", KIND_INT, 150, GROUP_IMAGE, low=10, high=500, unit="장",
          help="넘으면 그림 없이 '확인 후 안내'(skipped_cap)"),
    Field("image_pdf_pages", "PDF 쪽 상한", KIND_INT, 3, GROUP_IMAGE, low=1, high=10, unit="쪽",
          help="PDF 는 그림으로 바꾸지 않고 그대로 보낸다(D96). 쪽을 자르지 않으니 이보다 긴 PDF 는 보내지 않는다"),
    Field("image_pdf_max_mb", "PDF 바이트 상한", KIND_INT, 10, GROUP_IMAGE, low=1, high=20, unit="MB"),
    Field("image_truth_enabled", "정답 읽기(학습)", KIND_BOOL, False, GROUP_IMAGE,
          help="직원 계산기 화면 그림을 정답 자료로 읽는 밤 길(17.11 (g)) — 그 길이 생길 때까지 잠김", locked=True),
    Field("image_truth_model", "정답 읽기 모델", KIND_CHOICE, MODEL_HAIKU, GROUP_IMAGE, MODEL_CHOICES, locked=True),
)


def image_mode(cfg) -> str:
    """패널 설정의 그림 읽기 모드(``off`` · ``note`` · ``draft``)."""
    value = cfg.get(MODE_FIELD)
    return value if value in MODES else MODE_OFF
