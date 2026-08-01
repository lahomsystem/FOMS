"""도면 마법사 사용자 프리셋: 도면팀 공유 전역 저장(SystemSetting).

기본 프리셋(SR/EP/DOOR/옷봉)은 프론트 코드 상수로 유지하고, 사용자가 추가한
텍스트 스니펫만 SystemSetting 키 ``drawing_wizard_presets`` 에 **전역** 저장한다.
여러 도면 담당자가 표준 컷리스트 템플릿을 공유한다(주문 무관 전역 자원).

값 스키마: ``[{"label": str, "text": str}]`` (라벨=메뉴 표기, text=삽입 본문).
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import uuid
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.main.db import db_session
from foms.persistence.main.models import SystemSetting
from foms.services.datetime_kst import now_utc_naive
from models import SecurityLog, SystemSettingReceipt

__all__ = [
    "DRAWING_WIZARD_PRESETS_KEY",
    "MAX_PRESETS",
    "MAX_LABEL_LEN",
    "MAX_TEXT_LEN",
    "WIZ_PRESET_POLICY_ID",
    "sanitize_wizard_presets",
    "validate_wizard_presets",
    "load_wizard_presets",
    "current_presets_version",
    "request_hash_for",
    "update_wizard_presets",
    "PresetUpdateResult",
    "WizardPresetError",
    "WizardPresetSchemaError",
    "WizardPresetPreconditionError",
    "WizardPresetConflictError",
    "WizardPresetIdempotencyExpiredError",
    "WizardPresetIdempotencyConflictError",
]

#: AUTH-01 정책 식별자(WIZ-PRESET-01). DRAWING team + Admin(전역 preset 관리). CS/SALES deny.
WIZ_PRESET_POLICY_ID = "DRAWING_TEAM"

#: idempotency replay window(커밋+24시간). SHIPMENT-REFERENCE-01 과 동일 규약.
IDEMPOTENCY_REPLAY_WINDOW = datetime.timedelta(hours=24)

DRAWING_WIZARD_PRESETS_KEY = "drawing_wizard_presets"
MAX_PRESETS = 50
MAX_LABEL_LEN = 30
MAX_TEXT_LEN = 2000


def sanitize_wizard_presets(presets: object) -> list[dict]:
    """입력 프리셋 목록을 검증·정규화한다.

    비-리스트/비-딕트/비문자열 항목·본문 없는 항목·길이 초과 항목을 제거하고,
    라벨/본문을 ``strip`` 한 뒤 최대 ``MAX_PRESETS`` 개로 절단한다. 라벨이 비면
    본문 첫 줄 앞 ``MAX_LABEL_LEN`` 자로 기본 라벨을 만든다.

    Args:
        presets: 신뢰할 수 없는 입력(list[dict] 기대, 그 외 타입은 빈 목록).

    Returns:
        정규화된 ``[{"label": str, "text": str}]`` 목록.
    """
    if not isinstance(presets, list):
        return []
    cleaned: list[dict] = []
    for item in presets:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        text = item.get("text")
        if not isinstance(text, str):
            continue
        if label is not None and not isinstance(label, str):
            continue
        text = text.strip()
        label = (label or "").strip()
        if not text:
            continue
        if len(text) > MAX_TEXT_LEN or len(label) > MAX_LABEL_LEN:
            continue
        if not label:
            label = text.splitlines()[0][:MAX_LABEL_LEN].strip()
        cleaned.append({"label": label, "text": text})
        if len(cleaned) >= MAX_PRESETS:
            break
    return cleaned


def load_wizard_presets() -> list[dict]:
    """도면 마법사 사용자 프리셋을 DB에서 로드한다(없으면 빈 목록).

    Returns:
        정규화된 프리셋 목록(``sanitize_wizard_presets`` 통과분).
    """
    setting = (
        db_session.query(SystemSetting)
        .filter_by(setting_key=DRAWING_WIZARD_PRESETS_KEY)
        .first()
    )
    if setting and setting.setting_value:
        return sanitize_wizard_presets(setting.setting_value)
    return []


def current_presets_version(session: Session) -> int:
    """현재 preset collection 의 optimistic-lock version(row 없으면 0).

    Args:
        session: 조회 세션.

    Returns:
        ``SystemSetting.version`` 정수(저장 row 없으면 0 — GET 이 If-Match 로 되보냄).
    """
    setting = (
        session.query(SystemSetting)
        .filter(SystemSetting.setting_key == DRAWING_WIZARD_PRESETS_KEY)
        .first()
    )
    return int(getattr(setting, "version", 0) or 0) if setting is not None else 0


# --------------------------------------------------------------------------- #
# 전역 preset 저장 command: 명시 schema + optimistic lock(version) + idempotency + audit
# (silent global overwrite 차단 — SHIPMENT-REFERENCE-01 SystemSetting 패턴 재사용)
# --------------------------------------------------------------------------- #
_ALLOWED_ITEM_KEYS = frozenset({"label", "text"})


class WizardPresetError(RuntimeError):
    """preset command 계약 위반의 베이스(호출부가 ``status_code`` 로 매핑)."""

    status_code = 400
    error_code = "WIZARD_PRESET_ERROR"


class WizardPresetSchemaError(WizardPresetError):
    """preset payload 스키마 위반(비-리스트 payload·비-딕트 항목·임의 필드). 400."""

    status_code = 400
    error_code = "WIZARD_PRESET_SCHEMA"


class WizardPresetPreconditionError(WizardPresetError):
    """If-Match(settings_version) 누락. 428(전역 덮어쓰기 전 version 명시 강제)."""

    status_code = 428
    error_code = "PRECONDITION_REQUIRED"


class WizardPresetConflictError(WizardPresetError):
    """If-Match 불일치(stale). 409 + 현재 version 동봉(silent global overwrite 차단)."""

    status_code = 409
    error_code = "REVISION_CONFLICT"

    def __init__(self, current_version: int) -> None:
        super().__init__(f"presets_version mismatch; current={current_version}")
        self.current_version = current_version


class WizardPresetIdempotencyExpiredError(WizardPresetError):
    """같은 idempotency key 가 24시간 replay window 를 넘김. 409."""

    status_code = 409
    error_code = "IDEMPOTENCY_KEY_EXPIRED"


class WizardPresetIdempotencyConflictError(WizardPresetError):
    """같은 key 를 다른 request_hash 로 재사용(replay 아님). 409."""

    status_code = 409
    error_code = "IDEMPOTENCY_KEY_CONFLICT"


def validate_wizard_presets(payload: object) -> list[dict]:
    """preset 저장 payload 를 명시 schema 로 검증·정규화한다(임의 필드 거부).

    구조 위반(비-리스트 payload·비-딕트 항목·``label``/``text`` 외 임의 키)은
    :class:`WizardPresetSchemaError`(400)로 **강하게 거부**한다. 값 정규화(trim·빈 본문/
    길이초과 제거·최대 개수 절단)는 :func:`sanitize_wizard_presets` 에 위임한다(기존
    무손실 sanitize 유지).

    Args:
        payload: 저장 요청 preset 목록(신뢰 불가).

    Returns:
        정규화된 ``[{"label": str, "text": str}]`` 목록.

    Raises:
        WizardPresetSchemaError: 구조 위반(비-리스트·비-딕트 항목·임의 필드). 400.
    """
    if not isinstance(payload, list):
        raise WizardPresetSchemaError("presets 는 리스트여야 합니다.")
    for item in payload:
        if not isinstance(item, dict):
            raise WizardPresetSchemaError("preset 항목은 객체여야 합니다.")
        extra = set(item) - _ALLOWED_ITEM_KEYS
        if extra:
            raise WizardPresetSchemaError(f"허용되지 않은 필드: {sorted(extra)}")
    return sanitize_wizard_presets(payload)


def request_hash_for(payload: Any) -> str:
    """canonical preset payload 의 sha256 hex(idempotency same-key/different-hash 감지용)."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class PresetUpdateResult:
    """preset command 결과(호출부가 HTTP 응답으로 변환). ``replayed`` 면 write 미수행."""

    def __init__(
        self, *, version: int, receipt_id: str, presets: list[dict],
        body: dict, replayed: bool,
    ) -> None:
        self.version = version
        self.receipt_id = receipt_id
        self.presets = presets
        self.body = body
        self.replayed = replayed


