"""도면 작업실 파이프라인 bar 칸 계약 (사용자 결정 2026-09-30).

운영 증상: 칸 숫자 합(122)이 '전체'(84)보다 컸다. '완료' 칸이 단계와 무관한 전체 수령확정
수로 덮어써지는데 '전체'는 목록 행 수(len(rows))였고, 도면 단계에 남은 수령확정 주문도
'전체'에 섞였다. 또 담당 지정 없이 마법사에 그리기만 해 둔 주문은 '대기중'에 남았다.

잠그는 계약:
- '전체' = 열린 큐 네 칸(대기중·작업중·수정요청·확정대기)의 합. 컨펌 포함·검색과 무관.
- '누적 완료'는 따로 뗀 칸 — '전체'에 더하지 않는다. 최상위 ``drawing_status`` 우선 판정.
- 작업중 = PENDING/IN_PROGRESS 이면서 담당 지정 **또는** 마법사 저장 작업(객체 있는 시트
  또는 전달 대기) 있음. 칸 숫자와 상태 필터는 같은 판정(``_workbench_bucket``)을 쓴다.
- 모르는 상태값은 대기중으로 떨어진다.
"""
from __future__ import annotations

import datetime
import re

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache as dc
from foms.web.drawing.workbench import (
    WORKBENCH_OPEN_BUCKETS,
    _drawing_row_status_label,
    _drawing_wizard_has_saved_work,
    _workbench_bucket,
)
from models import Order, User

_AT = datetime.datetime(2026, 3, 5, 9, 0, 0)

_SHEET_WITH_WORK = {"v": 1, "sheets": [{"id": "s1", "objects": [{"type": "rect"}]}], "pending": {}}
_SHEET_EMPTY = {"v": 1, "sheets": [{"id": "s1", "objects": []}], "pending": {}}
_PENDING_ONLY = {"v": 1, "sheets": [], "pending": {"s1": {"key": "orders/1/x.png"}}}


@pytest.fixture(autouse=True)
def _reset_cache_runtime(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    dc.reset_dashboard_cache_runtime_for_tests()
    yield
    dc.reset_dashboard_cache_runtime_for_tests()


# --- 순수 판정 단위 ------------------------------------------------------------


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"drawing_status": "PENDING", "no_assignee": True}, "WAITING"),
        ({"drawing_status": "PENDING", "no_assignee": False}, "IN_PROGRESS"),
        ({"drawing_status": "PENDING", "no_assignee": True, "has_saved_work": True}, "IN_PROGRESS"),
        ({"drawing_status": "IN_PROGRESS", "no_assignee": True, "has_saved_work": True}, "IN_PROGRESS"),
        ({"drawing_status": "IN_PROGRESS", "no_assignee": True}, "WAITING"),
        ({"drawing_status": "RETURNED", "no_assignee": True, "has_saved_work": True}, "RETURNED"),
        ({"drawing_status": "TRANSFERRED", "no_assignee": False}, "TRANSFERRED"),
        ({"drawing_status": "CONFIRMED", "no_assignee": False}, "CONFIRMED"),
        ({"drawing_status": "confirmed", "no_assignee": False}, "CONFIRMED"),
        # 모르는 상태값·빈 값은 담당·작업이 있어도 대기중 — 네 칸 합 == 전체 보장.
        ({"drawing_status": "FOO", "no_assignee": False, "has_saved_work": True}, "WAITING"),
        ({"drawing_status": "", "no_assignee": True}, "WAITING"),
    ],
)
def test_workbench_bucket(row, expected):
    assert _workbench_bucket(row) == expected


def test_every_bucket_is_open_or_confirmed():
    for status in ("PENDING", "IN_PROGRESS", "RETURNED", "TRANSFERRED", "CONFIRMED", "NONE", "X"):
        for no_assignee in (True, False):
            b = _workbench_bucket({"drawing_status": status, "no_assignee": no_assignee})
            assert b in WORKBENCH_OPEN_BUCKETS or b == "CONFIRMED"


