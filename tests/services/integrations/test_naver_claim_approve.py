"""T9 — 네이버 클레임 **승인**(취소·반품) 계약.

설계서: `docs/specs/2026-09-01-naver-claim-approve_SPEC.md`.
원장: `docs/plans/2026-09-01-naver-claim-approve-ledger.md`.

승인은 **환불 확정**이고 되돌리는 엔드포인트가 없다. 취소 쪽은 더 좁다 — 판매자가
취소를 **거절하는 API 자체가 존재하지 않는다**(철회는 구매자만 한다). 그래서 이 파일이
무는 것은 거부(T8-S3) 계약과 같은 규율 다섯이다.

* **문서에 적힌 것만 나간다** — 승인 두 갈래는 path 파라미터 하나로 동작하고 **본문이
  없다**. 2026-08-27 원장이 ``approvalData`` 를 지어낼 뻔한 자리라, 신규 메서드에도
  같은 AST 판정을 파라미터화해 건다.
* **게이트는 화면과 라우트를 함께 닫는다** — 눌러도 안 나가는 버튼을 보여 주지 않는다.
* **술어는 화면과 서버가 한 벌** — 재진술 건수가 실제로 보내는 건수와 같아야 한다.
  불가역 경로에서 과대 진술이 곧 사고다.
* **보류 걸린 건은 우리가 건드리지 않는다**(반품안심케어 보류해제 금지).
* **돈이 나간 사실이 남는다** — 감사 로그와 주문 이력 양쪽. 접수+승인과 **다른 이름**
  이어야 "이미 있던 반품을 승인한 것"이 원장에서 갈린다.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce import fulfillment
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, OrderEvent, SecurityLog, User

CANCEL_PATH = "/admin/naver-ingest/{link_id}/cancel-approve"
RETURN_PATH = "/admin/naver-ingest/{link_id}/return-approve"
PANE_PATH = "/admin/naver-ingest/triage?tab=work&link_id={link_id}"

#: 화면 버튼 id — 게이트 off 판정의 정본. 반품 승인 버튼이 ``-btn`` 을 다는 이유는
#: ``wb-return-approve`` 가 **접수 모달의 체크박스**(T8-S2)라 이름이 겹치기 때문이다.
CANCEL_BTN = 'id="wb-cancel-approve"'
RETURN_BTN = 'id="wb-return-approve-btn"'
CANCEL_CONFIRM = 'id="wb-cancel-approve-confirm"'
RETURN_CONFIRM = 'id="wb-return-approve-confirm"'

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


# --------------------------------------------------------------------------- #
# 대역·헬퍼 (거부 계약 파일과 같은 모양)
# --------------------------------------------------------------------------- #

@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트 + 승인 게이트 2종을 켠다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    monkeypatch.setenv("FOMS_NAVER_CANCEL_APPROVE_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_RETURN_APPROVE_ENABLED", "1")
    yield


@pytest.fixture()
def queued(monkeypatch):
    """큐를 가로채 enqueue 인자를 그대로 붙잡는다(워커는 돌지 않는다)."""
    calls: list[dict] = []

    def _make(kind: str):
        def _fake(link_id, actor_user_id=None):
            calls.append({"kind": kind, "link_id": int(link_id),
                          "actor_user_id": actor_user_id})
            return True
        return _fake

    import foms.services.jobs.queue as queue_mod
    import foms.web.admin.naver_ingest as web_mod

    for module, raising in ((queue_mod, True), (web_mod, False)):
        monkeypatch.setattr(module, "enqueue_naver_cancel_approve", _make("cancel"),
                            raising=raising)
        monkeypatch.setattr(module, "enqueue_naver_return_approve", _make("return"),
                            raising=raising)
    return calls


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"wbapv_{role.lower()}_{_uid()}",
                password=generate_password_hash("pw"), role=role, team="CS",
                name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _link(*, claim: str = "CANCEL_REQUEST", holdback: str = "",
          order_id: int | None = None, order_no: str = "",
          state: dict | None = None) -> ExternalOrderLink:
    """구매자가 클레임을 걸어 온 수집 링크 1건."""
    external_id = f"PO-APV-{_uid()}"
    product_order = {"productOrderId": external_id, "productName": "루나 무몰딩 3000",
                     "totalPaymentAmount": 1230000}
    if claim:
        product_order["claimStatus"] = claim
        product_order["claimType"] = "CANCEL" if claim.startswith("CANCEL") else "RETURN"
    if holdback:
        product_order["holdbackStatus"] = holdback
    snapshot = {"order": {"orderId": order_no or f"N-APV-{_uid()}"},
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
    order = Order(received_date="2026-06-01", customer_name="김승인",
                  phone="010-3333-4444", address="서울 강남구 2", product="붙박이장",
                  status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return int(order.id)


class _CancelClient:
    """취소 승인 호출을 기록한다 — **보내기 직전 재조회**까지 흉내낸다.

    승인은 환불 확정이라 되돌릴 수 없다. 그래서 대상 판정을 수집 시점 스냅샷이 아니라
    **지금 상태**로 다시 한다(:func:`fulfillment.fresh_claim_statuses`, 감사 F10).
    기본 답은 "취소 요청 그대로"라 재조회가 없던 시절과 같은 경로를 탄다. ``fresh`` 로
    네이버 쪽 상태를 바꿔 끼우면 낡은 스냅샷 사례를 만들 수 있다.
    """

    def __init__(self, *, fail: str = "", fail_row: str = "",
                 fresh: dict | None = None, read_error: str = ""):
        self.calls: list[str] = []
        self.fail = fail
        self.fail_row = fail_row
        self.fresh = fresh or {}
        self.read_error = read_error
        self.reads: list[list[str]] = []

    def get_product_orders(self, product_order_ids):
        pids = [str(p) for p in product_order_ids]
        self.reads.append(pids)
        if self.read_error:
            raise RuntimeError(self.read_error)
        return [{"productOrder": {"productOrderId": pid,
                                  "claimStatus": self.fresh.get(pid, "CANCEL_REQUEST"),
                                  "claimType": "CANCEL"}}
                for pid in pids]

    def approve_cancel_product_order(self, product_order_id):
        self.calls.append(product_order_id)
        if self.fail:
            raise RuntimeError(self.fail)
        if self.fail_row:
            return {"data": {"successProductOrderIds": [],
                             "failProductOrderInfos": [
                                 {"productOrderId": product_order_id,
                                  "message": self.fail_row}]}}
        return {"data": {"successProductOrderIds": [product_order_id],
                         "failProductOrderInfos": []}}


class _ReturnClient:
    """반품 승인 대역 — ``_approve_returns`` 가 요구하는 재조회까지 흉내낸다."""

    def __init__(self, *, fail: str = "", detail_status: str = "RETURN_REQUEST"):
        self.calls: list[str] = []
        self.reads: list[list[str]] = []
        self.fail = fail
        self.detail_status = detail_status

    def get_product_orders(self, ids):
        self.reads.append(list(ids))
        return [{"order": {"orderId": "N-APV"},
                 "productOrder": {"productOrderId": pid},
                 "return": {"claimStatus": self.detail_status}} for pid in ids]

    def approve_return_product_order(self, product_order_id):
        self.calls.append(product_order_id)
        if self.fail:
            raise RuntimeError(self.fail)
        return {"data": {"successProductOrderIds": [product_order_id],
                         "failProductOrderInfos": []}}


def _state(link_id: int, axis: str) -> dict:
    db_session.expire_all()
    row = db_session.get(ExternalOrderLink, int(link_id))
    value = (row.triage_state or {}).get(axis)
    return value if isinstance(value, dict) else {}


# --------------------------------------------------------------------------- #
# 1. 선로 요청 — 문서에 적힌 것만 나간다
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
    """토큰과 승인 호출만 받는 최소 전송 — **네트워크를 타지 않는다**."""

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


def test_cancel_approve_sends_exactly_the_documented_request():
    """선로에 나가는 것이 **문서 그대로**여야 한다 (커머스API 공개 문서 2026-09-01 원문).

    요청 파라미터 표가 Path 의 ``productOrderId`` 하나뿐이고 요청 본문 절이 아예 없다
    ("path의 productOrderId만으로 동작하며 별도 본문이 필요 없고"). 그래서 **본문도
    Content-Type 도 붙지 않는다** — 거부(``rejectReturnReason`` + JSON 헤더)와 갈린다.
    """
    client, transport = _wire_client()

    out = client.approve_cancel_product_order("PO-1")

    sent = [call for call in transport.calls if "/claim/cancel/approve" in call[1]]
    assert len(sent) == 1, transport.calls
    method, url, kwargs = sent[0]
    assert method == "POST"
    assert url.endswith(
        "/v1/pay-order/seller/product-orders/PO-1/claim/cancel/approve"), url
    assert kwargs.get("json") is None, "문서에 요청 본문 절이 없다"
    assert kwargs.get("data") is None, "form 본문도 없다"
    assert "Content-Type" not in (kwargs.get("headers") or {}), (
        "본문이 없는데 Content-Type 을 붙였다")
    # 응답은 접수·거부와 동형이라 호출자가 _split_result 를 그대로 쓴다.
    assert out["data"]["successProductOrderIds"] == ["PO-1"]
    assert "failProductOrderInfos" in out["data"]


@pytest.mark.parametrize("method_name,path_fragment", [
    ("approve_cancel_product_order", "claim/cancel/approve"),
    ("approve_return_product_order", "claim/return/approve"),
])
def test_approve_methods_invent_no_request_body(method_name, path_fragment):
    """승인 두 갈래 모두 **본문을 만들지 않는다** — 같은 판정을 신규 메서드에도 건다.

    2026-08-27 원장이 "빈 body 는 400 이고 ``approvalData`` 를 넣어야 200"이라고 적었으나
    그 출처에 그 문장이 없었다(근거 폐기). 없는 필드를 지어내 불가역 API 에 보내지 않는다.
    판정은 docstring 이 아니라 **코드 본문**으로 한다 — docstring 은 왜 안 보내는지를
    설명하느라 그 낱말을 쓴다.
    """
    from foms.services.integrations.naver_commerce.client import NaverCommerceClient

    source = inspect.getsource(getattr(NaverCommerceClient, method_name))
    tree = ast.parse(source.lstrip())
    func = tree.body[0]
    body = func.body[1:] if ast.get_docstring(func) else func.body
    code = "\n".join(ast.unparse(node) for node in body)

    assert "json_body" not in code, code
    assert "approvalData" not in code, code
    assert "Content-Type" not in code, code
    assert path_fragment in code, code
    assert "NotImplementedError" not in code, "규격이 확인돼 막이 걷혔다"


def test_cancel_approve_refuses_an_empty_product_order_id():
    """빈 상품주문번호로 **불가역 API 를 때리지 않는다** — 규격과 무관하게 먼저 막는다."""
    from foms.services.integrations.naver_commerce.client import NaverCommerceClient

    client = NaverCommerceClient.__new__(NaverCommerceClient)

    with pytest.raises(ValueError):
        client.approve_cancel_product_order("")
    with pytest.raises(ValueError):
        client.approve_cancel_product_order("   ")


def test_no_cancel_reject_endpoint_exists_in_code():
    """**취소 거부 API 는 없다** — 코드에 존재조차 시키지 않는다(음성 단언).

    취소 철회는 구매자만 한다(흐름도 분기 C "구매자 취소철회" → ``CANCEL_REJECT``).
    판매자가 거절하는 경로를 만들면 언젠가 누가 부르고, 그건 400 을 받아 보며 배우는
    짓이다. 문서(`docs/`)에는 "존재하지 않는다"는 **서술**로 이 문자열이 있으므로
    판정 대상은 실행되는 코드뿐이다.
    """
    root = Path(__file__).resolve().parents[3]
    scanned = 0
    for folder, pattern in ((root / "foms", "**/*.py"), (root / "static", "**/*.js")):
        for path in folder.glob(pattern):
            text = path.read_text(encoding="utf-8", errors="ignore")
            scanned += 1
            assert "claim/cancel/reject" not in text, path
    assert scanned > 100, "스캔 대상이 비었다 — 음성 단언이 공회전한다"


def test_no_holdback_api_anywhere():
    """보류 해제는 **코드에 존재조차 시키지 않는다**(승인 계약과 같은 규율).

    안심케어 건은 보류해제 자체가 금지이고, 해제가 반품비를 0원으로 초기화하는 갈래도
    있다. 사람이 판매자센터에서 판단할 일이다.
    """
    from foms.services.integrations.naver_commerce import client as client_mod

    source = inspect.getsource(client_mod) + inspect.getsource(fulfillment)
    assert "holdback/release" not in source
    assert "claim/return/holdback" not in source


# --------------------------------------------------------------------------- #
# 2. 술어 — 양성/음성 대조군
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("claim", list(fulfillment.CANCEL_APPROVABLE_STATUSES))
def test_cancel_predicate_opens_on_the_documented_statuses(app, claim):
    """흐름도가 연 상태에서만 열린다 — 분기 C(``CANCEL_REQUEST``)와 분기 B(``CANCELING``)."""
    assert fulfillment.is_cancel_approvable(_link(claim=claim)) is True


@pytest.mark.parametrize("claim", ["CANCEL_DONE", "CANCEL_REJECT"])
def test_cancel_predicate_stays_closed_on_finished_claims(app, claim):
    """**음성 대조군** — 이미 끝난 취소에는 닫힌다.

    둘 다 취소 축(``CANCEL_*``) 안의 값이라 모집단 밖 표본이 아니다. 관측됐다는 이유로
    화이트리스트에 올리면 400 이 난다(WRONG_DELAYED_DELIVERY 사고와 같은 자리).
    """
    assert fulfillment.is_cancel_approvable(_link(claim=claim)) is False


@pytest.mark.parametrize("claim", list(fulfillment.RETURN_APPROVABLE_STATUSES))
def test_return_predicate_opens_on_the_approvable_set(app, claim):
    """반품 승인 술어는 :data:`RETURN_APPROVABLE_STATUSES` 4종을 그대로 쓴다."""
    assert fulfillment.is_return_approvable(_link(claim=claim)) is True


@pytest.mark.parametrize("claim", ["RETURN_DONE", "RETURN_REJECT"])
def test_return_predicate_stays_closed_on_finished_claims(app, claim):
    """**음성 대조군** — 반품 완료·이미 거부된 건에는 닫힌다."""
    assert fulfillment.is_return_approvable(_link(claim=claim)) is False


def test_cancel_and_return_predicates_do_not_bleed_into_each_other(app):
    """취소 술어가 반품 상태에, 반품 술어가 취소 상태에 열리면 안 된다(축 누출)."""
    assert fulfillment.is_cancel_approvable(_link(claim="RETURN_REQUEST")) is False
    assert fulfillment.is_return_approvable(_link(claim="CANCEL_REQUEST")) is False


@pytest.mark.parametrize("predicate,claim", [
    (fulfillment.is_cancel_approvable, "CANCEL_REQUEST"),
    (fulfillment.is_return_approvable, "RETURN_REQUEST"),
])
def test_holdback_closes_both_predicates(app, predicate, claim):
    """보류가 걸린 건은 술어부터 닫힌다 — 화면 버튼도 함께 사라진다."""
    assert predicate(_link(claim=claim, holdback="HOLDBACK_REQUEST")) is False


def test_cancel_predicate_is_closed_by_our_own_marker(app):
    """멱등은 **우리 표식**으로만 판정한다 — 네이버 ``cancelApprovalDate`` 는 읽기 값이라
    판매자센터 수동분과 API 분을 갈라 주지 않는다."""
    link = _link(claim="CANCEL_REQUEST",
                 state={"cancel": {"approved_at": "2026-09-01T00:00:00"}})
    assert fulfillment.is_cancel_approvable(link) is False


@pytest.mark.parametrize("marker", ["approved_at", "rejected_at"])
def test_return_predicate_is_closed_by_our_own_marker(app, marker):
    """이미 승인했거나 **거부한** 건은 다시 보내지 않는다."""
    link = _link(claim="RETURN_REQUEST",
                 state={"return": {marker: "2026-09-01T00:00:00"}})
    assert fulfillment.is_return_approvable(link) is False


# --------------------------------------------------------------------------- #
# 3. 서비스 — 대상 선별·표식·실패·멱등
# --------------------------------------------------------------------------- #

def test_approve_cancel_sends_only_the_rows_with_a_pending_request(app):
    """요청이 걸린 행만 보낸다 — 화면 재진술과 **같은 술어**다."""
    link = _link(claim="CANCEL_REQUEST")
    sibling = _link(claim="CANCEL_DONE", order_no=link.external_order_no)
    sibling.group_key = link.group_key
    db_session.commit()
    fake = _CancelClient()

    out = fulfillment.approve_cancel(db_session, fake, link_id=int(link.id),
                                     actor_user_id=7)
    db_session.commit()

    assert fake.calls == [link.external_id]
    assert out["approved"] == [link.external_id]


def test_approve_cancel_marks_the_cancel_axis(app):
    """표식은 **취소 축**(``triage_state['cancel']``)에 남는다 — 반품 축과 섞지 않는다."""
    link = _link(claim="CANCEL_REQUEST")

    fulfillment.approve_cancel(db_session, _CancelClient(), link_id=int(link.id),
                               actor_user_id=7)
    db_session.commit()

    state = _state(link.id, "cancel")
    assert state.get("approved_at") and state.get("approved_by") == 7
    assert not _state(link.id, "return"), "반품 축을 건드렸다"


def test_approve_cancel_never_touches_a_held_back_claim(app):
    """보류 걸린 건은 **한 번도 부르지 않는다** — 보류는 우리가 풀지 않는다."""
    link = _link(claim="CANCEL_REQUEST", holdback="HOLDBACK")
    fake = _CancelClient()

    with pytest.raises(fulfillment.FulfillmentError):
        fulfillment.approve_cancel(db_session, fake, link_id=int(link.id))

    assert fake.calls == [], "보류 건에 승인을 불렀다"


def test_approve_cancel_is_idempotent(app):
    """두 번 눌러도 한 번만 나간다 — 두 번째는 대상 0건이라 막힌다."""
    link = _link(claim="CANCEL_REQUEST")
    fake = _CancelClient()

    fulfillment.approve_cancel(db_session, fake, link_id=int(link.id))
    db_session.commit()
    with pytest.raises(fulfillment.FulfillmentError):
        fulfillment.approve_cancel(db_session, fake, link_id=int(link.id))

    assert len(fake.calls) == 1


def test_approve_cancel_records_the_failure_reason(app):
    """호출이 실패하면 사유가 DB 에 남는다 — 로그·RQ 에만 남기지 않는다.

    실패 띠(``last_error``)를 읽는 화면이 fulfillment 축만 보므로 **어느 작업**이
    실패했는지(``cancel-approve``)까지 그 축에 남아야 재시도가 엉뚱한 작업으로 안 간다.
    """
    link = _link(claim="CANCEL_REQUEST")
    fake = _CancelClient(fail="네이버 400: 처리 권한 없음")

    with pytest.raises(fulfillment.FulfillmentError) as exc:
        fulfillment.approve_cancel(db_session, fake, link_id=int(link.id))
    db_session.commit()

    assert "처리 권한 없음" in str(exc.value)
    assert "처리 권한 없음" in str(_state(link.id, "cancel").get("approve_skipped_reason"))
    assert _state(link.id, "fulfillment").get("last_error_action") == "cancel-approve"


def test_approve_cancel_records_a_per_row_failure(app):
    """예외가 아니라 ``failProductOrderInfos`` 로 온 실패도 같은 자리에 남는다."""
    link = _link(claim="CANCEL_REQUEST")
    fake = _CancelClient(fail_row="이미 취소 완료된 건입니다")

    with pytest.raises(fulfillment.FulfillmentError):
        fulfillment.approve_cancel(db_session, fake, link_id=int(link.id))
    db_session.commit()

    assert "이미 취소 완료된 건입니다" in str(_state(link.id, "cancel"))
    assert _state(link.id, "fulfillment").get("last_error_action") == "cancel-approve"


def test_approve_return_reaches_a_claim_the_customer_raised(app):
    """**고객이 먼저 낸 반품**을 승인한다 — 우리 접수 표식(``requested_at``)이 없다.

    접수 경로의 승인은 "방금 접수에 성공한 건"을 전제로 대상을 골라서, 그 전제를 그대로
    쓰면 독립 버튼이 주 대상을 통째로 놓친다. 이 테스트가 그 자리를 잠근다.
    """
    link = _link(claim="RETURN_REQUEST")
    assert not _state(link.id, "return").get("requested_at")
    fake = _ReturnClient()

    out = fulfillment.approve_return(db_session, fake, link_id=int(link.id),
                                     actor_user_id=9)
    db_session.commit()

    assert fake.calls == [link.external_id]
    assert out["approved"] == [link.external_id]
    state = _state(link.id, "return")
    assert state.get("approved_at") and state.get("approved_by") == 9
    assert not _state(link.id, "cancel"), "취소 축을 건드렸다"


def test_approve_return_skips_the_siblings_without_a_claim(app):
    """클레임이 없는 형제는 보내지 않는다 — 집 전체 수로 재진술하지 않는다."""
    link = _link(claim="RETURN_REQUEST")
    sibling = _link(claim="RETURN_DONE", order_no=link.external_order_no)
    sibling.group_key = link.group_key
    db_session.commit()
    fake = _ReturnClient()

    out = fulfillment.approve_return(db_session, fake, link_id=int(link.id))
    db_session.commit()

    assert fake.calls == [link.external_id]
    assert out["approved"] == [link.external_id]


def test_approve_return_never_touches_a_held_back_claim(app):
    """보류 걸린 반품은 **한 번도 부르지 않는다**(안심케어 보류해제 금지)."""
    link = _link(claim="RETURN_REQUEST", holdback="HOLDBACK_REQUEST")
    fake = _ReturnClient()

    with pytest.raises(fulfillment.FulfillmentError):
        fulfillment.approve_return(db_session, fake, link_id=int(link.id))

    assert fake.calls == []
    assert fake.reads == [], "보류 건은 재조회조차 하지 않는다"


def test_approve_return_is_idempotent(app):
    """두 번 눌러도 한 번만 나간다."""
    link = _link(claim="RETURN_REQUEST")
    fake = _ReturnClient()

    fulfillment.approve_return(db_session, fake, link_id=int(link.id))
    db_session.commit()
    with pytest.raises(fulfillment.FulfillmentError):
        fulfillment.approve_return(db_session, fake, link_id=int(link.id))

    assert len(fake.calls) == 1


def test_approve_return_failure_lands_on_the_fulfillment_axis(app):
    """반품 승인 실패도 실패 띠가 읽는 축에 **작업 이름과 함께** 남는다."""
    link = _link(claim="RETURN_REQUEST")
    fake = _ReturnClient(fail="네이버 400: 보류 상태 확인 필요")

    with pytest.raises(fulfillment.FulfillmentError):
        fulfillment.approve_return(db_session, fake, link_id=int(link.id))
    db_session.commit()

    assert "보류 상태 확인 필요" in str(_state(link.id, "return"))
    assert _state(link.id, "fulfillment").get("last_error_action") == "return-approve"


# --------------------------------------------------------------------------- #
# 4. 게이트 — 화면과 라우트를 함께 닫는다
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("path,kind", [(CANCEL_PATH, "cancel"), (RETURN_PATH, "return")])
def test_route_is_closed_while_the_gate_is_off(client, monkeypatch, queued, path, kind):
    """게이트가 꺼져 있으면 라우트가 403 — 화면 버튼과 **같은 조건**이다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    monkeypatch.delenv("FOMS_NAVER_CANCEL_APPROVE_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_NAVER_RETURN_APPROVE_ENABLED", raising=False)
    _login(client)
    link = _link(claim="CANCEL_REQUEST" if kind == "cancel" else "RETURN_REQUEST")

    response = client.post(path.format(link_id=link.id), json={})

    assert response.status_code == 403
    assert not queued, "게이트가 꺼졌는데 큐에 들어갔다"


