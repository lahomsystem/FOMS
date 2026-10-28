"""이력 탭 '내 담당만' 칩 (2026-10-28, SPEC `2026-10-28-naver-history-mine-filter`).

영업 사원이 이력 탭을 여는 이유는 **자기 고객의 결제 확인**이다. 목록이 전 직원 주문이면
이름을 하나씩 쳐야 했다. 이 파일이 무는 규율:

* 술어 = 붙은 주문의 **active SALES 담당**이 나인 집. released 옛 담당·남의 담당·주문 없는
  수집분은 빠진다.
* 목록뿐 아니라 **칩 숫자**도 같은 술어로 좁힌다(한 화면 두 모집단 금지).
* 기본값: 영업팀 켜짐, ADMIN 꺼짐, 회계팀은 칩이 없다. ``mine=0/1`` 이 기본값을 이긴다.
* 다른 칩·찾기·쪽 넘김이 켜짐·꺼짐을 들고 간다.
"""

from __future__ import annotations

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from models import ExternalOrderLink, Order, OrderAssignment

from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _uid,
    workbench_on,
)

TRIAGE_PATH = "/admin/naver-ingest/triage"


def _history_tbody(body: str) -> str:
    return body.split('class="wb-cmp wb-hist"')[1].split("<tbody>")[1].split("</tbody>")[0]


def _filters(body: str) -> str:
    return body.split('<div class="wb-filters">')[1].split("</div>")[0]


def _owned(order_no: str, product: str, owner_id: int | None, *, active: bool = True,
           place_status: str = "OK") -> ExternalOrderLink:
    """FOMS 주문이 붙은 집 1건 — ``owner_id`` 가 있으면 그 사람을 SALES 담당으로 단다."""
    seq = _uid()
    order = Order(received_date="2026-10-01", customer_name=f"고객{seq}",
                  phone=f"010-5{seq.zfill(3)[-3:]}-0000",
                  address=f"서울 강남구 {seq}", product=product, status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    link = _collected(order_no=order_no, product=product, amount=100_000,
                      address=f"서울 강남구 {seq}", tel=f"010-7{seq.zfill(3)[-3:]}-0000",
                      place_status=place_status)
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    if owner_id is not None:
        db_session.add(OrderAssignment(
            order_id=order.id, domain="SALES", user_id=owner_id, source="SELF_CLAIM",
            active=active, assigned_at=now_utc_naive(), assigned_by_user_id=owner_id))
    db_session.commit()
    return row


def _other_sales_user_id() -> int:
    from werkzeug.security import generate_password_hash

    from models import User

    other = User(username=f"wb_other_{_uid()}", password=generate_password_hash("pw"),
                 role="MANAGER", team="SALES", name="다른 영업", is_active=True)
    db_session.add(other)
    db_session.commit()
    return int(other.id)


def test_sales_sees_only_own_customers_by_default(client, workbench_on):
    """영업팀은 인자 없이 들어와도 **내 담당만** 보인다 — 남의 담당·옛 담당·주문 없는 집은 빠진다."""
    me = _login(client, role="MANAGER", team="SALES")
    other_id = _other_sales_user_id()
    _owned("N-MINE-1", "내 붙박이장", me.id)
    _owned("N-MINE-2", "남 붙박이장", other_id)
    _owned("N-MINE-3", "옛 담당 붙박이장", me.id, active=False)
    _collected(order_no="N-MINE-4", product="주문 없는 붙박이장", amount=100_000,
               address="부산 해운대 9", tel="010-9999-0009")

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    tbody = _history_tbody(body)

    assert "내 붙박이장" in tbody
    for gone in ("남 붙박이장", "옛 담당 붙박이장", "주문 없는 붙박이장"):
        assert gone not in tbody, gone
    chips = _filters(body)
    assert 'aria-pressed="true"' in chips.split("내 담당만")[0].rsplit("<a", 1)[1]
    assert "전체 1주문" in chips, "칩 숫자도 내 담당으로 좁혀야 한다"


def test_mine_off_shows_everyone_and_keeps_off_across_chips(client, workbench_on):
    """끄면 전체가 보이고, 다른 칩·찾기 폼이 `mine=0` 을 들고 간다(빠지면 다시 켜진다)."""
    me = _login(client, role="STAFF", team="SALES")
    _owned("N-MINE-OFF-1", "내 붙박이장", me.id)
    _owned("N-MINE-OFF-2", "남 붙박이장", _other_sales_user_id())

    body = client.get(f"{TRIAGE_PATH}?tab=all&mine=0").get_data(as_text=True)
    tbody = _history_tbody(body)

    assert "내 붙박이장" in tbody and "남 붙박이장" in tbody
    chips = _filters(body)
    assert "전체 2주문" in chips
    assert chips.count("mine=0") >= 4, "상태·네이버 칩이 꺼짐을 들고 가야 한다"
    mine_chip = chips.split("내 담당만")[0].rsplit("<a", 1)[1]
    assert "mine=" not in mine_chip, "다시 켜는 주소 = 기본값(인자 없음)"
    assert '<input type="hidden" name="mine" value="0">' in body


def test_mine_counts_follow_same_predicate(client, workbench_on):
    """'발주확인 남음' 칩 숫자도 내 담당 집만 센다."""
    me = _login(client, role="MANAGER", team="SALES")
    _owned("N-MINE-CNT-1", "내 발주 전", me.id, place_status="")
    _owned("N-MINE-CNT-2", "남 발주 전", _other_sales_user_id(), place_status="")

    on = _filters(client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True))
    off = _filters(client.get(f"{TRIAGE_PATH}?tab=all&mine=0").get_data(as_text=True))

    assert "발주확인 남음 · 취소 포함 1주문" in on
    assert "발주확인 남음 · 취소 포함 2주문" in off


def test_admin_sees_chip_off_by_default(client, workbench_on):
    """ADMIN 은 칩이 있되 꺼진 채 시작한다 — 켜면 자기 담당만."""
    me = _login(client, role="ADMIN", team="CS")
    _owned("N-MINE-ADM-1", "관리자 담당", me.id)
    _owned("N-MINE-ADM-2", "남 담당", _other_sales_user_id())

    body = client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True)
    assert "내 담당만" in _filters(body)
    assert "남 담당" in _history_tbody(body)

    on = _history_tbody(client.get(f"{TRIAGE_PATH}?tab=all&mine=1").get_data(as_text=True))
    assert "관리자 담당" in on and "남 담당" not in on


def test_accounting_has_no_mine_chip(client, workbench_on):
    """회계팀은 담당이 없어 칩이 없다 — `mine=1` 을 손으로 쳐도 전체를 본다."""
    _login(client, role="MANAGER", team="ACCOUNTING")
    _owned("N-MINE-ACC", "회계가 볼 집", _other_sales_user_id())

    body = client.get(f"{TRIAGE_PATH}?tab=all&mine=1").get_data(as_text=True)

    assert "내 담당만" not in _filters(body)
    assert "회계가 볼 집" in _history_tbody(body)
    assert 'name="mine"' not in body


def test_mine_empty_state_says_how_to_see_all(client, workbench_on):
    """내 담당이 0이면 '수집 이력이 없습니다' 는 거짓이다 — 끄는 길을 말한다."""
    _login(client, role="MANAGER", team="SALES")
    _owned("N-MINE-EMPTY", "남 담당", _other_sales_user_id())

    tbody = _history_tbody(client.get(f"{TRIAGE_PATH}?tab=all").get_data(as_text=True))

    assert "내 담당 네이버 주문이 없어요" in tbody
    assert "수집 이력이 없습니다" not in tbody
