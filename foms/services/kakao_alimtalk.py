"""카카오 알림톡 v1 — 실측 예약 확정 템플릿의 변수 빌더·자격 판정·발송.

두 계층이 한 파일에 있다.

* **순수 계층(T1)**: :func:`normalize_measure_schedule`~:func:`render_preview`. 외부
  호출·DB 접근이 없는 순수 함수다.
* **발송 계층(T2)**: :func:`send_alimtalk`(재조회→자격판정→발송→이력)과 자동 트리거
  진입점 :func:`maybe_send_measure_alimtalk`. 멱등은 ``domain_side_effect_outbox`` 의
  partial UNIQUE ``(effect_type, dedupe_key)`` 가 DB 제약으로 담당하고, 이력은
  ``structured_data['alimtalk_measurement']`` + ``OrderEvent`` 에 남는다.

발송 실행은 T0 결정(WORKER_OFF)에 따라 **요청 스레드 동기 호출**이다 — outbox 행은
멱등 전용으로 먼저 insert 하고 성공 시 DONE 으로 닫는다. 나중에 sidefx worker 가 붙으면
남은 PENDING 행이 그대로 재시도 경로가 된다(handler 등록은 T0 재판정 시).
"""

from __future__ import annotations

import copy
import logging
import os
import re
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from db import engine
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_display import erp_deposit_amount_from_structured
from foms.services.order_date_sync import _normalize_date_str
from foms.services.sidefx_outbox import enqueue_side_effect
from models import DomainSideEffectOutbox, Order, OrderEvent

__all__ = [
    "ALIMTALK_TEMPLATE_MEASURE",
    "ALIMTALK_MAX_BODY_LEN",
    "ALIMTALK_EFFECT_TYPE",
    "normalize_measure_schedule",
    "build_dedupe_key",
    "extract_valid_phone",
    "build_variables",
    "render_preview",
    "is_configured",
    "resolve_brand",
    "brand_config",
    "sender_phone",
    "send_alimtalk",
    "maybe_send_measure_alimtalk",
]

logger = logging.getLogger(__name__)

#: 심사 제출 확정본(스펙 §5). 제출 후 수정 불가 — 문자열 변경 금지.
ALIMTALK_TEMPLATE_MEASURE = """안녕하세요 #{고객명} 고객님, 실측 예약이 정상적으로 완료되었습니다.
일정 변경이 있을 경우 아래 문의하기 버튼으로 미리 연락 부탁드립니다.

실측일 : #{실측일}
시  간 : #{실측시간}

고객명 : #{고객명}
발주사 : #{발주사}
시공일 : #{시공일}
주  소 : #{주소}
연락처 : #{연락처}

#{품목내역}

예약금(선금) : #{예약금}"""

#: 치환 후 본문 하드 상한(스펙 §5).
ALIMTALK_MAX_BODY_LEN = 1000

#: 알림톡 변수는 비울 수 없어 빈값은 폴백 문구로 채운다(스펙 §5).
_CONSULT = "상담"
_UNDECIDED = "미정"
_DEFAULT_ORDERER = "라홈"

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PHONE_SPLIT_RE = re.compile(r"[/,;\n]")

#: `#{품목내역}` 블록 6줄. 값 후보 키는 앞에서부터 먼저 채워진 것을 쓴다.
_ITEM_FIELD_LABELS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("제품명", ("product_name",)),
    ("내 부", ("internal",)),
    ("색 상", ("color",)),
    ("옵 션", ("option_detail", "option")),
    ("손잡이", ("handle",)),
    ("기 타", ("misc",)),
)


