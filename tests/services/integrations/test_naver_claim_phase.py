"""클레임 **단계** 축 — 확정 전 취소를 확정과 갈라 놓는다 (2026-08-28).

왜 이 파일이 따로 있나
----------------------
후보 표와 유령 목록의 판정은 오랫동안 "``claimStatus`` 가 비어 있지 않은가" 한 비트였다.
그래서 세 가지가 같은 칸에 들어갔다:

* ``CANCEL_REQUEST`` — 네이버가 **아직 확정하지 않은** 취소 요청
* ``CANCEL_DONE`` — 확정된 취소
* ``CANCEL_REJECT`` — **거부**. 취소가 안 됐다는 뜻이고 그 결제는 살아 있다

표기만 틀린 게 아니었다. 유령 목록은 곧 **주문 폐기(soft delete) 허가증**이라, 승인 전
취소가 붙은 접수 단계 주문에 폐기 버튼이 열렸다(운영 ``link 79`` / 주문 ``#4998``).

**이 결함이 오래 산 이유는 테스트가 양성 표본만 봤기 때문이다.** 기존 후보표·유령 테스트의
입력은 전수 ``CANCEL_DONE``/``RETURN_DONE`` 이었고, ``CANCEL_REQUEST``·``CANCEL_REJECT`` 를
이 두 화면에 흘려 보는 테스트가 **하나도 없었다**. 여기 있는 것들이 그 음성 대조군이다.
"""
import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.ghost_orders import find_ghost_orders
from foms.services.integrations.naver_commerce.mapping import (
    CLAIM_PHASES,
    CLAIM_STATUS_LABELS,
    extract_claim,
    group_key_text,
)
from foms.services.integrations.naver_commerce.order_candidates import find_order_candidates
from models import ExternalOrderLink, Order, User
from tests.services.integrations._markup import is_disabled

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


