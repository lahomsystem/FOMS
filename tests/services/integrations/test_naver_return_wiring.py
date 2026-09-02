"""T8 반품 접수 **배선** 계약 — 큐·라우트·화면·지문 (R5~R8).

서비스 본체(가드·화이트리스트·멱등)는 :mod:`test_naver_return_send` 가 잠근다.
여기서는 그 본체까지 **도달하는 길**을 잠근다. 3차 세션까지 본체는 있었는데 호출자가
테스트 밖에 0곳이라 사람은 이 기능을 쓸 수 없었다.

고정하는 계약:

* web 은 **큐에 넣기만** 한다 — 커머스API 등록 호출 IP 가 WORKER 것뿐이다.
* 사유 화이트리스트를 **라우트가 먼저** 본다. 불가역 경로라 네이버 400 을 받아 보고
  배우지 않는다.
* 게이트가 꺼지면 라우트도 닫힌다 — 열어 두면 열린 탭·북마크가 게이트를 우회한다.
* 큐를 못 쓰면 **503 + 사유**다. 조용히 성공한 척하지 않는다.
* 폴링 지문(`rev`)이 **반품 축으로도 뒤집힌다** — 안 그러면 눌러도 화면이 영원히 그대로다.
* 화면이 재진술하는 건수 == **서버가 실제로 보낼 건수**. 부분 발송 집에서 집 전체 수를
  말하면 불가역 경로에서 과대 진술이 된다(2026-08-27 CEO 지적).
"""

from __future__ import annotations

import json

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.fulfillment import (
    RETURN_REASONS,
    is_return_pending,
)
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
    user = User(username=f"wb_ret_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _link(*, order_no: str = "", dispatched_ours: bool = False,
          dispatched_naver: bool = False, returned: bool = False,
          claim_status: str = "", addon: bool = False) -> ExternalOrderLink:
    """상품주문 1건. 발송 표식은 **우리 것**과 **네이버 원본** 둘 다 만들 수 있다.

    ``addon`` 은 ``productClass`` 를 가른다 — 본품/추가구성상품 판별의 정본이다.
    """
    from foms.services.integrations.naver_commerce.constants import ADDON_PRODUCT_CLASS

    external_id = f"PO-RW-{_uid()}"
    order_no = order_no or f"N-RW-{_uid()}"
    product_order = {
        "productOrderId": external_id, "productName": "붙박이장",
        "totalPaymentAmount": 594000, "placeOrderStatus": "OK",
        "claimStatus": claim_status or None,
        "productClass": ADDON_PRODUCT_CLASS if addon else "조합형옵션상품",
        "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if dispatched_naver:
        product_order["delivery"] = {"sendDate": "2026-08-26T10:00:00.0+09:00"}
    snapshot = {"order": {"orderId": order_no, "ordererName": "김주문"},
                "productOrder": product_order}
    state: dict = {}
    if dispatched_ours:
        state["fulfillment"] = {"dispatched_at": "2026-08-26T01:00:00"}
    if returned:
        state["return"] = {"requested_at": "2026-08-26T02:00:00"}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="COLLECTED", external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             place_order_status="OK", triage_state=state or None)
    db_session.add(link)
    db_session.commit()
    return link


# ─────────────────────────────────────────────────── 술어 전수 (양성·음성·어긋남)

def test_is_return_pending_over_every_state_combination(app):
    """술어를 **전수** 돌린다 — 양성 후보만 세는 것은 전수가 아니다.

    3차 세션이 두 번 걸린 자리다: 검증이 양성 후보만 돌아 음성 대조군에서 나던 결함을
    통째로 놓쳤다. 여기서는 (우리 발송 × 네이버 발송 × 이미 접수) 8가지를 **전부** 만들고
    기대값으로 갈라 **어긋남 0** 을 출력한다.

    규칙은 둘뿐이다: 나간 물건이어야 하고(우리 표식 **또는** 네이버 원본), 아직 우리가
    접수하지 않았어야 한다.
    """
    cases = []
    for ours in (False, True):
        for naver in (False, True):
            for returned in (False, True):
                link = _link(dispatched_ours=ours, dispatched_naver=naver,
                             returned=returned)
                expected = (ours or naver) and not returned
                cases.append((ours, naver, returned, expected,
                              is_return_pending(link)))

    assert len(cases) == 8, "조합을 하나라도 빠뜨리면 전수가 아니다"
    positives = [c for c in cases if c[3]]
    negatives = [c for c in cases if not c[3]]
    mismatches = [c for c in cases if c[3] != c[4]]

    assert len(positives) == 3, f"양성 기대 3, 실제 {len(positives)}"
    assert len(negatives) == 5, f"음성 기대 5, 실제 {len(negatives)}"
    assert mismatches == [], f"어긋남 {len(mismatches)}: {mismatches}"