def _node(sd: Any, *keys: str) -> dict[str, Any]:
    """중첩 dict를 안전하게 따라간다. 경로 중간이 dict가 아니면 빈 dict."""
    current = sd
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _valid_dates(raw: Any) -> list[str]:
    """콤마 다중 일자를 ``YYYY-MM-DD``로 정규화한다(정렬·중복제거, 실패 토큰 제외)."""
    normalized: set[str] = set()
    for token in str(raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        candidate = str(_normalize_date_str(token) or "")
        if _ISO_DATE_RE.match(candidate):
            normalized.add(candidate)
    return sorted(normalized)


def _korean_dates(raw: Any) -> str:
    """``YYYY-MM-DD`` 목록을 ``8월 14일, 8월 15일`` 표기로. 유효 0건이면 '상담'."""
    dates = _valid_dates(raw)
    if not dates:
        return _CONSULT
    return ", ".join(f"{int(d[5:7])}월 {int(d[8:10])}일" for d in dates)


def normalize_measure_schedule(sd: dict | None) -> tuple[str, str] | None:
    """실측 일정을 canonical 형태로 만든다.

    Args:
        sd: 주문 structured_data.

    Returns:
        ``(dates, time)`` — dates는 정렬·중복제거된 ``YYYY-MM-DD``의 ``|`` 결합,
        time은 strip한 원문. 유효 날짜 0건이면 ``None``(발송 미자격).
    """
    measure = _node(sd, "schedule", "measurement")
    dates = _valid_dates(measure.get("date"))
    if not dates:
        return None
    return "|".join(dates), str(measure.get("time") or "").strip()


def build_dedupe_key(order_id: int, sd: dict | None) -> str | None:
    """자동 발송 멱등키를 만든다.

    Args:
        order_id: 주문 id.
        sd: 주문 structured_data.

    Returns:
        ``alimtalk:measure:{order_id}:{dates}:{time}``. 미자격이면 ``None``.
    """
    schedule = normalize_measure_schedule(sd)
    if schedule is None:
        return None
    dates, time = schedule
    return f"alimtalk:measure:{order_id}:{dates}:{time}"


def extract_valid_phone(sd: dict | None) -> str | None:
    """고객 휴대폰 번호를 숫자만 남겨 추출한다.

    Args:
        sd: 주문 structured_data.

    Returns:
        10~11자리이고 ``01``로 시작하는 첫 번째 토큰(숫자만). 없으면 ``None``.
    """
    raw = _node(sd, "parties", "customer").get("phone")
    for token in _PHONE_SPLIT_RE.split(str(raw or "")):
        digits = re.sub(r"\D", "", token)
        if 10 <= len(digits) <= 11 and digits.startswith("01"):
            return digits
    return None


def _item_block(item: dict[str, Any]) -> str:
    """품목 1건을 6줄 블록으로 만든다(빈 필드는 '상담')."""
    lines: list[str] = []
    for label, keys in _ITEM_FIELD_LABELS:
        value = ""
        for key in keys:
            value = str(item.get(key) or "").strip()
            if value:
                break
        lines.append(f"{label} : {value or _CONSULT}")
    return "\n".join(lines)


def _items_text(items: Any) -> str:
    """품목 블록들을 빈 줄로 이어 붙인다. 품목이 없으면 '상담'."""
    blocks = [_item_block(it) for it in items if isinstance(it, dict)] if isinstance(items, list) else []
    return "\n\n".join(blocks) if blocks else _CONSULT


def _substitute(variables: dict[str, str]) -> str:
    """템플릿에 변수를 로컬 치환한다(Solapi 서버 렌더와 동일 규칙)."""
    text = ALIMTALK_TEMPLATE_MEASURE
    for name, value in variables.items():
        text = text.replace(name, value)
    return text


def _shrink_items(variables: dict[str, str], items: Any) -> None:
    """품목내역을 '첫 품목 블록 + 외 N건'으로 축약한다(길이 초과 1차 대응)."""
    blocks = [it for it in items if isinstance(it, dict)] if isinstance(items, list) else []
    if len(blocks) > 1:
        variables["#{품목내역}"] = f"{_item_block(blocks[0])}\n외 {len(blocks) - 1}건"


def _enforce_length(variables: dict[str, str]) -> None:
    """치환 결과가 상한을 넘으면 가장 긴 변수부터 잘라 하드 가드를 만족시킨다."""
    for _ in range(len(variables)):
        excess = len(_substitute(variables)) - ALIMTALK_MAX_BODY_LEN
        if excess <= 0:
            return
        key = max(variables, key=lambda name: len(variables[name]))
        keep = len(variables[key]) - excess - 1
        variables[key] = variables[key][:keep] + "…" if keep > 0 else _CONSULT


def build_variables(sd: dict | None) -> dict[str, str]:
    """알림톡 템플릿 변수 dict를 만든다.

    Args:
        sd: 주문 structured_data.

    Returns:
        ``{'#{고객명}': '임다슬', ...}`` — 키는 중괄호 포함 변수명. 빈값은 폴백 문구로
        채워지며, 치환 후 길이가 ``ALIMTALK_MAX_BODY_LEN``을 넘지 않도록 축약된다.
    """
    customer = _node(sd, "parties", "customer")
    measure = _node(sd, "schedule", "measurement")
    site = _node(sd, "site")
    items = sd.get("items") if isinstance(sd, dict) else None
    deposit = erp_deposit_amount_from_structured(sd if isinstance(sd, dict) else {})

    variables = {
        "#{고객명}": str(customer.get("name") or "").strip() or _CONSULT,
        "#{실측일}": _korean_dates(measure.get("date")),
        "#{실측시간}": str(measure.get("time") or "").strip() or _UNDECIDED,
        "#{발주사}": str(_node(sd, "parties", "orderer").get("name") or "").strip() or _DEFAULT_ORDERER,
        "#{시공일}": _korean_dates(_node(sd, "schedule", "construction").get("date")),
        "#{주소}": str(site.get("address_full") or site.get("address_main") or "").strip() or _CONSULT,
        "#{연락처}": str(customer.get("phone") or "").strip() or _CONSULT,
        "#{품목내역}": _items_text(items),
        "#{예약금}": f"{deposit:,}원" if deposit is not None else "없음",
    }

    if len(_substitute(variables)) > ALIMTALK_MAX_BODY_LEN:
        _shrink_items(variables, items)
    _enforce_length(variables)
    return variables


def render_preview(sd: dict | None) -> str:
    """저장본 sd로 알림톡 본문을 로컬 치환한 미리보기 텍스트를 만든다.

    Args:
        sd: 주문 structured_data.

    Returns:
        변수 치환이 끝난 본문(길이 ``ALIMTALK_MAX_BODY_LEN`` 이하 보장).
    """
    return _substitute(build_variables(sd))


# ---------------------------------------------------------------------------
# 발송 계층 (T2) — 설정·브랜드 프로필
# ---------------------------------------------------------------------------

#: outbox effect_type. dedupe unique 의 첫 축이라 값 변경 = 멱등 이력 단절.
ALIMTALK_EFFECT_TYPE = "ALIMTALK_SEND"
#: outbox one-of FK 매트릭스에서 이 side effect 가 매달리는 도메인.
_SIDEFX_SOURCE_DOMAIN = "ORDER_EVENT"
_EVENT_SENT = "ALIMTALK_SENT"
_EVENT_FAILED = "ALIMTALK_FAILED"

#: 벤더 예외 → 이력 error 코드(스펙 §6.7). 위에서부터 먼저 맞는 것을 쓴다.
_ERROR_SIGNATURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auth", ("unauthorized", "invalidapikey", "apikey", "signature", "forbidden", "authenticat")),
    ("balance", ("balance", "잔액", "충전", "point")),
    ("template_mismatch", ("template", "variable", "치환", "pfid", "profile", "kakaooption")),
    ("invalid_phone", ("phone", "receiver", "recipient", "수신번호")),
    ("length_exceeded", ("length", "byte", "초과")),
    ("network", ("timeout", "connect", "network", "unavailable", "temporarily")),
)

