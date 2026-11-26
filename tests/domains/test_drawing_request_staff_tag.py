"""도면 작업실 요청사항 칸 — 직원이 한 수정 요청 줄의 표 "수정 요청 · 영업"(사장님 2026-11-26 "도면이 볼 때 수정 요청 주체가 누군지").

공장 요청 줄 "수정 요청 · 공장"과 같은 꼴. 고객 요청은 지금 표("고객 요청 · 1차 · 카톡 답장") 그대로라 겹치지 않는다.
"""
from __future__ import annotations

import copy

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import Order

from foms.services.orders.drawing_revision_source import SOURCE_CUSTOMER, SOURCE_SALES, staff_request_tag
from tests.support.drawing_tab_send_pc_helpers import SALES_NAME, _order, _page, make_people


@pytest.fixture
def people():
    return make_people()


def test_tag_names_the_requesters_team_and_skips_customer_requests():
    assert staff_request_tag({"source": SOURCE_SALES}, "SALES") == "수정 요청 · 영업"
    assert staff_request_tag({}, "CS") == "수정 요청 · CS"  # 옛 기록(source 없음)도 직원 요청
    assert staff_request_tag({"source": SOURCE_CUSTOMER}, "SALES") == ""  # 고객 요청 표가 따로 있다
    assert staff_request_tag({}, None) == "" and staff_request_tag({}, " ") == ""  # 팀을 모르면 표 없음(지금 그대로)
    assert staff_request_tag({}, "DRAWING").startswith("수정 요청 · ") and staff_request_tag({}, "DRAWING") != "수정 요청 · DRAWING"


def _set_requester(order_id: int, user_id) -> None:
    """준비물의 수정 요청 기록에 요청한 사람 id 를 넣는다(실제 요청 API 는 늘 넣는다)."""
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    for event in sd["drawing_transfer_history"]:
        if event.get("action") == "REQUEST_REVISION":
            event["by_user_id"] = user_id
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def test_request_row_shows_staff_tag_from_the_requesters_team(client, people):
    oid = _order(people["drafter"]["id"], status="RETURNED")
    _set_requester(oid, people["sales"]["id"])
    soup = _page(client, people["drafter"], oid)  # 도면팀이 볼 때
    tags = [t.get_text(strip=True) for t in soup.select("[data-staff-tag]")]
    assert tags == ["수정 요청 · 영업"]
    row = soup.select_one("[data-staff-tag]").parent.get_text(" ", strip=True)
    assert row.startswith("수정 요청 · 영업") and row.endswith(SALES_NAME)  # 표 · 시각 · 요청한 사람
    assert "workbench-fix.css" in str(soup)  # 표 꼴(공장 요청 줄과 같은 CSS)이 실린다


def test_old_request_without_requester_id_keeps_todays_row(client, people):
    oid = _order(people["drafter"]["id"], status="RETURNED")  # 옛 기록 — 요청한 사람 id 없음
    soup = _page(client, people["drafter"], oid)
    assert not soup.select("[data-staff-tag]") and SALES_NAME in soup.get_text()
