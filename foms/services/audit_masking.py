"""감사 기록 고객 개인정보 가림 (AUDIT-PII-00).

``security_logs`` 의 사람용 문장(``message``)과 부가정보(``detail``)에서 **고객**의 전화번호·
주소·이름을 가린다. 호출부(170여 곳)를 하나씩 고치지 않고, 행이 실제로 저장되는 두 길목에서만
:func:`mask_security_log_values` 를 부른다.

* ORM 길 — ``models.py`` 의 ``SecurityLog`` ``before_insert``/``before_update`` 훅.
  ``log_access`` 와 ``db.add(SecurityLog(...))`` 직접 쓰기가 모두 여기를 지난다.
* Core 길 — :func:`foms.services.audit_writer.write_security_log_detached`.

이 두 길을 피해 쓰는 곳(raw SQL·대량 insert)은 ``tests/domains/test_audit_log_masking.py`` 의
래칫이 잡는다. 설계: ``docs/specs/2026-10-19-audit-log-masking_SPEC.md``.

가림 규칙: 전화번호는 가운데 자리(알림톡 로그와 같은 :func:`kakao_alimtalk._mask_phone`),
주소는 시·도 + 시·군·구까지, 고객명은 성(첫 글자)만. 주문 번호·바뀐 칸 라벨·직원/협력사/발주사
정보는 남긴다. 직원 대상 행(``target_type='user'`` 등)은 손대지 않는다. 같은 값을 두 번 가려도
결과가 같다(멱등). 가림이 실패하면 원문 대신 표식을 저장한다(개인정보 쪽으로 안전한 실패).
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any, Mapping

from foms.services.audit_message_display import FIELD_LABELS, PATH_LABELS
from foms.services.kakao_alimtalk import _mask_phone

logger = logging.getLogger(__name__)

__all__ = [
    "MASK",
    "MASK_FAILED_MESSAGE",
    "mask_address",
    "mask_person_name",
    "mask_phone_text",
    "mask_security_log_values",
]

MASK = "***"
MASK_FAILED_MESSAGE = "(감사 문장 가림 실패 — 원문은 저장하지 않았다)"

KIND_NAME = "name"
KIND_PHONE = "phone"
KIND_ADDRESS = "address"
KIND_ADDRESS_DETAIL = "address_detail"
_KIND_PROTECTED = "protected"

#: 직원·협력사 계정이 대상인 행 — 고객 정보가 아니므로 통째로 건너뛴다(직원 발신번호 변경 등).
STAFF_TARGET_TYPES = frozenset({"user", "password_reset_request", "partner_org"})

#: 고객 칸(평면 컬럼명·structured 경로) → 종류. 문장 라벨은 표시 SSOT 에서 이 키로 읽는다.
CUSTOMER_FIELD_KINDS: dict[str, str] = {
    "customer_name": KIND_NAME,
    "phone": KIND_PHONE,
    "address": KIND_ADDRESS,
    "parties.customer.name": KIND_NAME,
    "parties.customer.phone": KIND_PHONE,
    "parties.customer.phone2": KIND_PHONE,
    "parties.buyer.name": KIND_NAME,
    "parties.buyer.phone": KIND_PHONE,
    "site.address_full": KIND_ADDRESS,
    "site.address_detail": KIND_ADDRESS_DETAIL,
}

#: ``detail`` 에서 값 자체가 고객 정보인 키 → 종류. ``to`` 는 넣지 않는다 — 정산 내보내기의
#: ``from``/``to`` 날짜처럼 다른 뜻으로도 쓰인다(공유 발송 ``to`` 는 호출부가 이미 가리고,
#: 가리지 않은 번호가 와도 아래 일괄 전화번호 가림이 잡는다).
CUSTOMER_DETAIL_KEYS: dict[str, str] = {
    "customer_name": KIND_NAME,
    "buyer_name": KIND_NAME,
    "phone": KIND_PHONE,
    "phone2": KIND_PHONE,
    "customer_phone": KIND_PHONE,
    "to_phone": KIND_PHONE,
    "address": KIND_ADDRESS,
    "customer_address": KIND_ADDRESS,
    "address_full": KIND_ADDRESS,
    "address_detail": KIND_ADDRESS_DETAIL,
}

#: 고객이 아닌 연락처 칸(발주사 = 라홈·하우드 같은 회사) — 일괄 전화번호 가림에서 뺀다.
NON_CUSTOMER_CONTACT_FIELDS = frozenset({"parties.orderer.phone"})

#: 문장 꼬리말(``describe_action(note=…)``)이 곧 고객명인 행위.
NOTE_IS_CUSTOMER_NAME_ACTIONS = frozenset({"ESTIMATE_SAVED"})

#: 변경 dict(``{path|field, before, after}``)에서 값을 담는 키.
_VALUE_KEYS = frozenset({"before", "after", "old", "new", "value"})

#: 식별자 키 — 우연히 숫자 모양이 겹쳐도 건드리면 감사 추적이 끊긴다.
_ID_KEYS = frozenset({"storage_key", "key", "change_set", "draft_key", "external_id", "uid",
                      "path", "path_template", "field", "url", "action", "op"})
_ID_KEY_SUFFIXES = ("_id", "_ids", "_key", "_keys", "_uid", "_url")

#: 빈 값 표기 — 가리지 않는다(바뀌기 전에 값이 없었다는 사실 자체가 감사 정보다).
_PLACEHOLDERS = frozenset({"", "-", "(없음)", "(지움)", "없음", "미지정", "Unknown"})
_CONTENT_MODIFIED_MARK = "(내용 수정)"

# --- 전화번호 -------------------------------------------------------------------------
# 휴대 01X · 서울 02 · 지역 031~064 · 인터넷 070 · 안심번호 0502~0508. 대표번호(1566-…)는
# 0 으로 시작하지 않아 걸리지 않는다. 앞뒤가 숫자·별표면 더 긴 식별자의 일부라 건너뛴다.
_PHONE_PREFIX = r"0(?:1[016789]|2|[3-6][1-5]|70|50[2-8])"
_PHONE_RE = re.compile(rf"(?<![\d*]){_PHONE_PREFIX}[-.\s]?\d{{3,4}}[-.\s]?\d{{4}}(?![\d*])")
#: 문장 요약(60자 말줄임)에 잘린 번호 — ``010-1234-56…``.
_PHONE_CUT_RE = re.compile(rf"(?<![\d*]){_PHONE_PREFIX}[-.\s]?\d[\d\-.\s]{{2,9}}(?=…)")

# --- 주소 -----------------------------------------------------------------------------
_REGION1 = (r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주|"
            r"[가-힣]{1,8}(?:특별자치시|특별자치도|특별시|광역시|도|시))")
_REGION2 = r"(?:[가-힣]{1,8}(?:시|군|구))"
_REGION1_RE = re.compile(_REGION1)
_REGION2_RE = re.compile(_REGION2)
_ROAD = r"[가-힣0-9]{1,20}(?:대로|로|길|동|읍|면|리|가)(?![가-힣])"
_FREE_ADDRESS_RE = re.compile(
    rf"(?<![가-힣])(?P<keep>{_REGION1}\s+{_REGION2}(?:\s+{_REGION2})?)\s+"
    rf"(?P<rest>(?:{_ROAD}(?:\s*\d+(?:-\d+)?(?:번지)?)?"
    r"(?:\s*,?\s*[가-힣A-Za-z0-9-]{0,10}\d[가-힣A-Za-z0-9-]{0,10}(?:동|호|층)){0,3}"
    r"(?:\s*\([^()\n]{0,40}\))?"
    r"|[^\s…]{1,20}…))"
)

# --- 문장 라벨 구간 ---------------------------------------------------------------------
_LABEL_LEFT = frozenset(" :;·|—(\n,")
_SEGMENT_END_RE = re.compile(r";\s|\s·\s|\s\|\s|\n|\s외\s\d+건")
_ARROW_RE = re.compile(r"(\s*(?:→|⇒|->)\s*)")
#: ``주문 #4109 (홍길동)`` — 표시 SSOT ``order_label`` 형식(``지방 주문``·``자가실측 주문`` 포함).
_ORDER_LABEL_NAME_RE = re.compile(
    r"(?P<head>주문 #\d+ \()(?P<name>(?:[^()\n]|\([^()\n]*\)){1,60}?)(?P<tail>\))")


def _mask_digits(digits: str) -> str:
    """숫자열 전화번호를 가린다 — 알림톡 로그·공유 감사 ``to`` 와 같은 함수를 그대로 쓴다."""
    return _mask_phone(digits)


def mask_phone_text(text: str) -> str:
    """문자열 안의 전화번호 모양을 전부 가운데 자리 가림으로 바꾼다.

    :param text: 임의 문자열.
    :return: ``010****5678`` 형태로 바뀐 문자열(번호가 없으면 그대로).
    """
    text = _PHONE_RE.sub(lambda m: _mask_digits(re.sub(r"\D", "", m.group(0))), text)
    return _PHONE_CUT_RE.sub(lambda m: m.group(0)[:3] + re.sub(r"\d", "*", m.group(0)[3:]), text)


def _mask_phone_value(text: str) -> str:
    """고객 전화 칸으로 확실한 값 — 모양이 낯설어도(국가번호 등) 뒤 4자리만 남긴다."""
    masked = mask_phone_text(text)
    if masked != text or "*" in text or sum(ch.isdigit() for ch in text) < 7:
        return masked  # 이미 가린 값(``010****5678``)은 다시 손대지 않는다(멱등).
    seen, out = 0, []
    for ch in reversed(text):
        if ch.isdigit():
            seen += 1
            out.append(ch if seen <= 4 else "*")
        else:
            out.append(ch)
    return "".join(reversed(out))


def mask_person_name(value: str) -> str:
    """고객명을 성(첫 글자)만 남기고 가린다 — ``홍길동`` → ``홍**``.

    :param value: 이름 문자열.
    :return: 가린 이름(빈 값 표기는 그대로).
    """
    text = value.strip()
    if text in _PLACEHOLDERS:
        return value
    return "*" if len(text) == 1 else text[0] + "*" * (len(text) - 1)


def mask_address(value: str) -> str:
    """주소를 시·도 + 시·군·구까지만 남긴다 — ``서울특별시 강남구 테헤란로 1`` → ``서울특별시 강남구 ***``.

    :param value: 주소 문자열(고객 주소 칸으로 확실한 값).
    :return: 가린 주소. 시·도/시·군·구로 시작하지 않으면 통째로 ``***``.
    """
    text = value.strip()
    if text in _PLACEHOLDERS:
        return value
    tokens = text.split()
    keep: list[str] = []
    for token in tokens[:3]:
        if (not keep and _REGION1_RE.fullmatch(token)) or _REGION2_RE.fullmatch(token):
            keep.append(token)
        else:
            break
    if len(keep) == len(tokens):
        return text  # 시·구만 적힌 값 — 가릴 상세가 없다.
    return " ".join([*keep, MASK]) if keep else MASK


def _mask_by_kind(value: str, kind: str) -> str:
    """종류에 맞는 가림을 적용한다(빈 값 표기·``(내용 수정)`` 꼬리표는 보존)."""
    core = value.strip()
    suffix = ""
    if core.endswith(_CONTENT_MODIFIED_MARK):
        core, suffix = core[: -len(_CONTENT_MODIFIED_MARK)], _CONTENT_MODIFIED_MARK
    if core.strip() in _PLACEHOLDERS:
        return value
    if kind == KIND_NAME:
        masked = mask_person_name(core)
    elif kind == KIND_PHONE:
        masked = _mask_phone_value(core)
    elif kind == KIND_ADDRESS:
        masked = mask_address(core)
    else:
        masked = MASK
    lead = value[: len(value) - len(value.lstrip())]
    trail = value[len(value.rstrip()):]
    return f"{lead}{masked}{suffix}{trail}"


def _mask_free_text(text: str, names: tuple[str, ...]) -> str:
    """자유 글 — 알려진 고객명·``주문 #N (이름)``·주소 모양·전화번호 모양을 가린다."""
    for name in names:
        text = text.replace(name, mask_person_name(name))

    def _order_name(match: re.Match[str]) -> str:
        name = match.group("name")
        if not re.search(r"[가-힣A-Za-z]", name):
            return match.group(0)  # 날짜·숫자 괄호는 이름이 아니다.
        return f"{match.group('head')}{mask_person_name(name)}{match.group('tail')}"

    text = _ORDER_LABEL_NAME_RE.sub(_order_name, text)
    text = _FREE_ADDRESS_RE.sub(lambda m: f"{m.group('keep')} {MASK}", text)
    return mask_phone_text(text)


