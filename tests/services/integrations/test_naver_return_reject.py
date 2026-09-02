"""T8-S3 — 네이버 반품 **거부** 계약.

설계서: `docs/specs/2026-08-31-naver-return-reject_SPEC.md`.

거부는 접수·승인과 **대상이 다르다**: 접수는 *우리가* 반품을 내는 것이고, 거부는 *고객이 낸*
요청을 되돌려보내는 것이다. 그리고 사유가 **코드가 아니라 문장**이라 화이트리스트로 거를 수
없다 — 그 문장이 구매자에게 그대로 간다.

그래서 이 파일이 무는 것은 넷이다.

* **문서에 적힌 것만 나간다** — body 는 ``rejectReturnReason`` 한 필드다(커머스API 공개
  문서 2026-09-01 원문). 없는 필드를 지어내 불가역 API 에 보내지 않는다. 게이트는 화면과
  라우트를 함께 닫는다 — 눌러도 안 나가는 버튼을 보여 주지 않는다.
* **빈 문장으로 불가역 API 를 때리지 않는다** — 화면·라우트·서비스 세 겹.
* **보류 걸린 건은 우리가 건드리지 않는다** — 승인과 같은 규율(안심케어 보류해제 금지).
* **보낸 문장이 남는다** — 상태·감사 로그·주문 이력. 분쟁에서 필요한 것은 요약이 아니다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce import fulfillment
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, OrderEvent, SecurityLog, User

REJECT_PATH = "/admin/naver-ingest/{link_id}/return-reject"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트 + 거부 게이트를 켠다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    monkeypatch.setenv("FOMS_NAVER_RETURN_REJECT_ENABLED", "1")
    yield


@pytest.fixture()
def queued(monkeypatch):
    """큐를 가로채 enqueue 인자를 그대로 붙잡는다(워커는 돌지 않는다)."""
    calls: list[dict] = []

    def _fake(link_id, reason, actor_user_id=None):
        calls.append({"link_id": int(link_id), "reason": reason,
                      "actor_user_id": actor_user_id})
        return True

    import foms.services.jobs.queue as queue_mod
    import foms.web.admin.naver_ingest as web_mod

    monkeypatch.setattr(queue_mod, "enqueue_naver_return_reject", _fake, raising=True)
    monkeypatch.setattr(web_mod, "enqueue_naver_return_reject", _fake, raising=False)
    return calls


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"wbrej_{role.lower()}_{_uid()}",
                password=generate_password_hash("pw"), role=role, team="CS",
                name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _link(*, claim: str = "RETURN_REQUEST", holdback: str = "",
          order_id: int | None = None, order_no: str = "",
          state: dict | None = None) -> ExternalOrderLink:
    """고객이 반품을 걸어 온 수집 링크 1건."""
    external_id = f"PO-REJ-{_uid()}"
    product_order = {"productOrderId": external_id, "productName": "로라 무몰딩 1cm",
                     "totalPaymentAmount": 900000}
    if claim:
        product_order["claimStatus"] = claim
        product_order["claimType"] = "RETURN"
    if holdback:
        product_order["holdbackStatus"] = holdback
    snapshot = {"order": {"orderId": order_no or f"N-REJ-{_uid()}"},
                "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="LINKED" if order_id else "COLLECTED",
                             external_order_no=snapshot["order"]["orderId"],
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             order_id=order_id, triage_state=state or {})
    db_session.add(link)
    db_session.commit()
    return link


def _order() -> int:
    order = Order(received_date="2026-06-01", customer_name="김반품",
                  phone="010-1111-2222", address="서울 강남구 1", product="붙박이장",
                  status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return int(order.id)


class _Client:
    """거부 호출을 기록하는 가짜 클라이언트(규격이 채워지기 전의 대역).

    ``get_product_orders`` 도 답한다 — 거부는 **보내기 직전에 지금 상태를 다시 묻고**
    (:func:`fulfillment.fresh_claim_statuses`, 감사 F10) 못 읽으면 아예 안 보낸다.
    기본 답은 "요청이 걸린 그대로"라 재조회가 없던 시절과 같은 경로를 탄다.
    ``fresh`` 로 네이버 쪽 상태를 바꿔 끼우면 낡은 스냅샷 사례를 만들 수 있다.
    """

    def __init__(self, *, fail: str = "", fresh: dict | None = None):
        self.calls: list[tuple[str, str]] = []
        self.fail = fail
        self.fresh = fresh or {}
        self.refetched: list[list[str]] = []

    def get_product_orders(self, product_order_ids):
        pids = [str(p) for p in product_order_ids]
        self.refetched.append(pids)
        return [{"productOrder": {"productOrderId": pid,
                                  "claimStatus": self.fresh.get(pid, "RETURN_REQUEST"),
                                  "claimType": "RETURN"}}
                for pid in pids]

    def reject_return_product_order(self, product_order_id, *, reason):
        self.calls.append((product_order_id, reason))
        if self.fail:
            raise RuntimeError(self.fail)
        return {"data": {"successProductOrderIds": [product_order_id],
                         "failProductOrderInfos": []}}


# --------------------------------------------------------------------------- #
# 1. 문서에 적힌 요청만 나간다
# --------------------------------------------------------------------------- #

class _Response:
    """requests.Response 최소 계약만 흉내낸다."""

    def __init__(self, payload: dict):
        self.status_code = 200
        self.text = ""
        self.headers: dict = {}
        self._payload = payload

    def json(self):
        return self._payload


class _Transport:
    """토큰과 거부 호출만 받는 최소 전송 — **네트워크를 타지 않는다**."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/v1/oauth2/token"):
            return _Response({"access_token": "tok", "expires_in": 10799})
        return _Response({"timestamp": "2026-09-01T00:00:00.000+09:00",
                          "traceId": "trace-1",
                          "data": {"successProductOrderIds": ["PO-1"],
                                   "failProductOrderInfos": []}})