def test_naver_only_dispatch_is_return_pending(app):
    """판매자센터에서 손으로 발송한 건도 반품 대상이다 — 우리 표식이 없을 뿐이다."""
    assert is_return_pending(_link(dispatched_naver=True)) is True


# ─────────────────────────────────────────────────────────────── R5 큐

def test_enqueue_naver_return_targets_the_shared_task_with_return_action(monkeypatch):
    """큐는 취소와 **같은 태스크**에 ``action="return"`` 으로 태운다.

    갈래를 새로 파면 실패 사유를 DB 에 남기고 커밋하는 규율이 두 벌이 된다
    (한쪽만 고쳐지는 자리가 된다).
    """
    from foms.services.jobs import queue as jobs_queue

    seen: list[dict] = []

    class _Q:
        def enqueue(self, path, *args, **kwargs):
            seen.append({"path": path, "args": args, "kwargs": kwargs})

    monkeypatch.setattr(jobs_queue, "get_rq_queue", lambda: _Q())
    assert jobs_queue.enqueue_naver_return(7, "COLOR_AND_SIZE", "색상 상이", 42) is True

    assert len(seen) == 1
    call = seen[0]
    assert call["path"].endswith(".run_naver_fulfillment_task")
    assert call["args"] == (7, "return", 42)
    assert call["kwargs"]["reason"] == "COLOR_AND_SIZE"
    assert call["kwargs"]["detail"] == "색상 상이"


def test_enqueue_naver_return_reports_failure_when_queue_is_down(monkeypatch):
    """큐가 없으면 False — 화면이 "지금은 접수할 수 없다"를 그대로 보여준다."""
    from foms.services.jobs import queue as jobs_queue

    monkeypatch.setattr(jobs_queue, "get_rq_queue", lambda: None)
    assert jobs_queue.enqueue_naver_return(7, "COLOR_AND_SIZE") is False


def test_worker_task_routes_return_action_to_request_return(app, monkeypatch):
    """워커가 ``action="return"`` 을 **반품 서비스**로 보낸다 (배선의 마지막 칸)."""
    from foms.services.integrations.naver_commerce import fulfillment as svc
    from foms.services.jobs import tasks

    seen: list[dict] = []
    monkeypatch.setattr(
        svc, "request_return",
        lambda session, client, **kw: seen.append(kw) or {"returned": ["X"], "skipped": []})
    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.client.NaverCommerceClient",
        lambda *a, **k: object())

    out = tasks.run_naver_fulfillment_task(5, "return", 42,
                                          reason="COLOR_AND_SIZE", detail="색상 상이")

    assert out == {"returned": ["X"], "skipped": []}
    assert seen == [{"link_id": 5, "reason": "COLOR_AND_SIZE",
                     "detail": "색상 상이", "actor_user_id": 42, "approve": False}]


# ────────────────────────────────────────────────────────────── R6 라우트