def _lookup_preset_receipt(
    session: Session, actor_user_id: Optional[int], idempotency_key: str,
) -> Optional[SystemSettingReceipt]:
    """(actor, WIZ_PRESET_POLICY_ID, key) 로 기존 receipt 를 조회한다(없으면 None)."""
    return (
        session.query(SystemSettingReceipt)
        .filter(
            SystemSettingReceipt.actor_user_id == actor_user_id,
            SystemSettingReceipt.policy_id == WIZ_PRESET_POLICY_ID,
            SystemSettingReceipt.idempotency_key == idempotency_key,
        )
        .one_or_none()
    )


def _result_from_receipt(receipt: SystemSettingReceipt) -> PresetUpdateResult:
    """저장된 receipt 를 replay 결과(write 미수행)로 되돌린다."""
    body = receipt.response_body or {}
    presets = ((body.get("data") or {}).get("presets")) or []
    return PresetUpdateResult(
        version=receipt.resulting_version, receipt_id=str(receipt.read_receipt_id),
        presets=presets, body=body, replayed=True,
    )


def _preset_replay(
    session: Session, actor_user_id: Optional[int], idempotency_key: str,
    req_hash: str, now: datetime.datetime,
) -> Optional[PresetUpdateResult]:
    """idempotency replay 판정: 저장된 receipt 가 있으면 재사용(만료/hash 불일치는 409)."""
    existing = _lookup_preset_receipt(session, actor_user_id, idempotency_key)
    if existing is None:
        return None
    if now > existing.expires_at:
        raise WizardPresetIdempotencyExpiredError("idempotency key expired.")
    if existing.request_hash != req_hash:
        raise WizardPresetIdempotencyConflictError("idempotency key reused.")
    return _result_from_receipt(existing)


