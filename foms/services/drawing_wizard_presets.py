"""도면 마법사 사용자 프리셋: 도면팀 공유 전역 저장(SystemSetting).

기본 프리셋(SR/EP/DOOR/옷봉)은 프론트 코드 상수로 유지하고, 사용자가 추가한
텍스트 스니펫만 SystemSetting 키 ``drawing_wizard_presets`` 에 **전역** 저장한다.
여러 도면 담당자가 표준 컷리스트 템플릿을 공유한다(주문 무관 전역 자원).

값 스키마: ``[{"label": str, "text": str}]`` (라벨=메뉴 표기, text=삽입 본문).
"""
from __future__ import annotations

import copy

from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.main.db import db_session
from foms.persistence.main.models import SystemSetting

__all__ = [
    "DRAWING_WIZARD_PRESETS_KEY",
    "MAX_PRESETS",
    "MAX_LABEL_LEN",
    "MAX_TEXT_LEN",
    "sanitize_wizard_presets",
    "load_wizard_presets",
    "save_wizard_presets",
]

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


def save_wizard_presets(presets: list) -> list[dict]:
    """도면 마법사 사용자 프리셋을 검증·정규화 후 DB에 저장한다.

    Args:
        presets: 저장할 프리셋 목록(신뢰 불가 입력; 내부에서 정규화).

    Returns:
        실제 저장된 정규화 프리셋 목록(API 응답에 그대로 echo).
    """
    cleaned = sanitize_wizard_presets(presets)
    setting = (
        db_session.query(SystemSetting)
        .filter_by(setting_key=DRAWING_WIZARD_PRESETS_KEY)
        .first()
    )
    if not setting:
        setting = SystemSetting(
            setting_key=DRAWING_WIZARD_PRESETS_KEY,
            description="도면 마법사 사용자 프리셋(도면팀 공유 전역)",
        )
        db_session.add(setting)
    setting.setting_value = copy.deepcopy(cleaned)
    flag_modified(setting, "setting_value")
    db_session.commit()
    return cleaned