@lru_cache(maxsize=1)
def _label_tables() -> tuple[dict[str, str], re.Pattern[str]]:
    """(라벨 → 종류, 알려진 라벨 전부를 긴 것부터 고르는 정규식)을 표시 SSOT 에서 만든다."""
    def label_of(key: str) -> str | None:
        return PATH_LABELS.get(key) or FIELD_LABELS.get(key)

    kinds: dict[str, str] = {}
    for key, kind in CUSTOMER_FIELD_KINDS.items():
        if label_of(key):
            kinds[label_of(key)] = kind
    for key in NON_CUSTOMER_CONTACT_FIELDS:
        if label_of(key):
            kinds[label_of(key)] = _KIND_PROTECTED
    known = sorted(set(FIELD_LABELS.values()) | set(PATH_LABELS.values()), key=len, reverse=True)
    return kinds, re.compile("|".join(re.escape(label) for label in known if label))


def _segment_after(text: str, j: int) -> tuple[int, int] | None:
    """라벨 끝(``j``) 뒤 값 구간. ``라벨: 값`` 또는 ``라벨 이전 → 이후``(화살표 필수)만 인정한다."""
    if j >= len(text) or text[j] not in ": ":
        return None
    start = j + 1
    while text[j] == ":" and start < len(text) and text[start] == " ":
        start += 1
    match = _SEGMENT_END_RE.search(text, start)
    end = match.start() if match else len(text)
    if start >= end or (text[j] == " " and not _ARROW_RE.search(text[start:end])):
        return None
    return start, end