#: 이 사유들은 **슬롯(outbox 행)을 소진하지 않고** 이력만 남긴다 — 원인(전화번호 오타·
#: 브랜드 템플릿 미승인)이 해소되면 같은 일정이라도 다음 저장에서 자동 발송돼야 하기
#: 때문이다(D3 단계 가동). 나머지 사유(미설정·draft·일정없음)는 이력도 남기지 않는다.
_RECORDED_SKIP_REASONS = frozenset({"no_valid_phone", "brand_profile_missing"})

#: 발신번호·발신프로필 env 접미사로 쓰는 브랜드 코드(:func:`resolve_brand` 반환값).
_BRANDS = ("LAHOM", "HAUD")

_session_factory = sessionmaker(bind=engine)


def _env(name: str) -> str:
    """환경변수를 strip 해서 읽는다(미설정이면 빈 문자열)."""
    return (os.getenv(name) or "").strip()


def _env_flag(name: str) -> bool:
    """env 플래그 truthy 판정(1/true/yes/on)."""
    return _env(name).lower() in {"1", "true", "yes", "on"}


def _mask_phone(digits: str) -> str:
    """로그용 전화번호 마스킹(``01024736730`` → ``010****6730``)."""
    return f"{digits[:3]}****{digits[-4:]}" if len(digits) >= 7 else "***"


