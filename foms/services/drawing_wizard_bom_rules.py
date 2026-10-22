"""도면 마법사 자재표 계산 규칙 숫자: 도면팀 공유 전역 저장(SystemSetting).

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.3 · §3.6(2단계)

- 기본값(:data:`DEFAULT_RULES`)은 지난 자재표 670장에서 가장 많이 쓴 값을 찾은 것이다
  (도면팀 확인 전 초안). 계산식 자체는 브라우저(``static/js/drawing/bom-calc.js``)가 갖고,
  여기는 식에 들어가는 숫자만 둔다.
- 고친 값은 SystemSetting 키 ``drawing_wizard_bom_rules`` 에 **전체**를 저장한다.
  판 이름은 저장이 없으면 ``d1``(코드 기본값 1판), 저장이 있으면 ``s<version>`` 이다.
  시트의 ``calc.rules`` 에 이 판 이름이 남아 어떤 숫자로 계산했는지 나중에 가릴 수 있다.
- 저장은 optimistic lock(version — 누락 428 · 불일치 409) + SecurityLog 감사를 한
  transaction 에 한다(WIZ-PRESET-01 과 같은 꼴). idempotency receipt 는 쓰지 않는다 —
  같은 version 으로 두 번 보내면 두 번째가 409 라 두 번 적용되지 않는다.
- 읽기는 관대하게: 저장된 값 중 형식이 틀린 칸은 기본값으로 바꿔 읽어 마법사가 깨지지 않게 한다.
"""
from __future__ import annotations

import copy
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.main.models import SystemSetting
from models import SecurityLog

__all__ = [
    "BOM_RULES_KEY",
    "BOM_RULES_POLICY_ID",
    "DEFAULT_RULES",
    "DEFAULT_RULES_LABEL",
    "RULE_RANGES",
    "BomRulesError",
    "BomRulesSchemaError",
    "BomRulesPreconditionError",
    "BomRulesConflictError",
    "validate_bom_rules",
    "load_bom_rules",
    "update_bom_rules",
]

BOM_RULES_KEY = "drawing_wizard_bom_rules"
DEFAULT_RULES_LABEL = "d1"
#: 규칙 숫자 고치기 정책 — 프리셋(WIZ-PRESET-01)과 같은 DRAWING team + Admin.
BOM_RULES_POLICY_ID = "DRAWING_TEAM"

#: 설계서 §3.3 표의 숫자(mm). 키 이름은 bom-calc.js 가 그대로 읽는다.
DEFAULT_RULES: dict = {
    "door_gap_phoenix_pair": 34,     # 피닉스바 쌍문: (모듈 − 34) ÷ 2
    "door_gap_phoenix_single": 30,   # 피닉스바 외짝: 모듈 − 30
    "door_gap_other_pair": 8,        # 그 밖 손잡이 쌍문: (모듈 − 8) ÷ 2
    "door_gap_other_single": 4,      # 그 밖 손잡이 외짝: 모듈 − 4
    "door_std_heights": [1960, 2060, 2160, 2260, 2360],   # 몰딩·슬라이딩 표준 문 높이
    "door_ceiling_margin": 90,       # 표준 문은 '천장 − 90' 이하에서 가장 큰 것
    "nomold_cut": 45,                # 무몰딩(천장까지 문): 천장 − 45
    "nomold_step": 5,                # … 를 5 단위로 내림
    "rod_cut": 35,                   # 옷봉: 모듈 − 35
    "maida_w_cut": 5,                # 마이다 폭: 모듈 − 5
    "maida_h_cut": 15,               # 마이다 높이: 서랍 칸 ÷ 단수 − 15
    "drawer_zone": 753,              # 서랍 칸 높이 기본값(입력이 없을 때)
    "sr_small_gap": 55,              # SR 위: 위 틈이 55 이하면
    "sr_small_value": 60,            # … 60
    "sr_minus": 30,                  # 아니면 (위 틈 − 30) 을
    "sr_step": 10,                   # … 10 단위로 올림
    "sheet_len": 2440,               # SR·EP 판 길이
    "ep_plus_hinged": 10,            # 여닫이 EP 측판: 깊이 + 10
}

#: 정수 규칙의 허용 범위(mm). ``door_std_heights`` 는 :func:`_valid_heights` 가 따로 본다.
RULE_RANGES: dict[str, tuple[int, int]] = {
    "door_gap_phoenix_pair": (0, 200),
    "door_gap_phoenix_single": (0, 200),
    "door_gap_other_pair": (0, 200),
    "door_gap_other_single": (0, 200),
    "door_ceiling_margin": (0, 500),
    "nomold_cut": (0, 500),
    "nomold_step": (1, 100),
    "rod_cut": (0, 300),
    "maida_w_cut": (0, 300),
    "maida_h_cut": (0, 300),
    "drawer_zone": (100, 2000),
    "sr_small_gap": (0, 500),
    "sr_small_value": (0, 500),
    "sr_minus": (0, 500),
    "sr_step": (1, 100),
    "sheet_len": (500, 3600),
    "ep_plus_hinged": (0, 100),
}
_HEIGHTS_KEY = "door_std_heights"
_HEIGHT_RANGE = (500, 3000)
_MAX_HEIGHTS = 8


class BomRulesError(RuntimeError):
    """규칙 저장 계약 위반의 베이스(호출부가 ``status_code`` 로 매핑)."""

    status_code = 400
    error_code = "BOM_RULES_ERROR"


class BomRulesSchemaError(BomRulesError):
    """payload 형식 위반(비-딕트·모르는 칸·범위 밖 값). 400."""

    status_code = 400
    error_code = "BOM_RULES_SCHEMA"


