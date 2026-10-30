"""도면·계약서 '상담 먼저' 알림톡 — 확인코드와 채널톡 상담 자동 발송(설계서 2026-10-20).

알림톡에는 링크가 없고 [문서 받기](MD, 메시지 전달) 버튼 하나만 있다. 고객이 누르면 알림톡
본문이 고객 메시지로 채널톡 카카오 상담에 올라온다. 이 모듈이 그 메시지에서 주문번호·확인코드를
읽어, 발송 때 남긴 기록과 맞으면 도면·계약서 링크를 새로 발급해 **같은 상담**에 써 준다.

보안 규칙:
- 주문번호는 차례대로 늘어나는 숫자라 짐작할 수 있다. 그래서 발송마다 새 **확인코드**를 만들어
  해시만 남기고(:func:`hash_code`), 주문번호와 코드가 **둘 다** 맞아야만 링크를 보낸다.
- 코드는 링크 유효기간 동안만 쓸 수 있고, 한 코드로 보내는 횟수는 :data:`MAX_DELIVERIES` 번까지다.
- 고객(user)이 쓴 상담 메시지만 다룬다. 매니저·봇 메시지와 그룹 채팅은 무시한다.
- 코드가 틀리면 고객에게는 아무것도 보내지 않고 매니저만 보는 내부 메모만 남긴다.

발송 기록은 공유 알림톡 이벤트(``OrderEvent`` ``SHARE_ALIMTALK``)의 ``payload['consult']`` 에
남는다 — 새 표가 필요 없고, 도면 탭의 '보냄' 판정이 지금 그대로 이 이벤트를 센다.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import hmac
import logging
import os
import re
import secrets
from typing import Any, NamedTuple, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services import channel_client
from foms.services import kakao_alimtalk as ka
from foms.services import order_share as share_service
from foms.services.auth.partner_scope import is_partner_order
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.manager_names import order_manager_label
from models import Order, OrderEvent, OrderShareToken

logger = logging.getLogger(__name__)

__all__ = [
    "CONSULT_TEMPLATE_ENV_PREFIX",
    "DOC_LABELS",
    "LinkMessage",
    "MAX_DELIVERIES",
    "build_consult_record",
    "build_link_messages",
    "consult_template_id",
    "docs_for_kind",
    "handle_user_chat_message",
    "hash_code",
    "new_code",
    "parse_consult_message",
]

#: 브랜드별 '상담 먼저' 템플릿 env 접두(뒤에 브랜드). 비어 있으면 이 경로는 꺼져 있다.
CONSULT_TEMPLATE_ENV_PREFIX = "SOLAPI_TEMPLATE_SHARE_CONSULT_ID_"

#: 공유 링크 종류 → 상담으로 보낼 문서.
_KIND_TO_DOCS = {"drawing": "drawing", "estimate": "estimate", "bundle": "both"}

#: 알림톡 ``#{문서종류}`` 와 상담 안내 글에 쓰는 이름.
DOC_LABELS = {"drawing": "도면", "estimate": "계약서", "both": "도면·계약서"}

#: 한 확인코드로 링크를 보내 주는 최대 횟수(고객이 버튼을 여러 번 눌러도 이만큼만).
MAX_DELIVERIES = 3

#: 헷갈리는 글자(0·O·1·I)를 뺀 코드 글자.
_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_CODE_LEN = 6

_ORDER_NO_RE = re.compile(r"주문번호\s*[:：]\s*(\d{1,9})")
_CODE_RE = re.compile(r"확인코드\s*[:：]\s*([0-9A-Za-z]{6})")

#: 고객 상담에 보낼 때 보이는 이름.
_BOT_NAME = "FOMS"


def consult_template_id(brand: str) -> str:
    """브랜드별 '상담 먼저' 템플릿 id. 미설정이면 빈 문자열(= 이 경로 꺼짐)."""
    return ka._env(CONSULT_TEMPLATE_ENV_PREFIX + brand)


def docs_for_kind(kind: str) -> str:
    """공유 링크 종류를 상담으로 보낼 문서(``drawing``/``estimate``/``both``)로 바꾼다."""
    return _KIND_TO_DOCS.get(kind, "drawing")


def new_code() -> str:
    """발송마다 새로 만드는 6자리 확인코드."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))