def test_return_route_enqueues_and_returns_base_rev(app, client, workbench_on, monkeypatch):
    """web 은 큐에 넣고 바로 답한다 — ``rev`` 는 **누르기 직전** 지문이다."""
    from foms.services.jobs import queue as jobs_queue

    actor_id = int(_login(client).id)
    link_id = int(_link(dispatched_ours=True).id)
    calls: list[tuple] = []
    monkeypatch.setattr(
        jobs_queue, "enqueue_naver_return",
        lambda lid, reason, detail, actor, approve=False:
            calls.append((lid, reason, detail, actor, approve)) or True)

    res = client.post(f"/admin/naver-ingest/{link_id}/return",
                      json={"reason": "COLOR_AND_SIZE", "detail": "색상 상이"})

    assert res.status_code == 200
    body = res.get_json()
    assert body["success"] is True
    assert body["data"]["queued"] is True
    assert body["data"]["rev"]
    # 승인은 **안 보낸 사람에게 기본으로 켜지지 않는다** — 돈이 나가는 갈래다(T8-S2).
    assert calls == [(link_id, "COLOR_AND_SIZE", "색상 상이", actor_id, False)]
    assert body["data"]["approve"] is False


def test_return_route_passes_approve_flag(app, client, workbench_on, monkeypatch):
    """`승인까지 한 번에` 를 켜면 그 뜻이 큐까지 그대로 간다 (T8-S2)."""
    from foms.services.jobs import queue as jobs_queue

    _login(client)
    link_id = int(_link(dispatched_ours=True).id)
    calls: list[tuple] = []
    monkeypatch.setattr(
        jobs_queue, "enqueue_naver_return",
        lambda lid, reason, detail, actor, approve=False:
            calls.append((lid, approve)) or True)

    res = client.post(f"/admin/naver-ingest/{link_id}/return",
                      json={"reason": "COLOR_AND_SIZE", "approve": True})

    assert res.status_code == 200
    assert calls == [(link_id, True)]
    assert res.get_json()["data"]["approve"] is True


def test_return_route_does_not_read_string_false_as_true(app, client, workbench_on,
                                                         monkeypatch):
    """문자열 ``"false"`` 를 참으로 읽으면 **안 켠 사람이 환불을 낸다**.

    JSON 이 아니라 폼·직접 호출로 오는 값이 문자열일 수 있다. `bool("false")` 는 True 다.
    """
    from foms.services.jobs import queue as jobs_queue

    _login(client)
    link_id = int(_link(dispatched_ours=True).id)
    calls: list[tuple] = []
    monkeypatch.setattr(
        jobs_queue, "enqueue_naver_return",
        lambda lid, reason, detail, actor, approve=False:
            calls.append((lid, approve)) or True)

    res = client.post(f"/admin/naver-ingest/{link_id}/return",
                      json={"reason": "COLOR_AND_SIZE", "approve": "false"})

    assert res.status_code == 200
    assert calls == [(link_id, False)]


def test_return_route_rejects_a_code_outside_the_whitelist(app, client, workbench_on,
                                                           monkeypatch):
    """목록 밖 코드는 **큐에 들어가기 전에** 튕긴다 — 불가역 경로다."""
    from foms.services.jobs import queue as jobs_queue

    _login(client)
    link_id = int(_link(dispatched_ours=True).id)
    monkeypatch.setattr(jobs_queue, "enqueue_naver_return",
                        lambda *a, **k: pytest.fail("화이트리스트 밖 코드가 큐에 들어갔다"))

    res = client.post(f"/admin/naver-ingest/{link_id}/return",
                      json={"reason": "RETURN_ANYTHING"})

    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_return_route_rejects_a_cancel_reason_code(app, client, workbench_on, monkeypatch):
    """취소 사유는 반품 사유가 아니다 — 두 목록은 다르다."""
    from foms.services.integrations.naver_commerce.fulfillment import CANCEL_REASONS
    from foms.services.jobs import queue as jobs_queue

    only_cancel = sorted(set(CANCEL_REASONS) - set(RETURN_REASONS))
    assert only_cancel, "두 목록이 같아지면 이 계약은 의미가 없다"

    _login(client)
    link_id = int(_link(dispatched_ours=True).id)
    monkeypatch.setattr(jobs_queue, "enqueue_naver_return",
                        lambda *a, **k: pytest.fail("취소 사유가 반품으로 나갔다"))

    res = client.post(f"/admin/naver-ingest/{link_id}/return",
                      json={"reason": only_cancel[0]})
    assert res.status_code == 400


