"""
ERP 출고 설정: JSON 파일 기반 로드/저장 및 시공자 목록 정규화.
erp.py에서 분리 (Phase 4-2). shipment 대시보드·설정 페이지·API에서 공통 사용.
"""
import os
import json

ERP_SHIPMENT_SETTINGS_PATH = os.path.join('data', 'erp_shipment_settings.json')
DEFAULT_ERP_WORKER_CAPACITY = 10


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


def load_erp_shipment_settings():
    """ERP 출고 설정(시공시간/도면담당자/시공자/현장주소) JSON 파일에서 로드."""
    try:
        if os.path.exists(ERP_SHIPMENT_SETTINGS_PATH):
            with open(ERP_SHIPMENT_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {
                    'construction_time': data.get('construction_time', []),
                    'drawing_manager': data.get('drawing_manager', []),
                    'construction_workers': normalize_erp_shipment_workers(data.get('construction_workers', [])),
                    'site_extra': data.get('site_extra', []),
                }
        return {'construction_time': [], 'drawing_manager': [], 'construction_workers': [], 'site_extra': []}
    except Exception as e:
        print(f"Error loading ERP shipment settings: {e}")
        return {'construction_time': [], 'drawing_manager': [], 'construction_workers': [], 'site_extra': []}


def save_erp_shipment_settings(settings):
    """ERP 출고 설정 저장."""
    try:
        os.makedirs(os.path.dirname(ERP_SHIPMENT_SETTINGS_PATH), exist_ok=True)
        with open(ERP_SHIPMENT_SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving ERP shipment settings: {e}")
        return False