def _wire_client():
    """전송을 주입한 진짜 클라이언트(서명·토큰은 돌지만 밖으로 안 나간다)."""
    import bcrypt

    from foms.services.integrations.naver_commerce.client import (
        MemoryTokenCache,
        NaverCommerceClient,
    )

    transport = _Transport()
    client = NaverCommerceClient("test-client-id",
                                 bcrypt.gensalt(rounds=4).decode("utf-8"),
                                 transport=transport,
                                 token_cache=MemoryTokenCache(),
                                 sleep=lambda _seconds: None)
    return client, transport


def test_client_sends_exactly_the_documented_request():
    """선로에 나가는 것이 **문서 그대로**여야 한다 (커머스API 공개 문서 2026-09-01 원문).

    요청 본문 표에 ``rejectReturnReason``(string, 필수) 한 줄이고 curl 예시에
    ``Content-Type: application/json`` 이 있다. 승인 때 `approvalData` 를 지어낼 뻔한
    자리라 **문서에 없는 필드가 하나라도 붙으면 빨강**이다.
    """
    client, transport = _wire_client()

    out = client.reject_return_product_order("PO-1", reason="  반품이 어렵습니다.  ")

    sent = [call for call in transport.calls if call[1].endswith("/claim/return/reject")]
    assert len(sent) == 1, transport.calls
    method, url, kwargs = sent[0]
    assert method == "POST"
    assert url.endswith(
        "/v1/pay-order/seller/product-orders/PO-1/claim/return/reject"), url
    # 필드는 정확히 하나 — 여분이 붙으면 그게 곧 지어낸 규격이다.
    assert kwargs.get("json") == {"rejectReturnReason": "반품이 어렵습니다."}
    assert kwargs.get("headers", {}).get("Content-Type") == "application/json"
    assert kwargs.get("data") is None, "문서는 JSON 본문을 적는다(form 아님)"
    # 응답은 접수·승인과 동형이라 호출자가 _split_result 를 그대로 쓴다.
    assert out["data"]["successProductOrderIds"] == ["PO-1"]
    assert "failProductOrderInfos" in out["data"]


def test_client_invents_no_reason_code():
    """사유는 **문장 하나**다 — 문서에 사유 *코드* 필드가 없다.

    판정은 docstring 이 아니라 코드 본문으로 한다(승인 계약과 같은 규율). 네이버는
    읽기 코드가 쓰기 코드보다 많아서, 관측값을 화이트리스트로 올리면 400 이 난다.
    """
    import ast
    import inspect

    from foms.services.integrations.naver_commerce.client import NaverCommerceClient

    source = inspect.getsource(NaverCommerceClient.reject_return_product_order)
    tree = ast.parse(source.lstrip())

    bodies = [node.value for node in ast.walk(tree)
              if isinstance(node, ast.keyword) and node.arg == "json_body"]
    assert len(bodies) == 1, "요청 본문은 한 자리에서만 만든다"
    assert isinstance(bodies[0], ast.Dict), "리터럴이어야 계약이 읽을 수 있다"
    assert {key.value for key in bodies[0].keys} == {"rejectReturnReason"}

    func = tree.body[0]
    lines = [ast.unparse(node)
             for node in (func.body[1:] if ast.get_docstring(func) else func.body)]
    assert not any("NotImplementedError" in line for line in lines), (
        "규격이 확인돼 막이 걷혔다")


