"""다축 read model projection 계약 fixture (STATE-MODEL-00).

각 case는 order 저장 형태(``order`` kwargs) → 기대 canonical 축(``axes``) + 기대 legacy
projection(``projection``)을 고정한다. :mod:`foms.services.orders.state_axes`의 read 계약이
바뀌면 이 fixture가 깨져 회귀를 잡는다. STATE-CORE-00 등 하류는 이 계약을 신뢰하고 소비한다.

``order``는 Order-like 속성(status/deleted_at/erp_stage_code/is_erp_order/structured_data)만
담는다 — DB 불필요(순수 read-only 파생).
"""
from __future__ import annotations

from typing import Any, Dict, List

# axes: {main, logistics, hold, as_status, deleted, construction}
PROJECTION_CASES: List[Dict[str, Any]] = [
    {
        "id": "main_received",
        "order": {
            "status": "RECEIVED",
            "is_erp_order": True,
            "structured_data": {"workflow": {"stage": "RECEIVED"}},
            "erp_stage_code": "RECEIVED",
        },
        "axes": {
            "main": "RECEIVED",
            "logistics": "NONE",
            "hold": "NONE",
            "as_status": "NONE",
            "deleted": "NONE",
            "construction": "NONE",
        },
        "projection": "RECEIVED",
    },
    {
        "id": "main_korean_label_stage",
        "order": {
            "status": "생산",
            "is_erp_order": True,
            "structured_data": {"workflow": {"stage": "생산"}},
            "erp_stage_code": "생산",
        },
        # 한글 라벨도 main 코드로 정규화된다.
        "axes": {
            "main": "PRODUCTION",
            "logistics": "NONE",
            "hold": "NONE",
            "as_status": "NONE",
            "deleted": "NONE",
            "construction": "NONE",
        },
        "projection": "PRODUCTION",
    },
    {
        "id": "logistics_overlay_preserves_stage",
        "order": {
            # legacy logistics overlay: status=SCHEDULED 이지만 workflow.stage는 main 보존
            "status": "SCHEDULED",
            "is_erp_order": True,
            "structured_data": {"workflow": {"stage": "PRODUCTION"}},
            "erp_stage_code": "PRODUCTION",
        },
        "axes": {
            "main": "PRODUCTION",
            "logistics": "SCHEDULED",
            "hold": "NONE",
            "as_status": "NONE",
            "deleted": "NONE",
            "construction": "NONE",
        },
        # 우선순위상 logistics가 main보다 앞 → projection=SCHEDULED (정상 overlay divergence)
        "projection": "SCHEDULED",
    },
    {
        "id": "logistics_canonical_shipment",
        "order": {
            "status": "PRODUCTION",
            "is_erp_order": True,
            "structured_data": {
                "workflow": {"stage": "PRODUCTION"},
                "shipment": {"logistics_status": "SHIPPED_PENDING"},
            },
            "erp_stage_code": "PRODUCTION",
        },
        # canonical shipment.logistics_status가 legacy status보다 우선
        "axes": {
            "main": "PRODUCTION",
            "logistics": "SHIPPED_PENDING",
            "hold": "NONE",
            "as_status": "NONE",
            "deleted": "NONE",
            "construction": "NONE",
        },
        "projection": "SHIPPED_PENDING",
    },
    {
        "id": "hold_legacy_status",
        "order": {
            "status": "ON_HOLD",
            "is_erp_order": True,
            "structured_data": {"workflow": {"stage": "PRODUCTION"}},
            "erp_stage_code": "PRODUCTION",
        },
        "axes": {
            "main": "PRODUCTION",
            "logistics": "NONE",
            "hold": "HELD",
            "as_status": "NONE",
            "deleted": "NONE",
            "construction": "NONE",
        },
        # hold가 logistics/main보다 우선 → ON_HOLD
        "projection": "ON_HOLD",
    },
    {
        "id": "hold_canonical_workflow",
        "order": {
            "status": "PRODUCTION",
            "is_erp_order": True,
            "structured_data": {
                "workflow": {"stage": "PRODUCTION", "hold": {"active": True, "reason": "자재 대기"}}
            },
            "erp_stage_code": "PRODUCTION",
        },
        "axes": {
            "main": "PRODUCTION",
            "logistics": "NONE",
            "hold": "HELD",
            "as_status": "NONE",
            "deleted": "NONE",
            "construction": "NONE",
        },
        "projection": "ON_HOLD",
    },
    {
        "id": "hold_canonical_released",
        "order": {
            "status": "ON_HOLD",
            "is_erp_order": True,
            "structured_data": {
                "workflow": {"stage": "PRODUCTION", "hold": {"active": False}}
            },
            "erp_stage_code": "PRODUCTION",
        },
        # canonical hold.active=False가 legacy ON_HOLD status를 이긴다(read model이 정본)
        "axes": {
            "main": "PRODUCTION",
            "logistics": "NONE",
            "hold": "NONE",
            "as_status": "NONE",
            "deleted": "NONE",
            "construction": "NONE",
        },
        "projection": "PRODUCTION",
    },
    {
        "id": "as_legacy_received",
        "order": {
            "status": "AS_RECEIVED",
            "is_erp_order": True,
            "structured_data": {"workflow": {"stage": "CS"}},
            "erp_stage_code": "CS",
        },
        "axes": {
            "main": "CS",
            "logistics": "NONE",
            "hold": "NONE",
            "as_status": "RECEIVED",
            "deleted": "NONE",
            "construction": "NONE",
        },
        "projection": "AS_RECEIVED",
    },
    {
        "id": "as_canonical_cycle_in_progress",
        "order": {
            "status": "CS",
            "is_erp_order": True,
            "structured_data": {
                "workflow": {"stage": "CS"},
                "as_lifecycle": {
                    "current_cycle_id": "c1",
                    "cycles": [
                        {
                            "cycle_id": "c1",
                            "transitions": [
                                {"seq": 1, "to": "RECEIVED"},
                                {"seq": 2, "to": "IN_PROGRESS"},
                            ],
                        }
                    ],
                },
            },
            "erp_stage_code": "CS",
        },
        "axes": {
            "main": "CS",
            "logistics": "NONE",
            "hold": "NONE",
            "as_status": "IN_PROGRESS",
            "deleted": "NONE",
            "construction": "NONE",
        },
        # AS가 logistics보다 우선, main보다 우선 → 'AS'(AS처리)
        "projection": "AS",
    },
    {
        "id": "delete_by_deleted_at",
        "order": {
            "status": "PRODUCTION",
            "deleted_at": "2026-07-01 10:00:00",
            "is_erp_order": True,
            "structured_data": {"workflow": {"stage": "PRODUCTION"}},
            "erp_stage_code": "PRODUCTION",
        },
        "axes": {
            "main": "PRODUCTION",
            "logistics": "NONE",
            "hold": "NONE",
            "as_status": "NONE",
            "deleted": "DELETED",
            "construction": "NONE",
        },
        # delete가 최우선
        "projection": "DELETED",
    },
    {
        "id": "delete_priority_over_hold_and_as",
        "order": {
            "status": "DELETED",
            "deleted_at": "2026-07-01 10:00:00",
            "is_erp_order": True,
            "structured_data": {
                "workflow": {"stage": "CS", "hold": {"active": True}},
                "as_lifecycle": {
                    "current_cycle_id": "c1",
                    "cycles": [{"cycle_id": "c1", "transitions": [{"to": "RECEIVED"}]}],
                },
            },
            "erp_stage_code": "CS",
        },
        "axes": {
            "main": "CS",
            "logistics": "NONE",
            "hold": "HELD",
            "as_status": "RECEIVED",
            "deleted": "DELETED",
            "construction": "NONE",
        },
        "projection": "DELETED",
    },
    {
        "id": "construction_attempt_ready",
        "order": {
            "status": "CONSTRUCTION",
            "is_erp_order": True,
            "structured_data": {
                "workflow": {"stage": "CONSTRUCTION"},
                "construction": {
                    "current_attempt_id": "a1",
                    "attempts": [{"attempt_id": "a1", "status": "READY"}],
                },
            },
            "erp_stage_code": "CONSTRUCTION",
        },
        "axes": {
            "main": "CONSTRUCTION",
            "logistics": "NONE",
            "hold": "NONE",
            "as_status": "NONE",
            "deleted": "NONE",
            "construction": "READY",
        },
        # construction run 축은 legacy projection에 참여하지 않음 → main
        "projection": "CONSTRUCTION",
    },
    {
        "id": "non_erp_legacy_status_only",
        "order": {
            "status": "MEASURED",
            "is_erp_order": False,
            "structured_data": None,
            "erp_stage_code": None,
        },
        # ERP가 아니면 workflow 없음 → status가 logistics overlay로 분류
        "axes": {
            "main": None,
            "logistics": "MEASURED",
            "hold": "NONE",
            "as_status": "NONE",
            "deleted": "NONE",
            "construction": "NONE",
        },
        "projection": "MEASURED",
    },
]


__all__ = ["PROJECTION_CASES"]