def sender_phone(brand: str) -> str:
    """브랜드 발신번호를 결정한다(T14 — 라홈 1566-0792 / 하우드 1566-0703).

    Args:
        brand: :func:`resolve_brand` 결과(``LAHOM``/``HAUD``).

    Returns:
        ``SOLAPI_SENDER_PHONE_{brand}`` 우선, 없으면 구 단일 env ``SOLAPI_SENDER_PHONE``
        폴백(둘 다 없으면 빈 문자열). SMS/LMS 대체발송의 발신번호로 쓰인다.
        문자 공유(:mod:`foms.api.share`)는 담당자 개인번호가 ①순위라 규칙이 다르다.
    """
    return _env(f"SOLAPI_SENDER_PHONE_{brand}") or _env("SOLAPI_SENDER_PHONE")


def is_configured(brand: str | None = None) -> bool:
    """Solapi 공통 자격증명(API 키·시크릿·발신번호)이 설정됐는지 반환한다.

    Args:
        brand: 지정하면 그 브랜드로 실제 발신 가능한지까지 본다(브랜드 전용 번호 ∨
            구 폴백). 생략하면 브랜드 무관 공통 판정(구 env ∨ 브랜드 번호 중 하나).

    Returns:
        설정 완료 여부. 브랜드 발신프로필/템플릿은 여기서 보지 않는다 — 브랜드별
        단계 가동(D3)을 위해 :func:`brand_config` 가 따로 판정한다.
    """
    if not (_env("SOLAPI_API_KEY") and _env("SOLAPI_API_SECRET")):
        return False
    if brand:
        return bool(sender_phone(brand))
    return bool(_env("SOLAPI_SENDER_PHONE") or any(sender_phone(b) for b in _BRANDS))


def resolve_brand(sd: dict | None) -> str:
    """발주사명으로 브랜드를 판정한다.

    Args:
        sd: 주문 structured_data.

    Returns:
        ``parties.orderer.name`` 에 '라홈'이 있으면 ``'LAHOM'``, 그 외 전부 ``'HAUD'``
        (도면 로고 규칙 ``drawing_wizard_defaults._resolve_logo`` 와 동일 판정).
    """
    name = str(_node(sd, "parties", "orderer").get("name") or "")
    return "LAHOM" if "라홈" in name else "HAUD"


def brand_config(brand: str) -> dict[str, str] | None:
    """브랜드 발신프로필·템플릿 쌍을 env 에서 읽는다.

    Args:
        brand: :func:`resolve_brand` 결과(``LAHOM``/``HAUD``).

    Returns:
        ``{'pf_id': ..., 'template_id': ...}``. 쌍 중 하나라도 없으면 ``None``
        (해당 브랜드 건은 발송 스킵 — 템플릿 승인 전 안전 스킵).
    """
    pf_id = _env(f"SOLAPI_PF_ID_{brand}")
    template_id = _env(f"SOLAPI_TEMPLATE_MEASURE_ID_{brand}")
    if not (pf_id and template_id):
        return None
    return {"pf_id": pf_id, "template_id": template_id}


# ---------------------------------------------------------------------------
# 발송 계층 (T2) — Solapi 호출·오류 분류
# ---------------------------------------------------------------------------