def test_return_route_is_closed_when_the_gate_is_off(app, client, monkeypatch):
    """게이트를 끄는 것이 이 기능의 롤백 경로다 — 라우트도 함께 닫힌다."""
    from foms.services.jobs import queue as jobs_queue

    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "0")
    _login(client)
    link_id = int(_link(dispatched_ours=True).id)
    monkeypatch.setattr(jobs_queue, "enqueue_naver_return",
                        lambda *a, **k: pytest.fail("게이트가 꺼졌는데 큐에 들어갔다"))

    res = client.post(f"/admin/naver-ingest/{link_id}/return",
                      json={"reason": "COLOR_AND_SIZE"})
    assert res.status_code == 403


def test_return_route_says_so_when_queue_is_down(app, client, workbench_on, monkeypatch):
    """큐가 없으면 503 + 사유. 조용히 성공한 척하면 사람이 기다리다 놓친다."""
    from foms.services.jobs import queue as jobs_queue

    _login(client)
    link_id = int(_link(dispatched_ours=True).id)
    monkeypatch.setattr(jobs_queue, "enqueue_naver_return", lambda *a, **k: False)

    res = client.post(f"/admin/naver-ingest/{link_id}/return",
                      json={"reason": "COLOR_AND_SIZE"})

    assert res.status_code == 503
    assert "큐" in res.get_json()["error"]


def test_return_route_is_audited(app, client, workbench_on, monkeypatch):
    """감사 라벨이 붙는다 — 불가역 조작은 누가 눌렀는지가 기록이다."""
    from foms.services.jobs import queue as jobs_queue

    _login(client)
    link_id = int(_link(dispatched_ours=True).id)
    monkeypatch.setattr(jobs_queue, "enqueue_naver_return", lambda *a, **k: True)

    logged: list[dict] = []
    monkeypatch.setattr(
        "foms.web.admin.naver_ingest.log_access",
        lambda message, actor=None, **kw: logged.append(
            {"message": message, "actor": actor, **kw}))

    client.post(f"/admin/naver-ingest/{link_id}/return", json={"reason": "COLOR_AND_SIZE"})

    assert logged and logged[0]["action"] == "NAVER_INGEST_RETURN_ENQUEUE"
    assert logged[0]["detail"]["reason"] == "COLOR_AND_SIZE"
    # 감사 행에 **행위자**가 남아야 한다 — 누가 눌렀는지 없는 감사는 절반짜리다.
    assert logged[0]["actor"]


# ─────────────────────────────────────────────────────── R8 폴링 지문

def test_poll_fingerprint_flips_when_only_the_return_axis_moves(app, client, workbench_on):
    """반품 접수는 ``fulfillment`` 표식을 안 건드린다 — 그래도 지문이 바뀌어야 한다.

    안 바뀌면 화면이 "접수가 끝났다"를 영영 못 보고, 사용자에게는 눌러도 아무 일이
    없는 것으로 보인다. 새 엔드포인트를 만들지 않는 이유다.
    """
    from foms.web.admin.naver_ingest import _fulfillment_state

    _login(client)
    link = _link(dispatched_ours=True)
    with app.test_request_context():
        before = _fulfillment_state(db_session, link)["rev"]
    state = dict(link.triage_state or {})
    state["return"] = {"requested_at": "2026-08-27T09:00:00"}
    link.triage_state = state
    db_session.commit()
    with app.test_request_context():
        after = _fulfillment_state(db_session, link)
    assert after["rev"] != before
    assert after["returned"] == 1


# ──────────────────────────────────────────────────────────── R7 화면

def test_return_button_is_absent_before_dispatch(app, client, workbench_on):
    """안 나간 물건은 반품이 아니라 취소다 — 버튼 자체를 내지 않는다."""
    _login(client)
    _link()
    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    assert 'id="wb-return"' not in body


