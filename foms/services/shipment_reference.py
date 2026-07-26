"""SHIPMENT-REFERENCE-01: 출고 reference 설정(SystemSetting) 정본 command.

출고 대시보드/실측/도면 표기가 참조하는 **네 개의 reference 리스트**를 하나의
SystemSetting collection(``erp_shipment_settings``)으로 관리한다. 이 모듈은 그 collection
을 갱신하는 유일 command(``UPDATE_SHIPMENT_REFERENCE_LISTS``)의 스키마 검증 + optimistic
lock(If-Match/version) + collection receipt/idempotency + audit(SecurityLog)를 한 곳에
모은다.

**exact four-list schema** (임의 필드 거부):

* ``construction_time``     — 최대 50개, trim string 1..50
* ``drawing_managers``      — 최대 100개, ``{name:1..100, english_name:0..100}``
* ``measurement_managers``  — 최대 100개, ``{name:1..100, phone:0..50, sort_order:int 0..9999}``
* ``site_extra``            — 최대 100개, trim string 1..500

중복 normalized entry 는 422. old ``drawing_manager``(문자열 리스트) + ``drawing_manager_en``
(dict)는 한 object array(``drawing_managers``)로 **safe backfill**(무손실). ``construction_workers``
key 는 이 command 의 소관이 아니므로(worker master 는 CREW-00) request 에 있으면 400 이고,
이미 저장된 ``construction_workers`` 값은 **보존**한다(출고 대시보드가 계속 읽는다).

**경계**: 이 command 는 SystemSetting 만 쓴다. CREW-00 ``installation_workers`` 마스터도,
주문별 ``structured_data.shipment`` 도 쓰지 않는다(construction worker master·per-order write
혼합 금지).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from models import SecurityLog, SystemSetting, SystemSettingReceipt

#: AUTH-01 정책 식별자(STAFF+SHIPMENT 또는 ADMIN/MANAGER). route manifest·UI 은닉·핸들러 공유.
SHIPMENT_REFERENCE_POLICY_ID = "SHIPMENT_REFERENCE"

#: reference collection 을 담는 SystemSetting.setting_key(기존 키 재사용 — 무손실 이관).
SHIPMENT_REFERENCE_SETTING_KEY = "erp_shipment_settings"

#: exact four-list schema 의 최상위 허용 필드(그 외 key 는 400).
_ALLOWED_FIELDS = frozenset(
    {"construction_time", "drawing_managers", "measurement_managers", "site_extra"}
)

_MAX_CONSTRUCTION_TIME = 50
_MAX_DRAWING_MANAGERS = 100
_MAX_MEASUREMENT_MANAGERS = 100
_MAX_SITE_EXTRA = 100

# idempotency replay window(커밋+24시간). purge 는 향후 retention CLI 소관.
IDEMPOTENCY_REPLAY_WINDOW = datetime.timedelta(hours=24)


# --------------------------------------------------------------------------- #
# 오류(각자 HTTP status·code 로 매핑)
# --------------------------------------------------------------------------- #
class ShipmentReferenceError(RuntimeError):
    """SHIPMENT-REFERENCE command 계약 위반의 베이스(호출부가 status_code 로 매핑)."""

    status_code = 400
    error_code = "SHIPMENT_REFERENCE_ERROR"


class ShipmentReferenceSchemaError(ShipmentReferenceError):
    """exact four-list schema 위반(임의 필드·타입·길이·개수·construction_workers). 400."""

    status_code = 400
    error_code = "SHIPMENT_REFERENCE_SCHEMA"


class ShipmentReferenceDuplicateError(ShipmentReferenceError):
    """중복 normalized entry. 422."""

    status_code = 422
    error_code = "SHIPMENT_REFERENCE_DUPLICATE"


class ShipmentReferencePreconditionError(ShipmentReferenceError):
    """If-Match(settings_version) 누락. 428."""

    status_code = 428
    error_code = "PRECONDITION_REQUIRED"


class ShipmentReferenceConflictError(ShipmentReferenceError):
    """If-Match 불일치(stale). 409 + 현재 version 동봉."""

    status_code = 409
    error_code = "REVISION_CONFLICT"

    def __init__(self, current_version: int) -> None:
        super().__init__(f"settings_version mismatch; current={current_version}")
        self.current_version = current_version


class ShipmentReferenceIdempotencyExpiredError(ShipmentReferenceError):
    """같은 idempotency key 가 24시간 replay window 를 넘김. 409."""

    status_code = 409
    error_code = "IDEMPOTENCY_KEY_EXPIRED"


class ShipmentReferenceIdempotencyConflictError(ShipmentReferenceError):
    """같은 key 를 다른 request_hash 로 재사용(replay 아님). 409."""

    status_code = 409
    error_code = "IDEMPOTENCY_KEY_CONFLICT"


# --------------------------------------------------------------------------- #
# 정규화(safe backfill) — 마이그레이션·loader·command 가 공유
# --------------------------------------------------------------------------- #
def normalize_drawing_managers(raw: Any) -> list[dict[str, str]]:
    """old drawing 필드/신 스키마를 canonical ``[{name, english_name}]`` 로 정규화한다.

    허용 입력: 신 스키마 list ``[{name, english_name}]``, 또는 old 문자열 리스트
    ``["이름"]``(english_name 없음). 빈 name 항목·중복 name 은 첫 항목만 남긴다.

    Args:
        raw: 정규화 대상(list). 그 외 타입은 빈 list.

    Returns:
        ``{"name": str, "english_name": str}`` 리스트(name 기준 dedupe).
    """
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    seen: set[str] = set()
    for entry in raw:
        if isinstance(entry, dict):
            name = str(entry.get("name") or "").strip()
            english = str(entry.get("english_name") or entry.get("name_en") or "").strip()
        else:
            name = str(entry).strip()
            english = ""
        if not name or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "english_name": english})
    return out


def backfill_drawing_managers_from_legacy(
    drawing_manager: Any, drawing_manager_en: Any
) -> list[dict[str, str]]:
    """old ``drawing_manager``(list) + ``drawing_manager_en``(dict)를 한 object array 로 합친다.

    마이그레이션의 무손실 backfill 정본. 이름 순서는 ``drawing_manager`` 를 따르고 영문명은
    ``drawing_manager_en`` 매핑에서 채운다. ``drawing_manager`` 에 없지만 매핑에만 있는
    이름도 유실 없이 뒤에 덧붙인다.

    Args:
        drawing_manager: 한글 이름 문자열 리스트(old).
        drawing_manager_en: ``{한글명: 영문명}`` dict(old).

    Returns:
        canonical ``[{name, english_name}]``.
    """
    en_map = drawing_manager_en if isinstance(drawing_manager_en, dict) else {}
    names: list[str] = []
    if isinstance(drawing_manager, list):
        names = [str(n).strip() for n in drawing_manager if str(n).strip()]
    seen = set(names)
    for extra in en_map:
        key = str(extra).strip()
        if key and key not in seen:
            seen.add(key)
            names.append(key)
    return normalize_drawing_managers(
        [{"name": n, "english_name": str(en_map.get(n) or "").strip()} for n in names]
    )


# --------------------------------------------------------------------------- #
# exact four-list schema 검증
# --------------------------------------------------------------------------- #
def _trimmed_string_list(raw: Any, *, field: str, max_items: int, max_len: int) -> list[str]:
    """trim string 리스트를 검증한다(개수/길이/타입=400, 중복=422)."""
    if not isinstance(raw, list):
        raise ShipmentReferenceSchemaError(f"{field}는 리스트여야 합니다.")
    if len(raw) > max_items:
        raise ShipmentReferenceSchemaError(f"{field}는 최대 {max_items}개입니다.")
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        if isinstance(value, dict):  # site_extra 폼 왕복 호환({text}) 허용.
            value = value.get("text", "")
        text = str(value).strip()
        if not text:
            continue
        if len(text) > max_len:
            raise ShipmentReferenceSchemaError(f"{field} 항목은 {max_len}자 이하여야 합니다.")
        if text in seen:
            raise ShipmentReferenceDuplicateError(f"{field}에 중복 항목이 있습니다: {text}")
        seen.add(text)
        out.append(text)
    return out


def _validate_drawing_managers(raw: Any) -> list[dict[str, str]]:
    """drawing_managers 검증: 최대 100, ``{name:1..100, english_name:0..100}``, name 중복 422."""
    if not isinstance(raw, list):
        raise ShipmentReferenceSchemaError("drawing_managers는 리스트여야 합니다.")
    if len(raw) > _MAX_DRAWING_MANAGERS:
        raise ShipmentReferenceSchemaError(f"drawing_managers는 최대 {_MAX_DRAWING_MANAGERS}개입니다.")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in raw:
        if isinstance(entry, dict):
            name = str(entry.get("name") or "").strip()
            english = str(entry.get("english_name") or entry.get("name_en") or "").strip()
        else:
            name = str(entry).strip()
            english = ""
        if not name:
            continue
        if len(name) > 100 or len(english) > 100:
            raise ShipmentReferenceSchemaError("drawing manager 이름/영문명은 100자 이하여야 합니다.")
        if name in seen:
            raise ShipmentReferenceDuplicateError(f"drawing_managers에 중복 이름이 있습니다: {name}")
        seen.add(name)
        out.append({"name": name, "english_name": english})
    return out


def _validate_measurement_managers(raw: Any) -> list[dict[str, Any]]:
    """measurement_managers 검증: 최대 100, ``{name:1..100, phone:0..50, sort_order:0..9999}``."""
    if not isinstance(raw, list):
        raise ShipmentReferenceSchemaError("measurement_managers는 리스트여야 합니다.")
    if len(raw) > _MAX_MEASUREMENT_MANAGERS:
        raise ShipmentReferenceSchemaError(
            f"measurement_managers는 최대 {_MAX_MEASUREMENT_MANAGERS}개입니다."
        )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw:
        name = str((entry.get("name") if isinstance(entry, dict) else entry) or "").strip()
        if not name:
            continue
        phone = str((entry.get("phone") if isinstance(entry, dict) else "") or "").strip()
        sort_order = _coerce_sort_order(entry.get("sort_order") if isinstance(entry, dict) else None)
        if len(name) > 100 or len(phone) > 50:
            raise ShipmentReferenceSchemaError("measurement manager 이름/전화는 길이 제한을 넘습니다.")
        if name in seen:
            raise ShipmentReferenceDuplicateError(f"measurement_managers에 중복 이름이 있습니다: {name}")
        seen.add(name)
        out.append({"name": name, "phone": phone, "sort_order": sort_order})
    return out


def _coerce_sort_order(value: Any) -> int:
    """sort_order 를 0..9999 정수로 강제한다(비수/범위밖은 400)."""
    if value in (None, ""):
        return 999
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ShipmentReferenceSchemaError("sort_order는 정수여야 합니다.")
    if n < 0 or n > 9999:
        raise ShipmentReferenceSchemaError("sort_order는 0..9999 범위여야 합니다.")
    return n


def validate_reference_payload(payload: Any) -> dict[str, Any]:
    """exact four-list schema 로 request payload 를 검증·정규화한다.

    Args:
        payload: request JSON body(``settings_version`` 등 제어 필드는 호출부가 이미 분리).

    Returns:
        canonical dict ``{construction_time, drawing_managers, measurement_managers, site_extra}``.

    Raises:
        ShipmentReferenceSchemaError: 임의 필드·``construction_workers``·타입/길이/개수 위반(400).
        ShipmentReferenceDuplicateError: 중복 normalized entry(422).
    """
    if not isinstance(payload, dict):
        raise ShipmentReferenceSchemaError("payload는 객체여야 합니다.")
    if "construction_workers" in payload:
        raise ShipmentReferenceSchemaError(
            "construction_workers는 이 설정의 소관이 아닙니다(작업자 마스터는 CREW 관리)."
        )
    unknown = set(payload) - _ALLOWED_FIELDS
    if unknown:
        raise ShipmentReferenceSchemaError(f"허용되지 않은 필드: {sorted(unknown)}")
    return {
        "construction_time": _trimmed_string_list(
            payload.get("construction_time", []),
            field="construction_time", max_items=_MAX_CONSTRUCTION_TIME, max_len=50,
        ),
        "drawing_managers": _validate_drawing_managers(payload.get("drawing_managers", [])),
        "measurement_managers": _validate_measurement_managers(
            payload.get("measurement_managers", [])
        ),
        "site_extra": _trimmed_string_list(
            payload.get("site_extra", []),
            field="site_extra", max_items=_MAX_SITE_EXTRA, max_len=500,
        ),
    }


# --------------------------------------------------------------------------- #
# legacy projection(read 소비처 무회귀) — loader 가 사용
# --------------------------------------------------------------------------- #
def project_to_legacy_shape(raw: Any) -> dict[str, Any]:
    """저장된 collection(신/구 어느 형태든)을 legacy loader 출력 스키마로 투영한다.

    read 소비처(도면 마법사·견적·지도·대시보드 등)는 ``drawing_manager``(list)+
    ``drawing_manager_en``(dict)+``measurement_manager``+``construction_workers`` 를 읽는다.
    canonical 저장은 ``drawing_managers``/``measurement_managers`` 이므로 여기서 legacy 로
    되돌린다(저장 형태에 무관하게 동일 출력 → 소비처 무회귀).

    Args:
        raw: ``SystemSetting.setting_value``(dict) 또는 falsy.

    Returns:
        ``{construction_time, drawing_manager, drawing_manager_en, measurement_managers 원본,
        construction_workers 원본, site_extra}`` — measurement/worker 정규화는 loader 가 수행.
    """
    data = raw if isinstance(raw, dict) else {}
    if isinstance(data.get("drawing_managers"), list):
        managers = normalize_drawing_managers(data["drawing_managers"])
    else:
        managers = backfill_drawing_managers_from_legacy(
            data.get("drawing_manager"), data.get("drawing_manager_en")
        )
    drawing_manager = [m["name"] for m in managers]
    drawing_manager_en = {m["name"]: m["english_name"] for m in managers if m["english_name"]}
    measurement = data.get("measurement_managers")
    if not isinstance(measurement, list):
        measurement = data.get("measurement_manager", [])
    return {
        "construction_time": data.get("construction_time", []),
        "drawing_manager": drawing_manager,
        "drawing_manager_en": drawing_manager_en,
        "measurement_manager": measurement,
        "construction_workers": data.get("construction_workers", []),
        "site_extra": data.get("site_extra", []),
    }


# --------------------------------------------------------------------------- #
# command: version(If-Match) + receipt/idempotency + audit 를 한 transaction 에
# --------------------------------------------------------------------------- #
def request_hash_for(payload: Any) -> str:
    """canonical payload 의 sha256 hex(same-key/different-hash 감지·receipt 저장용)."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _lookup_receipt(
    session: Session, actor_user_id: int, idempotency_key: str
) -> Optional[SystemSettingReceipt]:
    return (
        session.query(SystemSettingReceipt)
        .filter(
            SystemSettingReceipt.actor_user_id == actor_user_id,
            SystemSettingReceipt.policy_id == SHIPMENT_REFERENCE_POLICY_ID,
            SystemSettingReceipt.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


class ReferenceUpdateResult:
    """command 결과(호출부가 HTTP 응답으로 변환). ``replayed`` 면 business write 미수행."""

    def __init__(self, *, version: int, receipt_id: str, body: dict, replayed: bool) -> None:
        self.version = version
        self.receipt_id = receipt_id
        self.body = body
        self.replayed = replayed


def update_shipment_reference_lists(
    session: Session,
    *,
    actor_user_id: int,
    payload: Any,
    if_match_version: Optional[int],
    idempotency_key: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> ReferenceUpdateResult:
    """reference 네 리스트를 optimistic lock + receipt + audit 로 원자 갱신한다.

    호출부가 ``session.commit()`` 을 소유한다. 순서: schema 검증 → SystemSetting row
    ``FOR UPDATE`` 잠금 → idempotency 조회(replay) → If-Match(version) 검증 → canonical
    저장(construction_workers 보존) → version bump → receipt/SecurityLog 기록.

    Args:
        session: business transaction 세션(커밋 미수행).
        actor_user_id: 요청 actor(receipt 소유자·audit 주체).
        payload: request body(제어 필드 제외한 four-list).
        if_match_version: client 가 보낸 현재 version(None 이면 428).
        idempotency_key: UUID 문자열(≤64자) 또는 None(dedupe 안 함).
        now: 테스트용 시각 주입(기본 now_utc_naive()).

    Returns:
        ReferenceUpdateResult(version/receipt_id/body/replayed).

    Raises:
        ShipmentReferenceSchemaError/DuplicateError: 스키마/중복 위반(400/422).
        ShipmentReferencePreconditionError: If-Match 누락(428).
        ShipmentReferenceConflictError: If-Match 불일치(409, 현재 version 동봉).
        ShipmentReferenceIdempotency*Error: replay window 초과/hash 불일치(409).
    """
    canonical = validate_reference_payload(payload)  # 400/422 먼저(잠금 전).
    req_hash = request_hash_for(canonical)
    now = now or now_utc_naive()

    setting = (
        session.query(SystemSetting)
        .filter(SystemSetting.setting_key == SHIPMENT_REFERENCE_SETTING_KEY)
        .with_for_update()
        .one_or_none()
    )
    current_version = setting.version if setting is not None else 0

    if idempotency_key is not None:
        existing = _lookup_receipt(session, actor_user_id, idempotency_key)
        if existing is not None:
            if now > existing.expires_at:
                raise ShipmentReferenceIdempotencyExpiredError("idempotency key expired.")
            if existing.request_hash != req_hash:
                raise ShipmentReferenceIdempotencyConflictError("idempotency key reused.")
            return ReferenceUpdateResult(
                version=existing.resulting_version,
                receipt_id=str(existing.read_receipt_id),
                body=existing.response_body,
                replayed=True,
            )

    if if_match_version is None:
        raise ShipmentReferencePreconditionError("If-Match(settings_version)가 필요합니다.")
    if if_match_version != current_version:
        raise ShipmentReferenceConflictError(current_version)

    setting = _write_canonical(session, setting, canonical)
    setting.version = current_version + 1

    receipt_id = str(uuid.uuid4())
    body = {"success": True, "data": {"version": setting.version, "settings": canonical}}
    receipt = SystemSettingReceipt(
        read_receipt_id=receipt_id,
        actor_user_id=actor_user_id,
        setting_key=SHIPMENT_REFERENCE_SETTING_KEY,
        policy_id=SHIPMENT_REFERENCE_POLICY_ID,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
        response_status=200,
        response_body=body,
        resulting_version=setting.version,
        expires_at=now + IDEMPOTENCY_REPLAY_WINDOW,
    )
    session.add(receipt)
    session.add(SecurityLog(
        user_id=actor_user_id,
        message=f"SHIPMENT_REFERENCE_UPDATE key={SHIPMENT_REFERENCE_SETTING_KEY} version={setting.version}",
    ))
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        if idempotency_key is None:
            raise
        winner = _lookup_receipt(session, actor_user_id, idempotency_key)
        if winner is None:
            raise
        return ReferenceUpdateResult(
            version=winner.resulting_version, receipt_id=str(winner.read_receipt_id),
            body=winner.response_body, replayed=True,
        )
    return ReferenceUpdateResult(
        version=setting.version, receipt_id=receipt_id, body=body, replayed=False,
    )


def _write_canonical(
    session: Session, setting: Optional[SystemSetting], canonical: dict[str, Any]
) -> SystemSetting:
    """canonical four-list 를 setting_value 에 병합 저장한다(construction_workers 보존).

    기존 row 가 없으면 생성한다(version=0 baseline → 호출부가 1 로 bump). 이미 저장된
    ``construction_workers`` 값은 그대로 둔다(worker master 는 CREW-00; 이 command 는 write
    하지 않지만 read 소비처를 위해 유실하지 않는다).
    """
    import copy

    from sqlalchemy.orm.attributes import flag_modified

    if setting is None:
        setting = SystemSetting(
            setting_key=SHIPMENT_REFERENCE_SETTING_KEY, version=0,
            description="ERP 출고 reference 리스트(SHIPMENT-REFERENCE-01)",
        )
        session.add(setting)
        session.flush()  # FOR UPDATE 이후 신규 row 를 즉시 물화(version bump 대상 확보).
    value = copy.deepcopy(setting.setting_value if isinstance(setting.setting_value, dict) else {})
    value.update(canonical)
    value.pop("drawing_manager", None)  # old drawing 필드는 canonical 로 대체(중복 제거).
    value.pop("drawing_manager_en", None)
    value.pop("measurement_manager", None)
    setting.setting_value = value
    flag_modified(setting, "setting_value")
    return setting


__all__ = [
    "SHIPMENT_REFERENCE_POLICY_ID",
    "SHIPMENT_REFERENCE_SETTING_KEY",
    "ShipmentReferenceError",
    "ShipmentReferenceSchemaError",
    "ShipmentReferenceDuplicateError",
    "ShipmentReferencePreconditionError",
    "ShipmentReferenceConflictError",
    "ShipmentReferenceIdempotencyExpiredError",
    "ShipmentReferenceIdempotencyConflictError",
    "ReferenceUpdateResult",
    "normalize_drawing_managers",
    "backfill_drawing_managers_from_legacy",
    "validate_reference_payload",
    "project_to_legacy_shape",
    "request_hash_for",
    "update_shipment_reference_lists",
]
