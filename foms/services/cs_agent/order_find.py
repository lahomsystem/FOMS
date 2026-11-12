"""상담 ↔ ERP 주문 본인 잇기 — 손님 원문에서 휴대폰 · 주문 번호를 읽고 열린 주문을 찾는다(서버 코드만, 두뇌는 결과 칸만 받는다).

설계서 2026-11-12 온톨로지 5.5 '본인 잇기' · 5.6 의 1 · 2(사장님 11-12 D189). 찾기는 **가리기 전 원문**으로 하고(두뇌는 가린 글만
본다), 찾은 값 · 원문은 로그 · 예외 · 기록에 싣지 않는다(코드 · 주문 번호 · 수만). 확정 근거(:data:`.order_block.BASIS_LABELS`):

- ``profile`` — 채널톡 손님 정보(상담 읽기 ``user`` 칸)의 휴대폰 + 이름이 열린 주문 정확히 하나와 맞음. 칸이 없으면 이 길은 없다.
- ``number`` — 손님이 적은 주문 번호 + 전화 끝 네 자리가 그 주문과 둘 다 맞음. 틀리면 손님에게 아무것도 알리지 않는다(``mismatch``).
- ``contact`` — 손님이 알려 준 휴대폰(원문)과 그 글 속 이름이 열린 주문 정확히 하나와 맞음. 둘 이상이면 품목 이름 · 주소 조각으로
  한 번 좁힌다(:func:`narrow`).

'상담에서 만든 주문'(5.5 의 1)은 쓰지 않는다 — 채널톡 웹훅은 직원 그룹 방 글로만 주문을 만들고 손님 상담 글은 주문 접수에 절대
넣지 않아(:mod:`foms.services.channel_inbound`) 손님 상담 id 와 이어진 주문이 없다(11-12 코드 확인).

**열린 주문**: 운영 화면 기준(:meth:`models.Order.active_filter` — 휴지통 · 초안 제외) · ERP 주문 · 끝난 단계가 아니거나 AS 가
진행 중. 이름은 표시 기호 · 띄어쓰기를 뗀 글자로 견준다(네이버 붙이기 후보와 같은 규칙).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import quote

from sqlalchemy import or_, select

from foms.services.cs_agent.channel_read import ChannelRateLimited, ChannelReadError
from foms.services.cs_agent.masking_contacts import normalize
from models import Order

logger = logging.getLogger(__name__)

__all__ = [
    "CLOSED_STAGES", "Lookup", "MAX_CANDIDATES", "by_contact", "by_number", "by_profile", "has_mobile", "mobiles",
    "name_key", "narrow", "open_orders", "read_profile",
]

CLOSED_STAGES = ("COMPLETED", "AS_COMPLETED")
_OPEN_AS = ("RECEIVED", "IN_PROGRESS")
MAX_CANDIDATES = 20
_MOBILE = re.compile(r"(?<!\d)(?:\+?82[-. ]?0?|0)(1[016789])[-. ]?(\d{3,4})[-. ]?(\d{4})(?!\d)")
_PIECE = re.compile(r"01[016789]\d{7,8}")
_ORDER_NO = re.compile(r"(?:주문\s?번호|(?<![\w&])#)\s*[:：]?\s*#?(\d{1,7})(?!\d)")
_LAST4 = re.compile(r"(?<!\d)(\d{4})(?!\d)")
_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")


@dataclass(frozen=True)
class Lookup:
    """찾기 결과 — ``one``(주문 하나 · 근거) · ``several``(후보 여럿) · ``none``(없음) · ``mismatch``(번호 · 끝 네 자리 틀림)."""

    status: str
    basis: str = ""
    order: Any = None
    candidates: tuple[Any, ...] = ()


NONE = Lookup("none")


def name_key(value: Any) -> str:
    """이름 비교 키 — 글자 · 숫자만(``★강민주`` · ``강 민주`` → ``강민주``)."""
    return "".join(ch for ch in str(value or "") if ch.isalnum())


def mobiles(texts: Iterable[str]) -> tuple[str, ...]:
    """원문 속 휴대폰 번호(숫자만 · ``010…`` 꼴 · 겹침 빼고 · 처음 나온 순서)."""
    found = (f"0{m.group(1)}{m.group(2)}{m.group(3)}" for text in texts for m in _MOBILE.finditer(normalize(text)))
    return tuple(dict.fromkeys(found))


def has_mobile(texts: Iterable[str]) -> bool:
    """원문에 휴대폰 꼴이 있나."""
    return bool(mobiles(texts))


def _pieces(digits: Optional[str]) -> tuple[str, ...]:
    """주문 전화 숫자 칸 → 번호들(여러 번호를 이어 붙인 칸은 휴대폰 꼴로 나눈다)."""
    text = digits or ""
    return tuple(_PIECE.findall(text)) or ((text,) if text else ())


def open_orders():
    """열린 주문 고르기(휴지통 · 초안 제외 · ERP 주문 · 끝난 단계 아님 또는 AS 진행 중)."""
    return select(Order).where(
        Order.active_filter(), Order.is_erp_order.is_(True),
        or_(Order.erp_stage_code.is_(None), Order.erp_stage_code.notin_(CLOSED_STAGES), Order.as_axis_status.in_(_OPEN_AS)))


def _by_phone(session: Any, phone: str) -> list[Any]:
    """그 휴대폰이 든 열린 주문(상한까지)."""
    rows = session.execute(open_orders().where(Order.erp_phone_digits.contains(phone))  # perf-ok: ix_orders_erp_phone_digits_trgm
                           .order_by(Order.id.desc()).limit(MAX_CANDIDATES)).scalars().all()
    return [order for order in rows if phone in _pieces(order.erp_phone_digits)]


def _named(orders: Sequence[Any], text_key: str) -> list[Any]:
    """주문 이름 키(두 글자 이상)가 글 키에 든 주문만."""
    return [order for order in orders if len(name_key(order.customer_name)) >= 2 and name_key(order.customer_name) in text_key]


def _result(orders: Sequence[Any], basis: str) -> Lookup:
    """후보 → 결과(하나면 확정 · 여럿이면 several · 없으면 none)."""
    unique = tuple({int(order.id): order for order in orders}.values())
    if len(unique) == 1:
        return Lookup("one", basis, unique[0])
    return Lookup("several", basis, candidates=unique) if unique else NONE


def by_contact(session: Any, texts: Sequence[str]) -> Lookup:
    """손님이 알려 준 휴대폰 + 이름(원문)으로 찾기 — 번호마다 열린 주문을 읽고 글 속에 이름이 든 주문만 남긴다."""
    phones = mobiles(texts)
    if not phones:
        return NONE
    key = name_key(" ".join(texts))
    found = [order for phone in phones for order in _named(_by_phone(session, phone), key)]
    return _result(found, "contact")


def by_number(session: Any, texts: Sequence[str]) -> Lookup:
    """손님이 적은 주문 번호 + 전화 끝 네 자리 — 둘 다 맞으면 확정, 번호는 있는데 끝 네 자리가 틀리면 ``mismatch``."""
    joined = normalize("\n".join(texts))
    numbers = tuple(dict.fromkeys(int(m.group(1)) for m in _ORDER_NO.finditer(joined)))
    if not numbers:
        return NONE
    rest = _ORDER_NO.sub(" ", joined)
    tails = {m.group(1) for m in _LAST4.finditer(rest)}
    rows = session.execute(open_orders().where(Order.id.in_(numbers[:3]))).scalars().all()
    hits = [order for order in rows if tails.intersection(piece[-4:] for piece in _pieces(order.erp_phone_digits))]
    if hits:
        return _result(hits, "number")
    return Lookup("mismatch", "number") if rows and tails else NONE


def by_profile(session: Any, profile: Optional[tuple[str, str]]) -> Lookup:
    """채널톡 손님 정보(이름, 휴대폰 숫자)로 찾기 — 이름 키가 주문 이름 키와 **같아야** 한다(포함이 아니라)."""
    if not profile:
        return NONE
    name, phone = profile
    key = name_key(name)
    if len(key) < 2:
        return NONE
    found = [order for order in _by_phone(session, phone) if name_key(order.customer_name) == key]
    return _result(found, "profile")


def narrow(lookup: Lookup, texts: Sequence[str]) -> Lookup:
    """후보 여럿 → 손님 글 속 품목 이름 · 주소 낱말(두 글자 이상)이 한 주문에만 맞으면 그 주문으로 확정."""
    if lookup.status != "several":
        return lookup
    key = name_key(" ".join(texts))
    if not key:
        return lookup
    hits = [order for order in lookup.candidates if _words_hit(order, key)]
    return Lookup("one", lookup.basis, hits[0]) if len(hits) == 1 else lookup


def _words_hit(order: Any, key: str) -> bool:
    """주문의 품목 이름 · 주소 낱말 가운데 하나라도 글 키에 드나(흔한 짧은 말은 빼려고 세 글자 이상만)."""
    words = _WORD.findall(f"{order.product or ''} {order.address or ''}")
    return any(len(word) >= 3 and name_key(word) in key for word in words)


def read_profile(reader: Any, brand: str, chat_id: str, get: Any) -> Optional[tuple[str, str]]:
    """상담 읽기(``GET /open/user-chats/{id}``)의 ``user`` 칸 → (이름, 휴대폰 숫자). 칸이 없거나 못 읽으면 ``None``(한도는 올린다).

    ``get`` 은 :func:`.drafting_read._get` 꼴(읽기 도우미 · 브랜드 · 경로 · 인자).
    """
    try:
        data = get(reader, brand, f"/open/user-chats/{quote(chat_id, safe='')}", {})
    except ChannelReadError as exc:
        if isinstance(exc, ChannelRateLimited):
            raise
        logger.warning("[CS 주문] 손님 정보를 못 읽어 이 길은 건너뜀 chat=%s status=%s", chat_id, exc.status)
        return None
    user = data.get("user") if isinstance(data, Mapping) and isinstance(data.get("user"), Mapping) else {}
    profile = user.get("profile") if isinstance(user.get("profile"), Mapping) else {}
    name = profile.get("name") or user.get("name")
    phones = mobiles([str(profile.get("mobileNumber") or user.get("mobileNumber") or "")])
    if not isinstance(name, str) or not phones:
        return None
    return name, phones[0]