def _login(client) -> User:
    user = User(username=f"phase_admin_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, status: str = "RECEIVED", tel: str) -> Order:
    order = Order(received_date="2026-08-27", customer_name=f"단계{_uid()}", phone=tel,
                  erp_phone_digits=tel.replace("-", ""), address="서울 강남구 1 101호",
                  product="붙박이장", status=status, payment_amount=0)
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, amount: int, tel: str, claim: str = "",
          order_id: int | None = None) -> ExternalOrderLink:
    product_order = {
        "productOrderId": f"PO-CP-{_uid()}",
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


def _ghost_row(order_id: int):
    return next((row for row in find_ghost_orders(db_session)["rows"]
                 if row["order_id"] == order_id), None)


# ── 매핑 계약 ────────────────────────────────────────────────────────────────

def test_every_labeled_claim_status_has_a_phase():
    """라벨과 단계는 **같은 키 집합**이어야 한다.

    라벨은 있는데 단계가 없으면 화면은 `취소 요청` 이라 적으면서 판정은 '모름'으로 떨어진다
    — 그게 정확히 이 사고의 모양이었다(`BLOCKING ⊆ LABELS` 계약과 같은 규율).
    """
    assert set(CLAIM_PHASES) == set(CLAIM_STATUS_LABELS), (
        f"라벨-단계 불일치: 단계만 {sorted(set(CLAIM_PHASES) - set(CLAIM_STATUS_LABELS))} · "
        f"라벨만 {sorted(set(CLAIM_STATUS_LABELS) - set(CLAIM_PHASES))}"
    )


def test_unknown_claim_status_never_reads_as_done():
    """모르는 상태는 `done` 이 아니다 — 모르면 파괴적 동작을 열지 않는다."""
    claim = extract_claim({"productOrder": {"claimStatus": "SOME_NEW_NAVER_STATUS"}})

    assert claim["phase"] == ""
    assert claim["phase"] != "done"


# ── 후보 표 (관계 — 네이버 옛 결제) ──────────────────────────────────────────

def test_cancel_request_reads_as_pending_not_done(app):
    """승인 전 취소는 `전부 취소 요청 — 확정 전`. 확정 취소와 같은 말을 하면 안 된다."""
    tel = "010-8100-0001"
    order = _order(tel=tel)
    _link(order_no="N-CP-1", amount=558_400, claim="CANCEL_REQUEST",
          order_id=int(order.id), tel=tel)
    new_link = _link(order_no="N-CP-1-NEW", amount=594_760, tel=tel)

    row = find_order_candidates(db_session, new_link)[0]

    assert row["naver_claim_code"] == "all_pending"
    assert row["naver_claim_label"] == "전부 취소 요청 — 확정 전"
    assert row["naver_pending_count"] == 1
    assert row["naver_canceled_count"] == 0, "확정 전인데 확정 칸에 셌다"
    assert row["naver_alive_count"] == 0


def test_cancel_reject_reads_as_alive(app):
    """취소 **거부**는 그 결제가 살아 있다는 뜻이다 — 예전에는 `전부 취소` 로 읽혔다."""
    tel = "010-8100-0002"
    order = _order(tel=tel)
    _link(order_no="N-CP-2", amount=500_000, claim="CANCEL_REJECT",
          order_id=int(order.id), tel=tel)
    new_link = _link(order_no="N-CP-2-NEW", amount=80_000, tel=tel)

    row = find_order_candidates(db_session, new_link)[0]

    assert row["naver_claim_code"] == "alive"
    assert row["naver_claim_label"] == "살아 있음"
    assert row["naver_alive_count"] == 1
    assert row["naver_canceled_count"] == 0
    assert row["naver_pending_count"] == 0


def test_mixed_done_and_pending_says_both(app):
    """확정과 확정 전이 섞이면 둘 다 말한다 — 한쪽으로 단정하지 않는다."""
    tel = "010-8100-0003"
    order = _order(tel=tel)
    _link(order_no="N-CP-3", amount=500_000, claim="CANCEL_DONE",
          order_id=int(order.id), tel=tel)
    _link(order_no="N-CP-3", amount=300_000, claim="CANCEL_REQUEST",
          order_id=int(order.id), tel=tel)
    new_link = _link(order_no="N-CP-3-NEW", amount=800_000, tel=tel)

    row = find_order_candidates(db_session, new_link)[0]

    assert row["naver_claim_code"] == "all_mixed"
    assert row["naver_claim_label"] == "전부 취소 — 확정 전 포함"
    assert row["naver_canceled_count"] == 1
    assert row["naver_pending_count"] == 1


def test_collect_done_is_still_pending(app):
    """수거 완료는 반품 **확정**이 아니다 — 환불 전 주문을 유령으로 접으면 안 된다."""
    tel = "010-8100-0004"
    order = _order(tel=tel)
    _link(order_no="N-CP-4", amount=400_000, claim="COLLECT_DONE",
          order_id=int(order.id), tel=tel)
    new_link = _link(order_no="N-CP-4-NEW", amount=400_000, tel=tel)

    row = find_order_candidates(db_session, new_link)[0]

    assert row["naver_claim_code"] == "all_pending"


# ── 유령 목록 · 폐기 게이트 ─────────────────────────────────────────────────

def test_pending_cancel_stays_in_the_list_but_locks_the_button(app):
    """확정 전 취소는 **목록에 남고**(담당자가 알아야 한다) 버튼만 잠근다."""
    tel = "010-8100-0011"
    order = _order(tel=tel)
    _link(order_no="N-CPG-1", amount=558_400, claim="CANCEL_REQUEST",
          order_id=int(order.id), tel=tel)

    row = _ghost_row(int(order.id))

    assert row is not None, "확정 전 취소가 목록에서 통째로 사라졌다"
    assert row["claim_phase"] == "pending"
    assert row["claim_text"] == "취소 요청 — 확정 전"
    assert row["can_discard"] is False, "확정 전인데 폐기 버튼이 열렸다"
    assert "확정" in row["discard_block"]


def test_rejected_cancel_is_not_a_ghost(app):
    """취소가 **거부**된 주문은 유령이 아니다 — 그 결제는 살아 있다."""
    tel = "010-8100-0012"
    order = _order(tel=tel)
    _link(order_no="N-CPG-2", amount=500_000, claim="CANCEL_REJECT",
          order_id=int(order.id), tel=tel)

    assert _ghost_row(int(order.id)) is None


def test_confirmed_cancel_still_opens_the_button(app):
    """양성 유지(회귀 방어) — 확정된 취소 + 접수 단계는 예전처럼 버튼이 열린다."""
    tel = "010-8100-0013"
    order = _order(tel=tel)
    _link(order_no="N-CPG-3", amount=500_000, claim="CANCEL_DONE",
          order_id=int(order.id), tel=tel)

    row = _ghost_row(int(order.id))

    assert row is not None
    assert row["claim_phase"] == "done"
    assert row["claim_text"] == "취소 완료"
    assert row["can_discard"] is True
    assert row["discard_block"] == ""


def test_discard_route_refuses_a_pending_cancel(app, client, workbench_on):
    """서버도 거절한다 — 화면만 막으면 주소를 아는 사람이 그대로 지운다."""
    _login(client)
    tel = "010-8100-0014"
    order = _order(tel=tel)
    order_id = int(order.id)
    _link(order_no="N-CPG-4", amount=558_400, claim="CANCEL_REQUEST",
          order_id=order_id, tel=tel)

    response = client.post(f"/admin/naver-ingest/ghost/{order_id}/discard", json={})

    assert response.status_code == 400, response.get_data(as_text=True)
    assert "확정" in response.get_json()["error"]
    db_session.expire_all()
    assert not db_session.get(Order, order_id).deleted_at, "확정 전인데 주문이 접혔다"


def test_band_shows_pending_row_without_a_button(app, client, workbench_on):
    """화면 실물 — 확정 전 행은 뜨되 폐기 버튼이 없다."""
    _login(client)
    tel = "010-8100-0015"
    order = _order(tel=tel)
    order_id = int(order.id)
    _link(order_no="N-CPG-5", amount=558_400, claim="CANCEL_REQUEST",
          order_id=order_id, tel=tel)

    body = client.get("/admin/naver-ingest/triage?tab=work").get_data(as_text=True)

    assert f'data-ghost-order-id="{order_id}"' in body, "확정 전 행이 안 보인다"
    assert "취소 요청 — 확정 전" in body
    assert "wb-ghost__claim--pending" in body, "확정 전인데 확정과 같은 색으로 칠했다"
    # 띠에는 폐기 버튼이 **없다**. 2026-09-04 부터 집 pane 에도 같은 판정의 버튼이 서므로
    # `data-order-id` 만으로는 두 자리가 안 갈린다 — 띠의 버튼 id 로 잰다.
    assert 'id="wb-ghost-discard"' not in body, "확정 전인데 띠에 폐기 버튼이 떴다"
    # pane 쪽은 **숨기지 않고 잠근다**(사용자 결정) — 숨기면 담당자가 관문 없는
    # 주문 목록 휴지통으로 간다.
    assert is_disabled(body, "wb-pane-ghost-discard"), "확정 전인데 pane 버튼이 열렸다"


def test_claim_badge_classes_all_have_css_rules():
    """템플릿이 쓰는 클레임 배지 클래스는 **전부 CSS 규칙이 있어야 한다**.

    `.wb-cand__claim--alive` 가 템플릿에만 있고 규칙이 없어서 오랫동안 기본 회색으로
    추락하고 있었다(2026-08-28). 색으로 뜻을 말하는 화면에서 규칙 누락은 조용한 오표기다.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    css = (root / "static/css/admin/naver-workbench.css").read_text(encoding="utf-8")
    used: set[str] = set()
    for name in ("templates/admin/naver_workbench.html",
                 "templates/admin/partials/naver_workbench_pane.html"):
        markup = (root / name).read_text(encoding="utf-8")
        used |= set(re.findall(r"wb-(?:cand|ghost)__claim--[a-z]+", markup))

    missing = sorted(cls for cls in used if f".{cls}" not in css)

    assert used, "배지 클래스를 하나도 못 찾았다 — 정규식이 낡았다"
    assert not missing, f"CSS 규칙이 없는 배지 클래스: {missing}"


# ── 교환 축 (R-2 · 2026-08-28) ───────────────────────────────────────────────
#
# 단계 축을 도입할 때 취소·반품만 봤다. `EXCHANGE_DONE` 도 `done` 이라, 교환이 끝난 주문에
# **폐기(soft delete) 버튼이 열렸다.** 교환 완료는 고객이 대체품을 받는다는 뜻이고 ERP 주문은
# 살아서 생산·배송을 기다린다 — `CANCEL_REJECT` 와 정확히 같은 부류다.
# 실데이터는 두 환경 모두 0건이라(교환 문자열 자체가 없다) **테스트가 유일한 관문**이다.

def test_exchange_done_is_not_a_ghost(app):
    """교환 완료 주문은 유령이 아니다 — 대체품을 보내야 하는 살아 있는 주문이다."""
    tel = "010-8100-0021"
    order = _order(tel=tel)
    _link(order_no="N-CPX-1", amount=500_000, claim="EXCHANGE_DONE",
          order_id=int(order.id), tel=tel)

    assert _ghost_row(int(order.id)) is None, "교환 완료가 폐기 목록에 들어왔다"


def test_exchange_request_is_not_a_ghost_either(app):
    """교환 **요청**도 마찬가지다 — 돈이 되돌아가는 축이 아니다."""
    tel = "010-8100-0022"
    order = _order(tel=tel)
    _link(order_no="N-CPX-2", amount=500_000, claim="EXCHANGE_REQUEST",
          order_id=int(order.id), tel=tel)

    assert _ghost_row(int(order.id)) is None


def test_discard_route_refuses_an_exchange(app, client, workbench_on):
    """서버도 거절한다 — 목록 계산이 나중에 바뀌어도 조용히 열리지 않게."""
    _login(client)
    tel = "010-8100-0023"
    order = _order(tel=tel)
    order_id = int(order.id)
    _link(order_no="N-CPX-3", amount=500_000, claim="EXCHANGE_DONE",
          order_id=order_id, tel=tel)

    response = client.post(f"/admin/naver-ingest/ghost/{order_id}/discard", json={})

    assert response.status_code == 400, response.get_data(as_text=True)
    db_session.expire_all()
    assert not db_session.get(Order, order_id).deleted_at, "교환 완료 주문이 접혔다"


def test_exchange_done_reads_as_alive_in_candidates(app):
    """후보 표도 같다 — 교환 완료를 `전부 취소 완료` 라고 세면 담당자가 재결제로 오해한다."""
    tel = "010-8100-0024"
    order = _order(tel=tel)
    _link(order_no="N-CPX-4", amount=500_000, claim="EXCHANGE_DONE",
          order_id=int(order.id), tel=tel)
    new_link = _link(order_no="N-CPX-4-NEW", amount=80_000, tel=tel)

    row = find_order_candidates(db_session, new_link)[0]

    assert row["naver_claim_code"] == "alive"
    assert row["naver_alive_count"] == 1
    assert row["naver_canceled_count"] == 0


def test_cancel_and_return_are_still_ghosts(app):
    """**음성 대조군** — 교환을 빼면서 취소·반품까지 빠지면 유령 화면이 통째로 죽는다."""
    for index, status in enumerate(("CANCEL_DONE", "RETURN_DONE")):
        tel = f"010-8100-003{index}"
        order = _order(tel=tel)
        _link(order_no=f"N-CPX-5{index}", amount=500_000, claim=status,
              order_id=int(order.id), tel=tel)

        assert _ghost_row(int(order.id)) is not None, f"{status} 가 유령 목록에서 사라졌다"


def test_collect_done_ghost_says_return_not_cancel(app):
    """수거 단계 반품을 **취소**라 부르지 않는다 (R-1).

    종류 판정이 `label.startswith("RETURN")` 이라 `COLLECTING`·`COLLECT_DONE` 이
    취소로 떨어졌다 — 정답 축은 `claimType`(없으면 상태 이름)이다.
    """
    tel = "010-8100-0041"
    order = _order(tel=tel)
    _link(order_no="N-CPX-6", amount=500_000, claim="COLLECT_DONE",
          order_id=int(order.id), tel=tel)

    row = _ghost_row(int(order.id))

    assert row is not None
    assert row["claim_kind"] == "반품", "수거 중인 반품을 취소라고 불렀다"