class BomRulesPreconditionError(BomRulesError):
    """If-Match(settings_version) 누락. 428(전역 덮어쓰기 전 version 명시 강제)."""

    status_code = 428
    error_code = "PRECONDITION_REQUIRED"


class BomRulesConflictError(BomRulesError):
    """If-Match 불일치(다른 사람이 먼저 저장). 409 + 현재 version 동봉."""

    status_code = 409
    error_code = "REVISION_CONFLICT"

    def __init__(self, current_version: int) -> None:
        super().__init__(f"bom_rules version mismatch; current={current_version}")
        self.current_version = current_version


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_int(key: str, value: object) -> bool:
    low, high = RULE_RANGES[key]
    return _is_int(value) and low <= value <= high


def _valid_heights(value: object) -> bool:
    """표준 문 높이: 정수 1~8개, 범위 안, 올라가는 순서(같은 값 없음)."""
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_HEIGHTS:
        return False
    low, high = _HEIGHT_RANGE
    if not all(_is_int(h) and low <= h <= high for h in value):
        return False
    return all(a < b for a, b in zip(value, value[1:]))


def _valid_value(key: str, value: object) -> bool:
    return _valid_heights(value) if key == _HEIGHTS_KEY else _valid_int(key, value)


def validate_bom_rules(payload: object) -> dict:
    """저장 payload 를 닫힌 형식으로 검증한다. 빠진 칸은 기본값으로 채운다.

    Args:
        payload: 규칙 dict(신뢰 불가). 빈 dict 는 '기본값으로 되돌리기'.

    Returns:
        모든 칸이 채워진 규칙 dict.

    Raises:
        BomRulesSchemaError: 비-딕트·모르는 칸·범위 밖 값. 400.
    """
    if not isinstance(payload, dict):
        raise BomRulesSchemaError("rules 는 객체여야 합니다.")
    extra = sorted(set(payload) - set(DEFAULT_RULES))
    if extra:
        raise BomRulesSchemaError(f"모르는 규칙 칸: {extra}")
    cleaned = copy.deepcopy(DEFAULT_RULES)
    for key, value in payload.items():
        if not _valid_value(key, value):
            raise BomRulesSchemaError(f"규칙 값이 올바르지 않습니다: {key}")
        cleaned[key] = copy.deepcopy(value)
    return cleaned


def _merge_stored(stored: object) -> dict:
    """저장값을 기본값 위에 얹는다. 형식이 틀린 칸은 기본값으로 둔다(읽기 관대)."""
    rules = copy.deepcopy(DEFAULT_RULES)
    if isinstance(stored, dict):
        for key in DEFAULT_RULES:
            if key in stored and _valid_value(key, stored[key]):
                rules[key] = copy.deepcopy(stored[key])
    return rules


def _label(version: int) -> str:
    return f"s{version}"


def load_bom_rules(session: Session) -> dict:
    """현재 규칙 ``{rules, label, version}`` 을 돌려준다(저장 없으면 기본값·``d1``·0)."""
    setting = (
        session.query(SystemSetting)
        .filter(SystemSetting.setting_key == BOM_RULES_KEY)
        .first()
    )
    if setting is None:
        return {"rules": copy.deepcopy(DEFAULT_RULES), "label": DEFAULT_RULES_LABEL, "version": 0}
    version = int(getattr(setting, "version", 0) or 0)
    return {"rules": _merge_stored(setting.setting_value), "label": _label(version), "version": version}


def update_bom_rules(
    session: Session,
    *,
    actor_user_id: Optional[int],
    payload: object,
    if_match_version: Optional[int],
) -> dict:
    """전역 규칙을 optimistic lock + 감사로 원자 저장한다. 호출부가 commit 을 소유한다.

    순서: 형식 검증(400) → SystemSetting row ``FOR UPDATE`` → If-Match 검증(누락 428 ·
    불일치 409) → 저장 → version +1 → SecurityLog(바뀐 칸의 전·후 값). Order 는 건드리지 않는다.

    Returns:
        저장 뒤 ``{rules, label, version}``.
    """
    cleaned = validate_bom_rules(payload)   # 400 먼저(잠금 전).
    setting = (
        session.query(SystemSetting)
        .filter(SystemSetting.setting_key == BOM_RULES_KEY)
        .with_for_update()
        .one_or_none()
    )
    current = int(setting.version or 0) if setting is not None else 0
    if if_match_version is None:
        raise BomRulesPreconditionError("If-Match(settings_version)가 필요합니다.")
    if if_match_version != current:
        raise BomRulesConflictError(current)

    before = _merge_stored(setting.setting_value) if setting is not None else copy.deepcopy(DEFAULT_RULES)
    if setting is None:
        setting = SystemSetting(
            setting_key=BOM_RULES_KEY, version=0,
            description="도면 마법사 자재표 계산 규칙 숫자(도면팀 공유 전역)",
        )
        session.add(setting)
        session.flush()   # FOR UPDATE 이후 새 row 물화(version 올릴 대상 확보).
    setting.setting_value = copy.deepcopy(cleaned)
    flag_modified(setting, "setting_value")
    setting.version = current + 1
    changed = {key: [before[key], cleaned[key]] for key in DEFAULT_RULES if before[key] != cleaned[key]}
    session.add(SecurityLog(
        user_id=actor_user_id,
        message=f"DRAWING_WIZARD_BOM_RULES_UPDATE key={BOM_RULES_KEY} version={setting.version}",
        action="DRAWING_WIZARD_BOM_RULES_UPDATE",
        target_type="system_setting",
        detail={"key": BOM_RULES_KEY, "version": setting.version, "changed": changed},
    ))
    session.flush()
    return {"rules": cleaned, "label": _label(setting.version), "version": setting.version}