def test_client_rejects_empty_input_before_anything_else():
    """빈 상품주문번호·빈 문장은 규격과 무관하게 먼저 막는다."""
    from foms.services.integrations.naver_commerce.client import NaverCommerceClient

    client = NaverCommerceClient.__new__(NaverCommerceClient)

    with pytest.raises(ValueError):
        client.reject_return_product_order("", reason="문장")
    with pytest.raises(ValueError):
        client.reject_return_product_order("PO-1", reason="   ")


def test_route_is_closed_while_the_gate_is_off(client, monkeypatch, queued):
    """게이트가 꺼져 있으면 라우트가 403 — 화면 버튼과 **같은 조건**이다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    monkeypatch.delenv("FOMS_NAVER_RETURN_REJECT_ENABLED", raising=False)
    _login(client)
    link = _link()

    response = client.post(REJECT_PATH.format(link_id=link.id),
                           json={"reason": "반품이 어렵습니다."})

    assert response.status_code == 403
    assert not queued, "게이트가 꺼졌는데 큐에 들어갔다"


def test_pane_hides_the_button_while_the_gate_is_off(client, monkeypatch):
    """게이트가 꺼져 있으면 **버튼 자체가 없다** — 눌러도 안 나가는 버튼은 거짓말이다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    monkeypatch.delenv("FOMS_NAVER_RETURN_REJECT_ENABLED", raising=False)
    _login(client)
    link = _link()

    body = client.get(f"/admin/naver-ingest/triage?tab=work&link_id={link.id}") \
        .get_data(as_text=True)

    assert 'id="wb-return-reject"' not in body
    assert 'id="wb-modal-return-reject"' not in body


# --------------------------------------------------------------------------- #
# 2. 화면 — 버튼과 모달이 같은 조건, 재진술 건수가 서버 술어와 같다
# --------------------------------------------------------------------------- #

def test_pane_offers_reject_when_the_customer_asked_for_one(client, workbench_on):
    """고객이 반품을 걸어 온 집에는 거부 버튼과 모달이 함께 뜬다."""
    _login(client)
    link = _link()

    body = client.get(f"/admin/naver-ingest/triage?tab=work&link_id={link.id}") \
        .get_data(as_text=True)

    assert 'id="wb-return-reject"' in body
    assert 'id="wb-modal-return-reject"' in body
    assert 'id="wb-reject-reason"' in body, "사유 입력칸이 없다"
    assert "구매자에게 그대로 전달됩니다" in body, "문장이 고객에게 간다는 사실을 안 말한다"
    assert "되돌릴 수 없습니다" in body


def test_pane_hides_reject_when_no_claim_is_pending(client, workbench_on):
    """반품 요청이 없는 집에는 거부가 없다 — 없는 요청을 거부할 수 없다."""
    _login(client)
    link = _link(claim="")

    body = client.get(f"/admin/naver-ingest/triage?tab=work&link_id={link.id}") \
        .get_data(as_text=True)

    assert 'id="wb-return-reject"' not in body


def test_pane_hides_reject_when_naver_put_it_on_hold(client, workbench_on):
    """보류 걸린 건은 버튼도 없다 — 보류는 우리가 풀지 않는다(안심케어 금지)."""
    _login(client)
    link = _link(holdback="HOLDBACK")

    body = client.get(f"/admin/naver-ingest/triage?tab=work&link_id={link.id}") \
        .get_data(as_text=True)

    assert 'id="wb-return-reject"' not in body


def test_modal_offers_fill_sentences_without_forcing_them(client, workbench_on):
    """상용구는 **채워 넣기 버튼**이다 — select 가 아니라 입력칸이 정본이다."""
    _login(client)
    link = _link()

    body = client.get(f"/admin/naver-ingest/triage?tab=work&link_id={link.id}") \
        .get_data(as_text=True)

    assert "wb-reject-fill" in body
    assert "<textarea" in body.replace("\n", "")
    for fill in fulfillment.RETURN_REJECT_FILLS:
        assert fill["label"] in body


