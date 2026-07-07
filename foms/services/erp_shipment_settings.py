"""
ERP 출고 설정: DB 기반 로드/저장 및 시공자 목록 정규화.
erp.py에서 분리 (Phase 4-2). shipment 대시보드·설정 페이지·API에서 공통 사용.
"""
from __future__ import annotations

import json
import os

from foms.persistence.main.db import db_session
from foms.persistence.main.models import SystemSetting

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
        mn = ((parties.get('manager') or {}).get('name') or '').strip()
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


def load_erp_shipment_settings():
    """ERP 출고 설정(시공시간/도면담당자/시공자/현장주소) DB에서 로드. (이전 JSON 파일 대체)"""
    default_settings = {
        'construction_time': [],
        'drawing_manager': [],
        'drawing_manager_en': {},
        'measurement_manager': [],
        'construction_workers': [],
        'site_extra': []
    }
    try:
        setting = db_session.query(SystemSetting).filter_by(setting_key=ERP_SHIPMENT_SETTINGS_KEY).first()
        if setting and setting.setting_value:
            data = setting.setting_value
            return {
                'construction_time': data.get('construction_time', []),
                'drawing_manager': data.get('drawing_manager', []),
                'drawing_manager_en': normalize_drawing_manager_en(data.get('drawing_manager_en', {})),
                'measurement_manager': normalize_measurement_managers(data.get('measurement_manager', [])),
                'construction_workers': normalize_erp_shipment_workers(data.get('construction_workers', [])),
                'site_extra': data.get('site_extra', []),
            }

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

                return {
                    'construction_time': data.get('construction_time', []),
                    'drawing_manager': data.get('drawing_manager', []),
                    'drawing_manager_en': normalize_drawing_manager_en(data.get('drawing_manager_en', {})),
                    'measurement_manager': normalize_measurement_managers(data.get('measurement_manager', [])),
                    'construction_workers': normalize_erp_shipment_workers(data.get('construction_workers', [])),
                    'site_extra': data.get('site_extra', []),
                }

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