def hash_code(order_id: int, code: str) -> str:
    """확인코드 저장용 해시 — 주문에 묶어서 같은 코드라도 다른 주문에는 맞지 않게 한다."""
    return hashlib.sha256(f"{int(order_id)}:{code.upper()}".encode("utf-8")).hexdigest()


def build_consult_record(*, order_id: int, code: str, kind: str, split: bool,
                         now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    """발송 이벤트 ``payload['consult']`` 에 넣을 기록(코드 원문은 넣지 않는다).

    Args:
        order_id: 대상 주문 id.
        code: 이번 발송의 확인코드 원문.
        kind: 공유 링크 종류(``drawing``/``estimate``/``bundle``).
        split: 도면·계약서를 따로따로 보낼지(둘 다일 때만 의미가 있다).
        now: 기준 시각(테스트 주입).

    Returns:
        ``{'docs', 'split', 'code_hash', 'expires_at', 'deliveries'}``.
    """
    now = now or now_utc_naive()
    docs = docs_for_kind(kind)
    return {
        "docs": docs,
        "split": bool(split) and docs == "both",
        "code_hash": hash_code(order_id, code),
        "expires_at": (now + datetime.timedelta(days=share_service.token_days())).isoformat(),
        "deliveries": 0,
    }


def parse_consult_message(text: str) -> Optional[tuple[int, str]]:
    """고객 메시지에서 ``(주문번호, 확인코드)`` 를 읽는다. 둘 중 하나라도 없으면 ``None``."""
    if not text:
        return None
    order_match = _ORDER_NO_RE.search(text)
    code_match = _CODE_RE.search(text)
    if not order_match or not code_match:
        return None
    return int(order_match.group(1)), code_match.group(1).upper()


def _find_request(session, order_id: int, code: str,
                  now: datetime.datetime) -> Optional[OrderEvent]:
    """주문번호·확인코드가 맞고 아직 쓸 수 있는 '상담 먼저' 발송 이벤트를 찾는다."""
    expected = hash_code(order_id, code)
    rows = (
        session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == "SHARE_ALIMTALK")
        .order_by(OrderEvent.id.desc())
        .limit(30)
        .all()
    )
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        consult = payload.get("consult")
        if not isinstance(consult, dict) or payload.get("status") != "sent":
            continue
        if not hmac.compare_digest(str(consult.get("code_hash") or ""), expected):
            continue
        try:
            expires_at = datetime.datetime.fromisoformat(str(consult.get("expires_at")))
        except ValueError:
            continue
        if expires_at <= now:
            return None
        # 동시에 두 번 눌러 워커 둘이 같은 횟수를 읽지 않게 이 행을 잠그고 다시 읽는다.
        return (session.query(OrderEvent)
                .filter(OrderEvent.id == row.id)
                .with_for_update()
                .populate_existing()
                .one())
    return None


def _revoked_by_staff(session, request_event: OrderEvent) -> bool:
    """직원이 이 발송의 링크를 회수했는지 — 그렇다면 같은 코드로 다시 보내지 않는다.

    알림톡 발송 때의 공유 row 와, 이 코드로 고객에게 **실제로 간** 링크들을 본다. 쓰기 실패로
    우리가 스스로 회수한 링크는 고객에게 가지 않았으므로 여기에 넣지 않는다.
    """
    share_ids = {request_event.payload.get("share_id")}
    delivered = (
        session.query(OrderEvent)
        .filter(OrderEvent.order_id == request_event.order_id,
                OrderEvent.event_type == "SHARE_CONSULT_DELIVERED")
        .all()
    )
    for row in delivered:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if payload.get("request_event_id") == request_event.id:
            share_ids.update(payload.get("sent_share_ids") or [])
    share_ids.discard(None)
    if not share_ids:
        return False
    return (session.query(OrderShareToken)
            .filter(OrderShareToken.id.in_(share_ids), OrderShareToken.revoked_at.isnot(None))
            .count() > 0)