# --------------------------------------------------------------------------- #
# 3. 라우트 — 권한·빈 문장·기록
# --------------------------------------------------------------------------- #

def test_staff_cannot_reject(client, workbench_on, queued):
    """실무자(STAFF)는 못 누른다 — 접수·승인보다 좁다(사용자 결정 2026-08-31)."""
    _login(client, role="STAFF")
    link = _link()

    response = client.post(REJECT_PATH.format(link_id=link.id),
                           json={"reason": "반품이 어렵습니다."})

    assert response.status_code in (302, 403)
    assert not queued


@pytest.mark.parametrize("role", ["ADMIN", "MANAGER"])
def test_admin_and_manager_can_reject(client, workbench_on, queued, role):
    """관리자·책임자는 누를 수 있다."""
    _login(client, role=role)
    link = _link()

    response = client.post(REJECT_PATH.format(link_id=link.id),
                           json={"reason": "시공이 완료된 건으로 반품이 어렵습니다."})

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["success"] is True
    assert queued and queued[-1]["reason"] == "시공이 완료된 건으로 반품이 어렵습니다."


def test_empty_reason_never_reaches_the_queue(client, workbench_on, queued):
    """빈 문장으로 불가역 API 를 때리지 않는다 — 라우트가 먼저 막는다."""
    _login(client)
    link = _link()

    response = client.post(REJECT_PATH.format(link_id=link.id), json={"reason": "   "})

    assert response.status_code == 400
    assert not queued


def test_reject_records_the_sentence_in_audit_and_order_history(client, workbench_on,
                                                                queued):
    """보낸 문장이 **감사 로그와 주문 이력 양쪽**에 남는다 — 분쟁의 유일한 방어선이다."""
    user_id = int(_login(client).id)
    order_id = _order()
    link = _link(order_id=order_id)
    sentence = "제품에 사용 흔적이 확인되어 반품 조건에 해당하지 않습니다."

    client.post(REJECT_PATH.format(link_id=link.id), json={"reason": sentence})

    db_session.expire_all()
    log = (db_session.query(SecurityLog)
           .filter(SecurityLog.action == "NAVER_INGEST_RETURN_REJECT_ENQUEUE")
           .order_by(SecurityLog.id.desc()).first())
    assert log is not None, "감사 로그가 없다"
    assert sentence in str(log.detail or ""), "보낸 문장이 감사 로그에 없다"

    event = (db_session.query(OrderEvent)
             .filter(OrderEvent.order_id == order_id,
                     OrderEvent.event_type == "NAVER_RETURN_REJECTED")
             .order_by(OrderEvent.id.desc()).first())
    assert event is not None, "주문 이력에 거부 표식이 없다"
    assert event.payload.get("reason") == sentence
    assert event.created_by_user_id == user_id


def test_order_history_sentence_quotes_what_we_sent():
    """주문 이력 문장이 **보낸 문장을 그대로** 싣는다(요약하면 쓸모를 잃는다)."""
    from foms.services.order_event_display import (
        generate_change_description,
        translate_event_type_to_korean,
    )

    text = translate_event_type_to_korean("NAVER_RETURN_REJECTED")
    sentence = generate_change_description(
        "NAVER_RETURN_REJECTED", "", "", "",
        {"reason": "시공이 완료된 건으로 원상 복구가 불가능하여 반품이 어렵습니다.",
         "external_order_no": "N-REJ-1", "product_order_count": 2})

    assert text and text != "기타 변경", "이벤트 라벨 미등재 — 주문 이력이 뭉갠다"
    assert "원상 복구가 불가능하여" in sentence
    assert "N-REJ-1" in sentence


# --------------------------------------------------------------------------- #
# 4. 서비스 — 술어·멱등·부분 실패
# --------------------------------------------------------------------------- #

def test_service_rejects_only_the_rows_with_a_pending_request():
    """요청이 걸린 행만 보낸다 — 화면 재진술과 **같은 술어**다."""
    link = _link()
    sibling = _link(claim="", order_no=link.external_order_no)
    sibling.group_key = link.group_key
    db_session.commit()
    fake = _Client()

    result = fulfillment.reject_return(db_session, fake, link_id=int(link.id),
                                       reason="반품이 어렵습니다.", actor_user_id=1)
    db_session.commit()

    assert result["rejected"] == [link.external_id]
    assert [pid for pid, _ in fake.calls] == [link.external_id]


