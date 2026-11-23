"""태블릿 출고 탭 "하루치 출고표" 묶음 · 사람별 집계 (설계서 §14.3, 결정 D25).

DB 를 건드리지 않는 순수 함수. 라우트가 이미 정렬 · 로드한 줄(Order) 과 시공자 설정만
받아 시공자 묶음 목록과 이름판용 사람별 `건수 · 자수` 를 만든다.

규칙
- 묶음 키 = 그 줄의 첫 유효 시공자(기존 `sort_shipment_rows` 와 같은 규칙).
- 묶음 순서 = 시공자 없음 → 설정에 적힌 시공자 순 → 설정에 없는 이름(이름 순).
- 묶음 안 = 일반 줄 먼저, AS 줄 뒤(그 안에서는 들어온 순서 유지).
- AS 줄인지는 줄에 붙은 그날 줄 종류(``schedule_row_kind``)로 정한다 — 본 흐름이 열린 AS 주문의 시공일 줄은 일반 줄.
- 자수(D25) = 줄 자수 ÷ 그 줄 시공자 수. AS 줄은 건수만 세고 자수는 0.
- 사람 색 번호(1~10, 넘으면 돌려 씀) = 묶음 순서대로 묶음 주인 → 둘째 이후로만 나온
  사람(화면 순서) → 그날 줄이 없는 설정 시공자(설정 순서). 같은 사람은 어디서나 같은 번호.
"""
from __future__ import annotations

from typing import Any

from foms.services.orders.schedule_row_kind import row_as_visit_too, row_is_as
from foms.services.shipment_dashboard_helpers import (
    _normalize_worker_name,
    visible_spec_units,
)

COLOR_COUNT = 10


def _row_workers(order: Any) -> list[str]:
    """줄의 유효 시공자 이름 목록(앞뒤 공백 제거 · 빈 값 버림 · 정규화 이름 중복 제거).

    Args:
        order: Order ORM 객체(또는 같은 속성을 가진 객체).

    Returns:
        처음 나온 글자 그대로의 이름 목록(순서 유지).
    """
    sd = order.structured_data if isinstance(getattr(order, 'structured_data', None), dict) else {}
    raw = (sd.get('shipment') or {}).get('construction_workers') or []
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for w in raw:
        text = str(w or '').strip()
        norm = _normalize_worker_name(text)
        if norm and norm not in seen:
            seen.add(norm)
            names.append(text)
    return names


def _color_for(position: int) -> int:
    """0부터 센 자리를 1~10 색 번호로 바꾼다(10 넘으면 돌려 씀)."""
    return position % COLOR_COUNT + 1


