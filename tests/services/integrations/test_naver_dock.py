"""NAVER-INGEST-01 T14-B: 네이버 원본 도크 계약 테스트 (SQLite 레인).

고정하는 것:

* 본품/추가옵션 판정은 원본 ``productClass`` 가 정본 — ``추가구성상품`` = 추가옵션,
  그 외(조합형옵션상품 등) = 본품. productClass 가 없으면 금액 최대 행을 본품으로 폴백.
* 귀속 추정: 단일 본품 = 자동, 복수 본품 = 이름 토큰 매칭, 단서 없음 = None(사람 지정).
* 체크·귀속 상태는 ``ExternalOrderLink.triage_state`` 에 즉시 저장(팀 공유)되고
  주문 데이터(items·spec_rows)는 절대 건드리지 않는다(폼 불가침).
* 편집 페이지 bootstrap JSON 에 naver_origin 이 동봉된다(네이버 수집 주문만).
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.dock import (
    ASSIGN_COMMON,
    build_dock_payload,
    build_width_hint,
    parse_length_mm,
    split_option_copies,
)
from foms.services.orders.order_create import create_order
from models import ExternalOrderLink, Order, SecurityLog, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _staff() -> User:
    user = User(username=f"dock_staff_{_uid()}", password=generate_password_hash("pw"),
                role="STAFF", team="CS", name="접수 담당", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _snapshot(*, product_name: str, option: str = "", product_class: str = "조합형옵션상품",
              amount: int = 100000, quantity: int = 1, order_no: str = "N-1",
              memo: str = "", orderer_name: str = "김주문",
              recipient_name: str = "이수취", claim_status: str = "",
              tel2: str = "", paid_at: str = "", pay_means: str = "",
              discount: int = 0) -> dict:
    return {
        "order": {"orderId": order_no, "ordererName": orderer_name,
                  "ordererTel": "010-1111-2222",
                  "paymentDate": paid_at, "paymentMeans": pay_means},
        "productOrder": {
            "productOrderId": f"PO-{_uid()}",
            "productName": product_name,
            "productOption": option,
            "productClass": product_class,
            "totalPaymentAmount": amount,
            "quantity": quantity,
            "shippingMemo": memo,
            "claimStatus": claim_status or None,
            "unitPrice": amount,
            "productDiscountAmount": discount,
            "shippingAddress": {"name": recipient_name, "tel1": "010-3333-4444",
                                "tel2": tel2,
                                "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
        },
    }


def _naver_order(owner: User) -> Order:
    order = create_order(
        db_session,
        actor_user_id=owner.id, owner_user_id=owner.id,
        order_fields=dict(received_date="2026-08-14", customer_name="이수취",
                          phone="010-3333-4444", address="서울 강남구 1 101호",
                          product="붙박이장", options="색상: 화이트",
                          status="RECEIVED"),
        structured_data={"source": "NAVER_SMARTSTORE"},
        is_erp_order=True,
    )
    db_session.flush()
    return order


def _link(order: Order | None, snapshot: dict, *, order_no: str = "N-1") -> ExternalOrderLink:
    link = ExternalOrderLink(
        channel="NAVER",
        external_id=snapshot["productOrder"]["productOrderId"],
        order_id=order.id if order is not None else None,
        external_order_no=order_no,
        sync_status="LINKED",
        raw_snapshot=snapshot,
    )
    db_session.add(link)
    db_session.commit()
    return link


def _login(client, user: User) -> None:
    user_id, username, role = user.id, user.username, user.role
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = role


# --------------------------------------------------------------------------- #
# 복사 칩 분해
# --------------------------------------------------------------------------- #

def test_split_option_copies_extracts_values():
    """"라벨: 값" 조각은 값만, 콜론 없는 조각은 통째로 칩이 된다."""
    copies = split_option_copies("사이즈: 150（무몰딩）/ 색상: 클린 화이트 / 피닉스바")
    assert copies == ["150（무몰딩）", "클린 화이트", "피닉스바"]


def test_split_option_copies_empty_input():
    assert split_option_copies("") == []
    assert split_option_copies(None) == []


# --------------------------------------------------------------------------- #
# 도크 payload — 본품/추가옵션 판정·귀속 추정
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# 총폭 힌트 (T14-I) — CS 가 손으로 하던 계산
# --------------------------------------------------------------------------- #

def test_parse_length_mm_handles_cm_mm_m():
    """240cm → 2400, 1cm → 10 — 사람이 손으로 하던 환산을 없앤다."""
    assert parse_length_mm("로라 무몰딩 여닫이 30cm") == 300
    assert parse_length_mm("240cm") == 2400
    assert parse_length_mm("길이추가(1cm): 로라 1cm") == 10
    assert parse_length_mm("2400mm") == 2400
    assert parse_length_mm("색상 화이트") is None


def _row(name, *, option="", quantity=1, role="main", assigned=None):
    return {"product_name": name, "option_text": option, "quantity": quantity,
            "role": role, "assigned_main": assigned, "external_id": name}


def test_width_hint_sums_modules_and_length_addons():
    """실사례: 30cm 모듈 12개 + 1cm 추가 12개 = 3,600 + 120 = 3,720."""
    main = _row("로라 무몰딩 여닫이 30cm", quantity=12)
    addon = _row("로라 무몰딩 여닫이(푸쉬) 1cm", option="길이추가(1cm)",
                 quantity=12, role="addon")
    hint = build_width_hint(main, [addon])
    assert hint["total_mm"] == 3720
    assert "300mm × 12" in hint["formula"] and "10mm × 12" in hint["formula"]
    assert hint["mismatch"] == []


def test_width_hint_ignores_non_length_addons():
    """수납구성(TYPE A)·거울도어는 폭과 무관하다 — 더하면 틀린 총폭이 나온다."""
    main = _row("로라 무몰딩 여닫이 30cm", quantity=10)
    addon = _row("TYPE A (반옷장)", option="수납구성: TYPE A", quantity=2, role="addon")
    hint = build_width_hint(main, [addon])
    assert hint["total_mm"] == 3000


def test_width_hint_flags_spec_mismatch():
    """고객이 본품은 무몰딩, 1cm 추가는 몰딩으로 주문하는 사고가 실재한다."""
    main = _row("로라 무몰딩 여닫이 30cm(푸쉬)", quantity=12)
    addon = _row("로라 몰딩 여닫이 (푸쉬) 1cm", option="길이추가(1cm)",
                 quantity=12, role="addon")
    hint = build_width_hint(main, [addon])
    assert hint["total_mm"] == 3720
    assert any("몰딩" in line for line in hint["mismatch"])


def test_width_hint_none_when_no_length_in_source():
    """길이를 못 읽으면 틀린 숫자를 만들지 않는다 — 힌트 자체를 안 준다."""
    assert build_width_hint(_row("붙박이장 세트", option="색상: 화이트"), []) is None


def test_payload_carries_width_hint_per_main(app):
    """도크 payload 는 본품별로 총폭 힌트를 싣는다."""
    order = _naver_order(_staff())
    main = _link(order, _snapshot(product_name="로라 무몰딩 여닫이 30cm",
                                  amount=800000, quantity=12))
    _link(order, _snapshot(product_name="로라 무몰딩 여닫이(푸쉬) 1cm",
                           option="길이추가(1cm)", product_class="추가구성상품",
                           amount=33200, quantity=12))
    payload = build_dock_payload(db_session, order)
    assert payload["width_hints"][main.external_id]["total_mm"] == 3720


def test_payload_flags_cancelled_orders(app):
    """주문을 만든 뒤 취소되는 건도 있다 — 도크가 규격 입력 전에 알려야 한다."""
    order = _naver_order(_staff())
    _link(order, _snapshot(product_name="본품", amount=500000,
                           claim_status="CANCEL_REQUEST"))
    assert build_dock_payload(db_session, order)["claim_label"] == "취소 요청"


def test_payload_has_no_claim_label_for_normal_order(app):
    """정상 주문에 경고를 띄우면 신호가 죽는다."""
    order = _naver_order(_staff())
    _link(order, _snapshot(product_name="본품", amount=500000))
    assert build_dock_payload(db_session, order)["claim_label"] == ""


def test_payload_carries_contact_and_payment_facts(app):
    """도크에 보조 연락처·결제·할인을 싣는다(T14-F). 묶음이면 할인은 합계다."""
    order = _naver_order(_staff())
    _link(order, _snapshot(product_name="본품", amount=800000, tel2="010-9999-8888",
                           paid_at="2026-08-14T16:27:12.156+09:00", pay_means="신용카드",
                           discount=11000))
    _link(order, _snapshot(product_name="옵션", product_class="추가구성상품",
                           amount=30000, discount=1000))
    payload = build_dock_payload(db_session, order)
    assert payload["recipient_tel2"] == "010-9999-8888"
    assert payload["paid_at"] == "2026-08-14T16:27"
    assert payload["pay_means"] == "신용카드"
    assert payload["discount"] == 12000


def test_payload_carries_shipping_memo_and_names(app):
    """도크 머리말: 수취인 이름·대리주문 표식·배송메모(상품주문별 서로 다른 값 전부)."""
    order = _naver_order(_staff())
    _link(order, _snapshot(product_name="본품", amount=800000, memo="문 앞에 놓아주세요"))
    _link(order, _snapshot(product_name="옵션", product_class="추가구성상품",
                           amount=30000, memo="부재 시 경비실"))
    payload = build_dock_payload(db_session, order)
    assert payload["recipient_name"] == "이수취"
    assert payload["orderer_name"] == "김주문"
    assert payload["orderer_differs"] is True
    assert payload["shipping_memo"] == "문 앞에 놓아주세요\n부재 시 경비실"


def test_payload_dedupes_identical_memo(app):
    """같은 메모가 상품주문마다 복사돼 오면 한 번만 보여준다."""
    order = _naver_order(_staff())
    _link(order, _snapshot(product_name="본품", amount=800000, memo="문 앞에 놓아주세요"))
    _link(order, _snapshot(product_name="옵션", product_class="추가구성상품",
                           amount=0, memo="문 앞에 놓아주세요"))
    assert build_dock_payload(db_session, order)["shipping_memo"] == "문 앞에 놓아주세요"


def test_payload_no_orderer_diff_when_same_person(app):
    """주문자=수취인이면 '다름' 표식을 켜지 않는다(대부분의 주문이 이 경우다)."""
    order = _naver_order(_staff())
    _link(order, _snapshot(product_name="본품", amount=500000,
                           orderer_name="이수취", recipient_name="이수취"))
    payload = build_dock_payload(db_session, order)
    assert payload["orderer_differs"] is False
    assert payload["shipping_memo"] == ""


def test_payload_roles_follow_product_class(app):
    """조합형옵션상품 = 본품, 추가구성상품 = 추가옵션."""
    order = _naver_order(_staff())
    _link(order, _snapshot(product_name="라홈 로라 240cm", option="사이즈: 240", amount=812000))
    _link(order, _snapshot(product_name="TYPE B", product_class="추가구성상품", amount=50000))

    payload = build_dock_payload(db_session, order)

    roles = {row["product_name"]: row["role"] for row in payload["rows"]}
    assert roles["라홈 로라 240cm"] == "main"
    assert roles["TYPE B"] == "addon"
    assert payload["order_no"] == "N-1"
    # 본품 칩 = 옵션 값들, 추가옵션 칩 = 이름.
    main_row = [r for r in payload["rows"] if r["role"] == "main"][0]
    addon_row = [r for r in payload["rows"] if r["role"] == "addon"][0]
    assert main_row["copies"] == ["240"]
    assert addon_row["copies"] == ["TYPE B"]


def test_payload_single_main_auto_assigns_addons(app):
    """본품이 하나면 모든 추가옵션이 자동 귀속(추정)된다."""
    order = _naver_order(_staff())
    main = _link(order, _snapshot(product_name="라홈 로라 240cm", amount=812000))
    _link(order, _snapshot(product_name="TYPE H", product_class="추가구성상품", amount=0))

    payload = build_dock_payload(db_session, order)

    addon = [r for r in payload["rows"] if r["role"] == "addon"][0]
    assert addon["guess_main"] == main.external_id
    assert "단일 본품" in addon["guess_reason"]


def test_payload_multi_main_guesses_by_name_clue(app):
    """본품 둘 — 원문에 본품 이름 단서가 있으면 그 본품으로 추정, 없으면 미정."""
    order = _naver_order(_staff())
    roras = _link(order, _snapshot(product_name="라홈 로라 안방 240cm", amount=812000))
    _link(order, _snapshot(product_name="라홈 보테가 작은방 160cm", amount=645000))
    clued = _link(order, _snapshot(product_name="길이추가 1cm", option="로라 무몰딩 여닫이",
                                   product_class="추가구성상품", amount=26560))
    unclued = _link(order, _snapshot(product_name="수납구성 TYPE D",
                                     product_class="추가구성상품", amount=30000))

    payload = build_dock_payload(db_session, order)

    by_ext = {row["external_id"]: row for row in payload["rows"]}
    assert by_ext[clued.external_id]["guess_main"] == roras.external_id
    assert by_ext[unclued.external_id]["guess_main"] is None
    assert "선택" in by_ext[unclued.external_id]["guess_reason"]


def test_payload_falls_back_to_max_amount_when_no_product_class(app):
    """productClass 부재 원본 — 금액 최대 행을 본품으로 폴백(map_group 대표 규칙과 동일)."""
    order = _naver_order(_staff())
    small = _snapshot(product_name="길이추가", product_class="추가구성상품", amount=20000)
    big = _snapshot(product_name="본품 옷장", product_class="추가구성상품", amount=900000)
    _link(order, small)
    _link(order, big)

    payload = build_dock_payload(db_session, order)

    roles = {row["product_name"]: row["role"] for row in payload["rows"]}
    assert roles["본품 옷장"] == "main"
    assert roles["길이추가"] == "addon"


def test_payload_none_when_no_links(app):
    """네이버 링크 없는 주문은 도크 자체가 없다."""
    order = _naver_order(_staff())
    assert build_dock_payload(db_session, order) is None


def test_payload_reflects_saved_state(app):
    """저장된 triage_state(체크·귀속)가 payload 에 그대로 실린다."""
    order = _naver_order(_staff())
    main = _link(order, _snapshot(product_name="본품", amount=500000))
    addon = _link(order, _snapshot(product_name="TYPE A", product_class="추가구성상품", amount=0))
    addon.triage_state = {"checked": True, "assigned_main": main.external_id}
    db_session.commit()

    payload = build_dock_payload(db_session, order)

    row = [r for r in payload["rows"] if r["external_id"] == addon.external_id][0]
    assert row["checked"] is True
    assert row["assigned_main"] == main.external_id


# --------------------------------------------------------------------------- #
# dock-state 저장 라우트
# --------------------------------------------------------------------------- #

def test_dock_state_staff_can_check_and_it_is_audited(app, client):
    """STAFF 체크 즉시 저장 + 감사 원장 기록. 주문 데이터는 불변."""
    staff = _staff()
    order = _naver_order(staff)
    link = _link(order, _snapshot(product_name="본품", amount=500000))
    link_id, order_id = link.id, order.id
    before_version = db_session.get(Order, order_id).mutation_version
    _login(client, staff)

    response = client.post(f"/admin/naver-ingest/{link_id}/dock-state", json={"checked": True})

    assert response.status_code == 200 and response.get_json()["success"] is True
    db_session.expire_all()
    saved = db_session.get(ExternalOrderLink, link_id).triage_state
    assert saved["checked"] is True and saved["checked_by"] is not None
    # 폼 불가침: 주문 낙관잠금 버전이 움직이지 않는다(주문 무변경의 관측 가능한 증거).
    assert db_session.get(Order, order_id).mutation_version == before_version
    actions = [row.action for row in db_session.query(SecurityLog).all()]
    assert "NAVER_DOCK_STATE_SET" in actions


def test_dock_state_uncheck_toggles_back(app, client):
    """체크 해제도 저장된다(토글) — reviewed_at 축과 무관."""
    staff = _staff()
    link = _link(_naver_order(staff), _snapshot(product_name="본품"))
    link_id = link.id
    _login(client, staff)

    client.post(f"/admin/naver-ingest/{link_id}/dock-state", json={"checked": True})
    client.post(f"/admin/naver-ingest/{link_id}/dock-state", json={"checked": False})

    db_session.expire_all()
    refreshed = db_session.get(ExternalOrderLink, link_id)
    assert refreshed.triage_state["checked"] is False
    assert refreshed.reviewed_at is None


def test_dock_state_assign_validates_sibling_main(app, client):
    """귀속은 같은 주문의 본품 external_id·COMMON·null 만 허용."""
    staff = _staff()
    order = _naver_order(staff)
    main = _link(order, _snapshot(product_name="본품", amount=500000))
    addon = _link(order, _snapshot(product_name="TYPE A", product_class="추가구성상품"))
    addon_id, main_ext = addon.id, main.external_id
    _login(client, staff)

    ok = client.post(f"/admin/naver-ingest/{addon_id}/dock-state",
                     json={"assigned_main": main_ext})
    common = client.post(f"/admin/naver-ingest/{addon_id}/dock-state",
                         json={"assigned_main": ASSIGN_COMMON})
    cleared = client.post(f"/admin/naver-ingest/{addon_id}/dock-state",
                          json={"assigned_main": None})
    foreign = client.post(f"/admin/naver-ingest/{addon_id}/dock-state",
                          json={"assigned_main": "PO-NOT-A-SIBLING"})

    assert ok.status_code == 200 and ok.get_json()["data"]["assigned_main"] == main_ext
    assert common.status_code == 200
    assert cleared.status_code == 200 and cleared.get_json()["data"]["assigned_main"] is None
    assert foreign.status_code == 400


def test_dock_state_requires_some_field_and_known_link(app, client):
    """빈 body 는 400, 없는 링크는 404."""
    staff = _staff()
    link = _link(_naver_order(staff), _snapshot(product_name="본품"))
    _login(client, staff)

    assert client.post(f"/admin/naver-ingest/{link.id}/dock-state", json={}).status_code == 400
    assert client.post("/admin/naver-ingest/999999/dock-state",
                       json={"checked": True}).status_code == 404


def test_dock_state_viewer_blocked(app, client):
    """VIEWER 는 저장 불가."""
    staff = _staff()
    link = _link(_naver_order(staff), _snapshot(product_name="본품"))
    link_id = link.id
    viewer = User(username=f"dock_viewer_{_uid()}", password=generate_password_hash("pw"),
                  role="VIEWER", team="CS", name="뷰어", is_active=True)
    db_session.add(viewer)
    db_session.commit()
    _login(client, viewer)

    response = client.post(f"/admin/naver-ingest/{link_id}/dock-state", json={"checked": True})

    assert response.status_code in (302, 403)


# --------------------------------------------------------------------------- #
# 편집 페이지 bootstrap 동봉
# --------------------------------------------------------------------------- #

def test_edit_page_bootstrap_carries_naver_origin(app, client):
    """네이버 수집 주문의 편집 페이지에 도크 데이터·마운트가 실린다."""
    staff = _staff()
    order = _naver_order(staff)
    _link(order, _snapshot(product_name="본품", option="사이즈: 240", amount=812000))
    order_id = order.id
    _login(client, staff)

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert "naver_origin" in html
    # 도크 전용 JSON — #erp-order-bootstrap 은 erp-order-shared.js 가 소비 후 제거하므로
    # 도크는 자기 데이터 태그가 반드시 따로 있어야 한다(스테이징 실사고 2026-08-14).
    assert 'id="naver-origin-data"' in html
    assert 'id="erpNaverDockPane"' in html
    assert "erp-naver-dock.js" in html


def test_edit_page_without_naver_source_has_no_dock(app, client):
    """일반 주문에는 도크 마운트가 없다(링크 쿼리도 나가지 않는 게이트)."""
    staff = _staff()
    order = create_order(
        db_session,
        actor_user_id=staff.id, owner_user_id=staff.id,
        order_fields=dict(received_date="2026-08-14", customer_name="일반 고객",
                          phone="010-5555-6666", address="서울 서초구 2",
                          product="옷장", options="", status="RECEIVED"),
        structured_data={},
        is_erp_order=True,
    )
    db_session.flush()
    db_session.commit()
    order_id = order.id
    _login(client, staff)

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert 'id="erpNaverDockPane"' not in html