@pytest.mark.parametrize("claim", ["RETURN_REQUEST", "COLLECTING"])
def test_document_opens_request_and_collecting(claim):
    """문서가 연 상태는 둘이다 — "반품요청·수거중 상태를 반품철회로 전이"(2026-09-01 원문).

    ``COLLECTING`` 은 규격 확인 전까지 닫아 뒀던 자리다. 흐름도의 R-2(거부) 분기도 1단계
    ``RETURN_REQUEST``/``COLLECTING`` 에서만 갈라진다.
    """
    link = _link(claim=claim)

    assert fulfillment.is_return_rejectable(link) is True


@pytest.mark.parametrize("claim", ["COLLECT_DONE", "RETURN_DONE", "RETURN_REJECT"])
def test_states_the_document_does_not_open_stay_closed(claim):
    """수거 완료·반품 완료·이미 거부된 건은 **열지 않는다** (음성 대조군).

    문서 서술이 거부 용례로 "회수된 상품에 문제"를 들지만, 상태 전이를 **규정한** 문장과
    흐름도는 둘 다 수거완료를 거부 출발점으로 적지 않는다. 불가역 경로에서는 서술이 아니라
    규정을 따른다 — 400 을 받아 보며 배우지 않는다. ``COLLECT_DONE`` 은 승인
    (:data:`RETURN_APPROVABLE_STATUSES`)에는 열려 있어, 이 셋은 모집단 안의 대조군이다.
    """
    link = _link(claim=claim)

    assert fulfillment.is_return_rejectable(link) is False


def test_screen_and_server_share_the_widened_set(client, workbench_on):
    """수거중 건도 **화면 버튼이 뜬다** — 술어가 한 벌이라 자동으로 따라와야 한다."""
    _login(client)
    link = _link(claim="COLLECTING")

    body = client.get(f"/admin/naver-ingest/triage?tab=work&link_id={link.id}")         .get_data(as_text=True)

    assert 'id="wb-return-reject"' in body


def test_service_refuses_an_empty_sentence():
    """서비스도 빈 문장을 막는다(라우트를 우회한 호출에도 마지막 문이 있다)."""
    link = _link()
    fake = _Client()

    with pytest.raises(fulfillment.FulfillmentError):
        fulfillment.reject_return(db_session, fake, link_id=int(link.id), reason="  ")

    assert fake.calls == []


def test_service_never_touches_a_held_back_claim():
    """보류 걸린 건은 부르지 않는다 — 우리가 보류를 풀지 않는다."""
    link = _link(holdback="HOLDBACK")
    fake = _Client()

    with pytest.raises(fulfillment.FulfillmentError):
        fulfillment.reject_return(db_session, fake, link_id=int(link.id),
                                  reason="반품이 어렵습니다.")

    assert fake.calls == []


def test_service_is_idempotent():
    """두 번 눌러도 한 번만 나간다 — 표식은 우리 것으로만 판정한다."""
    link = _link()
    fake = _Client()

    fulfillment.reject_return(db_session, fake, link_id=int(link.id),
                              reason="반품이 어렵습니다.")
    db_session.commit()
    with pytest.raises(fulfillment.FulfillmentError):
        fulfillment.reject_return(db_session, fake, link_id=int(link.id),
                                  reason="반품이 어렵습니다.")

    assert len(fake.calls) == 1


def test_service_writes_the_sentence_on_the_row():
    """상태에 **문장 원문**이 남는다(요약하지 않는다)."""
    link = _link()
    sentence = "반품 가능 기간이 지나 단순 변심에 의한 반품이 어렵습니다."

    fulfillment.reject_return(db_session, _Client(), link_id=int(link.id),
                              reason=sentence, actor_user_id=7)
    db_session.commit()

    db_session.expire_all()
    state = (db_session.get(ExternalOrderLink, int(link.id)).triage_state or {}).get("return")
    assert state["reject_reason"] == sentence
    assert state["rejected_at"] and state["rejected_by"] == 7