def _mask_message(text: str, names: tuple[str, ...]) -> str:
    """문장을 라벨 구간과 자유 글로 나눠 각각 가린다."""
    kinds, known = _label_tables()
    out: list[str] = []
    free_start = i = 0
    while i < len(text):
        if i and text[i - 1] not in _LABEL_LEFT:
            i += 1
            continue
        hit = known.match(text, i)  # 긴 라벨부터 시도 — ``주문자 연락처`` 가 ``주문자명`` 보다 먼저.
        label = hit.group(0) if hit else None
        segment = _segment_after(text, i + len(label)) if label else None
        if segment is None:
            i += len(label) if label else 1
            continue
        start, end = segment
        kind = kinds.get(label)
        if kind is not None:
            value = text[start:end]
            if kind != _KIND_PROTECTED:
                value = "".join(part if idx % 2 else _mask_by_kind(part, kind)
                                for idx, part in enumerate(_ARROW_RE.split(value)))
            out.append(_mask_free_text(text[free_start:start], names))
            out.append(value)
            free_start = end
        i = end  # 다른 칸의 값은 통째로 자유 글 — 그 안의 낱말을 라벨로 다시 읽지 않는다.
    out.append(_mask_free_text(text[free_start:], names))
    return "".join(out)


def _is_id_key(key: Any) -> bool:
    return isinstance(key, str) and (key in _ID_KEYS or key.endswith(_ID_KEY_SUFFIXES))