def _public_url(token: str) -> str:
    """고객 열람 주소(``/s/<토큰>``). 웹 요청 밖(워커)이라 url_for 대신 기준 주소로 만든다."""
    base = os.environ.get("FOMS_BASE_URL", "https://lahom-production.up.railway.app").rstrip("/")
    return f"{base}/s/{token}"


def _issue_links(session, order: Order, docs: str) -> list[tuple[str, Any, str]]:
    """보낼 문서의 링크를 새로 발급한다(커밋은 호출자 몫).

    Returns:
        ``[(문서 종류, 토큰 row, 토큰 원문), ...]`` — 도면이 먼저다.
    """
    links: list[tuple[str, Any, str]] = []
    if docs in ("drawing", "both"):
        row, token = share_service.create_share_token(session, order.id, "drawing")
        links.append(("drawing", row, token))
    if docs in ("estimate", "both"):
        snapshot = share_service.build_estimate_snapshot(order)
        row, token = share_service.create_share_token(session, order.id, "estimate",
                                                      snapshot=snapshot)
        links.append(("estimate", row, token))
    return links


def _customer_name(order: Order) -> str:
    sd = order.structured_data or {}
    return str(ka._node(sd, "parties", "customer").get("name") or "").strip() or "고객"


class LinkMessage(NamedTuple):
    """상담에 보낼 글 한 통 — 버튼으로 보낼 모양과 글 속 링크로 보낼 모양을 함께 든다."""

    head: str                     # 버튼 위에 보일 글(링크 없음)
    buttons: list[tuple[str, str]]  # [(버튼 이름, 주소)] — 최대 2개
    text: str                     # 버튼을 못 쓸 때 보낼 글(링크를 글 안에 넣는다)
    rows: list[Any]               # 이 글에 담긴 토큰 row 들


def build_link_messages(order: Order, links: list[tuple[str, Any, str]],
                        *, split: bool) -> list[LinkMessage]:
    """상담에 보낼 글 목록. 따로 보내기면 문서마다 한 통, 아니면 한 통에 모은다.

    링크는 버튼으로 보낸다(Open API 키가 있을 때). 키가 없거나 버튼 쓰기가 실패하면
    ``text``(글 속 링크)로 보낸다 — 카카오 상담톡에서도 그대로 눌린다.

    Returns:
        :class:`LinkMessage` 목록 — 쓰기가 중간에 실패하면 못 보낸 글의 링크만 회수하려고
        글마다 토큰 row 를 짝지어 둔다.
    """
    customer = _customer_name(order)
    days = share_service.token_days()
    closing = "보시고 궁금하신 점이나 바꾸실 부분은 이 대화방에 편하게 남겨 주세요."

    def _one(label: str, chunk: list[tuple[str, Any, str]], last: bool) -> LinkMessage:
        intro = f"{customer} 고객님, 요청하신 {label}입니다.\n{days}일 동안 열어 보실 수 있습니다."
        tail = f"\n\n{closing}" if last else ""
        buttons = [(f"{DOC_LABELS[kind]} 보기", _public_url(token)) for kind, _row, token in chunk]
        blocks = "\n\n".join(f"▶ {title}\n{url}" for title, url in buttons)
        return LinkMessage(head=f"{intro}{tail}", buttons=buttons,
                           text=f"{intro}\n\n{blocks}{tail}", rows=[row for _k, row, _t in chunk])

    if split and len(links) > 1:
        return [_one(DOC_LABELS[link[0]], [link], index == len(links) - 1)
                for index, link in enumerate(links)]
    label = "도면과 계약서" if len(links) > 1 else DOC_LABELS[links[0][0]]
    return [_one(label, links, True)]


