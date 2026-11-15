"""시공일 안내 알림톡 — 서식 글 초안 · 변수 · 나가는 조건 · 보내기 · 이력(설계서 2026-11-14-foms-graft 3.13 · D208).

실측 예약 알림톡(:mod:`foms.services.kakao_alimtalk`)의 부품을 그대로 쓴다 — 보내는 코드를 한 벌 더 만들지 않는다.
브랜드 고르기(``resolve_brand``) · 전화 고르기(``extract_valid_phone``) · Solapi 설정(``is_configured`` · ``sender_phone``) ·
보낼 수 없는 주문 가르기(삭제 · 초안 · 협력사) · Solapi 보내기(``send_template`` → ``_solapi_send`` — 시험이 바꿔 끼우는 한 곳) ·
오류 분류 · 이력 쓰기(``write_structured`` — ``structured_data`` 쓰기 한 곳).

**나가는 조건(모두 참일 때만)** — :func:`block_reason` 이 ``None``:

1. 스위치 ``FOMS_GRAFT_CONSTRUCTION_ALIMTALK_ENABLED``(전역 — :func:`foms.services.graft_flags.enabled_global`)
2. Solapi 설정(API 열쇠 · 비밀 · 그 브랜드 발신번호 — ``is_configured(brand)``)
3. 서식 번호 env ``SOLAPI_TEMPLATE_CONSTRUCTION_ID_<브랜드>`` + 그 브랜드 발신 프로필 ``SOLAPI_PF_ID_<브랜드>``
4. 보낼 수 있는 주문(있음 · 삭제 아님 · 협력사 주문 아님 · 초안 아님) · 손님 휴대폰 있음 · 시공일 있음

하나라도 아니면 코드만 돌려주고 **아무것도 보내지도 쓰지도 않는다**(이력 · 감사 줄 없음 — 스위치가 꺼지면 지금과 같다).
같은 주문 · 같은 시공일로 이미 나갔으면 다시 보내지 않는다(:func:`sent_for` — 판정은 주문 줄 잠금 아래에서 해 겹친 두 보내기가
두 통을 내지 않는다, :func:`_locked_order`). 보내 본 결과(나감 · 벤더 실패)만 이력
``structured_data.alimtalk_construction``(실측 예약 ``alimtalk_measurement`` 와 같은 꼴 + ``construction_date``)과 감사 줄
``ALIMTALK_CONSTRUCTION_SENT``(본문 · 손님 정보 없음 — 번호 · 코드만)에 남는다.

시공 팀 · 인원 글은 어디에도 없다(D211) — 변수는 고객명 · 시공일 · 시간대 · 주문처 넷뿐이다.
시험 · 스테이징에서는 나가지 않는다: 시험은 ``kakao_alimtalk._solapi_send`` 를 가짜로 바꾸고, 스테이징에는 서식 번호 env 를 넣지 않는다.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from foms.services import kakao_alimtalk as base
from foms.services.audit_writer import normalize_security_detail
from foms.services.auth.partner_scope import is_partner_order, is_partner_sd
from foms.services.datetime_kst import now_utc_naive
from foms.services.graft_flags import enabled_global
from models import Order, SecurityLog

logger = logging.getLogger(__name__)

__all__ = [
    "ALIMTALK_TEMPLATE_CONSTRUCTION", "AUDIT_SENT", "GATE_CODES", "HISTORY_KEY", "TEMPLATE_ENV_PREFIX",
    "block_reason", "build_construction_variables", "construction_config", "construction_day", "is_construction_ready",
    "last_record", "order_block", "readiness_code", "render_construction_preview", "send_construction_alimtalk",
    "sent_for",
]

# 초안이다 — 카카오 심사에 낼 글의 바탕(설계서 11절 남은 일 1). 실제 본문은 Solapi 에 등록된 심사 통과본이고 이 상수는
# 미리 보기 · 길이 확인용 사본이다. 변수 이름(#{…})이 심사 글과 한 글자라도 다르면 보내기가 실패한다(template_mismatch).
# **심사 글이 정해지면 이 글을 그 글로 맞춘다.** 팀 · 인원 글은 넣지 않는다(D211).
ALIMTALK_TEMPLATE_CONSTRUCTION = """안녕하세요 #{고객명} 고객님,
주문하신 가구의 시공 일정을 안내드립니다.

