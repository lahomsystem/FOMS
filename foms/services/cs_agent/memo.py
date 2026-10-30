"""AI 초안 메모 — 상담 에이전트가 채널톡에 쓰는 유일한 길(내부 메모 고정 · 라홈만 · 운영 밖은 시험 상담만).

플랜 ``docs/plans/2026-10-27-cs-ai-agent-plan.md`` C3-3 · 설계서 4절 8 · 10 · 15.2 의 5. 원장 R1-4 · R1-14.

- **늘 비공개(R1-14 · R10-14)**: 내부 메모 전용 :func:`foms.services.channel_client.send_private_memo` 만 부른다 — 그 함수는
  길마다 다른 비공개 옵션 이름(앱 함수 ``MESSAGE_OPTION_PRIVATE`` · Open API ``private``)이 빠지면 채널톡을 부르기 전에
  멈춘다. 링크 버튼([보내기] · [수정하기] 등)을 달면 Open API 길로 간다(앱 함수는 버튼 단 비공개도 422 — C10-2 시험 10-30,
  PC · 휴대폰 데스크에서 보이고 눌리며 카톡 손님 쪽엔 안 감). 이 패키지에서 채널톡에 글을 쓰는 곳은 이 모듈 하나다(시험이
  소스를 훑어 막는다).
- **라홈만 · 채널 상수만**: 브랜드는 라홈만 받는다(하우드 쓰기 금지 · 모르는 브랜드 거절). 채널 id 는 브랜드 짝 상수
  (:data:`~foms.services.cs_agent.channel_read.CHANNEL_BRANDS`)에서 불러올 때 한 번 정한다 — 부르는 쪽이 넘길 칸이 없고
  env 기본 채널(``CHANNEL_ID``)로 빠지지도 않는다.
- **운영 밖은 허용 목록만(R1-4)**: 채널이 브랜드마다 하나라 스테이징 · PC 도 진짜 손님 상담에 닿는다. 운영이 아니면
  env :data:`TEST_CHAT_IDS_ENV`(쉼표로 나눔) 또는 인자로 받은 시험 상담 id 에만 쓴다 — 목록이 비면 아무 데도 안 쓴다.
  운영 판정은 :func:`is_production` — 맞는 것만(환경 판정이 운영이고 프로젝트 이름이 ``-PRODUCTION`` 으로 끝날 때, R7-6).
- **올린 뒤 다시 읽기**: Open API 로 그 상담 최근 글을 읽어 올린 글이 비공개인지 본다. 못 찾거나 공개면
  ``verified=False`` 와 경고(공개면 오류 로그). 초안 바퀴는 공개면 초안 스위치를 끄고, 확인 못 함이면 '저장만'으로 바꾼다
  (원장 R7-1 · R7-2). 그래서 memo 로 켜기 전에 스테이징에서 우리 봇 메모가 Open API 글 목록에 오는지를 먼저 본다 —
  안 오면 모든 메모가 '못 찾음'이 되어 첫 메모에서 '저장만'으로 돌아간다.
- 글은 로그 · 예외 · 결과 어디에도 싣지 않는다(상담 id · 메시지 id · 이유 코드만).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from foms.platform.sentry_setup import resolve_environment
from foms.services import channel_client
from foms.services.cs_agent.channel_read import CHANNEL_BRANDS, ChannelReadError, OpenApiReader, channel_for_brand

logger = logging.getLogger(__name__)

__all__ = [
    "MEMO_BOT_NAME",
    "MEMO_BRAND",
    "MEMO_CHANNEL_ID",
    "MemoResult",
    "REASON_BAD_BUTTONS",
    "TEST_CHAT_IDS_ENV",
    "env_test_chat_ids",
    "is_production",
    "memo_allowed",
    "post_private_memo",
]

#: 메모를 쓰는 브랜드 — 하우드는 쓰기 허락이 날 때까지 감시 · 보고만(설계서 6절 단계 1).
MEMO_BRAND = "LAHOM"
#: 메모를 쓰는 채널 — 브랜드 짝 상수에서 불러올 때 한 번 정한다(뒤에 짝 표를 바꿔도 이 값은 그대로).
MEMO_CHANNEL_ID = channel_for_brand(MEMO_BRAND)
#: 채널톡에 보일 보낸 이 — '올리는 중' 복구가 우리 봇 메모를 알아보는 표지이기도 하다.
MEMO_BOT_NAME = "FOMS AI초안"
#: 운영이 아닌 환경에서 메모를 써도 되는 시험 상담 id(쉼표로 나눔). 없으면 아무 데도 안 쓴다.
TEST_CHAT_IDS_ENV = "FOMS_CS_MEMO_TEST_CHAT_IDS"
PRODUCTION = "production"
#: 운영 Railway 프로젝트 이름의 끝 — 정확히 이 글자로 끝나야 운영이다(대소문자까지).
PRODUCTION_PROJECT_SUFFIX = "-PRODUCTION"

REASON_BRAND = "brand_not_allowed"
REASON_NO_CHAT = "no_chat"
REASON_EMPTY = "empty_text"
REASON_STAGING = "staging_not_allowed"
REASON_NO_MESSAGE_ID = "no_message_id"
REASON_NOT_FOUND = "memo_not_found"
REASON_NOT_PRIVATE = "memo_not_private"
REASON_READ_FAILED = "verify_read_failed"
REASON_BAD_BUTTONS = "bad_buttons"
#: 보내기 실패 이유는 이 앞말 + channel_client 오류 코드(``send_provider_error`` · ``send_request_failed``).
SEND_PREFIX = "send_"
#: 요청이 채널톡에 닿았는지 모르는 실패(시간 초과 등) — 다시 보내면 메모가 둘이 될 수 있다.
SEND_UNKNOWN = SEND_PREFIX + "request_failed"

#: 채널톡 상담 id 꼴(빈칸 없는 ASCII, 64자까지). 손님 글이 자리를 바꿔 들어오면 여기서 걸린다.
_CHAT_ID = re.compile(r"[\x21-\x7e]{1,64}")
_ERROR_CODE = re.compile(r"[a-z_]{1,32}")


@dataclass(frozen=True)
class MemoResult:
    """메모 올리기 결과 — 글은 없다.

    Attributes:
        posted: 채널톡이 글을 받았다(``False`` 면 아무것도 안 썼거나 채널톡이 거절했다).
        verified: 다시 읽어 그 글이 비공개임을 확인했다.
        message_id: 올린 글의 채널톡 메시지 id(받았을 때만).
        reason: 안 올렸거나 확인 못 한 이유 코드(모두 잘 되면 ``None``).
    """

    posted: bool
    verified: bool = False
    message_id: Optional[str] = None
    reason: Optional[str] = None

    @property
    def outcome_unknown(self) -> bool:
        """채널톡에 닿았는지 모른다 — 부르는 쪽은 '올리는 중' 줄을 그대로 두고 복구 단계가 맞춘다(실패로 바꾸지 않는다)."""
        return self.reason == SEND_UNKNOWN


def env_test_chat_ids() -> frozenset[str]:
    """env :data:`TEST_CHAT_IDS_ENV` 의 시험 상담 id(쉼표로 나누고 앞뒤 빈칸 · 빈 칸은 버린다)."""
    raw = os.environ.get(TEST_CHAT_IDS_ENV, "")
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def is_production(environment: Optional[str] = None) -> bool:
    """운영인가 — 맞는 것만: :func:`resolve_environment` 가 운영이고 **그리고** Railway 프로젝트 이름이 정확히
    :data:`PRODUCTION_PROJECT_SUFFIX` 로 끝날 때만(원장 R7-6). 나머지는 모두 시험 상담 허용 목록을 따른다.

    프로젝트 이름이 없거나 바뀌었거나(``FOMS-STAGING``) Railway 환경 이름만 ``production`` 인 스테이징(FOMS-DEV 도 그렇다),
    스테이징에 잘못 남은 ``FOMS_ENV=production`` 은 운영이 아니다 — 채널이 브랜드마다 하나라 열린 쪽으로 닫히면 스테이징이
    진짜 손님 상담 전부에 쓴다. 인자 ``environment`` 는 더 막는 쪽으로만 쓴다(``"production"`` 을 줘도 실제 환경이 운영이
    아니면 운영이 아니다).
    """
    project = (os.environ.get("RAILWAY_PROJECT_NAME") or "").strip()
    if resolve_environment() != PRODUCTION or not project.endswith(PRODUCTION_PROJECT_SUFFIX):
        return False
    return environment is None or environment == PRODUCTION


def memo_allowed(chat_id: str, *, environment: Optional[str] = None,
                 allowed_chat_ids: Optional[Iterable[str]] = None) -> bool:
    """이 상담에 메모를 써도 되는 환경인가 — 운영이면 늘, 아니면 시험 상담 허용 목록 안일 때만.

    Args:
        chat_id: 채널톡 상담 id.
        environment: :func:`is_production` 과 같다.
        allowed_chat_ids: 시험 상담 id 목록. ``None`` 이면 env 를 읽는다. 빈 목록이면 아무 데도 안 쓴다.

    Raises:
        TypeError: ``allowed_chat_ids`` 가 글 하나(글자마다 나뉘어 엉뚱한 목록이 된다).
    """
    if isinstance(allowed_chat_ids, (str, bytes)):
        raise TypeError("allowed_chat_ids 는 상담 id 목록이다 — 글 하나를 넘기면 글자마다 나뉜다")
    if is_production(environment):
        return True
    allowed = env_test_chat_ids() if allowed_chat_ids is None else frozenset(
        str(item).strip() for item in allowed_chat_ids)
    return chat_id in allowed


def post_private_memo(chat_id: str, text: str, *, brand: str, environment: Optional[str] = None,
                      allowed_chat_ids: Optional[Iterable[str]] = None,
                      reader: Optional[Any] = None, buttons: Sequence[tuple[str, str]] = ()) -> MemoResult:
    """AI 초안을 그 상담의 내부 메모(비공개)로 올리고, 다시 읽어 비공개인지 확인한다.

    거르는 순서: 브랜드(라홈만) → 상담 id 꼴 → 빈 글 → 환경(운영 밖은 허용 목록만). 하나라도 걸리면 채널톡을
    부르지 않는다. 채널 id · 보낸 이 이름 · 비공개는 모두 상수다.

    Args:
        chat_id: 채널톡 상담 id.
        text: 올릴 글(로그 · 예외 · 결과에 싣지 않는다).
        brand: 상담 브랜드 — ``"LAHOM"`` 만 쓴다.
        environment: :func:`is_production` 과 같다(더 막는 쪽으로만).
        allowed_chat_ids: :func:`memo_allowed` 와 같다.
        reader: 다시 읽기에 쓸 Open API 읽기 도우미(``read_messages`` 꼴). 없으면 올린 뒤에 기본 도우미를 만든다.
        buttons: 메모에 달 링크 버튼 ``[(이름, https 주소), ...]``(2개까지). 꼴이 틀리면 채널톡을 부르지 않고 ``bad_buttons``.

    Returns:
        :class:`MemoResult`.
    """
    if brand != MEMO_BRAND:
        known = brand if brand in set(CHANNEL_BRANDS.values()) else "unknown"
        logger.warning("[CS 초안] 라홈이 아닌 브랜드엔 메모를 쓰지 않는다 brand=%s", known)
        return MemoResult(False, reason=REASON_BRAND)
    if not isinstance(chat_id, str) or not _CHAT_ID.fullmatch(chat_id):
        logger.warning("[CS 초안] 상담 id 꼴이 아니라 메모를 쓰지 않는다")
        return MemoResult(False, reason=REASON_NO_CHAT)
    if not isinstance(text, str) or not text.strip():
        return MemoResult(False, reason=REASON_EMPTY)
    if not memo_allowed(chat_id, environment=environment, allowed_chat_ids=allowed_chat_ids):
        logger.info("[CS 초안] 운영이 아니고 시험 상담 허용 목록 밖 — 메모를 쓰지 않는다 chat=%s", chat_id)
        return MemoResult(False, reason=REASON_STAGING)
    try:
        sent = channel_client.send_private_memo(chat_id, text, brand=MEMO_BRAND, bot_name=MEMO_BOT_NAME, private=True,
                                                channel_id=MEMO_CHANNEL_ID, buttons=buttons)
    except channel_client.PrivateOptionMissing:
        raise
    except ValueError:
        logger.warning("[CS 초안] 메모 버튼 꼴이 틀려 메모를 쓰지 않는다 chat=%s", chat_id)
        return MemoResult(False, reason=REASON_BAD_BUTTONS)
    if not sent.get("success"):
        error = str(sent.get("error") or "")
        reason = SEND_PREFIX + (error if _ERROR_CODE.fullmatch(error) else "unknown")
        logger.warning("[CS 초안] 메모 올리기 실패 chat=%s reason=%s", chat_id, reason)
        return MemoResult(False, reason=reason)
    message_id = str(sent.get("message_id") or "").strip() or None
    if message_id is None:
        logger.warning("[CS 초안] 채널톡이 메시지 id 없이 받았다 — 비공개를 확인하지 못한다 chat=%s", chat_id)
        return MemoResult(True, reason=REASON_NO_MESSAGE_ID)
    return _verify_private(chat_id, message_id, reader if reader is not None else OpenApiReader())


def _verify_private(chat_id: str, message_id: str, reader: Any) -> MemoResult:
    """올린 글을 Open API 로 다시 읽어 비공개인지 본다(GET 한 번 — 최근 글 묶음에서 그 id 를 찾는다)."""
    try:
        messages = reader.read_messages(MEMO_BRAND, chat_id)
    except ChannelReadError as exc:
        logger.warning("[CS 초안] 올린 메모 다시 읽기 실패 chat=%s message=%s status=%s", chat_id, message_id,
                       exc.status)
        return MemoResult(True, message_id=message_id, reason=REASON_READ_FAILED)
    found = next((m for m in messages if m.message_id == message_id), None)
    if found is None:
        logger.warning("[CS 초안] 올린 메모를 다시 읽어도 못 찾았다 chat=%s message=%s", chat_id, message_id)
        return MemoResult(True, message_id=message_id, reason=REASON_NOT_FOUND)
    if not found.is_private:
        logger.error("[CS 초안] 올린 메모가 비공개가 아니다 — 손님에게 보일 수 있다 chat=%s message=%s",
                     chat_id, message_id)
        return MemoResult(True, message_id=message_id, reason=REASON_NOT_PRIVATE)
    return MemoResult(True, verified=True, message_id=message_id)
