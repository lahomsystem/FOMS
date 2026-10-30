"""'AI 냐 사람이냐' 물음 알아보기 — 손님이 상대가 사람인지 · AI · 봇 · 로봇 · 자동응답 · 챗봇인지 묻는 글(코드 규칙).

설계서 17.1 · 17.8 · 원장 R10-27: 손님이 이렇게 물으면 초안 없이 늘 사람에게 넘긴다 — AI 가 사람인 척하면 안 되고, 정직한
답('AI 입니다')도 1단계에서는 사람이 정한다. 빠른 길(:mod:`.realtime`)이 두뇌를 부르기 **전에** 이 함수로 거른다.

- **넓게 잡으면** 초안이 안 뜨고(직원 일이 는다), **좁게 잡으면** AI 가 사람인 척하게 된다 — 둘 다 시험한다
  (``tests/domains/test_cs_realtime.py`` 음성 대조군: 'AI 로 만든 그림이에요?' · '사람 몇 명 와요?' · '자동으로 닫히는 문' ·
  '로봇청소기' · '두 사람이에요' · '실제 사람이 앉았을 때').
- 규칙은 '누구냐' 말(AI · 인공지능 · 챗봇 · 봇 · 로봇 · 자동응답 · 사람 …) **바로 뒤에** 정체를 묻는 끝말('이세요' · '인가요' ·
  '맞나요' · '아니죠' …)이나 답하는 일('이 답' · '랑 대화' …)이 붙을 때만이다. '로봇청소기' · 'AI 로 만든' · '자동으로 닫히는' 은
  사이에 다른 말이 끼어 걸리지 않는다. 사람 수('두 사람') 앞 숫자 · 수 말은 뺀다.
- 글은 이 함수 안에서만 본다 — 로그 · 예외에 싣지 않는다.
"""

from __future__ import annotations

import re
from typing import Iterable

__all__ = ["ASK_HUMAN_MEMO", "ASKED_IF_AI", "asks_if_human", "any_asks_if_human"]

#: 차례 기록의 넘김 까닭 · 건너뜀 코드(글이 아니다).
ASKED_IF_AI = "asked_if_ai"
#: 메모 스위치일 때 올리는 비공개 한 줄 — 손님에게 보내지 않는다(초안 없음).
ASK_HUMAN_MEMO = "[AI 초안 없음] 손님이 상대가 사람인지 AI 인지 물었습니다 — 직원이 직접 답해 주세요(손님에게 보내지 않는 메모)"

# '누구냐' 말. 영어는 앞뒤가 영문자가 아닐 때만(메일 · rain 같은 낱말 속 'ai' 는 아니다).
_LATIN = r"(?<![a-z])(?:a\.?i\.?|chat\s*gpt|gpt|chat\s*bot|robot|bot)(?![a-z])"
_KOREAN = r"(?:에이아이|인공\s*지능|챗\s*봇|챗\s*지피티|지피티|로봇|봇|자동\s*(?:응답|답변|답장))"
_WHO = rf"(?:{_LATIN}|{_KOREAN})"
# 정체를 묻는 끝말 — '누구냐' 말 바로 뒤(빈칸만 허용).
_IDENTITY_END = (
    r"(?:이세요|세요|이신가요|신가요|이신지|이에요|에요|이예요|예요|인가요|인가|인지|인거|인건|이야|이냐|냐|이죠|죠|"
    r"입니까|이십니까|십니까|맞(?:나요|죠|지요|아요|으세요|으신가요|습니까|냐|니)|"
    r"아니(?:에요|죠|지요|세요|신가요|냐|야)|아닌가요)"
)
# 답하는 일 — '누구냐' 말 + (조사) + 이 말이면 '누가 답하나' 물음이다. '만든 · 쓰는'은 넣지 않는다('AI 가 만든 그림').
_ANSWERING = r"(?:대화|얘기|이야기|상담|대답|답변|답장|답하|답해|답을|답이|응답|응대|채팅)"
_PARTICLE = r"(?:이|가|랑|이랑|와|과|하고|한테|로|으로)"
# 사람 수 앞말(숫자 · 수 말) — '두 사람이에요' 는 정체 물음이 아니다. 고정 길이 뒤보기 여러 개로 막는다.
_NOT_COUNTED = "".join(f"(?<!{word})" for word in (
    r"\d", r"\d ", "한", "한 ", "두", "두 ", "세", "세 ", "네", "네 ", "몇", "몇 ", "여러", "여러 ", "어떤 "))
_PERSON = r"(?:사람|인간)"

_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    rf"{_WHO}\s*{_IDENTITY_END}",  # 'AI 인가요' · '챗봇이에요' · '봇 아니죠' · '자동응답인가요'
    rf"(?:{_WHO}|기계)\s*{_PARTICLE}?\s*{_ANSWERING}",  # 'AI 가 답하는' · '로봇이랑 얘기' · '기계가 답해'
    r"자동\s*(?:으로)?\s*(?:대답|답변|답장|답하|답해|응답)",  # '자동으로 답장 오는 거예요'
    rf"{_NOT_COUNTED}{_PERSON}\s*{_IDENTITY_END}",  # '사람이세요' · '사람 맞나요' · '사람인지 궁금'
    rf"{_NOT_COUNTED}{_PERSON}\s*{_PARTICLE}\s*(?:직접\s*)?{_ANSWERING}",  # '사람이 답하는' · '사람이랑 대화'
    r"(?:상담원|상담사)\s*(?:분)?\s*(?:이세요|이신가요|인가요|맞(?:나요|죠|아요|으세요|으신가요))",  # '상담원이세요'
    r"(?<![a-z])are\s+you\s+(?:an?\s+)?(?:bot|robot|human|real|ai|person)(?![a-z])",
))


def asks_if_human(text: str) -> bool:
    """손님 글이 상대가 사람인지 · AI(봇 · 로봇 · 자동응답 · 챗봇)인지 묻는가. 글자가 아니거나 비면 거짓."""
    if not isinstance(text, str) or not text.strip():
        return False
    body = " ".join(text.split())
    return any(pattern.search(body) for pattern in _PATTERNS)


def any_asks_if_human(texts: Iterable[str]) -> bool:
    """글 여럿 가운데 하나라도 'AI 냐 사람이냐' 물음인가(마지막 직원 답 뒤 손님 글 묶음에 쓴다)."""
    return any(asks_if_human(text) for text in texts)
