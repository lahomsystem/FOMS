"""주문 대시보드 파이프라인 막대 순서 == 메인 파이프라인 정본 순서.

``process_steps`` 가 손으로 쓴 목록이라 완료가 CS 앞에 서 있었다(2026-02 대규모 업데이트
이후 방치). 실제 전이는 시공 → CS → 완료(``MAIN_PIPELINE_CODES``)이므로 막대도 따라야 한다.
"""

from __future__ import annotations

from db import db_session
from foms.services.orders.dashboard_read_model import compute_orders_summary_slice
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from foms.services.orders.stage_override import MAIN_PIPELINE_CODES
from models import Order


def test_process_steps_follow_main_pipeline_order(client) -> None:
    summary = compute_orders_summary_slice(db_session.query(Order))
    labels = [step["label"] for step in summary["process_steps"]]

    expected = [STAGE_LABELS[code] for code in MAIN_PIPELINE_CODES] + [STAGE_LABELS["AS"]]
    assert labels == expected