def _collect_names(node: Any, names: set[str]) -> None:
    """detail 에서 고객명 원문을 모은다(문장·다른 값에서 같은 이름을 가리기 위해)."""
    if isinstance(node, Mapping):
        field = node.get("path") or node.get("field")
        field_kind = CUSTOMER_FIELD_KINDS.get(field) if isinstance(field, str) else None
        for key, value in node.items():
            kind = field_kind if key in _VALUE_KEYS else CUSTOMER_DETAIL_KEYS.get(key)
            if kind == KIND_NAME and isinstance(value, str):
                name = value.strip()
                if len(name) >= 2 and name not in _PLACEHOLDERS and re.search(r"[가-힣A-Za-z]", name):
                    names.add(name)
            else:
                _collect_names(value, names)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _collect_names(value, names)


def _mask_detail(node: Any, names: tuple[str, ...], kind: str | None = None) -> Any:
    """detail 을 새 객체로 가린다(원본 dict 는 건드리지 않는다)."""
    if isinstance(node, Mapping):
        field = node.get("path") or node.get("field")
        field_kind = CUSTOMER_FIELD_KINDS.get(field) if isinstance(field, str) else None
        if isinstance(field, str) and field in NON_CUSTOMER_CONTACT_FIELDS:
            field_kind = _KIND_PROTECTED
        out: dict[Any, Any] = {}
        for key, value in node.items():
            if key in _VALUE_KEYS and field_kind:
                out[key] = _mask_detail(value, names, field_kind)
            elif key in CUSTOMER_DETAIL_KEYS:
                out[key] = _mask_detail(value, names, CUSTOMER_DETAIL_KEYS[key])
            elif _is_id_key(key):
                out[key] = value
            else:
                out[key] = _mask_detail(value, names)
        return out
    if isinstance(node, (list, tuple)):
        return [_mask_detail(value, names, kind) for value in node]
    if not isinstance(node, str):
        return node
    if kind == _KIND_PROTECTED:
        return node
    if kind is not None:
        return _mask_by_kind(node, kind)
    return _mask_free_text(node, names)


