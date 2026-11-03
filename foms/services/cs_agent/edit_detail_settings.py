"""관리 패널 '고친 까닭 자세히 · 사진 · 학습' 칸 묶음 — 설계서 17.6.1 (f) · 사장님 결정 D94(11-02).

칸은 :mod:`.settings` 의 ``FIELDS`` 끝에 붙는다(같은 읽기 · 쓰기 · 수정 기록 길 — 그림 읽기 :mod:`.image_settings` 와 같은 꼴).
처음 값은 모두 **끔**이다(설계서 (f) 표 — 스테이징에서 차례로 켠다). 비상 정지는 이 칸과 상관없이 모두 멈춘다(부르는 쪽이
:func:`.turns.read_switch` 를 같이 본다).

- 자세한 이유 칸 · 사진 올리기: [수정하기] 화면 칸과 저장 API(:mod:`.edit_detail`). 사진은 저장소가 R2 · S3 일 때만 — 로컬
  저장소(``static/uploads`` — 누구나 열 수 있는 정적 경로)면 이 칸을 켜도 꺼진 것으로 본다(17.6.1 (b)).
- 사진 설명 뽑기(D94 — 직원이 '손님 정보 안 보임'을 켠 사진만): WORKER 15분 바퀴(:mod:`.photo_desc`).
- 사례 재료에 이유 싣기: '고침' 사례에 까닭 · 자세한 이유 · 사진 설명 줄을 더한다(:mod:`.brain_cases`). 끄면 옛 꼴 그대로.
- 주간 고침 안(D94 — 사장님 승인 뒤에만 넣는다): 월요일 새벽 WORKER(:mod:`.weekly_fix`). 자동 반영 길은 없다.
"""

from __future__ import annotations

from typing import Any

from foms.services.cs_agent.brain_prompt import MODEL_HAIKU, MODEL_SONNET
from foms.services.cs_agent.settings_field import KIND_BOOL, KIND_CHOICE, MODEL_CHOICES, Field

__all__ = [
    "CASE_REASONS_FIELD", "DETAIL_FIELD", "DETAIL_FIELDS", "GROUP_DETAIL", "PHOTO_DESC_FIELD", "PHOTO_DESC_MODEL_FIELD",
    "PHOTOS_FIELD", "WEEKLY_FIELD", "WEEKLY_MODEL_FIELD", "switch_value",
]

GROUP_DETAIL = "고친 까닭 · 사진 · 학습"
DETAIL_FIELD = "edit_detail_enabled"
PHOTOS_FIELD = "edit_photos_enabled"
PHOTO_DESC_FIELD = "photo_desc_enabled"
PHOTO_DESC_MODEL_FIELD = "photo_desc_model"
CASE_REASONS_FIELD = "case_reasons_enabled"
WEEKLY_FIELD = "weekly_fix_enabled"
WEEKLY_MODEL_FIELD = "weekly_fix_model"

DETAIL_FIELDS: tuple[Field, ...] = (
    Field(DETAIL_FIELD, "자세한 이유 칸", KIND_BOOL, False, GROUP_DETAIL,
          help="[수정하기] 화면에 '왜 고쳤나요' 칸을 보여요(가린 글만 · 1,000자). 보내기를 막지 않고, 보낸 뒤 따로 "
               "저장해요"),
    Field(PHOTOS_FIELD, "사진 올리기", KIND_BOOL, False, GROUP_DETAIL,
          help="이유에 사진을 5장까지 붙여요(장당 5MB). 비공개 저장소에서만 켜지고 관리자 · 올린 직원(24시간)만 봐요. "
               "원본은 90일 뒤 지워요"),
    Field(PHOTO_DESC_FIELD, "사진 설명 뽑기", KIND_BOOL, False, GROUP_DETAIL,
          help="직원이 '손님 정보 안 보임'을 켠 사진만 Claude 에 한 번 보내 가린 설명 글로 남겨요(얼굴이 보이면 안 "
               "보냄). 15분 바퀴당 10장 · 60초, 하루 100장, 학습 돈 상한 안에서만"),
    Field(PHOTO_DESC_MODEL_FIELD, "사진 설명 모델", KIND_CHOICE, MODEL_HAIKU, GROUP_DETAIL, MODEL_CHOICES),
    Field(CASE_REASONS_FIELD, "지난 사례에 이유 싣기", KIND_BOOL, False, GROUP_DETAIL,
          help="비슷한 지난 상담 중 고친 사례에 까닭 · 이유(200자) · 사진 설명(2장)을 붙여 두뇌에 줘요. 다섯 사례 합쳐 "
               "1,500자까지"),
    Field(WEEKLY_FIELD, "주간 고침 안", KIND_BOOL, False, GROUP_DETAIL,
          help="월요일 새벽, 지난 7일 고친 사례의 까닭 · 이유로 기준 답 고침 안을 만들어요(손님 2명 · 직원 2명 이상 "
               "근거). 사장님이 승인하기 전엔 아무것도 안 바뀌어요"),
    Field(WEEKLY_MODEL_FIELD, "주간 고침 안 모델", KIND_CHOICE, MODEL_SONNET, GROUP_DETAIL, MODEL_CHOICES,
          help="사장님 확인 전 임시 값이에요"),
)


def switch_value(cfg: Any, name: str) -> bool:
    """패널 설정의 켬 · 끔 칸(없거나 참 · 거짓이 아니면 끔)."""
    return cfg.get(name) is True
