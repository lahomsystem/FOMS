"""
ERP 출고 설정: DB 기반 로드/저장 및 시공자 목록 정규화.
erp.py에서 분리 (Phase 4-2). shipment 대시보드·설정 페이지·API에서 공통 사용.
"""
from __future__ import annotations

import json
import os

from flask import g, has_request_context
from sqlalchemy import event

from foms.persistence.main.db import db_session
from foms.persistence.main.models import SystemSetting
from foms.services.erp_display import manager_display_name

__all__ = [
    "ERP_SHIPMENT_SETTINGS_KEY",
    "ERP_SHIPMENT_SETTINGS_PATH",
    "DEFAULT_ERP_WORKER_CAPACITY",
    "normalize_measurement_managers",
    "normalize_drawing_manager_en",
    "normalize_erp_shipment_workers",
    "is_order_assigned_to_user_for_construction",
    "is_order_mine_for_user",
    "load_erp_shipment_settings",
    "save_erp_shipment_settings",
]


ERP_SHIPMENT_SETTINGS_KEY = 'erp_shipment_settings'
ERP_SHIPMENT_SETTINGS_PATH = os.path.join('data', 'erp_shipment_settings.json')
DEFAULT_ERP_WORKER_CAPACITY = 10


def normalize_measurement_managers(managers):
    """실측 담당자 목록 정규화 (name, sort_order, phone).

    하위호환: 문자열 배열 ["이름"] → [{"name": "이름", "sort_order": 999, "phone": ""}]
    """
    normalized = []
    if not isinstance(managers, list):
        return normalized
    for idx, m in enumerate(managers):
        if isinstance(m, dict):
            name = str(m.get('name') or '').strip()
            phone = str(m.get('phone') or '').strip()
            try:
                sort_order = int(m.get('sort_order', 999))
            except (ValueError, TypeError):
                sort_order = 999
        else:
            name = str(m).strip()
            phone = ''
            sort_order = 999
        if name:
            normalized.append({'name': name, 'sort_order': sort_order, 'phone': phone})
    return normalized


def normalize_drawing_manager_en(
    mapping: dict[str, str] | list[dict[str, str]] | None,
) -> dict[str, str]:
    """도면담당자 한글명→영문명 매핑 정규화 (도면 마법사 DREW 셀 표기용).

    설정의 ``drawing_manager``(문자열 리스트)와 병렬로 저장되는 하위호환 키.
    한글 담당자명을 도면 마법사 DREW 셀 기본값으로 넣을 영문명으로 매핑한다.
    ``drawing_manager`` 자체는 문자열 리스트 그대로 두므로 기존 소비처
    (datalist·대시보드·quest 표시)는 영향받지 않는다.

    Args:
        mapping: 표준형은 dict ``{한글명: 영문명}``. 폼 왕복 편의를 위해
            list ``[{"name": .., "name_en": ..}]`` 형태도 허용한다. 그 외
            타입은 빈 dict로 정규화한다.

    Returns:
        빈 한글명·빈 영문명 항목을 제외한 ``dict[str, str]``.
    """
    normalized: dict[str, str] = {}
    if isinstance(mapping, dict):
        pairs = list(mapping.items())
    elif isinstance(mapping, list):
        pairs = [
            (entry.get('name'), entry.get('name_en'))
            for entry in mapping
            if isinstance(entry, dict)
        ]
    else:
        return normalized
    for raw_name, raw_en in pairs:
        name = str(raw_name or '').strip()
        name_en = str(raw_en or '').strip()
        if name and name_en:
            normalized[name] = name_en
    return normalized


def normalize_erp_shipment_workers(workers):
    """출고 설정 시공자 목록 정규화 (name, capacity, off_dates)."""
    normalized = []
    if not isinstance(workers, list):
        return normalized
    for w in workers:
        if isinstance(w, dict):
            name = str(w.get('name') or w.get('text') or '').strip()
            cap_raw = w.get('capacity', w.get('daily_capacity', DEFAULT_ERP_WORKER_CAPACITY))
            try:
                capacity = int(cap_raw)
            except (ValueError, TypeError):
                capacity = DEFAULT_ERP_WORKER_CAPACITY
            if capacity < 0:
                capacity = DEFAULT_ERP_WORKER_CAPACITY
            off_raw = w.get('off_dates') or w.get('offDays') or []
            if not isinstance(off_raw, list):
                off_raw = []
            off_dates = []
            seen = set()
            for d in off_raw:
                ds = str(d).strip()
                if ds and ds not in seen:
                    seen.add(ds)
                    off_dates.append(ds)
        else:
            name = str(w).strip()
            capacity = DEFAULT_ERP_WORKER_CAPACITY
            off_dates = []

        if name:
            normalized.append({
                'name': name,
                'capacity': capacity,
                'off_dates': off_dates,
            })
    return normalized