시공일 : #{시공일}
시간대 : #{시간대}
주문처 : #{주문처}

일정 변경이 필요하시면
현재 계신 카카오 고객센터 채팅 또는
담당자분께 문의 부탁 드립니다."""

#: 서식 번호 env 머리 — 뒤에 브랜드(``LAHOM`` · ``HAUD``)를 붙인다. 스테이징에는 넣지 않는다.
TEMPLATE_ENV_PREFIX = "SOLAPI_TEMPLATE_CONSTRUCTION_ID_"
HISTORY_KEY = "alimtalk_construction"
AUDIT_SENT = "ALIMTALK_CONSTRUCTION_SENT"
_TEMPLATE = "construction"
#: 변수 한 칸 글자 상한(본문 1,000자 상한 ``ALIMTALK_MAX_BODY_LEN`` 안에 넉넉히 든다).
_VALUE_LIMIT = 40

#: 나가지 않는 까닭 코드(보내 보지 않았다 — 이력 · 감사 없음). 벤더 실패 코드(``network`` 등)는 여기 없다.
GATE_CODES: frozenset[str] = frozenset({
    "order_not_found", base.PARTNER_ORDER_REASON, "not_eligible", "disabled", "not_configured",
    "brand_profile_missing", "no_valid_phone", "no_construction_date",
})


def _node(data: Any, *keys: str) -> dict[str, Any]:
    for key in keys:
        data = data.get(key) if isinstance(data, dict) else None
    return data if isinstance(data, dict) else {}


def _sd(order: Any) -> dict[str, Any]:
    data = getattr(order, "structured_data", None)
    return data if isinstance(data, dict) else {}


def _clip(value: Any, limit: int = _VALUE_LIMIT) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ── 서식 변수 · 미리 보기 ────────────────────────────────────────────────
def construction_day(sd: Any) -> Optional[str]:
    """시공일(``schedule.construction.date`` — 여러 날이면 정렬 · 중복 뺀 ``YYYY-MM-DD`` 를 ``|`` 로 이은 글). 없으면 ``None``."""
    dates = base.valid_dates(_node(sd, "schedule", "construction").get("date"))
    return "|".join(dates) if dates else None


def build_construction_variables(sd: Any) -> dict[str, str]:
    """서식 변수 넷 — 고객명 · 시공일 · 시간대 · 주문처(빈 값은 실측 예약 서식과 같은 대신 글). 팀 · 인원 칸은 읽지 않는다.

    Args:
        sd: 주문 ``structured_data``.

    Returns:
        ``{'#{고객명}': …, '#{시공일}': '11월 20일', '#{시간대}': '오전', '#{주문처}': …}``.
    """
    node = _node(sd, "schedule", "construction")
    return {
        "#{고객명}": _clip(_node(sd, "parties", "customer").get("name")) or base.CONSULT_FALLBACK,
        "#{시공일}": base.korean_dates(node.get("date")),
        "#{시간대}": _clip(node.get("time"), 20) or base.UNDECIDED_FALLBACK,
        "#{주문처}": _clip(_node(sd, "parties", "orderer").get("name")) or base.DEFAULT_ORDERER,
    }


def render_construction_preview(sd: Any) -> str:
    """서식 글 초안에 변수를 넣은 미리 보기(Solapi 서버와 같은 치환 — 바꾸기만)."""
    text = ALIMTALK_TEMPLATE_CONSTRUCTION
    for name, value in build_construction_variables(sd).items():
        text = text.replace(name, value)
    return text


# ── 나가는 조건 ──────────────────────────────────────────────────────────
def construction_config(brand: str) -> Optional[dict[str, str]]:
    """그 브랜드의 발신 프로필 · 시공일 안내 서식 번호(둘 다 있어야 — 없으면 ``None``)."""
    pf_id = base.env(f"SOLAPI_PF_ID_{brand}")
    template_id = base.env(f"{TEMPLATE_ENV_PREFIX}{brand}")
    return {"pf_id": pf_id, "template_id": template_id} if pf_id and template_id else None


def readiness_code(brand: str) -> Optional[str]:
    """쓸 수 있는 상태가 아닌 까닭 — 스위치 끔 ``disabled`` · Solapi 설정 없음 ``not_configured`` · 서식 번호 없음
    ``brand_profile_missing``. 셋 다 있으면 ``None``."""
    if not enabled_global("construction_alimtalk"):
        return "disabled"
    if not base.is_configured(brand):
        return "not_configured"
    return None if construction_config(brand) is not None else "brand_profile_missing"


def is_construction_ready(brand: str) -> bool:
    """스위치 + Solapi 설정 + 서식 번호 셋 다 있나(설계서 3.13 — 하나라도 없으면 나가지 않는다)."""
    return readiness_code(brand) is None


def order_block(order: Any) -> Optional[str]:
    """시공일을 빼고 이 주문에 보낼 수 없는 까닭 — 없음 · 삭제 · 협력사 · 초안 · 쓸 수 없는 상태 · 전화 없음. 되면 ``None``.

    시공일 잡기 · 옮기기 승인 창은 아직 쓰기 전의 날짜를 보므로 날짜 칸은 :func:`block_reason` 이 따로 본다.
    """
    if order is None or base.is_deleted_order(order):
        return "order_not_found"
    sd = _sd(order)
    if is_partner_order(order) or is_partner_sd(sd):
        return base.PARTNER_ORDER_REASON
    if base.is_draft_order(order, sd):
        return "not_eligible"
    code = readiness_code(base.resolve_brand(sd))
    if code is not None:
        return code
    return None if base.extract_valid_phone(sd) else "no_valid_phone"


def block_reason(order: Any) -> Optional[str]:
    """나가지 않는 까닭 코드(:data:`GATE_CODES`) — :func:`order_block` + 시공일 없음. 모두 되면 ``None``."""
    return order_block(order) or (None if construction_day(_sd(order)) else "no_construction_date")


# ── 이력 ─────────────────────────────────────────────────────────────────
def last_record(sd: Any) -> dict[str, Any]:
    """마지막 시공일 안내 이력(없으면 빈 dict)."""
    record = sd.get(HISTORY_KEY) if isinstance(sd, dict) else None
    return record if isinstance(record, dict) else {}


def sent_for(sd: Any, day: Optional[str]) -> bool:
    """그 시공일(:func:`construction_day` 꼴)로 이미 손님에게 나갔나 — 마지막 이력이 그 날 · 나감 · 벤더 번호 있음."""
    record = last_record(sd)
    return bool(day) and record.get("construction_date") == day and bool(record.get("sent_at")) \
        and record.get("error") is None and bool(record.get("message_id"))


def _record(session: Any, order: Order, *, day: str, dedupe_key: str, message_id: Optional[str],
            error: Optional[str], sent_by: Optional[int]) -> None:
    """이력 한 칸(실측 예약 이력과 같은 꼴 + 시공일). 커밋은 부르는 쪽."""
    sd = copy.deepcopy(order.structured_data or {})
    sd[HISTORY_KEY] = {
        "sent_at": now_utc_naive().isoformat() if error is None else None, "message_id": message_id,
        "dedupe_key": dedupe_key, "error": error, "sent_by": sent_by,
        "sent_by_name": base.resolve_sender_name(session, sent_by), "construction_date": day,
        "channel": None, "channel_checked_at": None,
    }
    base.write_structured(order, sd)


def _audit(session: Any, order: Order, *, sent: bool, error: Optional[str], sent_by: Optional[int],
           source: Optional[str]) -> None:
    """감사 줄 한 줄 — 번호 · 코드만(본문 · 손님 이름 · 전화 · 날짜 없음)."""
    detail: dict[str, Any] = {"sent": sent, "error": error, "template": _TEMPLATE}
    if source:
        detail["source"] = source
    session.add(SecurityLog(
        user_id=sent_by, action=AUDIT_SENT, target_type="order", target_id=int(order.id),
        message=f"주문 #{order.id} — 시공일 안내 알림톡 {'보냄' if sent else '못 보냄'}",
        detail=normalize_security_detail(detail)))


# ── 보내기 ───────────────────────────────────────────────────────────────
def _dispatch(sd: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """나가는 조건을 지난 주문 sd 로 한 통 — (벤더 번호, 오류 코드). 벤더 예외는 삼키지 않고 코드로 분류한다."""
    phone = base.extract_valid_phone(sd) or ""
    brand = base.resolve_brand(sd)
    config = construction_config(brand) or {}
    try:
        message_id = base.send_template(to=phone, from_=base.sender_phone(brand), pf_id=config["pf_id"],
                                        template_id=config["template_id"], variables=build_construction_variables(sd))
    except Exception as exc:  # noqa: BLE001 — 벤더 예외는 코드로 이력에 남긴다(로그에는 가린 번호 · 코드만)
        code = base.classify_error(exc)
        logger.warning("[ALIMTALK-CONSTRUCTION] 보내기 실패 to=%s error=%s", base.mask_phone(phone), code)
        return None, code
    logger.info("[ALIMTALK-CONSTRUCTION] 보냄 to=%s message_id=%s", base.mask_phone(phone), message_id)
    return message_id, None


def _locked_order(session: Any, order_id: int) -> Optional[Order]:
    """주문 줄을 ``FOR UPDATE`` 로 잠근 최신 값(없으면 ``None``) — 판정 · 보내기 · 이력이 한 잠금 아래에 있게.

    겹친 두 보내기(같은 주문의 할 일 · 시공일 승인의 ``notify_customer`` · 되맞추기 뒤 다시 승인)는 여기서 줄을 서고, 뒤에 온
    쪽은 앞쪽 이력이 커밋된 뒤 '이미 나감'(:func:`sent_for`)을 본다 — 같은 시공일로 두 통이 나가지 않는다(검수 R-12).
    잠금은 벤더 왕복(Solapi — httpx 기본 5초 시간 제한)까지 이어진다.
    """
    return session.query(Order).filter(Order.id == int(order_id)).populate_existing().with_for_update().first()


def _send_in_session(session: Any, order: Optional[Order], *, manual_by: Optional[int], dedupe_key: str,
                     source: Optional[str]) -> dict[str, Any]:
    """잠근 주문(:func:`_locked_order`)으로 판정 → (이미 나감이면 그대로) → 보내기 → 이력 · 감사(커밋은 부르는 쪽)."""
    sd = _sd(order)
    day = construction_day(sd)
    if sent_for(sd, day):
        return {"sent": True, "error": None}
    code = block_reason(order)
    if code is not None:
        logger.info("[ALIMTALK-CONSTRUCTION] 안 보냄 order=%s code=%s", getattr(order, "id", None), code)
        return {"sent": False, "error": code}
    message_id, error = _dispatch(sd)
    _record(session, order, day=str(day), dedupe_key=dedupe_key, message_id=message_id, error=error, sent_by=manual_by)
    _audit(session, order, sent=error is None, error=error, sent_by=manual_by, source=source)
    return {"sent": error is None, "error": error}


def send_construction_alimtalk(order_id: int, *, manual_by: Optional[int], dedupe_key: str,
                               source: Optional[str] = None) -> dict[str, Any]:
    """주문 줄을 잠가 다시 읽고 나가는 조건 → 보내기 → 이력 · 감사까지 한 트랜잭션(제 세션에서 스스로 커밋한다).

    Args:
        order_id: 주문 번호.
        manual_by: 승인한 사람 번호(감사 · 이력의 보낸 사람).
        dedupe_key: 이력에 남길 열쇠 — 할 일은 ``alimtalk:construction:<주문>:<시공일>:action:<제안 번호>``.
        source: 감사 줄 출처 표식(``erp_action:<제안 번호>``).

    Returns:
        ``{'sent': bool, 'error': str | None}`` — :func:`foms.services.kakao_alimtalk.send_alimtalk` 과 같은 꼴. 나가지 않은
        까닭은 :data:`GATE_CODES`, 벤더 실패는 실측 예약과 같은 분류 코드(``network`` · ``auth`` …).
    """
    session = base.open_session()
    try:
        order = _locked_order(session, order_id)
        result = _send_in_session(session, order, manual_by=manual_by, dedupe_key=dedupe_key, source=source)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