def _send_link_message(brand: str, user_chat_id: str, message: LinkMessage,
                       channel_id: str) -> dict[str, Any]:
    """버튼으로 먼저 쓰고, 키가 없거나 실패하면 글 속 링크로 다시 쓴다."""
    result = channel_client.send_user_chat_buttons(brand, user_chat_id, message.head,
                                                   message.buttons, bot_name=_BOT_NAME)
    if result.get("success"):
        return result
    if result.get("error") != "not_configured":
        logger.warning("[상담 먼저] 버튼 쓰기 실패 → 글 속 링크로 chat=%s error=%s",
                       user_chat_id, result.get("error"))
    return channel_client.send_user_chat_message(user_chat_id, message.text, bot_name=_BOT_NAME,
                                                 channel_id=channel_id)


def _order_url(order_id: int) -> str:
    base = os.environ.get("FOMS_BASE_URL", "https://lahom-production.up.railway.app").rstrip("/")
    return f"{base}/erp/orders/{int(order_id)}"


def _note(user_chat_id: str, text: str, channel_id: str = "") -> None:
    """매니저만 보는 내부 메모(실패해도 처리를 깨뜨리지 않는다)."""
    result = channel_client.send_user_chat_message(user_chat_id, text, bot_name=_BOT_NAME,
                                                   private=True, channel_id=channel_id)
    if not result.get("success"):
        logger.warning("[상담 먼저] 내부 메모 실패 chat=%s", user_chat_id)


def _record(session, order_id: int, event_type: str, payload: dict[str, Any]) -> None:
    session.add(OrderEvent(order_id=order_id, event_type=event_type, payload=payload))


