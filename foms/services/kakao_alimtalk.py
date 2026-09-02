"""카카오 알림톡 v1 — 실측 예약 확정 템플릿의 변수 빌더·자격 판정·발송.

두 계층이 한 파일에 있다.

* **순수 계층(T1)**: :func:`normalize_measure_schedule`~:func:`render_preview`. 외부
  호출·DB 접근이 없는 순수 함수다.
* **발송 계층(T2)**: :func:`send_alimtalk`(재조회→자격판정→발송→이력)과 자동 트리거
  진입점 :func:`maybe_send_measure_alimtalk`. 멱등은 ``domain_side_effect_outbox`` 의
  partial UNIQUE ``(effect_type, dedupe_key)`` 가 DB 제약으로 담당하고, 이력은
  ``structured_data['alimtalk_measurement']`` + ``OrderEvent`` 에 남는다.

자동 발송 실행은 SIDEFX ``ALIMTALK_SEND`` handler 몫이다. 저장 경로는 outbox 행만
선점하고(``maybe_send_measure_alimtalk``), 배달 워커가 소비한다. 수동 발송은 확인 모달이
결과를 기다려야 하므로 요청 스레드에서 :func:`send_alimtalk` 을 동기 호출한다.
"""

from __future__ import annotations

import copy
import datetime
import logging
import os
import re
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from db import engine
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_display import erp_deposit_amount_from_structured
from foms.services.order_date_sync import _normalize_date_str
from foms.services.sidefx_outbox import enqueue_side_effect
from models import Order, OrderEvent, User

__all__ = [
    "ALIMTALK_TEMPLATE_MEASURE",
    "SHARE_HISTORY_KEY",
    "SHARE_TRACKED_KINDS",
    "record_share_history",
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
    "send_alimtalk_in_session",
    "maybe_send_measure_alimtalk",
    "is_alimtalk_retryable_error",
    "confirm_channel",
    "ALIMTALK_CHANNEL_PROBE_DELAY_SEC",
    "draft_ineligible_reason",
    "send_alimtalk_for_sd",
    "build_draft_history_entry",
    "build_draft_dedupe_key",
    "build_draft_schedule_signature",
]

logger = logging.getLogger(__name__)

