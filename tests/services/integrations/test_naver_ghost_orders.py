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
from foms.services.integrations.naver_commerce.ghost_orders import (
    find_ghost_orders,
    judge_order_discard,
)
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, Order, User
from tests.services.integrations._markup import is_disabled

PANE_PATH = "/admin/naver-ingest/triage/pane"

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
          tel: str = "010-7000-0001", relation: str = "NEW",
          address: str = "서울 강남구 1") -> ExternalOrderLink:
    product_order = {
        "productOrderId": f"PO-G-{_uid()}",
        "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "shippingAddress": {"name": "이수취", "tel1": tel,
                            "baseAddress": address, "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    snapshot = {"order": {"orderId": order_no, "ordererTel": tel}, "productOrder": product_order}
    link = ExternalOrderLink(channel=CHANNEL, external_id=product_order["productOrderId"],
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED" if order_id else "COLLECTED",
                             relation=relation, order_id=order_id)
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


# ── 집 pane 의 휴지통 버튼 (2026-09-04) ──────────────────────────────────────
#
# 급소는 하나다: **판정 축은 주문이지 집이 아니다.** pane 은 집 화면인데 휴지통은 주문을
# 접는다. `find_ghost_orders` 는 링크를 order_id 로 묶고 `canceled == link_count` 일 때만
# 유령으로 치므로, 살아 있는 추가결제 집이 하나라도 붙어 있으면 그 주문은 모집단에서
# 자동으로 빠진다. pane 이 자기 축으로 판정식을 새로 만들면 그 안전이 사라진다.


def _pane(client, link_id: int) -> str:
    """집 pane 조각 HTML."""
    response = client.get(f"{PANE_PATH}?link_id={link_id}")
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_data(as_text=True)


def test_judge_opens_a_fully_confirmed_cancel(app):
    """전부 취소·확정 + 접수 단계 — 열리고 사유도 필요 없다."""
    tel = "010-7100-0001"
    order = _order(tel=tel)
    _link(order_no="N-JD-1", amount=558_400, claim="CANCEL_DONE", order_id=int(order.id), tel=tel)

    view = judge_order_discard(db_session, int(order.id))

    assert view["applicable"] is True
    assert view["can_discard"] is True
    assert view["discard_needs_reason"] is False
    assert view["discard_block"] == ""
    assert view["claim_kind"] == "취소"


def test_judge_demands_a_reason_after_the_received_stage(app):
    """접수 이후 단계도 열리되 사유가 필요하다 — 단계 이름은 한글이다."""
    tel = "010-7100-0002"
    order = _order(status="MEASURE", tel=tel)
    _link(order_no="N-JD-2", amount=558_400, claim="CANCEL_DONE", order_id=int(order.id), tel=tel)

    view = judge_order_discard(db_session, int(order.id))

    assert view["can_discard"] is True
    assert view["discard_needs_reason"] is True
    assert view["status_label"] == "실측", "담당자에게 MEASURE 는 코드지 단계가 아니다"


def test_judge_locks_a_partially_canceled_order_and_counts(app):
    """부분 취소는 닫힌다 — 몇 건 중 몇 건인지 사람이 읽게 센다."""
    tel = "010-7100-0003"
    order = _order(tel=tel)
    _link(order_no="N-JD-3", amount=300_000, claim="CANCEL_DONE", order_id=int(order.id), tel=tel)
    _link(order_no="N-JD-3", amount=200_000, order_id=int(order.id), tel=tel)

    view = judge_order_discard(db_session, int(order.id))

    assert view["applicable"] is True
    assert view["can_discard"] is False
    assert "2건 중 1건만 취소" in view["discard_block"]


def test_judge_names_the_living_addon_house(app):
    """이 집만 취소되고 **다른 집**이 살아 있으면 그 집을 이름과 금액으로 짚는다."""
    tel = "010-7100-0004"
    order = _order(tel=tel)
    dead = _link(order_no="N-JD-4", amount=300_000, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)
    _link(order_no="N-JD-4-ADD", amount=1_082_140, order_id=int(order.id), tel=tel,
          relation="ADDON", address="서울 서초구 9")

    view = judge_order_discard(db_session, int(order.id), group_key=dead.group_key)

    assert view["can_discard"] is False, "살아 있는 추가결제 집이 있는데 열렸다"
    assert "이 집만 취소됐고" in view["discard_block"]
    assert "추가결제 N-JD-4-ADD(1,082,140원)" in view["discard_block"]


def test_judge_locks_before_naver_confirms(app):
    """확정 전 취소 요청은 닫힌다 — 거부되면 살아 있어야 할 주문이다."""
    tel = "010-7100-0005"
    order = _order(tel=tel)
    _link(order_no="N-JD-5", amount=558_400, claim="CANCEL_REQUEST",
          order_id=int(order.id), tel=tel)

    view = judge_order_discard(db_session, int(order.id))

    assert view["can_discard"] is False
    assert "확정" in view["discard_block"]


def test_judge_is_silent_for_an_order_without_any_claim(app):
    """클레임이 하나도 없으면 블록 자체를 그리지 않는다 — 상시 회색 버튼은 안 읽힌다."""
    tel = "010-7100-0006"
    order = _order(tel=tel)
    _link(order_no="N-JD-6", amount=558_400, order_id=int(order.id), tel=tel)

    view = judge_order_discard(db_session, int(order.id))

    assert view["applicable"] is False
    assert view["can_discard"] is False


def test_judge_agrees_with_the_band_on_the_order_axis(app):
    """**급소**: 살아 있는 집이 붙은 주문은 띠 모집단에도 없고 pane 도 열지 않는다."""
    tel = "010-7100-0007"
    order = _order(tel=tel)
    dead = _link(order_no="N-JD-7", amount=300_000, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)
    _link(order_no="N-JD-7-ADD", amount=90_000, order_id=int(order.id), tel=tel,
          relation="ADDON", address="서울 서초구 7")

    ids = [row["order_id"] for row in find_ghost_orders(db_session)["rows"]]
    view = judge_order_discard(db_session, int(order.id), group_key=dead.group_key)

    assert int(order.id) not in ids, "띠가 이 주문을 유령으로 봤다"
    assert view["can_discard"] is False, "pane 이 띠보다 헐겁게 판정했다"


def test_pane_opens_the_button_and_restates_the_order(app, client, workbench_on):
    """화면 실물 — 열린 버튼 + 주문번호·고객명 재진술(집 화면이지만 접히는 것은 주문이다)."""
    _login(client)
    tel = "010-7200-0001"
    order = _order(tel=tel)
    link = _link(order_no="N-PD-1", amount=558_400, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)

    body = _pane(client, int(link.id))

    assert not is_disabled(body, "wb-pane-ghost-discard")
    assert "이 ERP 주문을 휴지통으로" in body
    assert "되돌릴 수 있음" in body
    assert f"주문 #{order.id}" in body and order.customer_name in body
    assert "전부 취소 확정" in body


def test_pane_locks_and_says_why_instead_of_hiding(app, client, workbench_on):
    """닫힌 상태에서도 버튼을 숨기지 않는다 — 숨기면 관문 0인 주문 목록 휴지통으로 간다."""
    _login(client)
    tel = "010-7200-0002"
    order = _order(tel=tel)
    link = _link(order_no="N-PD-2", amount=300_000, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)
    _link(order_no="N-PD-2", amount=200_000, order_id=int(order.id), tel=tel)

    body = _pane(client, int(link.id))

    assert is_disabled(body, "wb-pane-ghost-discard"), "부분 취소인데 열렸다"
    assert "지금은 안 됨" in body
    # 잠긴 이유를 title 에만 두지 않는다 — 마우스 없는 기기에서는 영영 못 읽는다.
    assert "2건 중 1건만 취소" in body


def test_pane_shows_the_reason_box_only_to_an_admin(app, client, workbench_on):
    """비관리자에게는 사유 칸을 아예 띄우지 않는다 — 버튼을 닫고 이유를 말한다."""
    _login(client, role="MANAGER")
    tel = "010-7200-0003"
    order = _order(status="MEASURE", tel=tel)
    link = _link(order_no="N-PD-3", amount=558_400, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)

    body = _pane(client, int(link.id))

    assert is_disabled(body, "wb-pane-ghost-discard")
    assert "wb-pane-discard-reason" not in body, "못 쓸 칸을 띄웠다"
    assert "관리자만 사유를 적고 접을 수 있습니다" in body
    assert "실측 단계라" in body, "단계 이름이 enum 으로 샜다"


def test_pane_admin_gets_the_reason_box_with_the_stage_named(app, client, workbench_on):
    """관리자에게는 사유 칸이 뜨고, 어느 단계라 필요한지 한글로 말한다."""
    _login(client)
    tel = "010-7200-0004"
    order = _order(status="DRAWING", tel=tel)
    link = _link(order_no="N-PD-4", amount=558_400, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)

    body = _pane(client, int(link.id))

    assert not is_disabled(body, "wb-pane-ghost-discard")
    assert 'id="wb-pane-discard-reason"' in body
    assert "이 주문은 도면 단계입니다" in body


def test_pane_warns_about_a_repay_candidate_but_keeps_the_button_open(app, client, workbench_on):
    """재결제 짝이 있어도 잠그지 않는다 — 경고만 띄우고 버튼 **위**에 둔다."""
    _login(client)
    tel = "010-7200-0005"
    order = _order(tel=tel)
    link = _link(order_no="N-PD-5", amount=558_400, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)
    _link(order_no="N-PD-5-NEW", amount=2_340_000, tel=tel)

    body = _pane(client, int(link.id))

    assert not is_disabled(body, "wb-pane-ghost-discard"), "경고인데 잠갔다"
    assert "재결제 후보가 있습니다" in body
    assert "N-PD-5-NEW" in body and "2,340,000원" in body
    assert "정리 계획 열기" in body
    assert body.index("재결제 후보가 있습니다") < body.index("wb-pane-ghost-discard"), \
        "경고가 버튼 아래에 있으면 누른 뒤에 읽힌다"


def test_pane_fragment_and_full_render_agree(app, client, workbench_on):
    """조각 렌더와 전체 렌더가 **같은 판정**을 낸다(둘 다 `_pane_context` 하나를 쓴다)."""
    _login(client)
    tel = "010-7200-0006"
    order = _order(tel=tel)
    link = _link(order_no="N-PD-6", amount=558_400, claim="CANCEL_DONE",
                 order_id=int(order.id), tel=tel)

    fragment = _pane(client, int(link.id))
    full = client.get(
        f"/admin/naver-ingest/triage?tab=work&link_id={link.id}").get_data(as_text=True)

    assert is_disabled(fragment, "wb-pane-ghost-discard") is False
    assert is_disabled(full, "wb-pane-ghost-discard") is False
    assert f'data-order-id="{order.id}"' in fragment and f'data-order-id="{order.id}"' in full


def test_pane_button_reuses_the_existing_route(app):
    """새 라우트를 만들지 않는다 — JS 가 기존 discard 라우트를 부르고 화면을 다시 읽는다."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    source = (root / "static/js/admin/naver-workbench.js").read_text(encoding="utf-8")

    assert "'wb-pane-ghost-discard': submitPaneGhostDiscard" in source
    body = source.split("async function submitPaneGhostDiscard")[1].split("\n    }")[0]
    assert "/discard'" in body and "ghost/" in body, "라우트가 바뀌었다"
    assert "softRefresh()" in body, "pane 에는 지울 행이 없다 — 다시 읽어야 한다"
    assert "window.confirm" in body, "확인창 1회는 유지한다"


def test_band_names_the_stage_in_korean(app, client, workbench_on):
    """유령 주문 띠도 단계를 한글로 말한다 — 감사 원장에는 enum 이 그대로 남는다."""
    _login(client)
    tel = "010-7300-0001"
    order = _order(status="MEASURE", tel=tel)
    _link(order_no="N-BD-1", amount=558_400, claim="CANCEL_DONE", order_id=int(order.id), tel=tel)

    body = client.get("/admin/naver-ingest/triage?tab=work").get_data(as_text=True)

    assert "실측 단계 — 관리자가 사유를 적어야 접힙니다" in body
    assert 'data-stage="실측"' in body