def build_tablet_day_sheet(
    rows: list, worker_settings: list, target_date: str | None, as_technicians: list | None = None,
) -> dict:
    """하루치 출고표의 시공자 묶음 · 사람별 집계를 만든다(추가 쿼리 없음).

    Args:
        rows: 그날(또는 기간) 출고 줄 Order 리스트. 들어온 순서를 묶음 안 순서로 쓴다.
        worker_settings: normalize_erp_shipment_workers 결과([{name, capacity, off_dates}]).
        target_date: 'YYYY-MM-DD'. None 이면(기간 보기) 쉬는 날 판정을 하지 않는다.
        as_technicians: 출고 설정의 AS 기사 이름 목록. 이름판 자료(people)에 ``as_tech`` 표식으로 싣는다 —
            AS 줄의 이름판은 AS 기사를 먼저 보이고, 시공 줄의 이름판은 AS 기사를 숨긴다(tablet-ship-assign.js).

    Returns:
        {'groups': [{'key', 'unassigned', 'color_index', 'rows': [
                        {'order', 'no', 'is_as', 'as_visit_too', 'units', 'workers': [{'name', 'color_index'}]}]}],
         'people': [{'name', 'count', 'units', 'capacity', 'over', 'off',
                     'color_index', 'in_settings', 'as_tech'}],
         'total': 줄 수, 'unassigned': 시공자 없는 줄 수}.
    """
    # 설정 시공자(정규화 이름 중복 제거, 설정 순서)
    settings_by_norm: dict[str, dict] = {}
    for w in worker_settings or []:
        name = str((w or {}).get('name') or '').strip()
        norm = _normalize_worker_name(name)
        if norm and norm not in settings_by_norm:
            settings_by_norm[norm] = {**w, 'name': name}
    settings_order = list(settings_by_norm)

    # 줄 준비 + 첫 시공자로 묶기
    display_name: dict[str, str] = {}
    prepared: list[dict] = []
    buckets: dict[str, list[dict]] = {}
    for order in rows or []:
        names = _row_workers(order)
        for n in names:
            display_name.setdefault(_normalize_worker_name(n), n)
        as_row = row_is_as(order)
        entry = {
            'order': order,
            'is_as': as_row,
            'as_visit_too': row_as_visit_too(order),
            'units': 0.0 if as_row else float(visible_spec_units(order) or 0.0),
            'names': names,
        }
        prepared.append(entry)
        key_norm = _normalize_worker_name(names[0]) if names else ''
        buckets.setdefault(key_norm, []).append(entry)

    extra_norms = sorted(n for n in display_name if n not in settings_by_norm)
    group_order = ([''] if '' in buckets else []) + [
        n for n in settings_order + extra_norms if n in buckets
    ]

    # 화면 순서(묶음 안 일반 → AS)
    ordered: list[tuple[str, list[dict]]] = []
    for key_norm in group_order:
        bucket = buckets[key_norm]
        ordered.append((key_norm, [e for e in bucket if not e['is_as']] + [e for e in bucket if e['is_as']]))

    # 사람 색 번호
    color_by_norm: dict[str, int] = {}

    def _assign(norm: str) -> None:
        if norm and norm not in color_by_norm:
            color_by_norm[norm] = _color_for(len(color_by_norm))

    for key_norm, _ in ordered:
        _assign(key_norm)
    for _, entries in ordered:
        for e in entries:
            for n in e['names']:
                _assign(_normalize_worker_name(n))
    for norm in settings_order:
        _assign(norm)
    # AS 기사(설정) — 시공자 설정 · 그날 줄에 없는 이름만 뒤에 붙인다. 같은 이름이 시공자 설정에도 있으면 시공자다.
    tech_name: dict[str, str] = {}
    for raw_name in as_technicians or []:
        text = str(raw_name or '').strip()
        norm = _normalize_worker_name(text)
        if norm and norm not in tech_name:
            tech_name[norm] = text
            display_name.setdefault(norm, text)
            _assign(norm)
    tech_only = [n for n in tech_name if n not in settings_by_norm and n not in extra_norms]

    # 묶음 · 줄 · 사람별 합
    count_by_norm: dict[str, int] = {}
    units_by_norm: dict[str, float] = {}
    groups: list[dict] = []
    no = 0
    for key_norm, entries in ordered:
        out_rows = []
        for e in entries:
            no += 1
            share = e['units'] / len(e['names']) if e['names'] and not e['is_as'] else 0.0
            for n in e['names']:
                norm = _normalize_worker_name(n)
                count_by_norm[norm] = count_by_norm.get(norm, 0) + 1
                units_by_norm[norm] = units_by_norm.get(norm, 0.0) + share
            out_rows.append({
                'order': e['order'],
                'no': no,
                'is_as': e['is_as'],
                'as_visit_too': e['as_visit_too'],
                'units': e['units'],
                'workers': [
                    {'name': n, 'color_index': color_by_norm[_normalize_worker_name(n)]}
                    for n in e['names']
                ],
            })
        groups.append({
            'key': display_name.get(key_norm, '') if key_norm else '',
            'unassigned': not key_norm,
            'color_index': color_by_norm.get(key_norm) if key_norm else None,
            'rows': out_rows,
        })

    people: list[dict] = []
    for norm in settings_order + extra_norms + tech_only:
        setting = settings_by_norm.get(norm)
        units = round(units_by_norm.get(norm, 0.0), 4)
        capacity = None
        off = False
        if setting is not None:
            cap_raw = setting.get('capacity')
            capacity = float(cap_raw) if cap_raw is not None else None
            off = bool(target_date) and target_date in (setting.get('off_dates') or [])
        people.append({
            'name': setting['name'] if setting is not None else display_name[norm],
            'count': count_by_norm.get(norm, 0),
            'units': units,
            'capacity': capacity,
            'over': capacity is not None and units > capacity,
            'off': off,
            'color_index': color_by_norm[norm],
            'in_settings': setting is not None,
            'as_tech': setting is None and norm in tech_name,
        })

    return {
        'groups': groups,
        'people': people,
        'total': len(prepared),
        'unassigned': len(buckets.get('', [])),
    }


def pc_card_rows(sheet: dict | None) -> list:
    """PC 출고 표가 그릴 줄을 하루치 출고표 순서로 펴고, 줄마다 카드 정보를 붙인다(추가 쿼리 없음).

    PC 표(dashboard_main.html)는 태블릿 하루치 출고표와 같은 묶음 순서 · 번호 · 사람 색을 쓴다
    (설계서 2026-11-23-pc-shipment-card-table §4.1). 묶음(시공자) 하나가 카드 하나다.

    Args:
        sheet: build_tablet_day_sheet 결과. None · 빈 값이면 빈 목록.

    Returns:
        Order 목록(묶음 순서). 각 Order 에 ``pc_card`` dict 가 붙는다:
        {'no', 'first', 'last', 'miss', 'count', 'workers', 'units', 'is_as', 'blob_top', 'blob_bottom'}.
        blob_top · blob_bottom = 같은 카드에서 시공자 구성이 같은 이웃 줄과 사람 색 덩어리를 잇는지.
    """
    out: list = []
    for group in (sheet or {}).get('groups') or []:
        rows = group.get('rows') or []
        sigs = ['|'.join(w['name'] for w in row['workers']) for row in rows]
        last = len(rows) - 1
        for i, row in enumerate(rows):
            order = row['order']
            order.pc_card = {
                'no': row['no'],
                'first': i == 0,
                'last': i == last,
                'miss': bool(group.get('unassigned')),
                'count': len(rows),
                'workers': row['workers'],
                'units': row['units'],
                'is_as': row['is_as'],
                'blob_top': i == 0 or sigs[i - 1] != sigs[i],
                'blob_bottom': i == last or sigs[i + 1] != sigs[i],
            }
            out.append(order)
    return out