@pytest.mark.parametrize(
    ("sd", "expected"),
    [
        ({"drawing_wizard": _SHEET_WITH_WORK}, True),
        ({"drawing_wizard": _PENDING_ONLY}, True),
        # 음성 대조: 빈 캔버스만 저장·마법사 없음·깨진 형식은 작업 아님.
        ({"drawing_wizard": _SHEET_EMPTY}, False),
        ({"drawing_wizard": {"v": 1, "sheets": [], "pending": {}}}, False),
        ({}, False),
        ({"drawing_wizard": "broken"}, False),
        ({"drawing_wizard": {"sheets": "broken"}}, False),
    ],
)
def test_wizard_saved_work(sd, expected):
    assert _drawing_wizard_has_saved_work(sd) is expected


def test_row_label_follows_bucket():
    assert _drawing_row_status_label("IN_PROGRESS", "PENDING") == "작업중"
    assert _drawing_row_status_label("WAITING", "PENDING") == "대기중"
    assert _drawing_row_status_label("WAITING", "FOO") == "대기중"
    assert _drawing_row_status_label("RETURNED", "RETURNED") == "수정 요청됨"


# --- 라우트(칸 숫자·필터 목록) -----------------------------------------------


def _login_admin(client) -> User:
    user = User(
        username="drawing_pipe_admin",
        password=generate_password_hash("x"),
        role="ADMIN",
        team="DRAWING",
        name="도면관리",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _seed(
    idx: int,
    *,
    stage: str = "DRAWING",
    drawing_status: str | None = "PENDING",
    assignee_id: int | None = None,
    wizard: dict | None = None,
    nested_status: str | None = None,
) -> int:
    sd: dict = {
        "workflow": {"stage": stage},
        "parties": {
            "customer": {"name": f"파이프고객{idx}", "phone": f"010-7100-{idx:04d}"},
            "manager": {"name": "도면관리"},
        },
        "site": {"address_full": f"서울시 파이프구 {idx}"},
        "items": [{"product_name": "붙박이장", "spec_width": "1500"}],
        "drawing_assignees": [],
    }
    if drawing_status is not None:
        sd["drawing_status"] = drawing_status
    if nested_status is not None:
        sd["drawing"] = {"status": nested_status}
    if assignee_id is not None:
        sd["assignments"] = {"drawing_assignee_user_ids": [assignee_id]}
    if wizard is not None:
        sd["drawing_wizard"] = wizard
    order = Order(
        received_date="2026-03-05",
        customer_name=f"파이프고객{idx}",
        phone=f"010-7100-{idx:04d}",
        address=f"서울시 파이프구 {idx}",
        product="붙박이장",
        status="RECEIVED",
        manager_name="도면관리",
        is_erp_order=True,
        erp_stage_code=stage,
        structured_data=sd,
        created_at=_AT + datetime.timedelta(minutes=idx),
    )
    db_session.add(order)
    db_session.flush()
    return order.id


def _get(client, query: str = ""):
    resp = client.get(
        f"/erp/drawing-workbench?view=fragment{query}",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )
    assert resp.status_code == 200
    return resp.get_data(as_text=True)


def _tiles(body: str) -> dict[str, int]:
    pipeline = body.split('<div class="erp-pro-pipeline">', 1)[1].split('data-filter="overdue"', 1)[0]
    out = {}
    for key in ("", "WAITING", "IN_PROGRESS", "RETURNED", "TRANSFERRED", "CONFIRMED"):
        m = re.search(
            r'data-status="' + key + r'"[^>]*>\s*<div class="erp-pro-pipeline__count">(\d+)<',
            pipeline,
        )
        assert m, f"타일 {key or '전체'} 을 찾지 못했다"
        out[key or "TOTAL"] = int(m.group(1))
    return out


def _link(order_id: int) -> str:
    return f"/erp/drawing-workbench/{order_id}?tab=timeline"


@pytest.fixture
def seeded(client):
    user = _login_admin(client)
    ids = {
        "waiting": _seed(1),
        "assigned": _seed(2, assignee_id=user.id),
        "wizard_sheet": _seed(3, wizard=_SHEET_WITH_WORK),
        "wizard_empty": _seed(4, wizard=_SHEET_EMPTY),
        "wizard_pending": _seed(5, wizard=_PENDING_ONLY),
        "returned_outside": _seed(6, stage="PRODUCTION", drawing_status="RETURNED"),
        "transferred": _seed(7, drawing_status="TRANSFERRED"),
        "confirmed_in_drawing": _seed(8, drawing_status="CONFIRMED"),
        "confirmed_outside": _seed(9, stage="CONFIRM", drawing_status="CONFIRMED"),
        "unknown_status": _seed(10, drawing_status="FOO"),
        # 음성 대조: 도면 모집단 밖(실측 단계 PENDING)은 어떤 칸에도 안 들어간다.
        "outside_measure": _seed(11, stage="MEASURE"),
    }
    db_session.commit()
    return ids


_EXPECTED = {"TOTAL": 8, "WAITING": 3, "IN_PROGRESS": 3, "RETURNED": 1, "TRANSFERRED": 1, "CONFIRMED": 2}


def test_tiles_sum_to_total_and_confirmed_is_separate(client, seeded):
    tiles = _tiles(_get(client))
    assert tiles == _EXPECTED
    open_sum = tiles["WAITING"] + tiles["IN_PROGRESS"] + tiles["RETURNED"] + tiles["TRANSFERRED"]
    assert open_sum == tiles["TOTAL"]
    # 누적 완료를 더하면 전체를 넘는다 — 옛 버그(칸 합 > 전체)의 모양이 여기서 끊긴다.
    assert open_sum + tiles["CONFIRMED"] > tiles["TOTAL"]


@pytest.mark.parametrize(
    "query",
    ["&include_confirmed=1", "&q=파이프고객", "&status=CONFIRMED", "&status=IN_PROGRESS", "&q=파이프고객1"],
)
def test_total_is_stable_across_confirmed_modes_and_search(client, seeded, query):
    assert _tiles(_get(client, query)) == _EXPECTED


def test_default_list_excludes_confirmed_even_in_drawing_stage(client, seeded):
    body = _get(client)
    assert _link(seeded["confirmed_in_drawing"]) not in body
    assert _link(seeded["confirmed_outside"]) not in body
    # 양성 대조: 열린 큐 주문은 보인다.
    assert _link(seeded["waiting"]) in body
    assert _link(seeded["returned_outside"]) in body


def test_confirmed_filter_lists_confirmed_rows(client, seeded):
    body = _get(client, "&status=CONFIRMED")
    assert _link(seeded["confirmed_in_drawing"]) in body
    assert _link(seeded["confirmed_outside"]) in body
    assert _link(seeded["waiting"]) not in body


def test_in_progress_filter_lists_exactly_its_bucket(client, seeded):
    body = _get(client, "&status=IN_PROGRESS")
    for key in ("assigned", "wizard_sheet", "wizard_pending"):
        assert _link(seeded[key]) in body, f"{key} 가 작업중 목록에 없다"
    for key in ("waiting", "wizard_empty", "unknown_status", "transferred", "outside_measure"):
        assert _link(seeded[key]) not in body, f"{key} 가 작업중 목록에 섞였다"


def test_waiting_filter_lists_exactly_its_bucket(client, seeded):
    body = _get(client, "&status=WAITING")
    for key in ("waiting", "wizard_empty", "unknown_status"):
        assert _link(seeded[key]) in body, f"{key} 가 대기중 목록에 없다"
    for key in ("assigned", "wizard_sheet", "wizard_pending", "returned_outside"):
        assert _link(seeded[key]) not in body, f"{key} 가 대기중 목록에 섞였다"


def test_confirmed_count_reads_top_level_status_first(client):
    """최상위 RETURNED + 중첩 CONFIRMED 잔재 주문은 수정요청으로만 센다(이중 집계 금지)."""
    _login_admin(client)
    _seed(21, stage="PRODUCTION", drawing_status="RETURNED", nested_status="CONFIRMED")
    # 양성 대조: 최상위가 비고 중첩만 CONFIRMED 면 완료로 센다(목록 판정과 같은 폴백).
    _seed(22, stage="CONFIRM", drawing_status=None, nested_status="CONFIRMED")
    db_session.commit()
    tiles = _tiles(_get(client))
    assert tiles["RETURNED"] == 1
    assert tiles["CONFIRMED"] == 1
    assert tiles["TOTAL"] == 1