def _solapi_send(
    *,
    to: str,
    from_: str,
    pf_id: str,
    template_id: str,
    variables: dict[str, str],
) -> str | None:
    """Solapi SDK 호출부(테스트 monkeypatch 격리 지점).

    Args:
        to: 수신 휴대폰(숫자만).
        from_: 사전 등록 발신번호 — SMS/LMS 대체발송(failover) 전제라 필수.
        pf_id: 브랜드 발신프로필 키.
        template_id: 심사 통과 템플릿 id.
        variables: ``{'#{고객명}': '임다슬', ...}`` 치환 변수.

    Returns:
        벤더 message id(없으면 group id). 실패는 예외로 올라온다.
    """
    from solapi import SolapiMessageService
    from solapi.model import KakaoOption, RequestMessage

    service = SolapiMessageService(_env("SOLAPI_API_KEY"), _env("SOLAPI_API_SECRET"))
    response = service.send(
        RequestMessage(
            from_=from_,
            to=to,
            kakaoOptions=KakaoOption(pf_id=pf_id, template_id=template_id, variables=variables),
        )
    )
    for item in getattr(response, "message_list", None) or []:
        if getattr(item, "message_id", None):
            return str(item.message_id)
    return str(getattr(getattr(response, "group_info", None), "group_id", "") or "") or None


def _solapi_send_text(*, to: str, from_: str, text: str) -> str | None:
    """Solapi 순수 문자(SMS/LMS) 호출부 — 공유 링크 발송(Phase A T8, 테스트 격리 지점).

    KakaoOption 없음. 발신번호는 Solapi 사전 등록 전제 — 미등록 번호는 벤더 예외로
    올라와 ``_classify_error`` 가 표면화한다(조용한 실패 없음).

    Args:
        to: 수신 휴대폰(숫자만).
        from_: 발신번호(개인 등록 번호 또는 회사 대표번호).
        text: 발송 본문(고정 문구 + 공유 URL — 단축 URL 금지).

    Returns:
        벤더 message id(없으면 group id). 실패는 예외로 올라온다.
    """
    from solapi import SolapiMessageService
    from solapi.model import RequestMessage

    service = SolapiMessageService(_env("SOLAPI_API_KEY"), _env("SOLAPI_API_SECRET"))
    response = service.send(RequestMessage(from_=from_, to=to, text=text))
    for item in getattr(response, "message_list", None) or []:
        if getattr(item, "message_id", None):
            return str(item.message_id)
    return str(getattr(getattr(response, "group_info", None), "group_id", "") or "") or None


def _classify_error(exc: BaseException) -> str:
    """벤더 예외를 이력 error 코드로 분류한다(스펙 §6.7, 미분류는 ``unknown``)."""
    if isinstance(exc, (TimeoutError, OSError)):  # ConnectionError 포함
        return "network"
    text = " ".join(str(a) for a in (getattr(exc, "args", None) or (exc,))).lower()
    for code, keywords in _ERROR_SIGNATURES:
        if any(keyword in text for keyword in keywords):
            return code
    return "unknown"


def _is_draft_order(order: Order, sd: dict) -> bool:
    """ERP draft(임시 저장) 주문 여부 — ``Order.erp_draft_filter`` 와 같은 판정."""
    if str(getattr(order, "status", "") or "").upper() == "DRAFT":
        return True
    return bool(_node(sd, "meta").get("draft"))


def _ineligible_reason(order: Order | None, sd: dict) -> str | None:
    """발송 미자격 사유 코드를 반환한다(자격이면 ``None``).

    판정 순서 = 설정 → draft → 일정 → 전화 → 브랜드 프로필. diff 비교는 쓰지 않는다
    (draft autosave 가 이전 sd 를 선점하는 함정 회피 — 스펙 §6.2).
    """
    if order is None:
        return "order_not_found"
    if not is_configured(resolve_brand(sd)):
        return "not_configured"
    if _is_draft_order(order, sd):
        return "not_eligible"
    if build_dedupe_key(int(order.id), sd) is None:
        return "not_eligible"
    if extract_valid_phone(sd) is None:
        return "no_valid_phone"
    if brand_config(resolve_brand(sd)) is None:
        return "brand_profile_missing"
    return None


def _dispatch(sd: dict) -> tuple[str | None, str | None]:
    """자격을 통과한 주문 sd 로 실제 발송한다.

    Returns:
        ``(message_id, error)`` — 성공이면 error 가 None, 실패면 message_id 가 None.
    """
    phone = extract_valid_phone(sd) or ""
    brand = resolve_brand(sd)
    config = brand_config(brand) or {}
    try:
        message_id = _solapi_send(
            to=phone,
            from_=sender_phone(brand),
            pf_id=config["pf_id"],
            template_id=config["template_id"],
            variables=build_variables(sd),
        )
    except Exception as exc:  # 벤더 예외는 삼키지 않고 코드로 분류해 이력에 남긴다
        code = _classify_error(exc)
        logger.warning("알림톡 발송 실패 (to=%s, error=%s): %s", _mask_phone(phone), code, exc)
        return None, code
    logger.info("알림톡 발송 성공 (to=%s, message_id=%s)", _mask_phone(phone), message_id)
    return message_id, None


