"""NAVER-BULKDISPATCH-02 후속: **안 붙은 수집분을 화면이 짚는가** 계약.

2026-09-01 운영에서 실제로 밟았다. 주문 #5054(천화진)는 오늘 실측인데 발송 대상 목록에
없었다. 수집은 08-28 에 끝나 있었고(링크 5행) **주문에 붙지 않았을 뿐**이다.

발송 대상 판정의 유일한 축이 "링크가 그 주문에 붙어 있는가" 라서(주문의 `source` 표식은
오염분이 있어 못 쓴다), 안 붙은 집은 화면 어디에도 안 나타난다 — 사람은 그 집이 **빠진
줄도 모른다.** 결과 UI 가 고친 결함("화면이 침묵한다")과 같은 결이다.

그래서 이 파일이 재는 것은 ①안 붙은 짝을 찾아내는가 ②**엉뚱한 집을 안 짚는가**
③대상이 0인 날에도 말하는가 이다.

판정 축은 둘 — **전화**와 **네이버 수령인명 == ERP 고객명**(운영 규칙, 사용자 확정
2026-09-01). 주문자명은 축이 아니다: 운영 실데이터에 ``문기범/문유주``·``김유리/김병준``
처럼 수령인과 주문자가 갈리는 집이 있고, ERP 에 들어간 이름은 **수령인명 쪽**이었다.
"""

from __future__ import annotations

import pytest

from sqlalchemy.orm.attributes import flag_modified

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


def _loose(order_no: str, *, tel: str = PHONE, count: int = 1,
           receiver: str = "이수취", orderer: str = "김주문") -> ExternalOrderLink:
    """주문에 **안 붙은** 수집분(``order_id`` 가 비어 있다).

    Args:
        order_no: 네이버 묶음 주문번호.
        tel: 수취인 전화.
        count: 상품주문 행 수.
        receiver: 네이버 **수령인명**(운영 규칙상 ERP 고객명이 되는 자리).
        orderer: 주문자명(축이 아니다 — 갈리는 집을 시험하려고 따로 준다).

    Returns:
        마지막으로 만든 링크 행.
    """
    link = None
    for _ in range(count):
        link = _collected(order_no=order_no, product="붙박이장", amount=1_000_000, tel=tel)
        row = db_session.get(ExternalOrderLink, int(link.id))
        snapshot = dict(row.raw_snapshot or {})
        shipping = dict((snapshot.get("productOrder") or {}).get("shippingAddress") or {})
        shipping["name"] = receiver
        product_order = dict(snapshot.get("productOrder") or {})
        product_order["shippingAddress"] = shipping
        snapshot["productOrder"] = product_order
        snapshot["order"] = {**(snapshot.get("order") or {}), "ordererName": orderer}
        row.raw_snapshot = snapshot
        flag_modified(row, "raw_snapshot")
        db_session.commit()
        link = row
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


def test_receiver_name_matches_even_when_the_phone_differs(today):
    """**전화가 달라도 수령인명이 같으면 짚는다** — 운영 규칙(사용자 확정 2026-09-01).

    ERP 입력은 네이버 수령인명으로 한다. 전화만 축으로 쓰면 연락처를 다르게 적어 넣은
    집이 통째로 안 보인다.
    """
    order = _order_measured_today(today, customer="천화진")
    order_no = f"N-UL2-{_uid()}"
    _loose(order_no, tel="010-0000-1111", count=2, receiver="천화진")
    found = find_unlinked_matches(db_session, on_date=today)
    mine = [row for row in found if row["order_no"] == order_no]
    assert len(mine) == 1
    assert mine[0]["order_id"] == int(order.id)
    assert mine[0]["reason"] == "수령인명 일치", "어느 축으로 걸렸는지 말해야 한다"


def test_orderer_name_alone_is_not_a_match(today):
    """**주문자명만 같은 집은 안 짚는다** — 축은 수령인명이다.

    운영 실데이터에 ``문기범/문유주``·``김유리/김병준`` 처럼 둘이 갈리는 집이 있고,
    ERP 에 들어간 이름은 수령인명 쪽이었다. 주문자명을 축으로 쓰면 남의 주문을 짚는다.
    """
    _order_measured_today(today, customer="문유주", phone="010-7777-6666")
    order_no = f"N-UL2B-{_uid()}"
    _loose(order_no, tel="010-0000-2222", receiver="문기범", orderer="문유주")
    found = find_unlinked_matches(db_session, on_date=today)
    assert not [row for row in found if row["order_no"] == order_no]


def test_nothing_matches_when_neither_phone_nor_receiver_name_agree(today):
    """음성 대조군 — 전화도 수령인명도 다르면 안 짚는다.

    모집단 안(오늘 실측·링크 없음)에 있으면서 두 축이 다 어긋난 표본이라, 짚히면 그
    자체가 반증이다.
    """
    _order_measured_today(today, customer="천화진")
    order_no = f"N-UL2C-{_uid()}"
    _loose(order_no, tel="010-0000-1111", count=2, receiver="남의사람")
    found = find_unlinked_matches(db_session, on_date=today)
    assert not [row for row in found if row["order_no"] == order_no]


def test_phone_beats_name_in_the_stated_reason(today):
    """두 축이 다 맞으면 **더 강한 축**(전화)을 사유로 남긴다."""
    _order_measured_today(today, customer="천화진")
    order_no = f"N-UL2D-{_uid()}"
    _loose(order_no, receiver="천화진")
    found = find_unlinked_matches(db_session, on_date=today)
    mine = [row for row in found if row["order_no"] == order_no]
    assert mine and mine[0]["reason"] == "전화 일치"


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