def is_order_assigned_to_user_for_construction(order, user_name):
    """주문의 시공/출고 배정(construction_workers)에 해당 사용자 이름이 포함되어 있는지 여부."""
    if not user_name or not order:
        return False
    sd = getattr(order, 'structured_data', None) or {}
    if not isinstance(sd, dict):
        return False
    shipment = sd.get('shipment') or {}
    workers = shipment.get('construction_workers') or []
    key = str(user_name or '').strip().lower()
    for w in workers:
        name_part = w if isinstance(w, str) else (isinstance(w, dict) and w.get('name')) or ''
        if str(name_part or '').strip().lower() == key:
            return True
    return False


def is_order_mine_for_user(order, user):
    """
    '내 할 일' 단일 판단: 시공자(construction_workers)에 있거나 담당자(manager)면 True.
    URL mine=1 필터용. 시공팀/영업팀 공통.
    """
    if not order or not user:
        return False
    if is_order_assigned_to_user_for_construction(order, getattr(user, 'name', None)):
        return True
    user_name = (getattr(user, 'name', None) or '').strip().lower()
    user_username = (getattr(user, 'username', None) or '').strip().lower()
    if not user_name and not user_username:
        return False
    manager_names = set()
    sd = getattr(order, 'structured_data', None) or {}
    if isinstance(sd, dict):
        parties = sd.get('parties') or {}
        mn = manager_display_name(parties)
        if mn:
            manager_names.add(mn.lower())
        wf = sd.get('workflow') or {}
        owner = (wf.get('current_quest') or {}).get('owner_person') or ''
        if (owner or '').strip():
            manager_names.add(str(owner).strip().lower())
    mn_col = (getattr(order, 'manager_name', None) or '').strip()
    if mn_col:
        manager_names.add(mn_col.lower())
    return (user_name in manager_names) or (user_username in manager_names)


def _project_loaded_settings(data):
    """저장 blob(신 canonical/구 legacy 무관)을 loader 출력 스키마로 정규화한다.

    SHIPMENT-REFERENCE-01 이후 저장 canonical 은 ``drawing_managers``(object array)/
    ``measurement_managers`` 이나, read 소비처는 여전히 ``drawing_manager``(list)+
    ``drawing_manager_en``(dict)+``measurement_manager``+``construction_workers`` 를 읽는다.
    :func:`~foms.services.shipment_reference.project_to_legacy_shape` 로 어느 저장 형태든
    동일한 legacy 출력으로 투영한 뒤 기존 정규화(measurement/worker/en)를 적용한다.
    """
    from foms.services.shipment_reference import project_to_legacy_shape

    legacy = project_to_legacy_shape(data)
    return {
        'construction_time': legacy.get('construction_time', []),
        'drawing_manager': legacy.get('drawing_manager', []),
        'drawing_manager_en': normalize_drawing_manager_en(legacy.get('drawing_manager_en', {})),
        'measurement_manager': normalize_measurement_managers(legacy.get('measurement_manager', [])),
        'construction_workers': normalize_erp_shipment_workers(legacy.get('construction_workers', [])),
        'site_extra': legacy.get('site_extra', []),
    }


# --- 요청당 캐시 -------------------------------------------------------------
#
# 출고 설정은 한 요청 안에서 1~3번 읽힌다(화면 본체 + 템플릿 담당자 후보 + 견적 연락처 등,
# 원장 P3-8). 값은 요청 사이에 바뀔 수 있으므로 **요청 하나 안에서만** 기억한다(flask.g —
# 요청이 끝나면 버려진다). 요청 밖(워커·스크립트)에서는 기억하지 않는다 — 앱 컨텍스트가
# 여러 잡에 걸쳐 오래 살 수 있다.
#
# 기억하는 것은 **DB 에서 읽은 저장 값 그 자체**(``setting_value``)이고, 투영
# (:func:`_project_loaded_settings`)은 예전처럼 호출마다 한다. 예전에도 같은 요청의 두 번째
# 조회는 세션 identity map 의 같은 행 객체를 돌려줬으므로 호출부가 받는 모양·공유 관계는
# 그대로다 — 줄어드는 것은 DB 왕복뿐이고 사본 복사 비용도 새로 생기지 않는다.
#
# 같은 요청 안에서 이 행을 고치면 기억을 지운다: 값 대입·flag_modified(속성 이벤트),
# flush 된 insert/update/delete(매퍼 이벤트), 세션 롤백. 그래서 저장 직후 다시 읽으면
# 예전처럼 새 값이 나온다.
_REQUEST_CACHE_ATTR = "_foms_erp_shipment_settings_raw"
#: "저장된 설정 없음(기본값)" 을 기억하는 표식 — ``None`` 은 "아직 안 읽음" 이다.
_NO_SAVED_SETTINGS = object()