def test_return_button_appears_after_dispatch(app, client, workbench_on):
    """발송분이 있는 집에는 버튼과 확인 모달이 함께 뜬다(불가역 경로 — 모달 필수).

    2026-08-27: "회수는 우리 차량이 갑니다" 문구는 사실이 아니었다(시공 전이라 실물이
    고객 집에 간 적이 없다 — 반품은 주문(금액)만 움직인다). 새 문구로 교체했고, 옛
    문구가 되살아나면 즉시 잡히도록 부정 단언을 함께 둔다.
    """
    _login(client)
    _link(dispatched_ours=True)
    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    assert 'id="wb-return"' in body
    assert 'id="wb-modal-return"' in body
    assert "되돌릴 수 없습니다" in body
    # 2026-08-31: 승인을 FOMS 에서도 할 수 있게 됐다(모달 체크박스, 기본 꺼짐).
    # 그래도 **기본은 접수까지**라, 체크를 안 켜면 환불이 안 나간다는 사실을 화면이 말한다.
    assert "승인까지 한 번에" in body
    assert 'id="wb-return-approve"' in body
    assert "켜지 않으면 이" in body and "환불이 나가지 않습니다" in body
    assert "물건은 오가지 않습니다" in body
    assert "주문(금액)만 반품" in body
    assert "회수는 우리 차량이 갑니다" not in body


def test_modal_restates_the_count_the_server_will_actually_send(app, client, workbench_on):
    """**혼합 사례** — 한 집에 나간 것과 안 나간 것이 섞이면 모달은 나간 것만 센다.

    3차 세션이 놓친 자리다: T8 테스트 9건이 전부 집당 1건짜리라 부분 발송 형태를 한 번도
    안 만들었고, 미발송 건에 불가역 반품이 나가는 결함을 못 봤다. 화면 쪽도 같은 함정이
    있다 — 집 전체 수로 재진술하면 사람은 3건이 나가는 줄 알고 누른다.
    """
    _login(client)
    order_no = f"N-RW-MIX-{_uid()}"
    _link(order_no=order_no, dispatched_ours=True)
    _link(order_no=order_no, dispatched_ours=False)
    _link(order_no=order_no, dispatched_ours=True, returned=True)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert 'id="wb-modal-return"' in body
    # 집은 3건, 서버가 보낼 것은 1건(안 나간 1건 + 이미 접수한 1건 제외).
    assert "상품주문 <b>1건</b>을" in body
    assert "발송된 1건만</b> 나갑니다" in body
    assert "이미 접수한 1건 제외" in body


def test_return_button_is_shown_disabled_while_a_claim_is_in_flight(app, client,
                                                                    workbench_on):
    """클레임이 도는 집은 서버가 거절한다 — 화면은 버튼을 **잠그되 보여 준다**.

    **이 단언은 2026-09-02 에 뒤집혔다(NVCLAIM-ORDER-01).** 예전 계약은
    ``'id="wb-return"' not in body`` 였는데, 그 "버튼을 아예 안 낸다"가 바로 그날 사고의
    복구를 막은 자리다: 황민철 집(ERP 5026)에서 추가상품 3건만 반품 성공하자 집이
    ``locked`` 가 됐고, 실패한 본품을 끝낼 버튼이 **렌더조차 되지 않아** 담당자에게
    판매자센터 수작업 말고는 길이 없었다.

    없는 버튼과 잠긴 버튼은 다른 것을 말한다 — 없는 버튼은 "여긴 그런 일이 없다"로 읽히고,
    잠긴 버튼은 "여기서 하는 일인데 지금은 이 이유로 못 한다"로 읽힌다. 불가역 경로에서
    **눌러도 안 나가는 버튼**을 활성으로 두는 것은 여전히 금지다(pane 주석) — 그래서
    ``disabled`` + 사유 ``title`` 이 정답이고, 판정 술어는 서버와 한 벌인
    :func:`fulfillment.return_sendable` 이다.
    """
    _login(client)
    _link(dispatched_ours=True, claim_status="RETURN_REQUEST")
    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    assert 'id="wb-return"' in body, "없는 버튼이 사고 복구를 막았다"
    assert 'id="wb-return" disabled' in body, "클레임이 도는데 버튼이 활성이다"


