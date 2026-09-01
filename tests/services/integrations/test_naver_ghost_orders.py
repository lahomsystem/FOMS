"""유령 주문 — 네이버 결제가 전부 취소됐는데 살아 있는 ERP 주문 (R-2 · 2026-08-25).

``claim_watch`` 는 취소를 목격해 링크에 표시하고 알림만 낸다 — 주문 상태를 자동으로 바꾸지
않는 것이 규율이다(취소가 곧 주문 폐기는 아니다). 그래서 재결제가 안 오면 그 ERP 주문이
살아 있는 채로 남는데, **그 사실을 말하는 화면이 하나도 없었다**. 2026-08-25 스테이징
실조회에서 3건이 그렇게 남아 있었다(#4467 원주현 2,451,500원 · #4462 박선미 · #4466 강재상).

여기서 못박는 것 셋:

1. **전부 취소만** 유령이다(부분 취소는 정상 진행 중일 수 있다).
2. **네이버가 취소를 확정한 건만** 접힌다 — 확정 전에 접으면 취소가 거부됐을 때 살아
   있어야 할 주문이 휴지통에 있다. 단계는 더 이상 잠금 축이 아니고, 접수 이후 단계는
   **관리자가 사유를 적어야** 접힌다(사용자 결정 2026-09-02).
3. 취소 처리는 **soft delete** 다(휴지통 복구). hard delete 가 아니다.
"""
import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.ghost_orders import find_ghost_orders
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"ghost_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, status: str = "RECEIVED", tel: str = "010-7000-0001") -> Order:
    order = Order(received_date="2026-08-13", customer_name=f"유령{_uid()}", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 1 101호",
                  product="붙박이장", status=status, payment_amount=0)
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, amount: int, claim: str = "", order_id: int | None = None,
          tel: str = "010-7000-0001") -> ExternalOrderLink:
    product_order = {
        "productOrderId": f"PO-G-{_uid()}",
        "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel}, "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=product_order["productOrderId"],
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED" if order_id else "COLLECTED",
                             order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def test_all_canceled_order_is_a_ghost(app):
    """붙은 링크가 전부 취소면 유령이다 — 금액도 함께 센다."""
    order = _order()
    _link(order_no="N-GH-1", amount=1_500_000, claim="CANCEL_DONE", order_id=int(order.id))
    _link(order_no="N-GH-1", amount=951_500, claim="CANCEL_DONE", order_id=int(order.id))

    rows = [row for row in find_ghost_orders(db_session)["rows"]
            if row["order_id"] == int(order.id)]

    assert rows, "전부 취소된 주문이 유령 목록에 없다"
    assert rows[0]["naver_amount_total"] == 2_451_500
    assert rows[0]["naver_link_count"] == 2
    assert rows[0]["claim_kind"] == "취소"


def test_partially_canceled_order_is_not_a_ghost(app):
    """일부만 취소면 유령이 아니다 — 정상 진행 중일 수 있다."""
    order = _order(tel="010-7000-0002")
    _link(order_no="N-GH-2", amount=500_000, claim="CANCEL_DONE", order_id=int(order.id),
          tel="010-7000-0002")
    _link(order_no="N-GH-2", amount=300_000, order_id=int(order.id), tel="010-7000-0002")

    ids = [row["order_id"] for row in find_ghost_orders(db_session)["rows"]]

    assert int(order.id) not in ids


def test_returned_order_reads_as_return_not_cancel(app):
    """반품과 취소를 한 낱말로 뭉치지 않는다 — 사람이 보는 사실이 다르다."""
    order = _order(tel="010-7000-0003")
    _link(order_no="N-GH-3", amount=497_490, claim="RETURN_DONE", order_id=int(order.id),
          tel="010-7000-0003")

    row = next(row for row in find_ghost_orders(db_session)["rows"]
               if row["order_id"] == int(order.id))

    assert row["claim_kind"] == "반품"


def test_measure_stage_opens_the_button_but_demands_a_reason(app):
    """실측 이후 단계도 접힌다 — 단 사유를 적어야 한다 (사용자 결정 2026-09-02).

    예전에는 접수 단계만 열어 뒀는데, 그러면 결제가 확정 취소된 죽은 주문이 실측·도면
    대시보드에 영원히 남는다. 휴지통은 복구되므로 잃는 것은 없고, 남겨야 할 것은
    **왜 접었나**다.
    """
    order = _order(status="MEASURE", tel="010-7000-0004")
    _link(order_no="N-GH-4", amount=579_200, claim="CANCEL_DONE", order_id=int(order.id),
          tel="010-7000-0004")

    row = next(row for row in find_ghost_orders(db_session)["rows"]
               if row["order_id"] == int(order.id))

    assert row["can_discard"] is True
    assert row["discard_needs_reason"] is True
    assert row["discard_block"] == ""


def test_received_stage_needs_no_reason(app):
    """접수 단계는 그대로다 — 붙은 이력이 없어 사유를 묻지 않는다(음성 대조군)."""
    order = _order(tel="010-7000-0014")
    _link(order_no="N-GH-14", amount=100_000, claim="CANCEL_DONE", order_id=int(order.id),
          tel="010-7000-0014")

    row = next(row for row in find_ghost_orders(db_session)["rows"]
               if row["order_id"] == int(order.id))

    assert row["can_discard"] is True
    assert row["discard_needs_reason"] is False


def test_unconfirmed_cancel_still_locks_every_stage(app):
    """확정 전 취소는 단계와 무관하게 잠긴다 — 이 조건은 돈의 문제라 안 바뀐다.

    취소가 거부되면 살아 있어야 할 주문이 휴지통에 있게 된다.
    """
    order = _order(status="MEASURE", tel="010-7000-0015")
    _link(order_no="N-GH-15", amount=100_000, claim="CANCEL_REQUEST", order_id=int(order.id),
          tel="010-7000-0015")

    row = next(row for row in find_ghost_orders(db_session)["rows"]
               if row["order_id"] == int(order.id))

    assert row["can_discard"] is False
    assert "확정" in row["discard_block"]


def test_discard_soft_deletes_and_keeps_the_row(app, client, workbench_on):
    """취소 처리는 soft delete 다 — 행은 남고 `deleted_at` 만 찍힌다."""
    _login(client)
    order = _order(tel="010-7000-0005")
    # 요청 뒤에는 세션이 걷혀 인스턴스가 detach 된다 — id 를 미리 뽑아 둔다.
    order_id = int(order.id)
    _link(order_no="N-GH-5", amount=100_000, claim="CANCEL_DONE", order_id=order_id,
          tel="010-7000-0005")

    response = client.post(f"/admin/naver-ingest/ghost/{order_id}/discard", json={})

    assert response.status_code == 200, response.get_data(as_text=True)
    db_session.expire_all()
    refreshed = db_session.get(Order, order_id)
    assert refreshed is not None, "hard delete 됐다 — 휴지통 복구가 불가능해진다"
    assert refreshed.deleted_at, "deleted_at 이 안 찍혔다"


def test_discard_refuses_a_measured_order_without_a_reason(app, client, workbench_on):
    """사유 없이 접수 이후 단계를 접으려 하면 서버가 거절한다.

    화면만 막으면 주소를 아는 사람이 그대로 지운다 — 서버가 같은 조건을 든다.
    """
    _login(client)
    order = _order(status="MEASURE", tel="010-7000-0006")
    order_id = int(order.id)
    _link(order_no="N-GH-6", amount=100_000, claim="CANCEL_DONE", order_id=order_id,
          tel="010-7000-0006")

    response = client.post(f"/admin/naver-ingest/ghost/{order_id}/discard", json={})

    assert response.status_code == 400
    db_session.expire_all()
    assert not db_session.get(Order, order_id).deleted_at


def test_discard_refuses_a_measured_order_from_a_manager(app, client, workbench_on):
    """접수 이후 단계는 **관리자만** 접는다 — 사유를 적어도 MANAGER 는 못 접는다."""
    _login(client, role="MANAGER")
    order = _order(status="DRAWING", tel="010-7000-0016")
    order_id = int(order.id)
    _link(order_no="N-GH-16", amount=100_000, claim="CANCEL_DONE", order_id=order_id,
          tel="010-7000-0016")

    response = client.post(f"/admin/naver-ingest/ghost/{order_id}/discard",
                           json={"reason": "고객이 재주문 안 함"})

    assert response.status_code == 403
    db_session.expire_all()
    assert not db_session.get(Order, order_id).deleted_at


def test_discard_accepts_a_measured_order_with_a_reason(app, client, workbench_on):
    """관리자가 사유를 적으면 접수 이후 단계도 접힌다 — 사유는 감사 원장에 원문으로 남는다."""
    from models import SecurityLog

    _login(client)
    order = _order(status="MEASURE", tel="010-7000-0017")
    order_id = int(order.id)
    _link(order_no="N-GH-17", amount=100_000, claim="CANCEL_DONE", order_id=order_id,
          tel="010-7000-0017")

    response = client.post(f"/admin/naver-ingest/ghost/{order_id}/discard",
                           json={"reason": "실측만 하고 결제 취소 — 재결제 계획 없음"})

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(Order, order_id).deleted_at, "사유를 적었는데 안 접혔다"
    logged = [row for row in db_session.query(SecurityLog).all()
              if (row.action or "") == "NAVER_INGEST_GHOST_DISCARD"]
    assert logged, "감사 기록이 없다"
    detail = str(logged[-1].detail or "")
    assert "실측만 하고 결제 취소" in detail, "사유 원문이 원장에 없다"
    assert "MEASURE" in detail, "어느 단계를 접었는지가 원장에 없다"


def test_discard_refuses_an_order_that_is_not_a_ghost(app, client, workbench_on):
    """유령이 아닌 주문은 못 지운다 — 이 라우트가 범용 삭제 경로가 되면 안 된다."""
    _login(client)
    order = _order(tel="010-7000-0007")
    order_id = int(order.id)
    _link(order_no="N-GH-7", amount=100_000, order_id=order_id, tel="010-7000-0007")

    response = client.post(f"/admin/naver-ingest/ghost/{order_id}/discard", json={})

    assert response.status_code == 400
    db_session.expire_all()
    assert not db_session.get(Order, order_id).deleted_at


def test_discard_is_closed_when_the_gate_is_off(app, client):
    """게이트가 꺼져 있으면 라우트도 닫힌다 — 게이트가 이 기능의 롤백 경로다."""
    _login(client)
    order = _order(tel="010-7000-0008")
    order_id = int(order.id)
    _link(order_no="N-GH-8", amount=100_000, claim="CANCEL_DONE", order_id=order_id,
          tel="010-7000-0008")

    response = client.post(f"/admin/naver-ingest/ghost/{order_id}/discard", json={})

    assert response.status_code == 403


def test_band_renders_with_count_and_buttons(app, client, workbench_on):
    """처리 탭에 띠가 뜨고, 잠긴 주문에는 버튼이 없다."""
    _login(client)
    open_order = _order(tel="010-7000-0009")
    open_id = int(open_order.id)
    _link(order_no="N-GH-9", amount=100_000, claim="CANCEL_DONE", order_id=open_id,
          tel="010-7000-0009")
    locked = _order(status="MEASURE", tel="010-7000-0010")
    locked_id = int(locked.id)
    _link(order_no="N-GH-10", amount=200_000, claim="CANCEL_DONE", order_id=locked_id,
          tel="010-7000-0010")

    body = client.get("/admin/naver-ingest/triage?tab=work").get_data(as_text=True)

    assert "네이버 결제가 전부 취소된 주문" in body
    assert f'data-ghost-order-id="{open_id}"' in body
    assert f'data-order-id="{open_id}"' in body, "접수 단계인데 버튼이 없다"
    # 실측 단계도 버튼은 뜬다 — 대신 사유 표식이 붙는다(2026-09-02).
    assert f'data-order-id="{locked_id}"' in body, "실측 단계인데 버튼이 없다"
    assert 'data-needs-reason="1"' in body, "사유 표식이 없다 — JS 가 확인창만 띄운다"
    assert "관리자가 사유를 적어야 접힙니다" in body
