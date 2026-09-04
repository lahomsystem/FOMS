"""재결제 정리 라우트 계약 — `POST /admin/naver-ingest/<link_id>/reconcile` (R-3 · 2026-08-25).

왜 이 파일이 있나
-----------------
재결제로 판명된 새 집을 정리하려면 담당자는 두 가지를 해야 했다: 새 집 **붙이기** ·
**ERP 기존 주문 처리**. 둘이 서로 다른 화면·다른 버튼이라 하나만 하고 멈춘 흔적이
스테이징 실데이터에 4건 남아 있었다(#4462 · #4466 · #4485 · #4467). 이 라우트는 그 둘을
**한 트랜잭션**으로 묶는다 — 그래서 여기서 못박아야 할 것은 "동작한다"가 아니라
**반쪽 상태가 생기지 않는다**는 쪽이다.

이 파일이 지키는 계약:

1. **승계(SUCCEED)** 는 붙이고 주문을 그대로 둔다 — 응답이 넣을 예약금을 말한다.
2. **취소 처리(DISCARD)** 는 soft delete 만 하고 **붙이지 않는다**. 휴지통에 든 주문에
   새 집을 묶으면 ``주문 만들기`` 가 막혀 사람이 되돌리기를 한 번 더 눌러야 한다(D-2).
3. **원자성** — 붙이기가 거절되면 ERP 쪽에 흔적이 남지 않는다(둘 다 되거나 둘 다 안 된다).
4. **후보 밖 주문은 거절** — 이 라우트가 범용 삭제·연결 경로가 되면 안 된다.
5. **잠긴 단계는 서버가 거절** — 화면만 막으면 주소를 아는 사람이 그대로 지운다.
6. 게이트가 꺼져 있으면 라우트도 닫힌다(게이트가 롤백 경로다).
7. 갈래·관계값은 닫힌집합이다.
8. **예약금은 자동 반영하지 않는다** — 응답에는 넣을 금액이 실리지만 DB 는 안 바뀐다(D-1).
9. 누가 무엇을 정리했는지 감사 원장에 남는다.

서비스 함수(``repay_reconcile``) 단위 계약은 별도 파일이 맡는다. 여기서는 **HTTP 경계**
(상태 코드 · 응답 본문 · 요청 뒤 DB 상태)만 본다.

요청은 자기 세션에서 커밋하므로 요청 뒤 ORM 인스턴스는 detach 된다 — id 를 **미리**
``int()`` 로 뽑고, 검증은 ``expire_all()`` 후 id 로 다시 읽어서 한다.
"""

from __future__ import annotations

from typing import Optional

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, SecurityLog

_SEQ = [0]

RECONCILE_ACTION = "NAVER_INGEST_REPAY_RECONCILE"


def _uid() -> str:
    """테스트끼리 값이 겹치지 않도록 붙이는 일련번호."""
    _SEQ[0] += 1
    return f"{_SEQ[0]:04d}"


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all). 빼면 라우트가 403 이다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _order(*, tel: str, name: str = "", status: str = "RECEIVED",
           address: str = "서울 강남구 테헤란로 152 101호",
           structured: Optional[dict] = None) -> int:
    """기존 ERP 주문 1건. 후보 매칭이 **전화 digits** 로 걸리므로 ``tel`` 이 열쇠다.

    Args:
        tel: 고객 전화(하이픈 표기). ``erp_phone_digits`` 도 함께 채운다.
        name: 고객명(비우면 자동 생성 — 이름·주소 규칙에 우연히 걸리지 않게 한다).
        status: 진행 단계. ``RECEIVED`` 여야 취소 처리 갈래가 열린다.
        address: 주소.
        structured: ``structured_data`` 초기값.

    Returns:
        주문 id(요청 뒤 detach 되므로 처음부터 id 만 들고 다닌다).
    """
    order = Order(received_date="2026-08-20", customer_name=name or f"정리고객{_uid()}",
                  phone=tel, erp_phone_digits=tel.replace("-", ""), address=address,
                  product="붙박이장", status=status, payment_amount=0,
                  structured_data=structured)
    db_session.add(order)
    db_session.commit()
    return int(order.id)


