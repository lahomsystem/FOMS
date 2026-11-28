"""Canonical production API surface."""

from foms.api.production.orders import erp_orders_production_bp
from foms.api.production.factory_done import erp_orders_factory_done_bp  # 공장마다 제작 완료(2026-11-23 §4-14)
from foms.api.production.drawing_request import erp_orders_drawing_request_bp  # 공장 [도면 수정 요청](2026-11-25 N3, D4)
from foms.api.production.alarms import production_alarms_bp  # 생산 현장 알람 다시 받기(2026-11-28 §4-4 · 약속 7)
from foms.api.production.drawing_notes import production_drawing_notes_bp  # 생산 도면 펜 기록(2026-11-28 펜 기록 §8)
from foms.api.production.part_marks import production_part_marks_bp
import foms.api.production.part_marks_read  # noqa: F401,E402  # 같은 Blueprint 에 30초 받아 오기 GET 을 붙인다(P15-7)
import foms.api.production.part_history  # noqa: F401,E402  # 같은 Blueprint 에 바뀐 기록 목록 GET 을 붙인다(2026-11-23 §4-11)
import foms.api.production.part_sheet  # noqa: F401,E402  # 같은 Blueprint 에 PC 도면 목록 창 GET 을 붙인다(2026-11-24)

__all__ = ["erp_orders_drawing_request_bp", "erp_orders_factory_done_bp", "erp_orders_production_bp", "production_alarms_bp",
           "production_drawing_notes_bp", "production_part_marks_bp"]