def _mask_note_name(message: str, action: str | None) -> str:
    """``견적 #12 — 견적 저장: 홍길동`` 처럼 꼬리말이 고객명인 행위의 꼬리말을 가린다."""
    if action not in NOTE_IS_CUSTOMER_NAME_ACTIONS or ": " not in message:
        return message
    head, _, note = message.rpartition(": ")
    return f"{head}: {mask_person_name(note)}"


def mask_security_log_values(
    message: Any,
    detail: Any,
    *,
    target_type: str | None = None,
    action: str | None = None,
) -> tuple[Any, Any]:
    """감사 행 1건의 ``message``·``detail`` 에서 고객 전화·주소·이름을 가린다(저장 직전 한 지점).

    :param message: 저장할 사람용 문장.
    :param detail: 저장할 구조화 부가정보(dict·None·기타).
    :param target_type: 행위 대상 종류 — 직원 대상(:data:`STAFF_TARGET_TYPES`)이면 건너뛴다.
    :param action: 행위 종류 — 꼬리말이 고객명인 행위 판정에 쓴다.
    :return: ``(가린 문장, 가린 detail)``. 예외를 밖으로 던지지 않는다 — 실패하면
        원문 대신 :data:`MASK_FAILED_MESSAGE` 와 ``{"mask_failed": True}`` 를 돌려준다.
    """
    if target_type in STAFF_TARGET_TYPES:
        return message, detail
    try:
        found: set[str] = set()
        _collect_names(detail, found)
        names = tuple(sorted(found, key=len, reverse=True))
        masked_detail = _mask_detail(detail, names) if detail is not None else None
        masked_message = message
        if isinstance(message, str):
            masked_message = _mask_message(_mask_note_name(message, action), names)
        return masked_message, masked_detail
    except Exception:  # noqa: BLE001 — 가림 오류가 업무 트랜잭션을 죽이거나 원문을 흘리면 안 된다.
        logger.warning("[AuditMasking] 감사 행 가림 실패 — 원문 대신 표식을 저장한다.", exc_info=True)
        return MASK_FAILED_MESSAGE, {"mask_failed": True}
