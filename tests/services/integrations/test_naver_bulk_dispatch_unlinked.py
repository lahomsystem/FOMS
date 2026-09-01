"""NAVER-BULKDISPATCH-02 후속: **안 붙은 수집분을 화면이 짚는가** 계약.

2026-09-01 운영에서 실제로 밟았다. 주문 #5054(천화진)는 오늘 실측인데 발송 대상 목록에
없었다. 수집은 08-28 에 끝나 있었고(링크 5행) **주문에 붙지 않았을 뿐**이다.

발송 대상 판정의 유일한 축이 "링크가 그 주문에 붙어 있는가" 라서(주문의 `source` 표식은
오염분이 있어 못 쓴다), 안 붙은 집은 화면 어디에도 안 나타난다 — 사람은 그 집이 **빠진
줄도 모른다.** 결과 UI 가 고친 결함("화면이 침묵한다")과 같은 결이다.

그래서 이 파일이 재는 것은 ①안 붙은 짝을 찾아내는가 ②**전화가 다르면 안 짚는가**(동명이인
오붙임 방지) ③대상이 0인 날에도 말하는가 이다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.integrations.naver_commerce.bulk_dispatch import (
    build_preview,
    find_unlinked_matches,
)
from models import ExternalOrderLink, Order, OrderScheduleDate

from tests.services.integrations.test_naver_bulk_dispatch_select import (  # noqa: F401
    _fresh_db,
)
from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _uid,
    workbench_on,
)

TRIAGE_PATH = "/admin/naver-ingest/triage"
MEASUREMENT_PATH = "/erp/measurement"
PHONE = "010-5413-6252"


@pytest.fixture()
def today() -> str:
    """오늘(KST).

    Returns:
        ``YYYY-MM-DD``.
    """
    return get_today_kst().strftime("%Y-%m-%d")


def _order_measured_today(today: str, *, customer: str = "천화진",
                          phone: str = PHONE) -> Order:
    """오늘 실측 일정이 잡힌 ERP 주문 1건(네이버 링크는 안 붙인다).

    Args:
        today: 오늘 날짜 문자열.
        customer: 고객명.
        phone: 연락처.

    Returns:
        커밋된 주문 행.
    """
    order = Order(received_date=today, customer_name=customer, phone=phone,
                  address="경기 남양주시 와부읍 덕소로 97번길 101", product="붙박이장",
                  status="MEASURE", is_erp_order=True, measurement_completed=True,
                  measurement_date=today, erp_measurement_date=today,
                  structured_data={"schedule": {"measurement": {"date": today}}})
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date=today, source="beta_schedule"))
    db_session.commit()
    return order


def _loose(order_no: str, *, tel: str = PHONE, count: int = 1) -> ExternalOrderLink:
    """주문에 **안 붙은** 수집분(``order_id`` 가 비어 있다).

    Args:
        order_no: 네이버 묶음 주문번호.
        tel: 수취인 전화.
        count: 상품주문 행 수.

    Returns:
        마지막으로 만든 링크 행.
    """
    link = None
    for _ in range(count):
        link = _collected(order_no=order_no, product="붙박이장", amount=1_000_000, tel=tel)
    return link


# --------------------------------------------------------------------------- #
# 짚어내는가
# --------------------------------------------------------------------------- #

def test_unlinked_collection_is_matched_by_phone(today):
    """전화가 같은 안 붙은 수집분을 집 단위로 짚는다."""
    order = _order_measured_today(today)
    order_no = f"N-UL-{_uid()}"
    _loose(order_no, count=3)
    found = find_unlinked_matches(db_session, on_date=today)
    mine = [row for row in found if row["order_no"] == order_no]
    assert len(mine) == 1, "집 하나로 접혀야 한다"
    assert mine[0]["order_id"] == int(order.id)
    assert mine[0]["links"] == 3
    assert mine[0]["customer"] == "천화진"


def test_different_phone_is_not_claimed_as_a_match(today):
    """**전화가 다르면 안 짚는다** — 이름만 같은 동명이인을 붙이게 하면 안 된다.

    음성 대조군이다. 모집단 안(오늘 실측·링크 없음)에 있으면서 전화만 다른 표본이라,
    통과하면 그 자체가 반증이다.
    """
    _order_measured_today(today, customer="천화진")
    order_no = f"N-UL2-{_uid()}"
    _loose(order_no, tel="010-0000-1111", count=2)
    found = find_unlinked_matches(db_session, on_date=today)
    assert not [row for row in found if row["order_no"] == order_no]


def test_already_linked_order_is_not_listed(today):
    """이미 붙은 주문은 짚지 않는다 — 그 집은 발송 대상 목록에 이미 있다."""
    order = _order_measured_today(today)
    link = _loose(f"N-UL3-{_uid()}")
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    db_session.commit()
    assert find_unlinked_matches(db_session, on_date=today) == []


def test_order_measured_on_another_day_is_not_matched(today):
    """오늘 실측이 아닌 주문의 짝은 오늘 띠가 말하지 않는다."""
    order = Order(received_date=today, customer_name="천화진", phone=PHONE,
                  address="경기 남양주시 와부읍 덕소로 97번길 101", product="붙박이장",
                  status="MEASURE", is_erp_order=True)
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date="2026-01-02", source="beta_schedule"))
    db_session.commit()
    _loose(f"N-UL4-{_uid()}")
    assert find_unlinked_matches(db_session, on_date=today) == []


# --------------------------------------------------------------------------- #
# 대상이 0인 날에도 말하는가 — 이 결함의 핵심
# --------------------------------------------------------------------------- #

def test_strip_appears_even_when_there_is_nothing_to_send(today):
    """**보낼 게 하나도 없는 날에도 띠가 뜬다** — 안 붙은 게 그 이유일 수 있다.

    여기서 침묵하면 사람은 "오늘 네이버 건이 없구나"로 읽고 넘어간다. 실제로는 붙이기만
    하면 나갈 집이 기다리고 있다.
    """
    _order_measured_today(today)
    _loose(f"N-UL5-{_uid()}", count=5)
    preview = build_preview(db_session, on_date=today)
    assert preview["show"] is True
    assert preview["state"] == "none"
    assert preview["day_total"] == 0 and preview["count"] == 0
    assert preview["unlinked"] == 1
    assert preview["unlinked_rows"][0]["links"] == 5


def test_no_strip_when_there_is_neither_target_nor_unlinked(today):
    """붙일 것도 보낼 것도 없으면 띠는 여전히 안 뜬다(빈 띠를 만들지 않는다)."""
    _order_measured_today(today, customer="박예약", phone="010-9999-8888")
    preview = build_preview(db_session, on_date=today)
    assert preview["show"] is False
    assert preview["unlinked"] == 0


# --------------------------------------------------------------------------- #
# 화면
# --------------------------------------------------------------------------- #

def test_workbench_strip_points_at_the_unlinked_collection(client, workbench_on, today):
    """워크벤치 띠가 안 붙은 집과 붙을 주문을 **함께** 말한다."""
    _login(client)
    order_id = int(_order_measured_today(today).id)
    order_no = f"N-UL6-{_uid()}"
    _loose(order_no, count=2)
    body = client.get(f"{TRIAGE_PATH}?tab=work").get_data(as_text=True)
    assert "붙이면 대상이 되는 집 1집" in body
    assert order_no in body
    assert f"#{order_id} 천화진" in body


def test_measurement_strip_points_at_the_unlinked_collection(client, today):
    """실측 대시보드 띠도 같은 사실을 말한다 — 이 화면에는 길이 아예 없었다."""
    _login(client)
    order_id = int(_order_measured_today(today).id)
    _loose(f"N-UL7-{_uid()}", count=2)
    body = client.get(MEASUREMENT_PATH).get_data(as_text=True)
    assert "붙이면 대상이 되는 집 1집" in body
    assert f"#{order_id} 천화진" in body
    assert "주문에 안 붙은 네이버 수집분 1집" in body


def test_matching_reuses_the_candidate_key_extractor():
    """키 뽑기를 새로 짜지 않는다 — 붙이기 후보 화면과 **같은 함수**를 쓴다.

    정규화 규칙을 두 벌 두면 한쪽만 고쳐지는 날 두 화면이 다른 집을 짚는다.
    """
    import inspect

    from foms.services.integrations.naver_commerce import bulk_dispatch

    source = inspect.getsource(bulk_dispatch.find_unlinked_matches)
    assert "_snapshot_keys" in source
    assert "normalize_phone_digits" in source
