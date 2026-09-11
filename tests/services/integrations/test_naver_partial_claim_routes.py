# -*- coding: utf-8 -*-
"""NVCLAIM-PARTIAL-01 — 부분 취소·반품의 큐·워커·라우트·미리보기·감사(계약 §2·§3).

web 은 큐에 넣기만 한다: 라우트가 ``product_order_ids`` 를 검사해 400·403 을 내고, 통과분만
``enqueue_*`` 로 넘기며 감사 기록에 고른 라인을 남긴다. 워커는 그 인자를 서비스로 그대로
흘린다. 미리보기 ``GET /claim-plan`` 은 web 에서 돌고 네이버를 **한 번도** 부르지 않는다 —
클라이언트 생성 자체를 raise 로 막아 0회를 증명한다.

서비스 계약은 ``test_naver_partial_claim``, 부분 취소 뒤 발송은
``test_naver_partial_claim_dispatch``, 화면은 ``test_naver_partial_claim_ui`` 가 본다.
픽스처·헬퍼는 ``naver_partial_claim_helpers`` 한 벌을 공유한다.
"""
from __future__ import annotations

from typing import Any

from db import db_session
from models import SecurityLog

from tests.services.integrations.naver_partial_claim_helpers import (  # noqa: F401
    _StubClient,
    _ext,
    _household_2354,
    _link,
    _login,
    _partial_off,
    partial_on,
    workbench_on,
)

# --------------------------------------------------------------------------- #
# 큐·워커 (계약 §2)
# --------------------------------------------------------------------------- #

class _FakeQueue:
    """``q.enqueue`` 인자를 기록하는 가짜 RQ 큐(test_naver_return_wiring.py 패턴)."""

    def __init__(self) -> None:
        self.seen: list[dict[str, Any]] = []

    def enqueue(self, path, *args, **kwargs):
        self.seen.append({"path": path, "args": args, "kwargs": kwargs})


def test_enqueue_cancel_passes_product_order_ids_only_when_given(monkeypatch):
    """목록을 주면 ``product_order_ids`` kwarg 로, None 이면 **kwarg 자체가 없다**(오늘 job 과 동일)."""
    from foms.services.jobs import queue as jobs_queue

    fake = _FakeQueue()
    monkeypatch.setattr(jobs_queue, "get_rq_queue", lambda: fake)

    assert jobs_queue.enqueue_naver_cancel(7, "INTENT_CHANGED", None, 42,
                                           product_order_ids=["PO-X", "PO-Y"]) is True
    assert jobs_queue.enqueue_naver_cancel(7, "INTENT_CHANGED", None, 42) is True

    with_ids, without = fake.seen
    assert with_ids["args"] == (7, "cancel", 42)
    assert with_ids["kwargs"]["product_order_ids"] == ["PO-X", "PO-Y"]
    assert "product_order_ids" not in without["kwargs"]
    assert without["kwargs"]["reason"] == "INTENT_CHANGED"


def test_enqueue_return_passes_product_order_ids_only_when_given(monkeypatch):
    """반품 큐도 같은 규칙 — None 이면 kwarg 부재."""
    from foms.services.jobs import queue as jobs_queue

    fake = _FakeQueue()
    monkeypatch.setattr(jobs_queue, "get_rq_queue", lambda: fake)

    assert jobs_queue.enqueue_naver_return(7, "COLOR_AND_SIZE", "색상", 42,
                                           product_order_ids=["PO-X"]) is True
    assert jobs_queue.enqueue_naver_return(7, "COLOR_AND_SIZE", "색상", 42) is True

    with_ids, without = fake.seen
    assert with_ids["args"] == (7, "return", 42)
    assert with_ids["kwargs"]["product_order_ids"] == ["PO-X"]
    assert with_ids["kwargs"]["approve"] is False
    assert "product_order_ids" not in without["kwargs"]


