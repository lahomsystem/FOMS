"""ERP 생산 대시보드 행 DTO·표시 헬퍼 (Batch 4 production 구조-추출, 동작 보존).

`erp_production_dashboard()`의 현재 페이지 주문 → 목록 행 dict 변환과 프로세스맵 카드
상단 단계 바 조립을 분리한다. 단계 라벨 매핑·퀘스트/영업 승인 판정·표시 필드·썸네일은
원본과 1:1 동일(캐시 아님). 쿼리/카운트/KPI/pagination은 production_read_model이 담당한다.
flat 모듈(subpackage __init__ 순환 회피).
"""
from __future__ import annotations

from typing import Any

from foms.services.erp_display import (
    _ensure_dict,
    _erp_alerts,
    _erp_get_stage,
    _erp_has_media,
)
from foms.services.erp_mobile_order_display import resolve_manager_phone_for_queue

__all__ = [
    "build_production_enriched_rows",
    "build_production_process_steps",
]


def _production_stage_label_from_stage(stage: str) -> str | None:
    if stage not in ['고객컨펌', '생산', '시공', 'CONFIRM', 'PRODUCTION', 'CONSTRUCTION']:
        return None
    label = stage
    if stage in ('CONFIRM', '고객컨펌'):
        label = '제작대기'
    if stage in ('PRODUCTION', '생산'):
        label = '제작중'
    if stage in ('CONSTRUCTION', '시공'):
        label = '제작완료'
    return label


def _production_quest_sales_state(
    sd: dict[str, Any], stage_label: str
) -> tuple[bool | None, Any]:
    """제작대기일 때 퀘스트·영업 승인 상태."""
    if stage_label != '제작대기':
        return True, None
    is_sales_approved = False
    quests = sd.get('quests') or []
    active_quest = next((q for q in quests if q.get('stage') in ('CONFIRM', '고객컨펌')), None)
    if not active_quest:
        return is_sales_approved, active_quest
    assignee_approval = active_quest.get('assignee_approval') or {}
    if isinstance(assignee_approval, dict):
        is_sales_approved = assignee_approval.get('approved') is True
    else:
        is_sales_approved = bool(assignee_approval)
    if not is_sales_approved:
        team_approvals = active_quest.get('team_approvals') or {}
        sales_val = team_approvals.get('SALES') or team_approvals.get('영업팀')
        if isinstance(sales_val, dict):
            is_sales_approved = sales_val.get('approved') is True
        else:
            is_sales_approved = bool(sales_val)
    return is_sales_approved, active_quest


def _enrich_one_production_order(
    o: Any, sd: dict[str, Any], stage_label: str, att_n: int
) -> dict[str, Any]:
    """단일 Order → 목록 행 dict."""
    is_sales_approved, active_quest = _production_quest_sales_state(sd, stage_label)
    alerts = _erp_alerts(o, sd, att_n)
    return {
        'id': o.id,
        'is_erp_order': o.is_erp_order,
        'is_self_measurement': getattr(o, 'is_self_measurement', False),
        'structured_data': sd,
        'customer_name': (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-',
        'address': (((sd.get('site') or {}).get('address_full')) or ((sd.get('site') or {}).get('address_main'))) or '-',
        'stage': stage_label,
        'alerts': alerts,
        'has_media': _erp_has_media(o, att_n),
        'attachments_count': att_n,
        'orderer_name': (((sd.get('parties') or {}).get('orderer') or {}).get('name') or '').strip() or None,
        'current_quest': active_quest if stage_label == '제작대기' else None,
        'is_sales_approved': is_sales_approved if stage_label == '제작대기' else True,
        'owner_team': 'PRODUCTION',
        'measurement_date': (((sd.get('schedule') or {}).get('measurement') or {}).get('date')),
        'construction_date': (((sd.get('schedule') or {}).get('construction') or {}).get('date')),
        'manager_name': (((sd.get('parties') or {}).get('manager') or {}).get('name')) or '-',
        'manager_phone': resolve_manager_phone_for_queue(sd.get('parties') or {}, order=o),
        'phone': (((sd.get('parties') or {}).get('customer') or {}).get('phone')) or '-',
    }


def build_production_enriched_rows(
    page_rows: list[Any], att_counts: dict[int, int]
) -> list[dict[str, Any]]:
    """현재 페이지 주문만 목록용 dict로 변환."""
    enriched: list[dict[str, Any]] = []
    for o in page_rows:
        sd = _ensure_dict(o.structured_data)
        raw_stage = _erp_get_stage(o, sd)
        if not raw_stage:
            continue
        stage_label = _production_stage_label_from_stage(raw_stage)
        if not stage_label:
            continue
        att_n = att_counts.get(o.id, 0)
        enriched.append(_enrich_one_production_order(o, sd, stage_label, att_n))
    return enriched


def build_production_process_steps(
    step_stats: dict[str, dict[str, int]]
) -> list[dict[str, Any]]:
    """프로세스 맵 카드용 상단 2단계(제작대기·제작중)."""
    return [
        {'label': '제작대기', 'display': '제작대기', **step_stats['제작대기']},
        {'label': '제작중', 'display': '제작중', **step_stats['제작중']},
    ]