def _link(*, order_no: str, amount: int, tel: str, order_id: Optional[int] = None,
          address: str = "서울 강남구 테헤란로 152") -> int:
    """네이버 수집 링크 1건(= 새 집의 상품주문 하나).

    같은 ``order_no``·``tel``·``address`` 를 주면 **같은 집**이 된다(붙이기는 집 단위).

    Args:
        order_no: 네이버 주문번호.
        amount: 이 상품주문의 결제 금액(집 합계가 예약금 안내 금액이 된다).
        tel: 수취인·주문자 전화 — 후보 매칭 열쇠.
        order_id: 이미 붙어 있는 주문 id(원자성 시나리오용).
        address: 배송지 기본주소.

    Returns:
        링크 id.
    """
    product_order = {
        "productOrderId": f"PO-RC-{_uid()}",
        "productName": "로라 무몰딩 1cm",
        "totalPaymentAmount": amount,
        # 수취인 이름은 매번 다르게 준다 — 이름·주소 규칙(60점)으로 엉뚱한 주문이
        # 후보에 섞여 들어오면 후보 밖 거절 테스트가 조용히 무력해진다.
        "shippingAddress": {"name": f"수취{_uid()}", "tel1": tel,
                            "baseAddress": address, "detailedAddress": "101호"},
    }
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel},
                "productOrder": product_order}
    link = ExternalOrderLink(
        channel=CHANNEL, external_id=product_order["productOrderId"],
        external_order_no=order_no, raw_snapshot=snapshot,
        group_key=group_key_text(snapshot),
        sync_status="LINKED" if order_id else "COLLECTED",
        relation="REPAY" if order_id else "NEW",
        order_id=order_id,
    )
    db_session.add(link)
    db_session.commit()
    return int(link.id)


def _reconcile(client, link_id: int, *, order_id: int, relation: str = "REPAY",
               fork: str = "SUCCEED", reason: str = ""):
    """정리 라우트 호출 한 줄."""
    return client.post(f"/admin/naver-ingest/{link_id}/reconcile",
                       json={"order_id": order_id, "relation": relation, "fork": fork,
                             "reason": reason})