#: 심사 승인본 미리보기 사본(2026-08-24 개정 템플릿). 승인 템플릿이 바뀌면 같이 바꾼다
#: — 실제 발송 본문은 Solapi 쪽 승인본이고 이 상수는 ERP 미리보기·길이 가드용이다.
ALIMTALK_TEMPLATE_MEASURE = """안녕하세요 #{고객명} 고객님, 실측 예약이 정상적으로 완료되었습니다.

일정 변경이 있을 경우
현재 계신 카카오 고객센터 채팅 또는
담당자분께 문의 부탁 드립니다(행복)

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


def build_draft_schedule_signature(sd: dict | None) -> str | None:
    """초안 발송 이력에 굳힐 실측 일정 서명을 만든다(WIZ-SEND-01 D4').

    주문 id 를 뺀 :func:`build_dedupe_key` 의 의미 부분이다 — 초안 발송 시점에는 주문
    id 가 없으므로 "무엇을 안내했는가"만 남긴다. 이 값이 등록 후 새 주문 sd 의 서명과
    같으면 자동 발송이 같은 안내를 한 번 더 보내는 것이므로 :func:`_already_sent` 가
    막는다.

    Args:
        sd: 초안/주문 structured_data.

    Returns:
        ``f"{dates}:{time}"`` (dates 는 ``|`` 결합된 ``YYYY-MM-DD`` 목록).
        유효 실측 일정이 없으면 ``None``.
    """
    schedule = normalize_measure_schedule(sd)
    if schedule is None:
        return None
    dates, time = schedule
    return f"{dates}:{time}"


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

#: handler 가 예외로 올려 워커 재시도할 오류. 그 외(템플릿 불일치 등)는 DONE 으로 닫아
#: 같은 본문을 10번 보내지 않는다. ``not_configured`` 는 SIDEFX env 누락일 수 있어 재시도.
_RETRYABLE_SEND_ERRORS = frozenset({"network", "unknown", "balance", "auth", "not_configured"})

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


def _is_deleted_order(order: Order) -> bool:
    """휴지통(soft delete) 주문 여부 — ``Order.not_deleted_filter`` 와 같은 판정.

    수동 API 는 ``Order.active_filter()`` 로 삭제 주문을 이미 404 로 막는다
    (``foms/api/kakao/__init__.py`` ``_load_order``). 자동 경로에는 그 축이 없어서
    휴지통 주문을 저장해도 안내가 나갔다 — 두 경로의 판정을 같게 맞춘다.

    Args:
        order: 판정할 주문.

    Returns:
        ``status == 'DELETED'`` 이거나 ``deleted_at`` 이 채워져 있으면 True.
    """
    if str(getattr(order, "status", "") or "").upper() == "DELETED":
        return True
    return getattr(order, "deleted_at", None) is not None


def _sd_ineligible_reason(sd: dict, *, order_draft: bool = False) -> str | None:
    """order 행과 무관한 sd 축 자격 판정 — 주문 경로·초안 경로의 **공통 정본**.

    판정 순서 = 설정 → (draft) → 일정 → 전화 → 브랜드 프로필. order 축(존재·삭제·draft)은
    호출자가 판정해 ``order_draft`` 플래그로만 넘긴다 — 두 경로가 판정 로직을 두 벌로
    갈라 갖지 않게 하기 위함이다. 일정 판정은 order_id 를 요구하지 않는
    :func:`normalize_measure_schedule` 로 한다(``build_dedupe_key`` 와 같은 조건).

    Args:
        sd: 주문/초안 structured_data.
        order_draft: 호출자가 판정한 'ERP 임시저장 주문' 여부(초안 경로는 항상 False).

    Returns:
        미자격 사유 코드. 자격이면 ``None``.
    """
    if not is_configured(resolve_brand(sd)):
        return "not_configured"
    if order_draft:
        return "not_eligible"
    if normalize_measure_schedule(sd) is None:
        return "not_eligible"
    if extract_valid_phone(sd) is None:
        return "no_valid_phone"
    if brand_config(resolve_brand(sd)) is None:
        return "brand_profile_missing"
    return None


def _ineligible_reason(order: Order | None, sd: dict) -> str | None:
    """발송 미자격 사유 코드를 반환한다(자격이면 ``None``).

    판정 순서 = 존재·삭제 → 설정 → draft → 일정 → 전화 → 브랜드 프로필. diff 비교는 쓰지
    않는다 (draft autosave 가 이전 sd 를 선점하는 함정 회피 — 스펙 §6.2).

    삭제 주문은 수동 API 와 같은 코드(``order_not_found``)를 돌려준다 — 사용자에게는 "발송
    대상이 아니다"로 같은 뜻이고, 화면 3곳의 사유 문구 맵에 이미 있는 코드다. 이 코드는
    :data:`_RECORDED_SKIP_REASONS` 에 없으므로 이력도 남기지 않고 슬롯도 쓰지 않는다.
    """
    if order is None:
        return "order_not_found"
    if _is_deleted_order(order):
        return "order_not_found"
    return _sd_ineligible_reason(sd, order_draft=_is_draft_order(order, sd))


def draft_ineligible_reason(sd: dict) -> str | None:
    """order 행이 없는 초안(마법사) sd 의 발송 자격을 판정한다.

    주문 경로와 **같은 정본**(:func:`_sd_ineligible_reason`)을 쓴다 — 초안 화면과 주문
    화면이 같은 sd 에 대해 서로 다른 사유를 말하지 않게 하기 위함이다.
    order 축(존재·삭제·draft·order_id 기반 멱등키)은 초안에 없으므로 판정하지 않는다.

    Args:
        sd: 초안 payload 를 변환한 structured_data.

    Returns:
        ``not_configured`` / ``not_eligible`` / ``no_valid_phone`` /
        ``brand_profile_missing`` 중 하나. 자격이면 ``None``.
    """
    return _sd_ineligible_reason(sd)


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


def _resolve_sender_name(session: Session, sent_by: int | None) -> str | None:
    """발송 시점의 사용자 표시명을 이력에 함께 굳힌다(자동 발송이면 ``None``).

    화면의 발송 흔적 칩은 추가 요청 없이 ``structured_data`` 만 읽어 그리므로 읽기 시점에
    id 를 이름으로 바꿀 기회가 없다. 이름이 나중에 바뀌어도 '그때 보낸 사람'이 남는 편이
    이력으로 옳다(T15).

    Args:
        session: 기록 트랜잭션의 세션.
        sent_by: 수동 발송자 user id(자동이면 ``None``).

    Returns:
        표시명. 자동 발송이거나 사용자를 찾을 수 없으면 ``None``.
    """
    if sent_by is None:
        return None
    user = session.get(User, int(sent_by))
    name = getattr(user, "name", None) if user is not None else None
    return str(name) if name else None


def _write_structured(order: Order, sd: dict[str, Any]) -> None:
    """이 모듈의 **유일한** ``Order.structured_data`` 쓰기 지점.

    REV-99 writer 게이트는 ``flag_modified(<recv>, "structured_data")`` 자리를 파일 단위로
    센다. 이력 종류가 늘 때마다 쓰기 지점을 새로 만들면 그때마다 EXTERNAL 이 하나씩 늘어
    검토 기록이 흐려진다 — 이력 조립은 각자 하고, 굳히는 곳은 여기 하나로 모은다.

    Args:
        order: 대상 주문.
        sd: 되쓸 structured_data 전체(호출자가 deepcopy 로 만든 사본).
    """
    order.structured_data = sd
    flag_modified(order, "structured_data")


SHARE_HISTORY_KEY = "alimtalk_share"

#: 흔적을 남기는 공유 종류. 도면 단독·견적서 단독은 아직 대상이 아니다(사용자 결정 2026-09-01).
SHARE_TRACKED_KINDS = ("bundle",)


def record_share_history(
    session: Session,
    order: Order,
    *,
    kind: str,
    channel: str,
    share_id: int | None,
    error: str | None,
    sent_by: int | None,
) -> dict[str, Any] | None:
    """공유 링크 발송 흔적을 ``sd['alimtalk_share']`` 에 남긴다(커밋은 호출자 몫).

    실측 예약 안내 흔적(:data:`alimtalk_measurement`)과 **대칭이되 별개 레코드**다. 두
    메시지는 서로 다른 안내라, 한 칸에 합치면 "아직 안 보냄"이 무엇을 안 보냈다는 뜻인지
    화면에서 갈리지 않는다.

    ``Order.structured_data`` 를 통째로 되쓰므로 **쓰기 직전 재조회**한다 — 벤더 왕복
    사이에 다른 요청이 저장한 내용을 덮지 않기 위해서다(T15 에서 같은 구조로 밟은 함정).

    Args:
        session: 기록 트랜잭션의 세션.
        order: 대상 주문.
        kind: 공유 종류(``drawing``/``estimate``/``bundle``).
        channel: 발송 경로(``alimtalk``/``sms``).
        share_id: 공유 row id(추적용, 없으면 ``None``).
        error: 실패 사유 코드(성공이면 ``None``).
        sent_by: 발송자 user id.

    Returns:
        화면이 그대로 그릴 수 있는 이력 dict. 추적 대상 종류가 아니면 ``None``
        (아무것도 쓰지 않는다).
    """
    if kind not in SHARE_TRACKED_KINDS:
        return None

    session.refresh(order)
    now = now_utc_naive()
    record: dict[str, Any] = {
        "sent_at": now.isoformat() if error is None else None,
        "kind": kind,
        "channel": channel,
        "share_id": int(share_id) if share_id is not None else None,
        "error": error,
        "sent_by": sent_by,
        "sent_by_name": _resolve_sender_name(session, sent_by),
    }
    sd = copy.deepcopy(order.structured_data or {})
    sd[SHARE_HISTORY_KEY] = record
    _write_structured(order, sd)
    return record


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
        "sent_by_name": _resolve_sender_name(session, sent_by),
        # 채널(카톡 ATA / 문자 대체발송 SMS·LMS)은 발송 직후엔 알 수 없다 — 카톡이 실패해야
        # 벤더가 바꾸기 때문이다. 1분 뒤 조회가 채운다(confirm_channel). None = 미확정.
        "channel": None,
        "channel_checked_at": None,
    }
    _write_structured(order, sd)

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


def is_alimtalk_retryable_error(error: str | None) -> bool:
    """SIDEFX handler 가 워커 재시도를 올려야 하는 발송 오류인지 반환한다."""
    return error in _RETRYABLE_SEND_ERRORS


def _already_sent(
    order: Order, dedupe_key: Optional[str], *, manual: bool = False
) -> bool:
    """이미 같은 안내가 고객에게 도달했으면 True(재전달 시 Solapi 0회).

    판정 축이 둘이다. 막으려는 것은 **같은 키의 재사용이 아니라 같은 실측 일정 안내의
    중복 도달**이기 때문이다.

    1. 멱등키 동일 — 같은 주문에서 같은 조건으로 다시 트리거된 자동 발송.
    2. 일정 서명 동일 — 성공 이력의 ``draft_schedule`` 이 현재 sd 의
       :func:`build_draft_schedule_signature` 와 같은 경우. 마법사 초안에서 등록 전에
       보낸 안내를 승계한 이력이 여기 걸린다(WIZ-SEND-01 D4'). 초안 이력의 키는 주문
       id 를 모르는 ``draft`` 네임스페이스라 1번으로는 절대 맞지 않는데, 안내 내용은
       같으므로 그대로 두면 등록 직후 첫 저장의 **자동** 발송이 고객에게 두 번째
       문자를 보낸다. 일정이 바뀌면 서명이 달라져 자동 재발송이 정상 동작한다.

    Args:
        order: 판정 대상 주문.
        dedupe_key: 이번 발송의 멱등키.
        manual: 사용자가 버튼으로 누른 발송이면 True. 이때는 2번 축을 쓰지 않는다 —
            수동 발송은 누른 만큼 나가는 것이 계약이고(수동 라우트는 매번 새 uuid 키를
            만들어 1번 축을 일부러 비껴간다), 여기서 서명으로 막으면 화면은 "발송됨"인데
            고객에게는 아무것도 안 가는 무음 실패가 된다.
    """
    hist = (order.structured_data or {}).get("alimtalk_measurement")
    if not isinstance(hist, dict):
        return False
    if hist.get("error") is not None or not hist.get("message_id"):
        return False
    if dedupe_key and hist.get("dedupe_key") == dedupe_key:
        return True
    if manual:
        return False
    signature = build_draft_schedule_signature(order.structured_data)
    return signature is not None and hist.get("draft_schedule") == signature


def send_alimtalk_in_session(
    session: Session,
    order: Order,
    *,
    manual_by: Optional[int] = None,
    dedupe_key: Optional[str] = None,
    event_id: Optional[int] = None,
) -> dict:
    """자격 판정·발송·이력을 ``session`` 안에서 수행한다(커밋은 호출자).

    Args:
        session: 호출자 세션(SIDEFX worker 또는 수동 API 세션).
        order: 그 세션에 attach 된 주문.
        manual_by: 수동 발송자 user id(자동이면 None).
        dedupe_key: 이력 멱등키(생략 시 자동 키).
        event_id: 자동 경로 앵커 OrderEvent id.

    Returns:
        ``{'sent': bool, 'error': str | None}``.
    """
    sd = order.structured_data or {}
    key = dedupe_key or build_dedupe_key(int(order.id), sd)
    if _already_sent(order, key, manual=manual_by is not None):
        return {"sent": True, "error": None}
    error = _ineligible_reason(order, sd)
    message_id = None
    if error is None:
        message_id, error = _dispatch(sd)
    _record_history(
        session, order, dedupe_key=key, message_id=message_id,
        error=error, sent_by=manual_by, event_id=event_id,
    )
    return {"sent": error is None, "error": error}


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
        if order is None:
            logger.warning("알림톡 발송 대상 주문 없음 (order_id=%s)", order_id)
            return {"sent": False, "error": "order_not_found"}
        result = send_alimtalk_in_session(
            session, order, manual_by=manual_by,
            dedupe_key=dedupe_key, event_id=event_id,
        )
        session.commit()
        return result
    finally:
        session.close()


#: 발송 직후엔 벤더가 아직 카톡→문자 전환을 결정하지 않았다(접수 시점 type=ATA). 이만큼
#: 지난 뒤에 한 번 조회해야 실제 나간 채널을 알 수 있다(T15 ③ — 웹훅 아님, 사용자 결정).
ALIMTALK_CHANNEL_PROBE_DELAY_SEC = 60

#: 벤더 조회 결과 ``type`` 이 이 집합이면 카톡이 실패해 문자로 대체발송된 것이다.
_TEXT_CHANNELS = frozenset({"SMS", "LMS", "MMS"})


def _solapi_lookup_channel(message_id: str) -> str | None:
    """벤더에 메시지 1건을 조회해 실제 나간 채널(``type``)을 돌려준다.

    격리된 호출부다 — 테스트는 이 함수를 monkeypatch 해 네트워크 없이 돈다
    (:func:`_solapi_send` 선례).

    Args:
        message_id: 발송 시 받은 벤더 message id.

    Returns:
        ``'ATA'``(카톡) · ``'SMS'``/``'LMS'``(문자 대체발송) 등 벤더 type. 벤더가 그
        메시지를 모르면 ``None``. 호출 실패는 예외로 올라온다.
    """
    from solapi import SolapiMessageService
    from solapi.model.request.messages.get_messages import GetMessagesRequest

    service = SolapiMessageService(_env("SOLAPI_API_KEY"), _env("SOLAPI_API_SECRET"))
    response = service.get_messages(GetMessagesRequest(message_id=message_id))
    for item in (getattr(response, "message_list", None) or {}).values():
        kind = getattr(item, "type", None)
        if kind:
            return str(kind).upper()
    return None


def _parse_history_time(value: object) -> datetime.datetime | None:
    """이력에 저장된 naive UTC ISO 문자열을 datetime 으로 되돌린다(불량이면 None)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


def is_text_channel(channel: object) -> bool:
    """이력의 channel 값이 '문자로 나갔다'를 뜻하는지 판정한다(화면 문구 SSOT)."""
    return str(channel or "").upper() in _TEXT_CHANNELS


def confirm_channel(order_id: int) -> dict:
    """발송된 알림톡이 실제 어느 채널로 나갔는지 벤더에 **한 번** 물어 이력에 굳힌다.

    카톡(ATA)으로 접수된 건이 실패하면 벤더가 문자(SMS/LMS)로 대체발송하는데, 그 전환은
    발송 직후엔 알 수 없다. 그래서 발송 1분 뒤에 이 함수가 한 번 조회한다.

    벤더 호출이 성공하면 결과가 비어 있어도 ``channel_checked_at`` 을 남긴다 — '물어봤다'는
    사실 자체가 재조회를 멈추는 기준이다(무한 재시도 방지). 호출이 실패하면 아무것도
    쓰지 않아 다음 기회에 다시 물을 수 있다.

    Args:
        order_id: 주문 id.

    Returns:
        ``{'channel': str | None, 'checked': bool, 'cached': bool, 'error': str | None}``.
        ``checked`` 는 채널 확정이 끝났는지, ``cached`` 는 이전 조회 결과를 그대로 돌려준
        것인지(이번에 벤더를 부르지 않음)를 뜻한다.
    """
    session = _session_factory()
    try:
        order = session.get(Order, order_id)
        if order is None:
            return {"channel": None, "checked": False, "cached": False,
                    "error": "order_not_found"}
        sd = order.structured_data or {}
        history = sd.get("alimtalk_measurement")
        history = history if isinstance(history, dict) else {}
        message_id = history.get("message_id")
        if history.get("error") is not None or not message_id:
            # 실패했거나 벤더 id 가 없는 건은 확인할 채널 자체가 없다.
            return {"channel": None, "checked": False, "cached": False,
                    "error": "nothing_to_confirm"}
        if history.get("channel_checked_at"):
            return {"channel": history.get("channel"), "checked": True,
                    "cached": True, "error": None}
        sent_at = _parse_history_time(history.get("sent_at"))
        if sent_at is not None:
            elapsed = (now_utc_naive() - sent_at).total_seconds()
            if elapsed < ALIMTALK_CHANNEL_PROBE_DELAY_SEC:
                return {"channel": None, "checked": False, "cached": False,
                        "error": "too_early"}
        if not is_configured(resolve_brand(sd)):
            return {"channel": None, "checked": False, "cached": False,
                    "error": "not_configured"}

        try:
            channel = _solapi_lookup_channel(str(message_id))
        except Exception as exc:  # 조회 실패는 삼키지 않고 코드로 표면화(이력 미변경)
            code = _classify_error(exc)
            logger.warning("알림톡 채널 조회 실패 (order_id=%s, error=%s): %s",
                           order_id, code, exc)
            return {"channel": None, "checked": False, "cached": False, "error": code}

        # 벤더 왕복 동안 사용자가 주문을 저장했을 수 있다. 그 사이의 저장본을 덮지 않도록
        # 쓰기 직전에 다시 읽는다(structured_data 전체를 통째로 되쓰는 구조라 필수).
        session.refresh(order)
        now = now_utc_naive()
        next_sd = copy.deepcopy(order.structured_data or {})
        record = next_sd.get("alimtalk_measurement")
        record = record if isinstance(record, dict) else {}
        record["channel"] = channel
        record["channel_checked_at"] = now.isoformat()
        next_sd["alimtalk_measurement"] = record
        order.structured_data = next_sd
        flag_modified(order, "structured_data")
        session.commit()
        logger.info("알림톡 채널 확정 (order_id=%s, channel=%s)", order_id, channel)
        return {"channel": channel, "checked": True, "cached": False, "error": None}
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


def maybe_send_measure_alimtalk(order_id: int) -> None:
    """실측 예약 알림톡 자동 발송 진입점 — 주문 저장 **커밋 후** 호출 전용.

    킬스위치·설정 게이트 → outbox 선점(중복 차단). 실제 Solapi 호출은 SIDEFX
    ``ALIMTALK_SEND`` handler 가 한다. 주문 저장을 막지 않도록 예외는 로그만 남긴다.

    Args:
        order_id: 방금 저장된 주문 id.
    """
    try:
        if not _env_flag("FOMS_ALIMTALK_AUTO_ENABLED") or not is_configured():
            return
        _reserve_dedupe(order_id)
    except Exception:  # 주문 저장 경로 비차단 — 실패는 로그로만 남긴다
        logger.exception("알림톡 자동 발송 처리 실패 (order_id=%s)", order_id)


# ---------------------------------------------------------------------------
# 초안(마법사) 발송 계층 — Order 행 없이 sd 로 발송 (WIZ-SEND-01 T1)
# ---------------------------------------------------------------------------


def build_draft_dedupe_key(draft_key: str) -> str:
    """초안 수동 발송용 멱등키를 만든다.

    수동 발송은 사용자가 누른 만큼 나가야 하므로(스펙 D2) 매번 새 키다 — 주문 정본
    이력으로 승계될 때 자동 발송의 ``build_dedupe_key`` 값과 충돌하지 않도록
    ``draft`` 네임스페이스를 쓴다.

    Args:
        draft_key: ``OrderDraft.draft_key``.

    Returns:
        ``alimtalk:measure:draft:{draft_key}:manual:{uuid4hex}``.
    """
    return f"alimtalk:measure:draft:{draft_key}:manual:{uuid4().hex}"


def build_draft_history_entry(
    *,
    dedupe_key: str | None,
    message_id: str | None,
    error: str | None,
    sent_by: int | None,
    sent_by_name: str | None,
    draft_schedule: str | None,
) -> dict[str, Any]:
    """초안 발송 이력 1건을 **주문 정본 이력 키 + ``draft_schedule``** 로 조립한다.

    제출 시 이 dict 를 새 주문 ``structured_data['alimtalk_measurement']`` 로 무변환
    복사하므로 정본 키(:func:`_record_history`)를 모두 담아야 한다(칩 렌더러가 sd 만
    읽어 그린다). 추가 키는 ``draft_schedule`` 하나뿐이며, 등록 후 자동 발송의
    :func:`_already_sent` 가 "같은 실측 일정 안내를 이미 보냈다"를 판정하는 근거다
    (WIZ-SEND-01 D4' — 주문 id 기반 멱등키 재작성을 대체한다).

    Args:
        dedupe_key: 이 발송의 멱등키.
        message_id: 벤더 메시지 id(실패면 None).
        error: 실패 사유 코드(성공이면 None).
        sent_by: 발송자 user id.
        sent_by_name: 발송 시점의 발송자 표시명(호출자가 조회해 넘긴다).
        draft_schedule: :func:`build_draft_schedule_signature` 로 만든 일정 서명
            (일정이 없으면 None).

    Returns:
        주문 정본 키를 모두 포함하고 ``draft_schedule`` 하나를 더 가진 이력 dict.
    """
    now = now_utc_naive()
    return {
        "draft_schedule": draft_schedule,
        "sent_at": now.isoformat() if error is None else None,
        "message_id": message_id,
        "dedupe_key": dedupe_key,
        "error": error,
        "sent_by": sent_by,
        "sent_by_name": sent_by_name,
        # 주문 경로와 같다 — 발송 직후엔 실제 채널(ATA/문자 대체발송)을 알 수 없다.
        "channel": None,
        "channel_checked_at": None,
    }


def send_alimtalk_for_sd(sd: dict, *, sent_by: int | None, dedupe_key: str) -> dict:
    """``Order`` 행 없이 초안 sd 로 실측 예약 안내를 발송한다.

    **DB 를 전혀 만지지 않는다** — 이력 기록·OrderEvent·감사는 호출자 몫이다
    (초안 이력은 ``OrderDraft.send_history`` 에 굳힌다).

    Args:
        sd: 초안 payload 를 변환한 structured_data.
        sent_by: 수동 발송자 user id(추적용).
        dedupe_key: 호출자가 만든 멱등키(:func:`build_draft_dedupe_key`) — 이력에 남길
            값이며 이 함수는 저장하지 않고 로그에만 쓴다.

    Returns:
        ``{'sent': bool, 'error': str | None, 'message_id': str | None}``.
        자격 미달이면 ``_dispatch`` 를 호출하지 않고 사유 코드를 error 로 돌려준다.
    """
    reason = draft_ineligible_reason(sd)
    if reason is not None:
        logger.info(
            "알림톡 초안 발송 미자격 (sent_by=%s, dedupe_key=%s, reason=%s)",
            sent_by, dedupe_key, reason,
        )
        return {"sent": False, "error": reason, "message_id": None}
    message_id, error = _dispatch(sd)
    logger.info(
        "알림톡 초안 발송 결과 (sent_by=%s, dedupe_key=%s, error=%s)",
        sent_by, dedupe_key, error,
    )
    return {"sent": error is None, "error": error, "message_id": message_id}
