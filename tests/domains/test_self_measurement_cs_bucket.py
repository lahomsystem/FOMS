"""자가실측 대시보드 — CS 단계 주문은 설치예정 섹션에 선다.

완료 버튼(cs/complete)은 설치예정 섹션에만 그려진다. CS 단계 주문이 진행 중 섹션에
남으면 완료할 수 있는 주문인데 버튼이 없는 막다른 길이 된다(주문 #5220 제보).
"""

from __future__ import annotations

import re

from tests.domains.drawing_transfer_helpers import _create_order, _login, _make_user

SCHEDULED_HEADING = "설치예정인 자가실측"


def _split_sections(html: str) -> tuple[str, str]:
    """(진행 중 섹션, 설치예정 섹션 이후) 로 나눈다."""
    idx = html.index(SCHEDULED_HEADING)
    return html[:idx], html[idx:]


def _row_present(section: str, order_id: int) -> bool:
    return f'<tr data-order-id="{order_id}"' in section


def _enabled_cs_complete(section: str, order_id: int) -> bool:
    for match in re.finditer(r"<button[^>]*js-complete-order[^>]*>", section):
        tag = match.group(0)
        if f'data-order-id="{order_id}"' in tag and 'data-complete-endpoint="cs_complete"' in tag:
            return True
    return False


def test_cs_stage_order_is_in_scheduled_section_with_complete_button(client) -> None:
    user = _make_user(role="STAFF", team="SALES", username="self-cs-bucket-staff")
    _login(client, user)
    cs_order = _create_order(stage="CS", status="CS", is_self_measurement=True)
    measure_order = _create_order(stage="MEASURE", status="MEASURE", is_self_measurement=True)

    resp = client.get("/self_measurement_dashboard")
    assert resp.status_code == 200
    pending, scheduled = _split_sections(resp.get_data(as_text=True))

    assert not _row_present(pending, cs_order.id), "CS 단계 주문이 진행 중 섹션에 남았다"
    assert _row_present(scheduled, cs_order.id), "CS 단계 주문이 설치예정 섹션에 없다"
    assert _enabled_cs_complete(scheduled, cs_order.id), "CS 단계 주문에 완료 버튼이 없다"

    # 음성 대조군: CS 이전 단계는 그대로 진행 중.
    assert _row_present(pending, measure_order.id)
    assert not _row_present(scheduled, measure_order.id)
