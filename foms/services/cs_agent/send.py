"""손님께 보내는 [보내기] 감싸개 — 상담 에이전트가 손님이 보는 글을 쓰는 유일한 길(봇 이름 공개 글 · 라홈만 · 운영 밖은
시험 상담만).

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C10-3 · 설계서 17.2('누를 때 서버가 확인하는 것' 4 · 5) · 원장 D68 · D69.
이 패키지에서 채널톡에 쓰는 곳은 메모 감싸개(:mod:`.memo` — 내부 메모만)와 이 모듈 둘뿐이다(시험이 소스를 훑어 막는다).

- **봇 이름 공개 글(D68)**: 상담원 이름으로 보내지 않는다 — :data:`SEND_BOT_NAME` 봇 이름으로 쓰고, 누른 직원은 FOMS 차례 줄에만
  남긴다. 외부 메신저(카카오 · 톡톡)에서 손님에게는 채널 프로필로 보인다(원장 F12-8). 앱 함수(네이티브)로 라홈 채널 상수
  (:data:`SEND_CHANNEL_ID`)에 쓴다 — Open API 쓰기에는 requestId 칸이 없어 맞추기 표지가 사라진다(스테이징 실화면 11-01).
- **라홈만 · 운영 밖은 허용 목록만**: 브랜드는 라홈만(하우드는 쓰기 허락 전 — 막음). 운영이 아니면 메모와 같은 시험 상담 허용
  목록(:func:`.memo.memo_allowed`)에만 쓴다 — 목록이 비면 아무 데도 안 쓴다(설계서 4절 10 · D69).
- **requestId = 차례 id(:func:`request_id_for`)**: 채널톡은 같은 requestId 를 거르지 않는다(C10-2 ⑤) — 두 번 나가지 않게 막는
  것은 부르는 쪽의 '보내는 중' 조건부 쓰기다. requestId 는 결과를 모를 때 상담 글을 다시 읽어 맞추는 표지이고, 이 앞말이 붙은
  봇 공개 글은 상태 표 · 초안 재료에서 '직원 답'으로 읽힌다(:data:`.channel_read.SENT_REPLY_REQUEST_PREFIX`).
- 모델을 부르지 않는다. 글은 로그 · 예외 · 결과 어디에도 싣지 않는다(상담 id · 차례 id · 이유 코드만).
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from dataclasses import dataclass
from typing import Iterable, Optional

from foms.services import channel_send
from foms.services.cs_agent.channel_read import SENT_REPLY_REQUEST_PREFIX, _created_at
from foms.services.cs_agent.memo import MEMO_BRAND, MEMO_CHANNEL_ID, memo_allowed
from foms.services.notifications.cs_draft_link import edit_path, send_path

logger = logging.getLogger(__name__)

__all__ = [
    "REASON_BRAND", "REASON_EMPTY", "REASON_NO_CHAT", "REASON_STAGING", "SEND_BOT_NAME", "SEND_BRAND", "SEND_CHANNEL_ID",
    "SEND_PREFIX", "SEND_UNKNOWN", "SendResult", "memo_buttons", "request_id_for", "send_reply",
]

#: 손님께 보내는 브랜드 — 하우드는 쓰기 허락 전이라 막는다.
SEND_BRAND = MEMO_BRAND
#: 손님께 보내는 채널 — 브랜드 짝 상수(메모와 같은 라홈 채널). 부르는 쪽이 넘길 칸이 없고 env 기본 채널로 빠지지 않는다.
SEND_CHANNEL_ID = MEMO_CHANNEL_ID
#: 보낸 이로 보일 봇 이름(D68 — 상담원 이름 아님). AI 표시 · 내부 말(FOMS)을 넣지 않는다(설계서 17.1 'AI 소개 삭제').
SEND_BOT_NAME = "라홈"
REASON_BRAND, REASON_NO_CHAT, REASON_EMPTY = "brand_not_allowed", "no_chat", "empty_text"
REASON_STAGING = "staging_not_allowed"
#: 보내기 실패 이유 앞말 + 채널 보내기 오류 코드(``send_provider_error`` · ``send_not_configured`` …).
SEND_PREFIX = "send_"
#: 채널톡에 닿았는지 모르는 실패(시간 초과 · 연결 오류 · 5xx) — 다시 보내면 손님에게 두 번 간다.
SEND_UNKNOWN = SEND_PREFIX + "request_failed"
_CHAT_ID = channel_send.CHAT_ID  # 상담 id 꼴은 한 곳(channel_send) — 검수 R15 단순화
_ERROR_CODE = re.compile(r"[a-z_]{1,32}")
_MESSAGE_ID = re.compile(r"[\x21-\x7e]{1,64}")


@dataclass(frozen=True)
class SendResult:
    """보내기 결과 — 글은 없다.

    Attributes:
        posted: 채널톡이 글을 받았다.
        message_id: 받은 글 id(받았을 때 — 응답 꼴이 틀리면 ``None``).
        created_at: 받은 글 시각(시간대 있는 UTC — 응답에 없으면 ``None``).
        reason: 안 보냈거나 못 보낸 이유 코드(보냈으면 ``None``).
    """

    posted: bool
    message_id: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    reason: Optional[str] = None

    @property
    def outcome_unknown(self) -> bool:
        """채널톡에 닿았는지 모른다 — 부르는 쪽은 다시 보내지 않고 상담 글을 읽어 requestId 로 맞춘다."""
        return self.reason == SEND_UNKNOWN


#: 메모 링크 버튼 이름 · 화면 경로(``foms/web/cs_agent_send.py``).
BUTTON_SEND, BUTTON_EDIT = "보내기", "수정하기"
BASE_URL_ENV = "FOMS_BASE_URL"


def memo_buttons(turn_id: int, chat_id: str) -> tuple[tuple[str, str], ...]:
    """초안 메모의 [보내기] · [수정하기] 링크 — FOMS 기본 주소(env :data:`BASE_URL_ENV`, https 만) + 차례 id + 상담 id(``c``).

    주소에 서명 표를 넣지 않는다(메신저 미리 읽기 · 기록에 남는다 — 권한은 화면 안 POST 의 로그인 · CSRF · 서명 표). 상담 id 는
    다른 환경의 같은 차례 번호로 잘못 들어온 링크를 화면이 거르는 표지다. env 가 없거나 https 가 아니면 버튼을 달지 않는다(운영
    주소로 빠지면 스테이징 메모가 운영 화면을 연다).
    """
    base = (os.environ.get(BASE_URL_ENV) or "").strip().rstrip("/")
    if not base.startswith("https://") or not isinstance(chat_id, str) or not _CHAT_ID.fullmatch(chat_id):
        logger.warning("[CS 보내기] FOMS 기본 주소(https)가 없어 메모에 버튼을 달지 않는다 turn=%s", turn_id)
        return ()
    return ((BUTTON_SEND, base + send_path(turn_id, chat_id)), (BUTTON_EDIT, base + edit_path(turn_id, chat_id)))


def request_id_for(turn_id: int) -> str:
    """차례의 requestId — ``foms-cs-send-<차례 id>``(차례마다 하나로 정한 글자, 다시 읽어 맞추는 표지)."""
    return f"{SENT_REPLY_REQUEST_PREFIX}{int(turn_id)}"


def send_reply(chat_id: str, text: str, *, brand: str, turn_id: int, environment: Optional[str] = None,
               allowed_chat_ids: Optional[Iterable[str]] = None) -> SendResult:
    """손님께 봇 이름 공개 글 하나를 보낸다(거르는 순서: 브랜드 → 상담 id 꼴 → 빈 글 → 환경 — 걸리면 채널톡을 부르지 않는다).

    Args:
        chat_id: 채널톡 상담 id.
        text: 보낼 글(로그 · 예외 · 결과에 싣지 않는다).
        brand: 상담 브랜드 — ``"LAHOM"`` 만 보낸다.
        turn_id: 초안 차례 id(requestId 를 정한다).
        environment · allowed_chat_ids: :func:`.memo.memo_allowed` 와 같다(더 막는 쪽으로만).

    Returns:
        :class:`SendResult`.
    """
    if brand != SEND_BRAND:
        logger.warning("[CS 보내기] 라홈이 아닌 브랜드엔 보내지 않는다 turn=%s", turn_id)
        return SendResult(False, reason=REASON_BRAND)
    if not isinstance(chat_id, str) or not _CHAT_ID.fullmatch(chat_id):
        logger.warning("[CS 보내기] 상담 id 꼴이 아니라 보내지 않는다 turn=%s", turn_id)
        return SendResult(False, reason=REASON_NO_CHAT)
    if not isinstance(text, str) or not text.strip():
        return SendResult(False, reason=REASON_EMPTY)
    if not memo_allowed(chat_id, environment=environment, allowed_chat_ids=allowed_chat_ids):
        logger.info("[CS 보내기] 운영이 아니고 시험 상담 허용 목록 밖 — 보내지 않는다 chat=%s turn=%s", chat_id, turn_id)
        return SendResult(False, reason=REASON_STAGING)
    sent = channel_send.send_public_bot_message(chat_id, text.strip(), channel_id=SEND_CHANNEL_ID,
                                                bot_name=SEND_BOT_NAME, request_id=request_id_for(turn_id))
    if not sent.get("success"):
        error = str(sent.get("error") or "")
        reason = SEND_PREFIX + (error if _ERROR_CODE.fullmatch(error) else "unknown")
        logger.warning("[CS 보내기] 보내기 실패 chat=%s turn=%s reason=%s", chat_id, turn_id, reason)
        return SendResult(False, reason=reason)
    message_id = sent.get("message_id")
    message_id = message_id if isinstance(message_id, str) and _MESSAGE_ID.fullmatch(message_id) else None
    created = sent.get("created_at")
    logger.info("[CS 보내기] 손님께 보냈다 chat=%s turn=%s message=%s", chat_id, turn_id, message_id)
    return SendResult(True, message_id=message_id, created_at=_created_at(created) if created is not None else None)