# ---------------------------------------------------------------------------
# 발송 계층 (T2) — 이력·멱등·진입점
# ---------------------------------------------------------------------------


def _record_history(
    session: Session,
    order: Order,
    *,
    dedupe_key: str | None,
    message_id: str | None,
    error: str | None,
    sent_by: int | None,
    event_id: int | None,
) -> None:
    """``sd['alimtalk_measurement']`` 와 OrderEvent 이력을 같은 tx 에 기록한다.

    ``event_id`` 가 오면 자동 경로가 미리 만든 앵커 이벤트를 최종 상태로 승격한다
    (이벤트 중복 생성 방지). 커밋은 호출자가 소유한다.
    """
    now = now_utc_naive()
    sd = copy.deepcopy(order.structured_data or {})
    sd["alimtalk_measurement"] = {
        "sent_at": now.isoformat() if error is None else None,
        "message_id": message_id,
        "dedupe_key": dedupe_key,
        "error": error,
        "sent_by": sent_by,
    }
    order.structured_data = sd
    flag_modified(order, "structured_data")

    event = session.get(OrderEvent, event_id) if event_id else None
    if event is None:
        event = OrderEvent(order_id=order.id, created_by_user_id=sent_by, created_at=now)
        session.add(event)
    event.event_type = _EVENT_SENT if error is None else _EVENT_FAILED
    event.payload = {
        "dedupe_key": dedupe_key,
        "message_id": message_id,
        "error": error,
        "manual": sent_by is not None,
    }


def _record_skip(session: Session, order: Order, reason: str) -> None:
    """슬롯(outbox 행)을 소진하지 않고 스킵 사유만 이력에 남긴다.

    같은 일정·같은 사유가 이미 기록돼 있으면 아무것도 하지 않는다 — 같은 주문을 반복
    저장할 때 타임라인이 동일 실패 이벤트로 도배되는 것을 막는다. 커밋은 호출자 몫.
    """
    sd = order.structured_data or {}
    dedupe_key = build_dedupe_key(int(order.id), sd)
    previous = sd.get("alimtalk_measurement")
    previous = previous if isinstance(previous, dict) else {}
    if previous.get("dedupe_key") == dedupe_key and previous.get("error") == reason:
        return
    logger.info("알림톡 자동 발송 스킵 (order_id=%s, reason=%s)", order.id, reason)
    _record_history(
        session,
        order,
        dedupe_key=dedupe_key,
        message_id=None,
        error=reason,
        sent_by=None,
        event_id=None,
    )


def send_alimtalk(
    order_id: int,
    *,
    manual_by: Optional[int] = None,
    dedupe_key: Optional[str] = None,
    event_id: Optional[int] = None,
) -> dict:
    """주문을 재조회해 자격 판정 → 발송 → 이력 기록까지 한 트랜잭션으로 처리한다.

    Args:
        order_id: 주문 id.
        manual_by: 수동 발송자 user id(자동이면 None — 감사 기록용).
        dedupe_key: 이력에 남길 멱등키(생략 시 자동 키를 재계산).
        event_id: 자동 경로가 선점 단계에서 만든 앵커 OrderEvent id.

    Returns:
        ``{'sent': bool, 'error': str | None}`` — error 는 스펙 §6.7 분류 코드.
    """
    session = _session_factory()
    try:
        order = session.get(Order, order_id)
        sd = (order.structured_data or {}) if order is not None else {}
        error = _ineligible_reason(order, sd)
        if order is None:
            logger.warning("알림톡 발송 대상 주문 없음 (order_id=%s)", order_id)
            return {"sent": False, "error": error}
        message_id = None
        if error is None:
            message_id, error = _dispatch(sd)
        _record_history(
            session,
            order,
            dedupe_key=dedupe_key or build_dedupe_key(order_id, sd),
            message_id=message_id,
            error=error,
            sent_by=manual_by,
            event_id=event_id,
        )
        session.commit()
        return {"sent": error is None, "error": error}
    finally:
        session.close()