# --------------------------------------------------------------------------- #
# 캡 함정 — 소급 수집분이 300칸을 다 차지해도 짚어야 한다 (NAVER-INGEST-BACKFILL)
# --------------------------------------------------------------------------- #

def test_match_survives_hundreds_of_newer_unlinked_links(today):
    """매칭 대상보다 **더 최신인** 미연결 수집분이 300행을 넘어도 그 집을 짚는다.

    예전에는 미연결 링크를 id 내림차순 300행만 훑었다. 과거 소급 수집으로 미연결이
    1,500행대가 되면 그 300칸을 소급분이 다 차지해 띠가 조용히 잘렸다 — 잘린 자리는
    "짚을 게 없다"와 구분되지 않는다.
    """
    from foms.services.integrations.naver_commerce.bulk_dispatch import UNLINKED_SCAN_CAP
    from foms.services.integrations.naver_commerce.ingest import _match_key_values

    order = _order_measured_today(today)
    order_no = f"N-CAP-{_uid()}"
    target = _loose(order_no, count=1)
    keys = _match_key_values(target.raw_snapshot)
    target.recipient_name = keys["recipient_name"]
    target.recipient_phone_digits = keys["recipient_phone_digits"]
    target.orderer_phone_digits = keys["orderer_phone_digits"]
    db_session.commit()

    # 그 뒤에 소급분(더 큰 id)을 캡보다 많이 쌓는다 — 전부 매칭 축이 다르다.
    for index in range(UNLINKED_SCAN_CAP + 20):
        db_session.add(ExternalOrderLink(
            channel="NAVER", external_id=f"PO-CAPOLD-{_uid()}-{index}",
            external_order_no=f"ORD-CAPOLD-{index}", sync_status="COLLECTED",
            raw_snapshot={"productOrder": {"productOrderId": f"PO-CAPOLD-{index}"}},
            recipient_name=f"옛손님{index}", recipient_phone_digits="01000000001",
            orderer_phone_digits="01000000001",
        ))
    db_session.commit()

    rows = find_unlinked_matches(db_session, on_date=today)
    assert [row["order_no"] for row in rows] == [order_no]


# --------------------------------------------------------------------------- #
# 못 보내는 건 갈래 — "원본이 없다" vs "네이버 주문이 아니다" (T8)
# --------------------------------------------------------------------------- #

def _set_coverage(start: str) -> None:
    """소급 수집이 훑은 구간을 기록해 둔다(백필 상태 = 커버리지 정본)."""
    from foms.services.integrations.naver_commerce import backfill as bf

    bf._write_state(db_session, {"requested_from": start + "T00:00:00+09:00",  # noqa: SLF001
                                 "requested_to": start + "T23:59:59+09:00", "rev": 1})
    db_session.commit()


def test_order_inside_coverage_without_origin_is_called_foreign(today):
    """수집이 훑은 구간 안인데 원본이 없으면 **네이버 주문이 아니다**라고 말한다."""
    from foms.services.integrations.naver_commerce.bulk_dispatch import (
        COVERAGE_MARGIN_DAYS, build_preview,
    )
    from datetime import date, timedelta

    _set_coverage("2026-01-01")
    received = (date.fromisoformat("2026-01-01")
                + timedelta(days=COVERAGE_MARGIN_DAYS + 1)).isoformat()
    order = _order_measured_today(today, customer="원본없음", phone="010-9999-0001")
    order.received_date = received
    db_session.commit()

    preview = build_preview(db_session, on_date=today)
    ids = [row["order_id"] for row in preview["foreign"]]
    assert int(order.id) in ids
    assert preview["coverage_from"] == "2026-01-01"


def test_order_before_coverage_is_called_unknown(today):
    """구간 밖이면 **모른다**고 말한다 — 원본을 받아 온 적이 없다."""
    from foms.services.integrations.naver_commerce.bulk_dispatch import build_preview

    _set_coverage("2026-08-01")
    order = _order_measured_today(today, customer="범위밖", phone="010-9999-0002")
    order.received_date = "2026-07-01"
    db_session.commit()

    preview = build_preview(db_session, on_date=today)
    assert int(order.id) in [row["order_id"] for row in preview["unknown"]]
    assert int(order.id) not in [row["order_id"] for row in preview["foreign"]]


def test_matched_order_is_not_called_unsendable(today):
    """붙일 짝이 있는 집은 '못 보낸다' 갈래에 넣지 않는다(두 줄이 같은 집을 말하면 안 된다)."""
    from foms.services.integrations.naver_commerce.bulk_dispatch import build_preview

    _set_coverage("2026-01-01")
    order = _order_measured_today(today)
    order.received_date = "2026-08-01"
    db_session.commit()
    _loose(f"N-UM-{_uid()}", count=1)

    preview = build_preview(db_session, on_date=today)
    assert preview["unlinked"] == 1
    assert int(order.id) not in [row["order_id"] for row in preview["foreign"]]
    assert int(order.id) not in [row["order_id"] for row in preview["unknown"]]


def test_without_backfill_nothing_is_called_foreign(today):
    """소급 수집을 안 돌렸으면 아무것도 '네이버 아님'으로 단정하지 않는다."""
    from foms.services.integrations.naver_commerce.bulk_dispatch import build_preview

    order = _order_measured_today(today, customer="커버리지없음", phone="010-9999-0003")
    order.received_date = "2026-08-20"
    db_session.commit()

    preview = build_preview(db_session, on_date=today)
    assert preview["foreign"] == []
    assert int(order.id) in [row["order_id"] for row in preview["unknown"]]