def test_service_records_the_failure_reason():
    """호출이 실패하면 사유가 DB 에 남는다 — 로그·RQ 에만 남기지 않는다."""
    link = _link()
    fake = _Client(fail="네이버 400: 처리 권한 없음")

    with pytest.raises(fulfillment.FulfillmentError) as exc:
        fulfillment.reject_return(db_session, fake, link_id=int(link.id),
                                  reason="반품이 어렵습니다.")
    db_session.commit()

    assert "처리 권한 없음" in str(exc.value)
    db_session.expire_all()
    row = db_session.get(ExternalOrderLink, int(link.id))
    assert "처리 권한 없음" in str(row.triage_state)


def test_reject_is_followed_by_a_refresh():
    """거부 뒤 그 집을 다시 읽는다 — 불가역 경로에서 재조회는 확인이다(T3 규율)."""
    from foms.services.jobs.tasks import REFRESH_AFTER_ACTIONS

    assert "return-reject" in REFRESH_AFTER_ACTIONS


# --------------------------------------------------------------------------- #
# 5. 상용구 문장 — 회사 전체가 같이 쓰고, 관리자만 고친다 (2026-09-01)
# --------------------------------------------------------------------------- #

TEMPLATES_PATH = "/admin/naver-ingest/reject-templates"


def test_default_sentences_show_until_someone_saves(workbench_on):
    """저장한 적이 없으면 코드 기본 5종이 보인다 — DB 에 미리 심지 않는다."""
    from foms.services.integrations.naver_commerce.reject_templates import load_templates

    rows = load_templates(db_session)

    assert [r["label"] for r in rows] == [f["label"] for f in fulfillment.RETURN_REJECT_FILLS]


def test_admin_saves_a_sentence_for_everyone(client, workbench_on):
    """관리자가 저장하면 **모두의 화면**이 그 목록을 쓴다(전역 저장)."""
    from foms.services.integrations.naver_commerce.reject_templates import load_templates

    _login(client, role="ADMIN")
    body = {"templates": [{"label": "우리 문장", "text": "이 건은 반품이 어렵습니다."}],
            "version": 0}

    response = client.post(TEMPLATES_PATH, json=body)

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["data"]["version"] == 1
    db_session.expire_all()
    assert load_templates(db_session) == [{"label": "우리 문장",
                                           "text": "이 건은 반품이 어렵습니다."}]


def test_manager_can_reject_but_cannot_edit_the_list(client, workbench_on):
    """책임자는 거부는 눌러도 **문장은 못 고친다**(사용자 결정 2026-09-01)."""
    _login(client, role="MANAGER")

    response = client.post(TEMPLATES_PATH,
                           json={"templates": [{"label": "x", "text": "y"}], "version": 0})

    assert response.status_code in (302, 403)


def test_second_admin_cannot_silently_overwrite(client, workbench_on):
    """관리자 둘이 따로 저장하면 뒤에 누른 쪽을 막는다 — 조용한 덮어쓰기가 사고다."""
    _login(client, role="ADMIN")
    client.post(TEMPLATES_PATH, json={"templates": [{"label": "첫", "text": "첫 문장입니다."}],
                                      "version": 0})

    stale = client.post(TEMPLATES_PATH,
                        json={"templates": [{"label": "둘", "text": "둘째 문장입니다."}],
                              "version": 0})

    assert stale.status_code == 409
    assert stale.get_json()["data"]["version"] == 1


def test_saving_rejects_an_empty_list(client, workbench_on):
    """빈 목록으로 덮어쓰지 않는다 — 화면에 기본 문장이 되살아나 '지웠다'와 뜻이 갈린다."""
    _login(client, role="ADMIN")

    response = client.post(TEMPLATES_PATH, json={"templates": [], "version": 0})

    assert response.status_code == 400


def test_saved_sentence_cannot_exceed_the_send_limit():
    """저장 상한과 **보낼 때 상한이 같다** — 저장은 되고 보낼 때 잘리면 안 된다."""
    from foms.services.integrations.naver_commerce.reject_templates import sanitize_templates

    too_long = "가" * (fulfillment.RETURN_REJECT_REASON_MAX + 1)

    assert sanitize_templates([{"label": "긴 문장", "text": too_long}]) == []


def test_same_label_overwrites_instead_of_piling_up():
    """같은 이름으로 저장하면 덮어쓴다 — 같은 이름 버튼이 두 개 나오지 않는다."""
    from foms.services.integrations.naver_commerce.reject_templates import sanitize_templates

    rows = sanitize_templates([{"label": "제작", "text": "옛 문장입니다."},
                               {"label": "제작", "text": "새 문장입니다."}])

    assert rows == [{"label": "제작", "text": "새 문장입니다."}]