def handle_user_chat_message(session, payload: dict[str, Any],
                             *, now: Optional[datetime.datetime] = None) -> str:
    """채널톡 고객 상담 메시지 하나를 처리한다(웹훅 워커가 부른다).

    Args:
        session: DB 세션(이 함수가 커밋한다).
        payload: 채널톡 웹훅 본문(``entity`` 가 메시지).
        now: 기준 시각(테스트 주입).

    Returns:
        처리 결과 이름 — ``ignored_*``/``rejected``/``limit``/``send_failed``/``partial``/``delivered``.
    """
    now = now or now_utc_naive()
    entity = payload.get("entity") if isinstance(payload.get("entity"), dict) else {}
    if str(entity.get("chatType") or "") != "userChat":
        return "ignored_not_user_chat"
    if str(entity.get("personType") or "") != "user":
        return "ignored_not_customer"
    user_chat_id = str(entity.get("chatId") or "")
    # 라홈·하우드는 채널톡 채널이 따로다 — 답장은 메시지가 온 채널로 써야 한다.
    channel_id = str(entity.get("channelId") or "")
    parsed = parse_consult_message(str(entity.get("plainText") or ""))
    if not user_chat_id or parsed is None:
        return "ignored_no_code"
    order_id, code = parsed

    order = (
        session.query(Order)
        .filter(Order.id == order_id, Order.active_filter())
        .one_or_none()
    )
    # 주문이 없을 때와 코드가 틀릴 때 메모를 똑같이 쓴다 — 어느 주문이 있는지 드러내지 않는다.
    rejected_note = "[FOMS 자동] 확인코드를 확인하지 못해 자동으로 보내지 않았어요. 담당자가 확인해 주세요."
    if order is None or is_partner_order(order):
        _note(user_chat_id, rejected_note, channel_id)
        return "rejected"

    request_event = _find_request(session, order.id, code, now)
    revoked = request_event is not None and _revoked_by_staff(session, request_event)
    if request_event is None or revoked:
        _record(session, order.id, "SHARE_CONSULT_REJECTED",
                {"user_chat_id": user_chat_id,
                 "reason": "revoked" if revoked else "code_mismatch_or_expired"})
        session.commit()
        _note(user_chat_id, rejected_note, channel_id)
        return "rejected"

    request_payload = copy.deepcopy(request_event.payload)
    consult = request_payload["consult"]
    if int(consult.get("deliveries") or 0) >= MAX_DELIVERIES:
        session.rollback()  # 행 잠금 풀기
        _note(user_chat_id, f"[FOMS 자동] 이 코드로 이미 {MAX_DELIVERIES}번 보냈어요. "
                            f"더 필요하면 담당자가 직접 보내 주세요.\n{_order_url(order.id)}", channel_id)
        return "limit"

    try:
        links = _issue_links(session, order, str(consult.get("docs") or "drawing"))
    except share_service.SnapshotTooLargeError:
        session.rollback()
        _note(user_chat_id, f"[FOMS 자동] 계약서가 너무 커서 링크를 못 만들었어요. "
                            f"담당자가 직접 보내 주세요.\n{_order_url(order.id)}", channel_id)
        return "send_failed"
    # 잠금을 쥔 채로 횟수를 먼저 하나 잡아 둔다(동시에 눌러도 한도를 넘지 않게). 하나도 못 보내면 되돌린다.
    consult["deliveries"] = int(consult.get("deliveries") or 0) + 1
    request_event.payload = request_payload
    flag_modified(request_event, "payload")
    session.commit()

    brand = ka.resolve_brand(order.structured_data or {})
    messages = build_link_messages(order, links, split=bool(consult.get("split")))
    sent_rows: list[Any] = []
    sent_ids: list[Optional[str]] = []
    error: Optional[str] = None
    for message in messages:
        result = _send_link_message(brand, user_chat_id, message, channel_id)
        if not result.get("success"):
            error = result.get("error") or "provider_error"
            break
        sent_rows.extend(message.rows)
        sent_ids.append(result.get("message_id"))

    # 고객에게 못 닿은 링크만 회수한다(이미 간 링크는 고객 손에서 열려야 한다).
    unsent = [row for _kind, row, _token in links if row not in sent_rows]
    for row in unsent:
        share_service.revoke_token(row)
    status = "sent" if error is None else ("partial" if sent_rows else "failed")
    if status == "failed":
        locked = (session.query(OrderEvent).filter(OrderEvent.id == request_event.id)
                  .with_for_update().populate_existing().one())
        undo = copy.deepcopy(locked.payload)
        undo["consult"]["deliveries"] = max(int(undo["consult"].get("deliveries") or 1) - 1, 0)
        locked.payload = undo
        flag_modified(locked, "payload")
    _record(session, order.id, "SHARE_CONSULT_DELIVERED",
            {"user_chat_id": user_chat_id, "status": status, "error": error,
             "request_event_id": request_event.id,
             "sent_share_ids": [row.id for row in sent_rows],
             "revoked_share_ids": [row.id for row in unsent],
             "docs": consult.get("docs"), "split": bool(consult.get("split")),
             "message_ids": sent_ids})
    session.commit()

    if status == "failed":
        _note(user_chat_id, f"[FOMS 자동] 링크를 상담에 쓰지 못했어요. 담당자가 직접 보내 주세요.\n"
                            f"{_order_url(order.id)}", channel_id)
        return "send_failed"
    manager = order_manager_label(order.structured_data, order.manager_name) or "미지정"
    # 받은편지함에 누구인지 보이게 — 고객 이름과 "주문 · 고객 · 담당"(Open API 키가 있을 때만).
    channel_client.label_user_chat(
        brand, user_chat_id=user_chat_id,
        user_id=str(entity.get("personId") or ""), customer_name=_customer_name(order),
        description=f"주문 {order.id} · {_customer_name(order)} · 담당 {manager}")
    sent_label = "·".join(DOC_LABELS[kind] for kind, row, _t in links if row in sent_rows)
    tail = "" if status == "sent" else " 나머지는 쓰지 못했어요 — 담당자가 직접 보내 주세요."
    _note(user_chat_id, f"[FOMS 자동] 주문 {order.id} · 담당 {manager}\n"
                        f"{sent_label} 링크를 보냈어요.{tail}\n{_order_url(order.id)}", channel_id)
    return "delivered" if status == "sent" else "partial"