def _reserve_dedupe(order_id: int) -> tuple[int, int] | None:
    """자동 발송 슬롯을 선점한다 — 앵커 OrderEvent + outbox 행을 별도 tx 로 insert.

    앵커 이벤트는 발송 **전**에 만들어야 하므로(outbox one-of FK 가 ORDER_EVENT 도메인
    이라 order_event_id 필수) ``ALIMTALK_FAILED(in_flight)`` 로 시작하고 발송 성공 시
    :func:`_record_history` 가 ``ALIMTALK_SENT`` 로 승격한다 — 중간에 프로세스가 죽어도
    '보냈다'고 남지 않는다.

    자격 판정은 **선점 전**에 끝낸다 — 전화번호 불량·브랜드 프로필 미구성으로 못 보낼
    건이 슬롯을 소진하면 원인을 고쳐도 같은 일정이 영구 차단되기 때문이다(:data:
    `_RECORDED_SKIP_REASONS`).

    Returns:
        ``(outbox_id, event_id)``. 미자격이거나 같은 일정으로 이미 보냈으면 ``None``.
    """
    session = _session_factory()
    try:
        order = session.get(Order, order_id)
        sd = (order.structured_data or {}) if order is not None else {}
        reason = _ineligible_reason(order, sd)
        if reason is not None:
            if reason in _RECORDED_SKIP_REASONS:
                _record_skip(session, order, reason)  # 슬롯 미소진 — 원인 해소 후 재시도
                session.commit()
            return None
        dedupe_key = build_dedupe_key(order_id, sd)
        event = OrderEvent(
            order_id=order_id,
            event_type=_EVENT_FAILED,
            payload={"error": "in_flight", "dedupe_key": dedupe_key},
        )
        session.add(event)
        session.flush()  # event.id 확보(outbox one-of FK 참조)
        row = enqueue_side_effect(
            session,
            source_domain=_SIDEFX_SOURCE_DOMAIN,
            source_id=event.id,
            effect_type=ALIMTALK_EFFECT_TYPE,
            payload={"order_id": order_id, "kind": "measure"},
            dedupe_key=dedupe_key,
            provider_idempotency_key=dedupe_key,
        )
        session.commit()
        return row.id, event.id
    except IntegrityError:
        session.rollback()
        logger.info("알림톡 자동 발송 중복 차단 (order_id=%s)", order_id)
        return None
    finally:
        session.close()


def _mark_outbox_done(outbox_id: int) -> None:
    """동기 발송에 성공한 outbox 행을 DONE 으로 닫는다(worker 승격 시 재소비 방지)."""
    session = _session_factory()
    try:
        row = session.get(DomainSideEffectOutbox, outbox_id)
        if row is not None:
            row.status = "DONE"
            row.completed_at = now_utc_naive()
            session.commit()
    finally:
        session.close()


def maybe_send_measure_alimtalk(order_id: int) -> None:
    """실측 예약 알림톡 자동 발송 진입점 — 주문 저장 **커밋 후** 호출 전용.

    킬스위치·설정 게이트 → outbox 선점(중복 차단) → 동기 발송 → 성공 시 DONE 마킹.
    주문 저장 트랜잭션을 절대 막지 않도록 모든 예외를 내부에서 로그로 처리하며 호출부로
    전파하지 않는다. 발송 실패 행은 PENDING 으로 남아 worker 가 붙으면 재시도된다.

    Args:
        order_id: 방금 저장된 주문 id.
    """
    try:
        if not _env_flag("FOMS_ALIMTALK_AUTO_ENABLED") or not is_configured():
            return
        reserved = _reserve_dedupe(order_id)
        if reserved is None:
            return
        outbox_id, event_id = reserved
        if send_alimtalk(order_id, event_id=event_id).get("sent"):
            _mark_outbox_done(outbox_id)
    except Exception:  # 주문 저장 경로 비차단 — 실패는 로그로만 남긴다
        logger.exception("알림톡 자동 발송 처리 실패 (order_id=%s)", order_id)