def _request_cached_raw():
    if not has_request_context():
        return None
    return getattr(g, _REQUEST_CACHE_ATTR, None)


def _remember_for_request(raw) -> None:
    if has_request_context():
        setattr(g, _REQUEST_CACHE_ATTR, raw)


def _forget_for_request() -> None:
    if has_request_context():
        g.pop(_REQUEST_CACHE_ATTR, None)


def _is_shipment_settings_row(target) -> bool:
    return getattr(target, "setting_key", None) == ERP_SHIPMENT_SETTINGS_KEY


def _on_row_written(mapper, connection, target) -> None:  # noqa: ARG001 - SQLAlchemy 서명
    if _is_shipment_settings_row(target):
        _forget_for_request()


def _on_value_changed(target, *_args) -> None:
    if _is_shipment_settings_row(target):
        _forget_for_request()


def _on_session_rollback(session, previous_transaction=None) -> None:  # noqa: ARG001
    _forget_for_request()


for _row_event in ("after_insert", "after_update", "after_delete"):
    event.listen(SystemSetting, _row_event, _on_row_written)
event.listen(SystemSetting.setting_value, "set", _on_value_changed)
event.listen(SystemSetting.setting_value, "modified", _on_value_changed)
event.listen(db_session, "after_soft_rollback", _on_session_rollback)


def load_erp_shipment_settings():
    """ERP 출고 설정(시공시간/도면담당자/시공자/현장주소) DB에서 로드. (이전 JSON 파일 대체)

    같은 요청 안의 두 번째 호출부터는 DB 를 다시 읽지 않는다(위 "요청당 캐시").
    """
    cached_raw = _request_cached_raw()
    default_settings = {
        'construction_time': [],
        'drawing_manager': [],
        'drawing_manager_en': {},
        'measurement_manager': [],
        'construction_workers': [],
        'site_extra': []
    }
    if cached_raw is _NO_SAVED_SETTINGS:
        return default_settings
    if cached_raw is not None:
        return _project_loaded_settings(cached_raw)
    try:
        setting = db_session.query(SystemSetting).filter_by(setting_key=ERP_SHIPMENT_SETTINGS_KEY).first()
        if setting and setting.setting_value:
            _remember_for_request(setting.setting_value)
            return _project_loaded_settings(setting.setting_value)

        # Migration from JSON if DB is empty
        if os.path.exists(ERP_SHIPMENT_SETTINGS_PATH):
            with open(ERP_SHIPMENT_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

                # Migrate to DB immediately
                new_setting = SystemSetting(
                    setting_key=ERP_SHIPMENT_SETTINGS_KEY,
                    setting_value=data,
                    description="ERP 출고/실측 등 제반 설정값"
                )
                db_session.add(new_setting)
                db_session.commit()

                _remember_for_request(data)
                return _project_loaded_settings(data)

        _remember_for_request(_NO_SAVED_SETTINGS)
        return default_settings
    except Exception as e:
        db_session.rollback()
        print(f"Error loading ERP shipment settings from DB: {e}")
        return default_settings


def save_erp_shipment_settings(settings):
    """ERP 출고 설정 DB에 저장."""
    try:
        setting = db_session.query(SystemSetting).filter_by(setting_key=ERP_SHIPMENT_SETTINGS_KEY).first()
        if not setting:
            setting = SystemSetting(
                setting_key=ERP_SHIPMENT_SETTINGS_KEY,
                description="ERP 출고/실측 등 제반 설정값"
            )
            db_session.add(setting)

        # update setting value (copy to be safe with JSON mutations)
        import copy
        setting.setting_value = copy.deepcopy(settings)

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(setting, "setting_value")

        db_session.commit()
        return True
    except Exception as e:
        db_session.rollback()
        print(f"Error saving ERP shipment settings to DB: {e}")
        return False
