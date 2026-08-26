"""T4 — "다시 읽기" 라우트·버튼 계약.

고정하는 계약:

* web 은 **큐에 넣기만** 한다 — 커머스API 등록 호출 IP 가 WORKER 것뿐이다.
* 큐를 못 쓰면 **503 + 사유**다. 조용히 성공한 척하지 않는다.
* 버튼은 **잠긴 주문에도 뜬다**. 취소·반품이 어디까지 갔는지를 보려고 누르는 버튼이라
  잠금이 이유가 되지 않는다(네이버에 쓰는 것이 없다).
* 폴링 지문(`rev`)이 **다시 읽기로도 뒤집힌다** — 안 그러면 눌러도 화면이 영원히 그대로다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, User

TRIAGE_PATH = "/admin/naver-ingest/triage"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


@pytest.fixture()
def workbench_on(monkeypatch):
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client) -> User:
    user = User(username=f"wb_ref_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _link(*, claim_status: str = "") -> ExternalOrderLink:
    external_id = f"PO-RF-{_uid()}"
    order_no = f"N-RF-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no, "ordererName": "김주문"},
        "productOrder": {
            "productOrderId": external_id, "productName": "붙박이장",
            "totalPaymentAmount": 594000, "placeOrderStatus": "OK",
            "claimStatus": claim_status or None,
            "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                                "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
        },
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="COLLECTED", external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             place_order_status="OK")
    db_session.add(link)
    db_session.commit()
    return link


def test_refresh_route_enqueues_and_returns_base_rev(app, client, workbench_on, monkeypatch):
    """web 은 큐에 넣고 바로 답한다 — 응답의 ``rev`` 는 **누르기 직전** 지문이다."""
    from foms.services.jobs import queue as jobs_queue

    _login(client)
    link_id = int(_link().id)
    calls: list[tuple] = []
    monkeypatch.setattr(jobs_queue, "enqueue_naver_refresh",
                        lambda link_id, actor: calls.append((link_id, actor)) or True)

    res = client.post(f"/admin/naver-ingest/{link_id}/refresh", json={})

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["data"]["queued"] is True
    assert body["data"]["rev"]
    assert calls and calls[0][0] == link_id


def test_refresh_route_says_so_when_queue_is_down(app, client, workbench_on, monkeypatch):
    """큐가 없으면 503 + 사유. 조용히 성공한 척하면 사람이 기다리다 놓친다."""
    from foms.services.jobs import queue as jobs_queue

    _login(client)
    link_id = int(_link().id)
    monkeypatch.setattr(jobs_queue, "enqueue_naver_refresh", lambda link_id, actor: False)

    res = client.post(f"/admin/naver-ingest/{link_id}/refresh", json={})

    assert res.status_code == 503
    assert res.get_json()["success"] is False
    assert "큐" in res.get_json()["error"]


def test_refresh_route_404_for_unknown_link(app, client, workbench_on):
    """없는 링크는 404 — 큐에 넣기 전에 멈춘다."""
    _login(client)
    res = client.post("/admin/naver-ingest/999999999/refresh", json={})
    assert res.status_code == 404


def test_refresh_button_is_shown_even_on_a_locked_order(app, client, workbench_on):
    """잠긴 주문에서 **더** 필요한 버튼이다 — 반품이 어디까지 갔는지 보려고 누른다."""
    _login(client)
    _link(claim_status="RETURN_REQUEST")
    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    assert 'id="wb-refresh"' in body
    assert "다시 읽기" in body


def test_poll_fingerprint_flips_when_only_the_read_axis_moves(app, client, workbench_on):
    """다시 읽기는 `fulfillment` 표식을 안 건드린다 — 그래도 지문이 바뀌어야 한다.

    안 바뀌면 화면이 "다시 읽기가 끝났다"를 영영 못 보고, 사용자에게는 눌러도 아무 일이
    없는 것으로 보인다.
    """
    from foms.web.admin.naver_ingest import _fulfillment_state

    _login(client)
    link = _link()
    with app.test_request_context():
        before = _fulfillment_state(db_session, link)["rev"]
    link.triage_state = {"claim_sync": {"refreshed_at": "2026-08-26T21:00:00"}}
    db_session.commit()
    with app.test_request_context():
        after = _fulfillment_state(db_session, link)["rev"]

    assert before != after