def test_return_button_is_locked_when_an_addon_is_left_out_of_scope(app, client,
                                                                   workbench_on):
    """**범위 규격**(FAQ 3880, 감사 F2) — 함께 갈 추가구성상품이 빠지면 버튼을 잠근다.

    서버는 이 조건이 깨지면 한 건도 안 보내고 거절한다
    (:func:`fulfillment.addon_return_gap`). 화면이 버튼을 열어 두면 담당자는 불가역
    호출인 줄 알고 누르고 예외만 받는다 — 술어를 서버와 한 벌로 둔다.

    잠그되 **보여 준다**. 없는 버튼은 "여긴 그런 일이 없다"로 읽힌다(RC3 의 교훈).
    """
    _login(client)
    order_no = f"N-RW-F2-{_uid()}"
    _link(order_no=order_no, dispatched_ours=True)
    _link(order_no=order_no, dispatched_ours=False, addon=True)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert 'id="wb-return"' in body, "없는 버튼이 사고 복구를 막았다"
    assert 'id="wb-return" disabled' in body, "추가구성상품이 빠졌는데 버튼이 활성이다"
    assert "함께 반품해야 하는 추가구성상품" in body, "왜 막혔는지가 화면에 없다"


def test_return_button_stays_open_when_every_addon_goes_together(app, client,
                                                                 workbench_on):
    """**음성 대조군** — 추가구성상품이 함께 나가는 집은 그대로 열려 있어야 한다.

    범위 가드가 정상 경로까지 잡아먹으면 F2 수정이 새 RC3 가 된다.
    """
    _login(client)
    order_no = f"N-RW-F2OK-{_uid()}"
    _link(order_no=order_no, dispatched_ours=True)
    _link(order_no=order_no, dispatched_ours=True, addon=True)

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert 'id="wb-return" disabled' not in body, "정상 집의 반품 버튼이 잠겼다"
    assert "함께 반품해야 하는 추가구성상품" not in body


def test_the_table_says_unknown_when_the_product_class_is_missing(app, client,
                                                                  workbench_on):
    """옛 수집분은 표가 `구성 미상` 이라고 말한다 — `본품` 이라 단정하지 않는다 (감사 F12)."""
    _login(client)
    link = _link(dispatched_ours=True)
    snapshot = dict(link.raw_snapshot)
    product_order = dict(snapshot["productOrder"])
    product_order.pop("productClass", None)
    snapshot["productOrder"] = product_order
    link.raw_snapshot = snapshot
    db_session.commit()

    body = client.get(TRIAGE_PATH).get_data(as_text=True)

    assert "구성 미상" in body, "근거 없는 판정을 사실처럼 적었다"


def test_screen_no_longer_tells_people_to_use_the_seller_center_for_returns(app, client,
                                                                           workbench_on):
    """버튼이 생긴 뒤에도 "판매자센터에서 반품하세요"가 남으면 화면이 자기와 모순된다."""
    _login(client)
    _link(dispatched_ours=True)
    body = client.get(TRIAGE_PATH).get_data(as_text=True)
    assert "<b>반품</b>으로 판매자센터에서 처리하세요" not in body


# ─────────────────────────────────────────────── 신규 mutation 계약 4종

@pytest.mark.parametrize("path", [
    "docs/harness/foms_order_mutation_policy_manifest.json",
    "docs/harness/foms_write_guard_manifest.json",
])
def test_new_mutation_route_is_registered_in_the_manifest(path):
    """신규 mutation 라우트는 manifest **2종**에 등재돼야 한다 (로컬 green → CI red 방지)."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    entry = doc["routes"].get("admin.naver_ingest_return")
    assert entry, f"{path}: admin.naver_ingest_return 미등재"
    assert entry["mode"] == "guard"
    assert entry["rule"] == "/admin/naver-ingest/<int:link_id>/return"


def test_new_audit_action_has_a_display_label():
    """새 감사 action 은 라벨을 가져야 한다 — 미등재면 FOMS CI red 다."""
    from foms.services.audit_message_display import ACTION_LABELS

    assert "NAVER_INGEST_RETURN_ENQUEUE" in ACTION_LABELS