def test_worker_passes_product_order_ids_to_the_service(app, monkeypatch):
    """워커가 ``product_order_ids`` 를 서비스에 그대로 넘긴다(네이버 클라이언트는 스텁)."""
    from foms.services.jobs import tasks

    seen: dict[str, Any] = {}

    def _fake_cancel(session, client, *, link_id, reason, detail=None, actor_user_id=None,
                     product_order_ids=None):
        seen.update({"link_id": link_id, "reason": reason, "ids": product_order_ids})
        return {"canceled": ["X"], "skipped": [], "scope": "partial", "auto_added": []}

    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.fulfillment.cancel_order", _fake_cancel)
    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.client.NaverCommerceClient",
        lambda *a, **k: _StubClient())
    lid = _link("PO-PC-WK-M", order_no="N-PC-WK", addon=False)

    tasks.run_naver_fulfillment_task(lid, "cancel", 5, reason="INTENT_CHANGED",
                                     product_order_ids=["X"])

    assert seen == {"link_id": lid, "reason": "INTENT_CHANGED", "ids": ["X"]}


def test_worker_omits_the_kwarg_when_none(app, monkeypatch):
    """None 이면 워커는 kwarg 를 **안 넘긴다** — 옛 시그니처 가짜 서비스(test_naver_cancel.py:299 모양)가 TypeError 없이 받는다."""
    from foms.services.jobs import tasks

    seen: dict[str, Any] = {}

    def _old_shape_cancel(session, client, *, link_id, reason, detail=None, actor_user_id=None):
        seen.update({"link_id": link_id, "reason": reason})
        return {"canceled": [], "skipped": []}

    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.fulfillment.cancel_order", _old_shape_cancel)
    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.client.NaverCommerceClient",
        lambda *a, **k: _StubClient())
    lid = _link("PO-PC-WKN-M", order_no="N-PC-WKN", addon=False)

    tasks.run_naver_fulfillment_task(lid, "cancel", 5, reason="INTENT_CHANGED")

    assert seen == {"link_id": lid, "reason": "INTENT_CHANGED"}


# --------------------------------------------------------------------------- #
# 라우트 (계약 §3) — web 은 큐에 넣기만 한다
# --------------------------------------------------------------------------- #

def _capture_enqueue(monkeypatch, name: str) -> list[dict[str, Any]]:
    """``foms.services.jobs.queue.<name>`` 을 기록기로 바꾼다(**kwargs 로 새 인자도 받는다)."""
    calls: list[dict[str, Any]] = []

    def _fake(link_id, reason, detail=None, actor_user_id=None, **kwargs):
        calls.append({"link_id": link_id, "reason": reason, "detail": detail,
                      "actor_user_id": actor_user_id, **kwargs})
        return True

    monkeypatch.setattr(f"foms.services.jobs.queue.{name}", _fake)
    return calls


def _last_audit(action: str) -> SecurityLog:
    """그 action 의 마지막 감사 행."""
    db_session.expire_all()
    row = (db_session.query(SecurityLog).filter(SecurityLog.action == action)
           .order_by(SecurityLog.id.desc()).first())
    assert row is not None, f"{action} 감사 행이 없다"
    return row


def test_cancel_route_400s_on_an_empty_list(auth_client, monkeypatch, workbench_on, partial_on):
    """빈 목록은 400 — "선택 없으면 전체" 는 2026-08-14 사고의 모양이다(C2)."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_cancel")
    lid = _link("PO-PC-R0-M", order_no="N-PC-R0", addon=False)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/cancel",
                                json={"reason": "INTENT_CHANGED", "product_order_ids": []})

    assert response.status_code == 400
    assert response.get_json()["error"] == "대상 상품주문을 고르세요."
    assert calls == []


def test_cancel_route_400s_on_an_id_outside_the_household(auth_client, monkeypatch,
                                                          workbench_on, partial_on):
    """집 밖 id 는 400 이고 그 id 를 말한다 — 큐에 넣지 않는다."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_cancel")
    lid = _link("PO-PC-RX-M", order_no="N-PC-RX", addon=False)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/cancel",
                                json={"reason": "INTENT_CHANGED",
                                      "product_order_ids": ["PO-NOPE-ROUTE"]})

    assert response.status_code == 400
    assert "PO-NOPE-ROUTE" in response.get_json()["error"]
    assert calls == []