def _write_presets(
    session: Session, setting: Optional[SystemSetting], cleaned: list[dict],
) -> SystemSetting:
    """정규화된 preset 목록을 setting_value 에 저장한다(없으면 version=0 baseline 생성)."""
    if setting is None:
        setting = SystemSetting(
            setting_key=DRAWING_WIZARD_PRESETS_KEY, version=0,
            description="도면 마법사 사용자 프리셋(도면팀 공유 전역)",
        )
        session.add(setting)
        session.flush()  # FOR UPDATE 이후 신규 row 물화(version bump 대상 확보).
    setting.setting_value = copy.deepcopy(cleaned)
    flag_modified(setting, "setting_value")
    return setting


def _record_preset_receipt(
    session: Session, actor_user_id: Optional[int], idempotency_key: Optional[str],
    req_hash: str, cleaned: list[dict], version: int, now: datetime.datetime,
) -> PresetUpdateResult:
    """receipt + SecurityLog 를 같은 transaction 에 기록한다(경합 IntegrityError=replay)."""
    receipt_id = str(uuid.uuid4())
    body = {"success": True, "data": {"version": version, "presets": cleaned}}
    session.add(SystemSettingReceipt(
        read_receipt_id=receipt_id, actor_user_id=actor_user_id,
        setting_key=DRAWING_WIZARD_PRESETS_KEY, policy_id=WIZ_PRESET_POLICY_ID,
        idempotency_key=idempotency_key, request_hash=req_hash,
        response_status=200, response_body=body, resulting_version=version,
        expires_at=now + IDEMPOTENCY_REPLAY_WINDOW,
    ))
    session.add(SecurityLog(
        user_id=actor_user_id,
        message=f"DRAWING_WIZARD_PRESET_UPDATE key={DRAWING_WIZARD_PRESETS_KEY} version={version}",
    ))
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        if idempotency_key is None:
            raise
        winner = _lookup_preset_receipt(session, actor_user_id, idempotency_key)
        if winner is None:
            raise
        return _result_from_receipt(winner)
    return PresetUpdateResult(
        version=version, receipt_id=receipt_id, presets=cleaned, body=body, replayed=False,
    )


def update_wizard_presets(
    session: Session,
    *,
    actor_user_id: Optional[int],
    payload: object,
    if_match_version: Optional[int],
    idempotency_key: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
) -> PresetUpdateResult:
    """전역 preset 목록을 optimistic lock + receipt + audit 로 원자 저장한다.

    호출부가 ``session.commit()`` 을 소유한다. 순서: schema 검증(400) → SystemSetting row
    ``FOR UPDATE`` 잠금 → idempotency replay → If-Match(version) 검증(누락 428·불일치 409,
    silent global overwrite 차단) → 저장 → version bump → receipt/SecurityLog. **Order 는
    건드리지 않는다**(전역 SystemSetting collection).

    Args:
        session: business transaction 세션(커밋 미수행).
        actor_user_id: 요청 actor(receipt 소유자·audit 주체).
        payload: 저장 preset 목록(신뢰 불가; 내부에서 validate).
        if_match_version: client 가 보낸 현재 version(None 이면 428).
        idempotency_key: UUID 문자열(≤64자) 또는 None(dedupe 안 함).
        now: 테스트용 시각 주입(기본 ``now_utc_naive()``).

    Returns:
        PresetUpdateResult(version/receipt_id/presets/body/replayed).

    Raises:
        WizardPresetSchemaError: 스키마 위반(400).
        WizardPresetPreconditionError: If-Match 누락(428).
        WizardPresetConflictError: If-Match 불일치(409, 현재 version 동봉).
        WizardPresetIdempotencyExpiredError/ConflictError: replay window 초과/hash 불일치(409).
    """
    cleaned = validate_wizard_presets(payload)  # 400 먼저(잠금 전).
    req_hash = request_hash_for(cleaned)
    now = now or now_utc_naive()

    setting = (
        session.query(SystemSetting)
        .filter(SystemSetting.setting_key == DRAWING_WIZARD_PRESETS_KEY)
        .with_for_update()
        .one_or_none()
    )
    current_version = setting.version if setting is not None else 0

    if idempotency_key is not None:
        replay = _preset_replay(session, actor_user_id, idempotency_key, req_hash, now)
        if replay is not None:
            return replay

    if if_match_version is None:
        raise WizardPresetPreconditionError("If-Match(settings_version)가 필요합니다.")
    if if_match_version != current_version:
        raise WizardPresetConflictError(current_version)

    setting = _write_presets(session, setting, cleaned)
    setting.version = current_version + 1
    return _record_preset_receipt(
        session, actor_user_id, idempotency_key, req_hash, cleaned, setting.version, now,
    )