def _login_as(client, *, role: str):
    """지정 역할로 세션을 바꾼다 — 관리자 전용 관문을 반대편에서 두드리기 위해."""
    from werkzeug.security import generate_password_hash

    from models import User

    user = User(username=f"rc_{role.lower()}_{_uid()}",
                password=generate_password_hash("pw"), role=role, team="CS",
                name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _fresh_order(order_id: int) -> Order:
    """요청 뒤 주문을 DB 에서 다시 읽는다(detach 된 인스턴스를 믿지 않는다)."""
    db_session.expire_all()
    return db_session.get(Order, order_id)


def _fresh_link(link_id: int) -> ExternalOrderLink:
    """요청 뒤 링크를 DB 에서 다시 읽는다."""
    db_session.expire_all()
    return db_session.get(ExternalOrderLink, link_id)


def test_succeed_attaches_the_household_and_reports_the_deposit(auth_client, workbench_on):
    """승계 — 새 집이 기존 주문에 붙고, 응답이 **넣을 예약금**을 말한다.

    재결제는 옛 돈이 환불된 경우라 예약금을 **바꾼다**(더하면 이중 계상이다).
    """
    tel = "010-7100-0001"
    order_id = _order(tel=tel)
    link_id = _link(order_no="N-RC-1", amount=1_610_780, tel=tel)

    response = _reconcile(auth_client, link_id, order_id=order_id)

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["discarded"] is False, "승계인데 취소 처리로 기록됐다"
    assert data["attached"] == 1
    assert data["fork"] == "SUCCEED"
    assert data["deposit"]["target"] == 1_610_780, "새 집 금액이 안내 금액이 아니다"
    assert data["deposit"]["verb"] == "바꾸기"
    link = _fresh_link(link_id)
    assert link.order_id == order_id, "승계했는데 링크가 주문에 안 붙었다"
    assert link.relation == "REPAY"
    assert link.sync_status == "LINKED"
    assert _fresh_order(order_id).deleted_at is None, "승계는 주문을 그대로 둔다"


def test_discard_soft_deletes_the_order_and_never_attaches(auth_client, workbench_on):
    """취소 처리 — 기존 주문은 휴지통으로, 새 집은 **붙이지 않는다**.

    붙여 놓고 그 주문을 접으면 새 집이 휴지통에 든 주문에 묶여 ``주문 만들기`` 가 막힌다 —
    사람이 되돌리기를 한 번 더 눌러야 빠져나오는 함정이다(2026-08-25 D-2 확정).
    """
    tel = "010-7100-0002"
    order_id = _order(tel=tel)
    link_id = _link(order_no="N-RC-2", amount=500_000, tel=tel)

    response = _reconcile(auth_client, link_id, order_id=order_id, fork="DISCARD")

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["discarded"] is True
    assert data["attached"] == 0, "취소 처리인데 붙었다"
    assert data["deposit"] is None, "휴지통 간 주문에 예약금 안내는 뜻이 없다"
    order = _fresh_order(order_id)
    assert order is not None, "hard delete 됐다 — 휴지통 복구가 불가능해진다"
    assert order.deleted_at, "deleted_at 이 안 찍혔다"
    link = _fresh_link(link_id)
    assert link.order_id is None, "취소 처리가 새 집을 휴지통 주문에 묶었다"
    assert link.sync_status == "COLLECTED", "새 집은 큐에 그대로 남아야 한다"


def test_a_refused_attach_leaves_the_erp_side_untouched(auth_client, workbench_on):
    """원자성 — 붙이기가 거절되면 ERP 쪽에 **아무 흔적도 안 남는다**.

    이미 다른 주문에 붙은 형제가 있는 집을 승계하면 붙이기가 거절된다. 그런데 붙이기는
    집을 순서대로 돌며 쓰다가 중간에 거절하므로(promotion.attach_link_to_order),
    라우트의 rollback 이 없으면 **먼저 지나간 형제만 남의 주문으로 넘어간 반쪽 상태**가
    남는다. 여기서는 자유 링크가 먼저(id 작은 쪽) 오도록 만들어 그 구간을 실제로 밟는다.
    """
    tel = "010-7100-0003"
    holder_id = _order(tel=tel, name="먼저붙은고객")
    target_id = _order(tel=tel, name="정리대상고객")
    # 자유 링크를 먼저 만든다 = 붙이기 루프가 이 줄을 쓴 **뒤** 형제에서 거절한다.
    free_link_id = _link(order_no="N-RC-3", amount=700_000, tel=tel)
    held_link_id = _link(order_no="N-RC-3", amount=300_000, tel=tel, order_id=holder_id)

    response = _reconcile(auth_client, free_link_id, order_id=target_id)

    assert response.status_code == 400, response.get_data(as_text=True)
    assert "이미 다른 주문" in response.get_json()["error"]
    assert _fresh_link(free_link_id).order_id is None, "거절됐는데 링크가 붙어 버렸다"
    assert _fresh_link(held_link_id).order_id == holder_id, "원래 붙어 있던 곳이 바뀌었다"
    target = _fresh_order(target_id)
    assert target.deleted_at is None
    assert not (target.structured_data or {}), "실패한 정리가 대상 주문에 흔적을 남겼다"
    holder = _fresh_order(holder_id)
    assert holder.deleted_at is None, "실패한 정리가 원래 주문을 건드렸다"
    assert not (holder.structured_data or {})


def test_reconcile_refuses_an_order_outside_the_candidates(auth_client, workbench_on):
    """후보 밖 주문은 거절한다 — 이 라우트가 범용 삭제 경로가 되면 안 된다.

    후보 목록 밖 id 를 받아 처리하면 주소를 아는 사람이 아무 주문이나 접을 수 있다.
    권한 규칙이 다른 주문 화면의 일이지 정리 화면의 일이 아니다.
    """
    stranger_id = _order(tel="010-7100-0041", name="상관없는고객",
                         address="부산 해운대구 우동 9 202호")
    link_id = _link(order_no="N-RC-4", amount=100_000, tel="010-7100-0042")

    response = _reconcile(auth_client, link_id, order_id=stranger_id, fork="DISCARD")

    assert response.status_code == 400, response.get_data(as_text=True)
    assert "후보" in response.get_json()["error"]
    assert _fresh_order(stranger_id).deleted_at is None, "후보도 아닌 주문이 지워졌다"


def test_discard_after_measure_needs_a_reason(auth_client, workbench_on):
    """접수 이후 단계는 **사유 없이는** 거절한다 — 잠그지 않고 이유를 받는다.

    2026-09-04 정책 동기화: 예전에는 ``MEASURE`` 부터 완전 잠금이었다. 그래서 유령 주문
    띠는 사유를 적으면 접히는데 이 화면은 아예 못 접어, 같은 상수가 두 화면에서 다른 뜻으로
    읽혔다(`ghost_orders.DISCARDABLE_STATUSES`).
    """
    tel = "010-7100-0005"
    order_id = _order(tel=tel, status="MEASURE")
    link_id = _link(order_no="N-RC-5", amount=100_000, tel=tel)

    response = _reconcile(auth_client, link_id, order_id=order_id, fork="DISCARD")

    assert response.status_code == 400, response.get_data(as_text=True)
    assert "사유" in response.get_json()["error"] or "적어" in response.get_json()["error"]
    assert not _fresh_order(order_id).deleted_at, "사유 없이 접혔다"


def test_discard_after_measure_succeeds_with_a_reason(auth_client, workbench_on):
    """관리자가 사유를 적으면 접힌다 — 사유는 감사 원장에 원문으로 남는다."""
    tel = "010-7100-0015"
    order_id = _order(tel=tel, status="MEASURE")
    link_id = _link(order_no="N-RC-15", amount=100_000, tel=tel)

    response = _reconcile(auth_client, link_id, order_id=order_id, fork="DISCARD",
                          reason="고객이 같은 건을 새로 결제해 옛 주문을 접음")

    assert response.status_code == 200, response.get_data(as_text=True)
    assert _fresh_order(order_id).deleted_at is not None
    row = (db_session.query(SecurityLog)
           .filter(SecurityLog.action == RECONCILE_ACTION)
           .order_by(SecurityLog.id.desc()).first())
    assert "새로 결제" in (row.detail or {}).get("discard_reason", "")


def test_discard_after_measure_refuses_a_manager(client, workbench_on):
    """접수 이후 단계는 **관리자만** 접는다 — 사유를 적어도 MANAGER 는 못 접는다."""
    _login_as(client, role="MANAGER")
    tel = "010-7100-0016"
    order_id = _order(tel=tel, status="DRAWING")
    link_id = _link(order_no="N-RC-16", amount=100_000, tel=tel)

    response = _reconcile(client, link_id, order_id=order_id, fork="DISCARD",
                          reason="고객이 재주문 안 함")

    assert response.status_code == 400, response.get_data(as_text=True)
    assert "관리자" in response.get_json()["error"]
    assert not _fresh_order(order_id).deleted_at


def test_reconcile_is_closed_when_the_gate_is_off(auth_client):
    """게이트가 꺼져 있으면 라우트도 닫힌다 — 게이트가 이 기능의 롤백 경로다."""
    tel = "010-7100-0006"
    order_id = _order(tel=tel)
    link_id = _link(order_no="N-RC-6", amount=100_000, tel=tel)

    response = _reconcile(auth_client, link_id, order_id=order_id)

    assert response.status_code == 403
    assert _fresh_link(link_id).order_id is None
    assert _fresh_order(order_id).deleted_at is None


def test_reconcile_rejects_an_unknown_fork(auth_client, workbench_on):
    """갈래는 닫힌집합이다(``SUCCEED``/``DISCARD``) — 오타가 조용히 삭제로 흐르면 안 된다."""
    tel = "010-7100-0007"
    order_id = _order(tel=tel)
    link_id = _link(order_no="N-RC-7", amount=100_000, tel=tel)

    for fork in ("DELETE", "", "WHATEVER"):
        response = _reconcile(auth_client, link_id, order_id=order_id, fork=fork)
        assert response.status_code == 400, f"{fork}: {response.get_data(as_text=True)}"

    assert _fresh_link(link_id).order_id is None
    assert _fresh_order(order_id).deleted_at is None


def test_reconcile_rejects_an_unattachable_relation(auth_client, workbench_on):
    """관계값도 닫힌집합이다 — ``NEW`` 는 붙이기가 아니라 주문 생성 경로다."""
    tel = "010-7100-0071"
    order_id = _order(tel=tel)
    link_id = _link(order_no="N-RC-71", amount=100_000, tel=tel)

    for relation in ("NEW", "", "WHATEVER"):
        response = _reconcile(auth_client, link_id, order_id=order_id, relation=relation)
        assert response.status_code == 400, f"{relation}: {response.get_data(as_text=True)}"

    assert _fresh_link(link_id).order_id is None


def test_succeed_never_writes_the_deposit_into_the_order(auth_client, workbench_on):
    """예약금은 **안내만** 한다 — 응답에 금액이 실려도 DB 는 그대로다 (D-1 확정).

    재결제·추가결제·부분환불이 섞이면 자동 셈이 틀리는 경우가 생기고, 그 틀림은
    ``잔금 = 출고가 − 예약금`` 공식을 타고 고객 청구로 흘러간다. 입력은 사람이 한다.
    """
    tel = "010-7100-0008"
    order_id = _order(tel=tel, structured={"payment": {"deposit": 300_000}})
    link_id = _link(order_no="N-RC-8", amount=1_200_000, tel=tel)

    response = _reconcile(auth_client, link_id, order_id=order_id)

    assert response.status_code == 200, response.get_data(as_text=True)
    deposit = response.get_json()["data"]["deposit"]
    assert deposit["current"] == 300_000
    assert deposit["target"] == 1_200_000, "안내 금액이 새 집 금액이 아니다"
    payment = (_fresh_order(order_id).structured_data or {}).get("payment") or {}
    assert payment.get("deposit") == 300_000, "시스템이 예약금을 대신 넣었다"


def test_reconcile_is_audited(auth_client, workbench_on):
    """누가 어느 주문을 어떻게 정리했는지 감사 원장에 남는다."""
    tel = "010-7100-0009"
    order_id = _order(tel=tel)
    link_id = _link(order_no="N-RC-9", amount=100_000, tel=tel)

    response = _reconcile(auth_client, link_id, order_id=order_id, fork="DISCARD")

    assert response.status_code == 200, response.get_data(as_text=True)
    logs = (db_session.query(SecurityLog)
            .filter(SecurityLog.action == RECONCILE_ACTION).all())
    assert logs, "재결제 정리 감사 로그가 없다"
    assert logs[0].target_type == "order"
    assert logs[0].target_id == order_id