def test_cancel_route_403s_when_the_partial_gate_is_off_but_ids_are_given(auth_client, monkeypatch,
                                                                          workbench_on):
    """부분 선택 게이트가 꺼진 화면에서 목록이 오면 403 — 게이트 끄기가 롤백 경로다(C8)."""
    _partial_off(monkeypatch)
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_cancel")
    lid = _link("PO-PC-RG-M", order_no="N-PC-RG", addon=False)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/cancel",
                                json={"reason": "INTENT_CHANGED",
                                      "product_order_ids": ["PO-PC-RG-M"]})

    assert response.status_code == 403
    assert response.get_json()["error"] == "이 화면에서는 일부 상품주문만 고를 수 없습니다."
    assert calls == []


def test_cancel_route_passes_ids_to_the_queue_and_audits_them(auth_client, monkeypatch,
                                                              workbench_on, partial_on):
    """목록이 큐 kwarg 로 가고, 응답과 감사 원장이 ``scope="partial"`` 과 목록을 함께 남긴다."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_cancel")
    lid = _link("PO-PC-RQ-M", order_no="N-PC-RQ", addon=False)
    _link("PO-PC-RQ-A1", order_no="N-PC-RQ", addon=True)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/cancel",
                                json={"reason": "INTENT_CHANGED",
                                      "product_order_ids": ["PO-PC-RQ-A1"]})

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["scope"] == "partial"
    assert body["data"]["product_order_ids"] == ["PO-PC-RQ-A1"]
    assert len(calls) == 1 and calls[0]["product_order_ids"] == ["PO-PC-RQ-A1"]
    audit = _last_audit("NAVER_INGEST_CANCEL_ENQUEUE")
    assert audit.detail["product_order_ids"] == ["PO-PC-RQ-A1"]
    assert audit.detail["scope"] == "partial"


def test_cancel_route_without_the_key_enqueues_the_household(auth_client, monkeypatch,
                                                             workbench_on, partial_on):
    """★ 음성 대조군 — 키 부재 본문은 오늘처럼 집 전체: 큐에 ``product_order_ids`` 가 None 이거나 없다."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_cancel")
    lid = _link("PO-PC-RH-M", order_no="N-PC-RH", addon=False)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/cancel",
                                json={"reason": "INTENT_CHANGED"})

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert len(calls) == 1
    assert calls[0].get("product_order_ids") is None


