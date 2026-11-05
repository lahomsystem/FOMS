"""관리 패널 '고친 까닭 자세히 · 사진 · 학습' 칸 묶음 — 설계서 17.6.1 (f) · 사장님 결정 D94(11-02).

칸은 :mod:`.settings` 의 ``FIELDS`` 끝에 붙는다(같은 읽기 · 쓰기 · 수정 기록 길 — 그림 읽기 :mod:`.image_settings` 와 같은 꼴).
처음 값은 모두 **끔**이다(설계서 (f) 표 — 스테이징에서 차례로 켠다). 비상 정지는 이 칸과 상관없이 모두 멈춘다(부르는 쪽이
:func:`.turns.read_switch` 를 같이 본다).

- 자세한 이유 칸 · 사진 올리기: [수정하기] 화면 칸과 저장 API(:mod:`.edit_detail`). 사진은 저장소가 R2 · S3 일 때만 — 로컬
  저장소(``static/uploads`` — 누구나 열 수 있는 정적 경로)면 이 칸을 켜도 꺼진 것으로 본다(17.6.1 (b)).
- 사진 설명 뽑기(D94 — 직원이 '손님 정보 안 보임'을 켠 사진만): WORKER 15분 바퀴(:mod:`.photo_desc`).
- 사례 재료에 이유 싣기: '고침' 사례에 까닭 · 자세한 이유 · 사진 설명 줄을 더한다(:mod:`.brain_cases`). 끄면 옛 꼴 그대로.
- 주간 고침 안(D94 — 사장님 승인 뒤에만 넣는다): 월요일 새벽 WORKER(:mod:`.weekly_fix`). 자동 반영 길은 없다.
- 사진 학습 → 회사 지식 제안(설계서 17.11.1 의 7 · D172): 같은 월요일 새벽(:mod:`.photo_learning`), master brain 제안 길로만
  '승인 대기' 카드를 만든다(자동 반영 없음). 모델은 주간 고침 안 모델 칸을 같이 쓴다.
- 상담 전체 대화(설계서 17.11.2 · D173): 사진 읽기(초안 때) · 사진 학습 · 주간 고침 안이 읽는 전체 대화의 글 수 · 가린 글 자 수
  상한과 사진 학습 묶음당 사례 수(:mod:`.full_conversation`). 글 수 상한 0 이면 읽지 않고 예전 재료 그대로다.
"""

from __future__ import annotations

from typing import Any

from foms.services.cs_agent.brain_prompt import MODEL_HAIKU, MODEL_SONNET
from foms.services.cs_agent.settings_field import KIND_BOOL, KIND_CHOICE, KIND_INT, MODEL_CHOICES, Field

__all__ = [
    "CASE_REASONS_FIELD", "DETAIL_FIELD", "DETAIL_FIELDS", "GROUP_DETAIL", "PHOTO_DESC_FIELD", "PHOTO_DESC_MODEL_FIELD",
    "PHOTOS_FIELD", "PHOTO_LEARN_FIELD", "TALK_CASES_FIELD", "TALK_CHARS_FIELD", "TALK_MESSAGES_FIELD", "WEEKLY_FIELD",
    "WEEKLY_MODEL_FIELD", "switch_value",
]

GROUP_DETAIL = "고친 까닭 · 사진 · 학습"
DETAIL_FIELD = "edit_detail_enabled"
PHOTOS_FIELD = "edit_photos_enabled"
PHOTO_DESC_FIELD = "photo_desc_enabled"
PHOTO_DESC_MODEL_FIELD = "photo_desc_model"
CASE_REASONS_FIELD = "case_reasons_enabled"
WEEKLY_FIELD = "weekly_fix_enabled"
WEEKLY_MODEL_FIELD = "weekly_fix_model"
PHOTO_LEARN_FIELD = "photo_learn_enabled"
TALK_MESSAGES_FIELD = "full_talk_messages"
TALK_CHARS_FIELD = "full_talk_chars"
TALK_CASES_FIELD = "photo_learn_cases"

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
    Field(PHOTO_LEARN_FIELD, "사진 학습 → 회사 지식 제안", KIND_BOOL, False, GROUP_DETAIL,
          help="월요일 새벽, 지난 7일 손님 사진을 읽은 끝난 상담을 (사진 종류, 의도)로 묶어(손님 2명 · 직원 2명 이상 근거) "
               "회사 지식 제안(상황 · 제작 조건 · 비슷한 말 · 링크)을 만들어요. '승인 대기' 카드로만 들어가고 승인 "
               "전엔 아무것도 안 바뀌어요(모델은 주간 고침 안 모델 · 학습 돈 상한 안)"),
    Field(TALK_MESSAGES_FIELD, "전체 대화 글 수 상한", KIND_INT, 300, GROUP_DETAIL, low=0, high=1000, unit="개",
          help="사진 읽기(초안 때) · 사진 학습 · 주간 고침 안이 그 상담 글을 처음부터 이만큼까지 같이 봐요(새 글부터 50개씩 "
               "읽고 저장은 안 해요). 0 이면 전체 대화를 안 읽고 예전 재료(최근 30줄 · 질문 앞 6줄)를 써요"),
    Field(TALK_CHARS_FIELD, "전체 대화 자 수 상한", KIND_INT, 12000, GROUP_DETAIL, low=2000, high=40000, unit="자",
          help="가린 글 기준이에요. 넘으면 앞부분부터 덜고 맨 앞에 '앞 대화 몇 줄 줄임'을 적어요. 사진 읽기 입력(돈)이 "
               "이만큼까지 늘어요(학습은 한 번에 합쳐 12만 자 안으로 나눠요)"),
    Field(TALK_CASES_FIELD, "사진 학습 묶음당 사례 수", KIND_INT, 4, GROUP_DETAIL, low=1, high=8, unit="개",
          help="전체 대화가 길어 묶음마다 최근 사례부터 이만큼만 보내요(전체 대화를 읽을 때만 — 글 수 상한이 0 이면 예전처럼 "
               "모두)"),
)


def switch_value(cfg: Any, name: str) -> bool:
    """패널 설정의 켬 · 끔 칸(없거나 참 · 거짓이 아니면 끔)."""
    return cfg.get(name) is True