def test_pane_hides_both_buttons_while_the_gates_are_off(client, monkeypatch):
    """게이트가 꺼져 있으면 **버튼도 모달도 없다** — 눌러도 안 나가는 버튼은 거짓말이다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    monkeypatch.delenv("FOMS_NAVER_CANCEL_APPROVE_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_NAVER_RETURN_APPROVE_ENABLED", raising=False)
    _login(client)
    cancel_link = _link(claim="CANCEL_REQUEST")
    return_link = _link(claim="RETURN_REQUEST")

    cancel_body = client.get(PANE_PATH.format(link_id=cancel_link.id)).get_data(as_text=True)
    return_body = client.get(PANE_PATH.format(link_id=return_link.id)).get_data(as_text=True)

    assert CANCEL_BTN not in cancel_body
    assert CANCEL_CONFIRM not in cancel_body
    assert 'id="wb-modal-cancel-approve"' not in cancel_body
    assert RETURN_BTN not in return_body
    assert RETURN_CONFIRM not in return_body
    assert 'id="wb-modal-return-approve"' not in return_body


def test_one_gate_does_not_open_the_other(client, monkeypatch):
    """게이트는 **따로 판다** — 취소 승인만 켜도 반품 승인 버튼은 안 뜬다.

    진짜 클레임 1건에서 한쪽을 먼저 켜 성공을 확인한 뒤 다른 쪽을 켠다. 하나로 묶으면
    첫 실호출이 두 배선의 동시 검증이 되어, 실패했을 때 어느 쪽이 틀렸는지 안 갈린다.
    """
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    monkeypatch.setenv("FOMS_NAVER_CANCEL_APPROVE_ENABLED", "1")
    monkeypatch.delenv("FOMS_NAVER_RETURN_APPROVE_ENABLED", raising=False)
    _login(client)
    cancel_link = _link(claim="CANCEL_REQUEST")
    return_link = _link(claim="RETURN_REQUEST")

    cancel_body = client.get(PANE_PATH.format(link_id=cancel_link.id)).get_data(as_text=True)
    return_body = client.get(PANE_PATH.format(link_id=return_link.id)).get_data(as_text=True)

    assert CANCEL_BTN in cancel_body
    assert RETURN_BTN not in return_body


# --------------------------------------------------------------------------- #
# 5. 권한 — 돈이 나가는 판단은 거부와 같은 층
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("path,kind", [(CANCEL_PATH, "cancel"), (RETURN_PATH, "return")])
def test_staff_cannot_approve(client, workbench_on, queued, path, kind):
    """실무자(STAFF)는 못 누른다 — 취소처리(STAFF 포함)보다 좁다(사용자 결정 2026-09-01)."""
    _login(client, role="STAFF")
    link = _link(claim="CANCEL_REQUEST" if kind == "cancel" else "RETURN_REQUEST")

    response = client.post(path.format(link_id=link.id), json={})

    assert response.status_code in (302, 403)
    assert not queued


@pytest.mark.parametrize("role", ["ADMIN", "MANAGER"])
@pytest.mark.parametrize("path,kind", [(CANCEL_PATH, "cancel"), (RETURN_PATH, "return")])
def test_admin_and_manager_can_approve(client, workbench_on, queued, role, path, kind):
    """관리자·책임자는 누를 수 있고, 그 누름이 **큐로** 간다(네이버 HTTP 는 WORKER 만)."""
    _login(client, role=role)
    link_id = int(_link(claim="CANCEL_REQUEST" if kind == "cancel"
                        else "RETURN_REQUEST").id)

    response = client.post(path.format(link_id=link_id), json={})

    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["success"] is True
    assert queued and queued[-1]["kind"] == kind
    assert queued[-1]["link_id"] == link_id


def test_pane_hides_the_buttons_from_staff(client, workbench_on):
    """STAFF 화면에는 버튼이 없다 — 라우트와 **같은 조건**으로 렌더한다(403 예방)."""
    _login(client, role="STAFF")
    cancel_link = _link(claim="CANCEL_REQUEST")
    return_link = _link(claim="RETURN_REQUEST")

    cancel_body = client.get(PANE_PATH.format(link_id=cancel_link.id)).get_data(as_text=True)
    return_body = client.get(PANE_PATH.format(link_id=return_link.id)).get_data(as_text=True)

    assert CANCEL_BTN not in cancel_body
    assert RETURN_BTN not in return_body


# --------------------------------------------------------------------------- #
# 6. 화면·서버 술어 한 벌 — 재진술 건수 == 보내는 건수
# --------------------------------------------------------------------------- #

def test_pane_restates_exactly_what_the_cancel_approval_will_send(client, workbench_on):
    """화면이 "1건"이라 말하면 서버도 1건만 보낸다.

    집 하나에 상품주문이 여럿이고, 이 프로젝트는 집 묶기에서 이미 데였다. 불가역
    경로에서 과대 진술은 그대로 사고다(2026-08-27 CEO 지적).
    """
    _login(client)
    link = _link(claim="CANCEL_REQUEST")
    sibling = _link(claim="CANCEL_DONE", order_no=link.external_order_no)
    sibling.group_key = link.group_key
    db_session.commit()

    body = client.get(PANE_PATH.format(link_id=link.id)).get_data(as_text=True)

    assert CANCEL_BTN in body
    assert "환불 확정 1건" in body, "화면 재진술 건수가 1건이 아니다"
    assert f"상품주문 {link.external_id}" in body
    fake = _CancelClient()
    out = fulfillment.approve_cancel(db_session, fake, link_id=int(link.id))
    db_session.commit()
    assert len(fake.calls) == 1 and out["approved"] == [link.external_id]


def test_pane_restates_exactly_what_the_return_approval_will_send(client, workbench_on):
    """반품 승인도 같다 — 재진술 건수와 실제 호출 건수가 한 벌이다."""
    _login(client)
    link = _link(claim="RETURN_REQUEST")
    sibling = _link(claim="RETURN_DONE", order_no=link.external_order_no)
    sibling.group_key = link.group_key
    db_session.commit()

    body = client.get(PANE_PATH.format(link_id=link.id)).get_data(as_text=True)

    assert RETURN_BTN in body
    assert "환불 확정 1건" in body
    fake = _ReturnClient()
    out = fulfillment.approve_return(db_session, fake, link_id=int(link.id))
    db_session.commit()
    assert len(fake.calls) == 1 and out["approved"] == [link.external_id]


def test_pane_hides_the_buttons_when_naver_put_the_claim_on_hold(client, workbench_on):
    """보류 걸린 건은 버튼도 없다 — 술어가 한 벌이라 자동으로 따라온다."""
    _login(client)
    cancel_link = _link(claim="CANCEL_REQUEST", holdback="HOLDBACK")
    return_link = _link(claim="RETURN_REQUEST", holdback="HOLDBACK")

    cancel_body = client.get(PANE_PATH.format(link_id=cancel_link.id)).get_data(as_text=True)
    return_body = client.get(PANE_PATH.format(link_id=return_link.id)).get_data(as_text=True)

    assert CANCEL_BTN not in cancel_body
    assert RETURN_BTN not in return_body


def test_pane_hides_the_buttons_once_we_have_approved(client, workbench_on):
    """우리 표식이 있으면 버튼이 닫힌다 — 멱등을 화면에서도 말한다."""
    _login(client)
    cancel_link = _link(claim="CANCEL_REQUEST",
                        state={"cancel": {"approved_at": "2026-09-01T00:00:00"}})
    return_link = _link(claim="RETURN_REQUEST",
                        state={"return": {"approved_at": "2026-09-01T00:00:00"}})

    cancel_body = client.get(PANE_PATH.format(link_id=cancel_link.id)).get_data(as_text=True)
    return_body = client.get(PANE_PATH.format(link_id=return_link.id)).get_data(as_text=True)

    assert CANCEL_BTN not in cancel_body
    assert RETURN_BTN not in return_body


def test_modal_says_it_cannot_be_undone(client, workbench_on):
    """모달이 **되돌릴 수 없음**을 말하고, 취소 쪽은 거절 API 부재까지 말한다."""
    _login(client)
    link = _link(claim="CANCEL_REQUEST")

    body = client.get(PANE_PATH.format(link_id=link.id)).get_data(as_text=True)

    assert CANCEL_CONFIRM in body
    assert "되돌릴 수 없습니다" in body
    assert "거절하는 방법이 없습니다" in body


# --------------------------------------------------------------------------- #
# 7. 감사 로그·주문 이력 — 돈이 나간 사실이 워크벤치 밖에서 읽힌다
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("path,kind,action,event_type", [
    (CANCEL_PATH, "cancel", "NAVER_INGEST_CANCEL_APPROVE_ENQUEUE", "NAVER_CANCEL_APPROVED"),
    (RETURN_PATH, "return", "NAVER_INGEST_RETURN_APPROVE_ONLY_ENQUEUE",
     "NAVER_RETURN_APPROVED"),
])
def test_approval_is_recorded_in_audit_and_order_history(client, workbench_on, queued,
                                                         path, kind, action, event_type):
    """감사 로그와 주문 이력 **양쪽**에 남는다.

    워크벤치를 안 여는 담당자가 "이 주문의 돈이 왜 나갔나"를 읽는 자리는 주문 이력뿐이다.
    """
    user_id = int(_login(client).id)
    order_id = _order()
    link_id = int(_link(claim="CANCEL_REQUEST" if kind == "cancel" else "RETURN_REQUEST",
                        order_id=order_id).id)

    response = client.post(path.format(link_id=link_id), json={})
    assert response.status_code == 200, response.get_data(as_text=True)

    db_session.expire_all()
    log = (db_session.query(SecurityLog)
           .filter(SecurityLog.action == action)
           .order_by(SecurityLog.id.desc()).first())
    assert log is not None, f"감사 로그가 없다 ({action})"
    assert str(link_id) in str(log.detail or "")

    event = (db_session.query(OrderEvent)
             .filter(OrderEvent.order_id == order_id,
                     OrderEvent.event_type == event_type)
             .order_by(OrderEvent.id.desc()).first())
    assert event is not None, f"주문 이력에 승인 표식이 없다 ({event_type})"
    assert event.created_by_user_id == user_id
    assert int(event.payload.get("link_id")) == link_id


def test_return_approve_only_is_a_different_action_from_request_plus_approve():
    """접수+승인과 **다른 감사 이름**이어야 한다.

    같은 action 으로 묶으면 원장에서 "접수하면서 승인한 것"과 "이미 있던 반품을 승인한
    것"이 안 갈린다 — 환불을 누가 냈는지 읽으려는 목적이 무너진다.
    """
    from foms.services.audit_message_display import ACTION_LABELS

    assert "NAVER_INGEST_RETURN_APPROVE_ONLY_ENQUEUE" != "NAVER_INGEST_RETURN_APPROVE_ENQUEUE"
    for action in ("NAVER_INGEST_CANCEL_APPROVE_ENQUEUE",
                   "NAVER_INGEST_RETURN_APPROVE_ONLY_ENQUEUE"):
        # 라벨 미등재는 FOMS CI red 이고 pre_push_smoke 사각이다(4커밋 연속 red 사고).
        assert action in ACTION_LABELS, f"감사 라벨 미등재: {action}"
    labels = {ACTION_LABELS["NAVER_INGEST_RETURN_APPROVE_ONLY_ENQUEUE"],
              ACTION_LABELS["NAVER_INGEST_RETURN_APPROVE_ENQUEUE"]}
    assert len(labels) == 2, "화면 문구까지 같으면 원장에서 여전히 안 갈린다"


@pytest.mark.parametrize("event_type,word", [
    ("NAVER_CANCEL_APPROVED", "취소"),
    ("NAVER_RETURN_APPROVED", "반품"),
])
def test_order_history_labels_are_registered(event_type, word):
    """이벤트 라벨이 사전에 있어야 한다 — 빠지면 영문 코드가 뜨는 게 아니라 한글
    **"기타 변경"**으로 조용히 뭉개져 다른 미등재 이벤트와 구분이 안 된다."""
    from foms.services.order_event_display import (
        generate_change_description,
        translate_event_type_to_korean,
    )

    label = translate_event_type_to_korean(event_type)
    assert label and label != "기타 변경", f"이벤트 라벨 미등재: {event_type}"
    assert word in label

    sentence = generate_change_description(
        event_type, "", "", "",
        {"link_id": 1, "external_order_no": "N-APV-9", "product_order_count": 2})
    assert "N-APV-9" in sentence, sentence


def test_both_approvals_are_followed_by_a_refresh():
    """승인 뒤 그 집을 다시 읽는다 — 불가역 경로에서 재조회는 확인이다(T3 규율)."""
    from foms.services.jobs.tasks import REFRESH_AFTER_ACTIONS

    assert "cancel-approve" in REFRESH_AFTER_ACTIONS
    assert "return-approve" in REFRESH_AFTER_ACTIONS


# --------------------------------------------------------------------------- #
# F10 — 낡은 스냅샷으로 환불을 확정하지 않는다
# --------------------------------------------------------------------------- #

def test_cancel_approval_refetches_the_state_before_calling(app):
    """승인 직전에 네이버에 **지금 상태**를 다시 묻는다 (감사 F10).

    화면 술어는 수집 시점 스냅샷으로 버튼을 연다 — 그건 옳다. 그러나 승인은 환불 확정이고
    되돌리는 엔드포인트가 없다. 반품 승인(`_approve_returns`)은 처음부터 재조회를 했는데
    취소 승인만 안 했다 — 같은 불가역 등급인데 규율이 갈려 있던 자리다.
    """
    link = _link(claim="CANCEL_REQUEST")
    client = _CancelClient()

    fulfillment.approve_cancel(db_session, client, link_id=int(link.id), actor_user_id=1)
    db_session.commit()

    assert client.reads == [[link.external_id]], "보내기 전에 다시 묻지 않았다"
    assert client.calls == [link.external_id]


def test_a_withdrawn_cancel_is_not_approved_even_though_the_snapshot_says_so(app):
    """스냅샷은 `CANCEL_REQUEST` 인데 네이버는 이미 다른 상태 — **부르지 않는다**.

    구매자가 취소를 철회한 뒤 우리가 옛 사실로 승인을 부르면 환불이 확정될 수 있고,
    되돌릴 방법이 없다. 조용히 빼지 않는다 — 사유를 남기고 예외를 올린다.
    """
    link = _link(claim="CANCEL_REQUEST")
    client = _CancelClient(fresh={link.external_id: "CANCEL_REJECT"})

    with pytest.raises(fulfillment.FulfillmentError) as err:
        fulfillment.approve_cancel(db_session, client, link_id=int(link.id))
    db_session.commit()

    assert client.calls == [], "낡은 스냅샷으로 환불을 확정했다"
    assert "상태가 아닙니다" in str(err.value)
    assert "CANCEL_REJECT" in _state(link.id, "cancel").get("approve_skipped_reason", "")


def test_a_failed_refetch_stops_the_cancel_approval(app):
    """상태를 **못 읽으면 부르지 않는다** — 모르면 불가역 호출을 열지 않는다."""
    link = _link(claim="CANCEL_REQUEST")
    client = _CancelClient(read_error="HTTP 500 일시 오류")

    with pytest.raises(fulfillment.FulfillmentError) as err:
        fulfillment.approve_cancel(db_session, client, link_id=int(link.id))
    db_session.commit()

    assert client.calls == [], "상태를 모르는 채로 환불을 확정했다"
    assert "읽지 못했습니다" in str(err.value)
