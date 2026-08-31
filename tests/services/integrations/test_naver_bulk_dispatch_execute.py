"""NAVER-BULKDISPATCH-01 T4: 일괄 발송처리 **실행** 계약.

되돌릴 수 없는 조작이다. 그래서 이 파일이 재는 것은 "보내지는가"보다 **"보내지 말아야 할
것을 안 보내는가"** 와 **"보낸 사실을 정직하게 말하는가"** 쪽이 무겁다.

핵심 4가지:

1. **대상은 서버가 다시 계산한다** — 화면이 보낸 목록을 받지 않는다.
2. **막힌 집은 안 나간다** — 미리보기에는 사유와 함께 보이지만 실행에서는 빠진다.
3. **상한에 닿으면 잘린 사실을 말한다** — 조용한 절단은 "전부 보냈다"로 읽힌다.
4. **꺼져 있으면 아무것도 안 나간다** — 전역 킬스위치.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.integrations.naver_commerce.bulk_dispatch import BULK_DISPATCH_LIMIT
from models import ExternalOrderLink, Order, OrderScheduleDate

from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _uid,
)

BULK_PATH = "/admin/naver-ingest/bulk-dispatch"


@pytest.fixture()
def today() -> str:
    """오늘(KST).

    Returns:
        ``YYYY-MM-DD``.
    """
    return get_today_kst().strftime("%Y-%m-%d")


@pytest.fixture()
def bulk_on(monkeypatch):
    """전역 킬스위치를 켠다.

    Args:
        monkeypatch: pytest fixture.
    """
    monkeypatch.setenv("FOMS_NAVER_BULK_DISPATCH_ENABLED", "1")


@pytest.fixture()
def queue_spy(monkeypatch):
    """enqueue 를 가로채 **네이버로 아무것도 안 나가게** 하고 호출을 기록한다.

    실 enqueue 를 그대로 두면 테스트가 워커를 부르는 경로에 붙는다 — 되돌릴 수 없는
    조작의 테스트에서 그건 있을 수 없다.

    Args:
        monkeypatch: pytest fixture.

    Returns:
        ``(link_id, action)`` 튜플이 쌓이는 리스트.
    """
    calls: list[tuple[int, str]] = []

    def _fake(link_id, action, actor_user_id=None):
        calls.append((int(link_id), str(action)))
        return True

    import foms.services.jobs.queue as queue_module

    monkeypatch.setattr(queue_module, "enqueue_naver_fulfillment", _fake)
    return calls


def _target(today: str, *, customer: str = "김실측", **kwargs) -> int:
    """오늘 실측 + 네이버 링크가 붙은 주문 1건.

    Args:
        today: 오늘 날짜.
        customer: 고객명.
        **kwargs: :func:`_collected` 인자(``place_status`` 등).

    Returns:
        붙인 링크 id. **ORM 객체를 돌려주지 않는다** — 요청이 세션을 떼어내면
        ``link.id`` 접근이 DetachedInstanceError 로 죽는다.
    """
    order = Order(received_date=today, customer_name=customer, phone="010-5-6",
                  address="서울 강남구 테헤란로 1", product="붙박이장",
                  status="MEASURE", is_erp_order=True, measurement_completed=True,
                  measurement_date=today, erp_measurement_date=today,
                  structured_data={"schedule": {"measurement": {"date": today}}})
    db_session.add(order)
    db_session.commit()
    db_session.add(OrderScheduleDate(order_id=int(order.id), kind="measurement",
                                     date=today, source="beta_schedule"))
    db_session.commit()
    link = _collected(order_no=f"N-EX-{_uid()}", product="붙박이장",
                      amount=1_000_000, **kwargs)
    row = db_session.get(ExternalOrderLink, int(link.id))
    row.order_id = int(order.id)
    row.sync_status = "LINKED"
    db_session.commit()
    return int(row.id)


def test_sends_today_targets(client, bulk_on, queue_spy, today):
    """보낼 수 있는 집이 집마다 큐에 들어간다."""
    _login(client)
    link_id = _target(today)
    response = client.post(BULK_PATH, json={})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["queued"] == 1
    assert queue_spy == [(link_id, "dispatch")]


def test_blocked_household_is_not_sent(client, bulk_on, queue_spy, today):
    """**막힌 집은 안 나간다** — 미리보기에는 보이지만 실행에서는 빠진다."""
    _login(client)
    ok_id = _target(today, customer="김보냄")
    _target(today, customer="이막힘", place_status="")  # 발주확인 전
    response = client.post(BULK_PATH, json={})
    data = response.get_json()["data"]
    assert data["queued"] == 1
    assert queue_spy == [(ok_id, "dispatch")], "막힌 집이 큐에 들어가면 안 된다"


def test_client_supplied_ids_are_ignored(client, bulk_on, queue_spy, today):
    """**화면이 보낸 목록을 받지 않는다** — 서버가 다시 계산한다.

    화면이 낡았거나 조작됐을 때 그 목록이 그대로 네이버로 나가면 안 된다.
    """
    _login(client)
    link_id = _target(today)
    response = client.post(BULK_PATH, json={"link_ids": [999999], "date": "2020-01-01"})
    assert response.status_code == 200
    assert queue_spy == [(link_id, "dispatch")], "화면이 준 id 를 쓰면 안 된다"


def test_disabled_switch_sends_nothing(client, queue_spy, today):
    """킬스위치가 꺼져 있으면 404 이고 **아무것도 안 나간다**."""
    _login(client)
    _target(today)
    response = client.post(BULK_PATH, json={})
    assert response.status_code == 404
    assert queue_spy == []


def test_staff_cannot_execute(client, bulk_on, queue_spy, today):
    """STAFF 는 실행할 수 없다(ADMIN·MANAGER 만) — 읽기 전용 전체 다시 읽기보다 느슨할 수 없다."""
    _login(client, role="STAFF")
    _target(today)
    response = client.post(BULK_PATH, json={})
    assert response.status_code in (302, 403)
    assert queue_spy == []


def test_no_targets_returns_zero_without_touching_queue(client, bulk_on, queue_spy, today):
    """대상이 없으면 큐를 건드리지 않고 0으로 답한다."""
    _login(client)
    response = client.post(BULK_PATH, json={})
    assert response.status_code == 200
    assert response.get_json()["data"]["queued"] == 0
    assert queue_spy == []


def test_queue_outage_returns_503(client, bulk_on, monkeypatch, today):
    """큐가 통째로 죽으면 503 + 판매자센터 안내 — 조용히 성공이라고 말하지 않는다."""
    _login(client)
    _target(today)
    import foms.services.jobs.queue as queue_module

    monkeypatch.setattr(queue_module, "enqueue_naver_fulfillment",
                        lambda *a, **k: False)
    response = client.post(BULK_PATH, json={})
    assert response.status_code == 503
    assert "판매자센터" in response.get_json()["error"]


def test_truncation_is_reported(client, bulk_on, queue_spy, monkeypatch, today):
    """**상한에 닿으면 잘린 사실을 응답이 말한다** — 조용한 절단은 '전부 보냈다'로 읽힌다."""
    _login(client)
    for idx in range(3):
        _target(today, customer=f"고객{idx}")
    from foms.services.integrations.naver_commerce import bulk_dispatch as svc

    monkeypatch.setattr(svc, "BULK_DISPATCH_LIMIT", 2)
    response = client.post(BULK_PATH, json={})
    data = response.get_json()["data"]
    assert data["queued"] == 2
    assert data["total"] == 3
    assert data["truncated"] is True
    assert len(queue_spy) == 2


def test_limit_is_far_above_observed_daily_volume():
    """상한은 '평소엔 안 닿는 안전장치' 여야 한다.

    2026-08-31 운영 실측에서 하루 최대는 7집이었다. 상한이 그보다 조금 크기만 하면
    정상 운영에서 잘리고, 잘림은 사람이 봐야 하는 신호라 의미가 죽는다.
    """
    assert BULK_DISPATCH_LIMIT >= 35, "관측 최대(7집)의 5배 미만이면 안전장치가 아니다"
