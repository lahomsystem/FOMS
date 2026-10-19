"""지방 대시보드 '도면 작업실' 바로가기 노출 계약.

도면 단계 ERP 주문 행에만 링크가 붙는다. 작업실 상세는 ERP 주문만 열기 때문에
비ERP 주문과 다른 단계 주문에는 붙지 않아야 한다.
"""

from __future__ import annotations

from tests.domains.drawing_transfer_helpers import _create_order, _login, _make_user


def test_regional_dashboard_links_drawing_stage_order_to_workbench(client) -> None:
    user = _make_user(role="STAFF", team="SALES", username="regional-workbench-staff")
    _login(client, user)
    drawing = _create_order(stage="DRAWING", status="DRAWING", is_regional=True)
    measure = _create_order(stage="MEASURE", status="MEASURE", is_regional=True)
    legacy = _create_order(stage="DRAWING", status="DRAWING", is_regional=True, is_erp_order=False)

    body = client.get("/regional_dashboard").get_data(as_text=True)
    assert f'href="/erp/drawing-workbench/{drawing.id}"' in body
    assert f'href="/erp/drawing-workbench/{measure.id}"' not in body
    assert f'href="/erp/drawing-workbench/{legacy.id}"' not in body