def test_modal_shows_manage_controls_only_to_admin(client, workbench_on):
    """저장·지우기는 관리자에게만 보인다 — 책임자에게 보이면 눌렀다가 403 을 받는다."""
    _login(client, role="MANAGER")
    link = _link()
    manager_body = client.get(f"/admin/naver-ingest/triage?tab=work&link_id={link.id}") \
        .get_data(as_text=True)

    _login(client, role="ADMIN")
    admin_body = client.get(f"/admin/naver-ingest/triage?tab=work&link_id={link.id}") \
        .get_data(as_text=True)

    assert 'id="wb-reject-save"' not in manager_body
    assert "wb-reject-drop" not in manager_body
    assert 'id="wb-reject-save"' in admin_body
    assert "wb-reject-drop" in admin_body


def test_audit_log_keeps_what_the_list_became(client, workbench_on):
    """저장 기록에 **문장 원문**이 남는다 — 고객이 받은 말의 뿌리다."""
    _login(client, role="ADMIN")
    sentence = "제작이 시작되어 반품이 어렵습니다."

    client.post(TEMPLATES_PATH, json={"templates": [{"label": "제작", "text": sentence}],
                                      "version": 0})

    db_session.expire_all()
    log = (db_session.query(SecurityLog)
           .filter(SecurityLog.action == "NAVER_INGEST_REJECT_TEMPLATES_SAVE")
           .order_by(SecurityLog.id.desc()).first())
    assert log is not None and sentence in str(log.detail or "")


# --------------------------------------------------------------------------- #
# F10 — 낡은 스냅샷으로 거부 문장을 보내지 않는다
# --------------------------------------------------------------------------- #

def test_reject_refetches_the_state_before_calling():
    """거부 직전에 네이버에 **지금 상태**를 다시 묻는다 (감사 F10).

    거부 문장은 구매자에게 그대로 가고 되돌릴 수 없다. 화면 술어가 보는 스냅샷은 수집
    시점 사실이라, 그사이 구매자가 반품을 철회했으면 우리는 없는 요청을 거부하게 된다.
    """
    link = _link()
    client = _Client()

    fulfillment.reject_return(db_session, client, link_id=int(link.id),
                              reason="제작이 이미 시작됐습니다.")
    db_session.commit()

    assert client.refetched == [[link.external_id]], "보내기 전에 다시 묻지 않았다"
    assert [pid for pid, _ in client.calls] == [link.external_id]


def test_a_withdrawn_return_is_not_rejected_even_though_the_snapshot_says_so():
    """스냅샷은 `RETURN_REQUEST` 인데 네이버는 이미 다른 상태 — **부르지 않는다**.

    조용히 빼지 않는다: 사유를 실패로 남기고 예외를 올린다(빈 대상을 성공으로 돌려주는
    것이 NVCLAIM-ORDER-01 사고의 결함 그 자체였다).
    """
    link = _link()
    client = _Client(fresh={link.external_id: "RETURN_DONE"})

    with pytest.raises(fulfillment.FulfillmentError) as err:
        fulfillment.reject_return(db_session, client, link_id=int(link.id),
                                  reason="제작이 이미 시작됐습니다.")
    db_session.commit()

    assert client.calls == [], "낡은 스냅샷으로 구매자에게 거부 문장을 보냈다"
    assert "상태가 아닙니다" in str(err.value)
    assert "RETURN_DONE" in str(err.value)


def test_a_failed_refetch_stops_the_rejection():
    """상태를 **못 읽으면 부르지 않는다** — 모르면 불가역 호출을 열지 않는다."""
    link = _link()

    class _ReadFails(_Client):
        def get_product_orders(self, product_order_ids):
            raise RuntimeError("HTTP 500 일시 오류")

    client = _ReadFails()
    with pytest.raises(fulfillment.FulfillmentError) as err:
        fulfillment.reject_return(db_session, client, link_id=int(link.id),
                                  reason="제작이 이미 시작됐습니다.")
    db_session.commit()

    assert client.calls == [], "상태를 모르는 채로 거부 문장을 보냈다"
    assert "읽지 못했습니다" in str(err.value)
