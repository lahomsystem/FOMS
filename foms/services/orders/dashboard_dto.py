"""ERP 주문 대시보드 DTO 조립 (Batch 2 orders 구조-추출, 동작 보존).

이미 필터·정렬된 page_orders를 템플릿 표시용 dict 리스트로 조립한다.
필터링/정렬/카운트 결정은 하지 않는다(순수 표시 매핑). 캐시 대상 아님.
원본은 `erp_dashboard()` 라우트의 enriched 루프였고 verbatim 이전한다.
"""
from __future__ import annotations

from foms.services.erp_display import _erp_get_stage, _erp_alerts, _erp_has_media
from foms.services.erp_policy import (
    STAGE_NAME_TO_CODE,
    DEFAULT_OWNER_TEAM_BY_STAGE,
    recommend_owner_team,
)
from foms.services.erp_quest_display import build_current_quest_payload, resolve_order_role_assignees
from foms.services.erp_mobile_order_display import (
    product_subtitle_from_sd,
    resolve_manager_phone_for_queue,
    stage_badge_label,
    stage_badge_modifier,
)
from foms.services.estimate_service import build_measurement_manager_phone_map


def build_orders_row_dtos(page_orders, page_sds, att_counts, user_map, current_user):
    """page_orders를 템플릿 표시용 row dict 리스트로 조립 (구 route enriched 루프).

    Args:
        page_orders: 표시 대상 Order 객체 리스트(이미 필터/정렬됨).
        page_sds: order_id -> structured_data dict.
        att_counts: order_id -> 첨부 수.
        user_map: user_id -> name (담당자명 해석).
        current_user: 퀘스트 페이로드용 현재 사용자.

    Returns:
        list[dict]: 원본 enriched와 동일 구조.
    """
    # N+1 제거: 행마다 resolve_manager_phone_for_queue가 load_erp_shipment_settings를
    # 재조회(=행당 SELECT system_settings)하던 것을, 출고 설정 실측담당자 연락처 map을
    # 요청당 1회 로드해 전달한다(construction/production DTO와 동일 배치 패턴).
    manager_phone_map = build_measurement_manager_phone_map()
    enriched = []
    for o in page_orders:
        sd = page_sds[o.id]
        cnt = att_counts.get(o.id, 0)
        stage = _erp_get_stage(o, sd)
        alerts = _erp_alerts(o, sd, cnt)
        has_media = _erp_has_media(o, cnt)
        stage_key = stage if isinstance(stage, str) else ''
        stage_code = STAGE_NAME_TO_CODE.get(stage_key, stage_key)
        quest_payload = build_current_quest_payload(
            sd=sd,
            stage=stage,
            stage_code=stage_code,
            order=o,
            current_user=current_user,
            user_map=user_map,
        )
        responsible_team = DEFAULT_OWNER_TEAM_BY_STAGE.get(stage_code, None)
        if stage_code in ("MEASURE", "CONFIRM"):
            orderer_check = (((sd.get("parties") or {}).get("orderer") or {}).get("name") or "").strip()
            if orderer_check and "라홈" in orderer_check:
                responsible_team = 'CS'

        parties = sd.get('parties') or {}
        site = sd.get('site') or {}
        schedule = sd.get('schedule') or {}
        enriched.append({
            'id': o.id,
            # v3 CS 콜/접수 홈: 접수 큐 필터(status)·접수일 표시(파생값, 신규 쿼리 없음).
            'status': getattr(o, 'status', '') or '',
            'received_date': getattr(o, 'received_date', '') or '',
            'is_erp_order': o.is_erp_order,
            'is_self_measurement': getattr(o, 'is_self_measurement', False),
            'structured_data': sd,
            'customer_name': (parties.get('customer') or {}).get('name') or '-',
            'phone': (parties.get('customer') or {}).get('phone') or '-',
            'address': site.get('address_full') or site.get('address_main') or '-',
            'measurement_date': (schedule.get('measurement') or {}).get('date'),
            'construction_date': (schedule.get('construction') or {}).get('date'),
            'manager_name': (parties.get('manager') or {}).get('name') or '-',
            'manager_phone': resolve_manager_phone_for_queue(
                parties, order=o, manager_phone_map=manager_phone_map
            ),
            'orderer_name': (parties.get('orderer') or {}).get('name') or None,
            'owner_team': responsible_team,
            'stage': stage,
            'stage_code': stage_code,
            'alerts': alerts,
            'has_media': has_media,
            'attachments_count': cnt,
            'recommended_owner_team': recommend_owner_team(sd) or None,
            'current_quest': quest_payload,
            'stage_badge_modifier': stage_badge_modifier(stage),
            'stage_badge_label': stage_badge_label(stage),
            'product_subtitle': product_subtitle_from_sd(sd),
            'role_assignees': resolve_order_role_assignees(sd, order=o, user_map=user_map),
        })
    return enriched