def test_return_route_400s_on_an_empty_list(auth_client, monkeypatch, workbench_on, partial_on):
    """반품 라우트 — 빈 목록 400(취소의 거울)."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_return")
    lid = _link("PO-PC-RR0-M", order_no="N-PC-RR0", addon=False, dispatched=True)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/return",
                                json={"reason": "COLOR_AND_SIZE", "product_order_ids": []})

    assert response.status_code == 400
    assert response.get_json()["error"] == "대상 상품주문을 고르세요."
    assert calls == []


def test_return_route_passes_ids_to_the_queue_and_audits_them(auth_client, monkeypatch,
                                                              workbench_on, partial_on):
    """반품 라우트 — 목록이 큐로 가고 ``NAVER_INGEST_RETURN_ENQUEUE`` 감사 detail 에 남는다."""
    calls = _capture_enqueue(monkeypatch, "enqueue_naver_return")
    lid = _link("PO-PC-RRQ-M", order_no="N-PC-RRQ", addon=False, dispatched=True)
    _link("PO-PC-RRQ-A1", order_no="N-PC-RRQ", addon=True, dispatched=True)

    response = auth_client.post(f"/admin/naver-ingest/{lid}/return",
                                json={"reason": "COLOR_AND_SIZE",
                                      "product_order_ids": ["PO-PC-RRQ-A1"]})

    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["scope"] == "partial"
    assert body["data"]["product_order_ids"] == ["PO-PC-RRQ-A1"]
    assert len(calls) == 1 and calls[0]["product_order_ids"] == ["PO-PC-RRQ-A1"]
    audit = _last_audit("NAVER_INGEST_RETURN_ENQUEUE")
    assert audit.detail["product_order_ids"] == ["PO-PC-RRQ-A1"]
    assert audit.detail["scope"] == "partial"


# --------------------------------------------------------------------------- #
# 미리보기 GET /claim-plan (계약 §3, T5) — web 에서 돌고 네이버를 부르지 않는다
# --------------------------------------------------------------------------- #

def _plan(client, link_id: int, query: str) -> Any:
    """claim-plan 응답 전체(JSON)."""
    return client.get(f"/admin/naver-ingest/{link_id}/claim-plan?{query}")


def test_claim_plan_returns_the_default_selection(client, workbench_on, partial_on):
    """``po`` 부재 = 보낼 수 있는 전부(claim 순). 이미 취소된 C1 은 ``sendable False, reason_code "claim"``."""
    _login(client)
    order_no = "N-PC-CP"
    ids = _household_2354(order_no)

    response = _plan(client, ids["M"], "action=cancel")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["link_id"] == ids["M"]
    assert data["todo"] == [_ext(order_no, n) for n in ("A1", "A2", "A3", "M")]
    rows = {r["external_id"]: r for r in data["rows"]}
    assert rows[_ext(order_no, "C1")]["sendable"] is False
    assert rows[_ext(order_no, "C1")]["reason_code"] == "claim"
    assert rows[_ext(order_no, "M")]["is_addon"] is False
    assert len(data["rows"]) == 8


def test_claim_plan_applies_auto_companion(client, workbench_on, partial_on):
    """``po=M`` 만 고르면 서버가 A1~A3 을 자동 동반으로 붙이고 ``ok`` 다(결정 3)."""
    _login(client)
    order_no = "N-PC-CPA"
    ids = _household_2354(order_no)

    data = _plan(client, ids["M"], f"action=cancel&po={_ext(order_no, 'M')}").get_json()["data"]

    assert data["ok"] is True
    assert data["auto_added"] == [_ext(order_no, n) for n in ("A1", "A2", "A3")]
    assert data["todo"] == [_ext(order_no, n) for n in ("A1", "A2", "A3", "M")]
    assert data["selected"] == [_ext(order_no, "M")]


def test_claim_plan_says_so_on_an_empty_selection(client, workbench_on, partial_on):
    """``po=``(빈 문자열) = [] — ``ok False`` 와 고르라는 문장. 빈 선택은 전체가 아니다."""
    _login(client)
    ids = _household_2354("N-PC-CPE")

    data = _plan(client, ids["M"], "action=cancel&po=").get_json()["data"]

    assert data["ok"] is False
    assert data["message"] == "대상 상품주문을 고르세요."
    assert data["todo"] == []


def test_claim_plan_404s_when_the_gate_is_off(client, monkeypatch, workbench_on):
    """부분 선택 게이트가 꺼진 화면에는 이 경로가 없다(404)."""
    _partial_off(monkeypatch)
    _login(client)
    ids = _household_2354("N-PC-CPG")

    assert _plan(client, ids["M"], "action=cancel").status_code == 404


def test_claim_plan_400s_on_a_bad_action(client, workbench_on, partial_on):
    """``action`` 은 cancel|return 만 — 그 밖은 400 JSON."""
    _login(client)
    ids = _household_2354("N-PC-CPB")

    response = _plan(client, ids["M"], "action=swap")

    assert response.status_code == 400
    body = response.get_json()
    assert body["success"] is False
    assert body["error"] == "action 이 올바르지 않습니다."


def test_claim_plan_never_constructs_the_naver_client(client, monkeypatch, workbench_on,
                                                      partial_on):
    """미리보기는 순수 계산이다 — 클라이언트 생성 자체를 폭탄으로 바꿔도 200."""
    def _boom(*a, **k):
        raise AssertionError("claim-plan 이 NaverCommerceClient 를 만들었다 — web 에서 네이버로 나간다")

    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.client.NaverCommerceClient", _boom)
    _login(client)
    ids = _household_2354("N-PC-CPN")

    response = _plan(client, ids["M"], "action=return")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
