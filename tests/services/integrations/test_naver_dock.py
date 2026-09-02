"""NAVER-INGEST-01 T14-B: 네이버 원본 도크 계약 테스트 (SQLite 레인).

고정하는 것:

* 본품/추가옵션 판정은 원본 ``productClass`` 가 정본 — ``추가구성상품`` = 추가옵션,
  그 외(조합형옵션상품 등) = 본품. productClass 가 없으면 금액 최대 행을 본품으로 폴백.
* 귀속 추정: 단일 본품 = 자동, 복수 본품 = 이름 토큰 매칭, 단서 없음 = None(사람 지정).
* 체크·귀속 상태는 ``ExternalOrderLink.triage_state`` 에 즉시 저장(팀 공유)되고
  주문 데이터(items·spec_rows)는 절대 건드리지 않는다(폼 불가침).
* 편집 페이지 bootstrap JSON 에 naver_origin 이 동봉된다(네이버 수집 주문만).
* 결제 기록 요약은 **관계별로 갈라서** 싣는다(R1) — ``ADDON`` 은 더 낸 차액,
  ``REPAY`` 는 원 결제가 환불된 뒤 다시 낸 같은 물건값이라 문구가 달라야 한다.
* 워크벤치 처리 탭으로 돌아가는 링크(R2)는 **ADMIN·MANAGER 응답에만** 실린다 —
  STAFF 응답에는 주소 자체가 없다(숨기는 게 아니라 만들지 않는다).
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.dock import (
    ASSIGN_COMMON,
    build_dock_payload,
    build_width_hint,
    main_product_name,
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


def test_split_option_copies_trims_product_name_to_main_name():
    """``제품`` 칩은 메인 제품명만 남는다 — 규격(30cm)·꼬리 괄호 설명은 뗀다."""
    copies = split_option_copies(
        "제품: 보테가 슬라이딩 30cm （풀오토댐퍼 포함） / 컬러: 포그 그레이")
    assert copies == ["보테가 슬라이딩", "포그 그레이"]

    copies = split_option_copies(
        "제품: 로라 무몰딩 여닫이 30cm / 컬러: 클린 화이트 / 손잡이: 푸쉬타입")
    assert copies == ["로라 무몰딩 여닫이", "클린 화이트", "푸쉬타입"]


def test_split_option_copies_keeps_non_product_keys_intact():
    """제품명이 아닌 키의 값은 건드리지 않는다 — 규격·수량이 값 자체다."""
    assert split_option_copies("사이즈: 1800mm 이하 / 색상: 화이트") == [
        "1800mm 이하", "화이트"]
    assert split_option_copies("서랍: 1단(소)") == ["1단(소)"]
    assert split_option_copies("사이즈: 180（무몰딩）") == ["180（무몰딩）"]


def test_main_product_name_falls_back_to_source():
    """다 깎여 빈 값이 되면 원문을 돌려준다 — 칩이 사라지느니 원문이 낫다."""
    assert main_product_name("30cm") == "30cm"
    assert main_product_name("（상담）") == "（상담）"
    assert main_product_name("") == ""
    assert main_product_name("스타일러장") == "스타일러장"


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


def test_width_hint_axis_reads_option_over_product_line_name():
    """상품 라인 이름의 '무몰딩' 이 고객이 고른 옵션 '몰딩' 을 이기면 안 된다.

    2026-08-18 스테이징 실측: 본품 상품명은 '라홈 무몰딩 붙박이장 ...' 인데 옵션은
    '제품: 로라 몰딩 여닫이 30cm' 다. 본품·추가가 둘 다 몰딩인데 경고가 떴다(오탐).
    """
    main = _row("라홈 무몰딩 붙박이장 로라 시리즈 30cm 푸쉬타입 친환경 E0",
                option="제품: 로라 몰딩 여닫이 30cm / 컬러: 화이트 / 손잡이: 푸쉬타입",
                quantity=10)
    addon = _row("로라 몰딩 여닫이 (푸쉬) 1cm",
                 option="길이추가(1cm): 로라 몰딩 여닫이 (푸쉬) 1cm",
                 quantity=24, role="addon")
    hint = build_width_hint(main, [addon])
    assert hint["total_mm"] == 3240
    assert hint["mismatch"] == []


def test_width_hint_still_flags_real_axis_mismatch_from_option():
    """진짜 불일치는 옵션 원문에서 그대로 검출된다(문 방식 축)."""
    main = _row("라홈 로라 붙박이장 30cm",
                option="제품: 로라 무몰딩 여닫이 30cm / 손잡이: 푸쉬타입", quantity=10)
    addon = _row("보테가 슬라이딩 1cm",
                 option="길이추가(1cm): 보테가 슬라이딩 1cm", quantity=5, role="addon")
    hint = build_width_hint(main, [addon])
    assert any("문 방식" in line for line in hint["mismatch"])


def test_width_hint_reads_size_option_over_product_line_name():
    """운영 실사례 2026-08-31(주문 2026083175016621): 상품명 길이가 사이즈 옵션을 이겼다.

    본품 상품명은 '라홈 루나 3000 붙박이장 안방 작은방 슬라이딩 240cm' 인데 고객이 고른
    사이즈는 '330'(=330cm) 이다. 상품명의 '240cm' 를 읽어 2,400 + 340 = 2,740 이 떴다.
    사이즈 옵션이 정본이므로 3,300 + 340 = 3,640 이어야 한다.
    """
    main = _row("라홈 루나 3000 붙박이장 안방 작은방 슬라이딩 240cm", option="사이즈: 330")
    addon = _row("1cm", option="길이추가(1cm): 1cm", quantity=34, role="addon")
    hint = build_width_hint(main, [addon])
    assert hint["total_mm"] == 3640
    assert "3,300mm × 1" in hint["formula"]


def test_width_hint_size_option_units():
    """사이즈 값의 단위 해석 — 단위가 적혀 있으면 그대로, 없으면 cm(운영 표기)."""
    # 단위 없는 세 자리 = cm (운영 실데이터: 150/180/330).
    assert build_width_hint(_row("라홈 로라 180cm", option="사이즈: 150（몰딩） / 색상: 클린 화이트"),
                            [])["total_mm"] == 1500
    # 단위가 적혀 있으면 그대로 읽는다(냉장고장 '사이즈: 1800mm 이하').
    assert build_width_hint(_row("라홈 냉장고장", option="사이즈: 1800mm 이하 / 색상: 화이트"),
                            [])["total_mm"] == 1800
    # 네 자리 이상 단위 없는 값은 mm 표기로 본다 — cm 로 읽으면 30m 가 된다.
    assert build_width_hint(_row("라홈 냉장고장", option="사이즈: 3000 / 색상: 화이트"),
                            [])["total_mm"] == 3000
    # 사이즈가 아닌 키의 숫자는 폭이 아니다(서랍 1단을 1cm 로 읽으면 안 된다).
    assert build_width_hint(_row("라홈 내부 서랍 옵션", option="서랍: 1단(소)"), []) is None
    # 제품 키에 든 모듈 길이는 지금대로 읽는다(회귀 방지).
    assert build_width_hint(_row("라홈 무몰딩 붙박이장 로라 시리즈 30cm",
                                 option="제품: 로라 무몰딩 여닫이 30cm / 컬러: 화이트",
                                 quantity=10), [])["total_mm"] == 3000


def test_width_hint_reads_size_from_fullwidth_paired_option():
    """운영 실사례 2026-09-01(주문 2026090191203001): 키·값이 **전각 슬래시**로 짝지어 온다.

    원문 `사이즈 ／ 색상: 180cm ／ 클린 화이트 / 손잡이: 푸쉬타입 / 화장대: TYPE 01 （600mm）`
    — 그룹은 반각 `/`, 그룹 안의 짝은 전각 `／` 다. 반각으로만 자르면 키가 '색상' 으로 읽혀
    사이즈를 못 찾고 상품명의 '150cm' 로 떨어진다(총폭 1,500mm 오출력).
    """
    main = _row("라홈 로라 붙박이장 화장대 포함 누드 거울 작은방 여닫이 150cm 푸쉬타입 친환경 E0",
                option="사이즈 ／ 색상: 180cm ／ 클린 화이트 / 손잡이: 푸쉬타입"
                       " / 화장대: TYPE 01 （600mm）")
    hint = build_width_hint(main, [])
    assert hint["total_mm"] == 1800


def test_width_hint_pairs_fullwidth_keys_by_position():
    """전각 짝은 **자리로** 맞춘다 — 사이즈가 뒤에 오면 값도 뒤엣것을 읽는다."""
    main = _row("라홈 로라 150cm", option="색상 ／ 사이즈: 클린 화이트 ／ 210cm")
    assert build_width_hint(main, [])["total_mm"] == 2100
    # 짝이 모자라면 그 값은 안 쓴다(상품명으로 떨어진다).
    main2 = _row("라홈 로라 150cm", option="색상 ／ 사이즈: 클린 화이트")
    assert build_width_hint(main2, [])["total_mm"] == 1500


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
    """본품이 하나면 모든 추가옵션이 자동 귀속된다(수집 순서)."""
    order = _naver_order(_staff())
    main = _link(order, _snapshot(product_name="라홈 로라 240cm", amount=812000))
    _link(order, _snapshot(product_name="TYPE H", product_class="추가구성상품", amount=0))

    payload = build_dock_payload(db_session, order)

    addon = [r for r in payload["rows"] if r["role"] == "addon"][0]
    assert addon["guess_main"] == main.external_id
    assert "수집 순서" in addon["guess_reason"]


def test_payload_multi_main_assigns_addons_by_collection_order(app):
    """본품 둘 — 옵션은 **바로 위 본품**의 구성이다(2026-08-18 사용자 확정).

    네이버 응답 순서가 본품 → 그 본품의 옵션들이다. 이름 토큰 유사도로 추정하던 옛 방식은
    본품 이름이 비슷하면 엉뚱한 짝을 만들었다.
    """
    order = _naver_order(_staff())
    first = _link(order, _snapshot(product_name="라홈 로라 안방 240cm", amount=812000))
    first_addon = _link(order, _snapshot(product_name="수납구성 TYPE D",
                                         product_class="추가구성상품", amount=30000))
    second = _link(order, _snapshot(product_name="라홈 보테가 작은방 160cm", amount=645000))
    second_addon = _link(order, _snapshot(product_name="길이추가 1cm",
                                          option="로라 무몰딩 여닫이",
                                          product_class="추가구성상품", amount=26560))

    payload = build_dock_payload(db_session, order)

    by_ext = {row["external_id"]: row for row in payload["rows"]}
    assert by_ext[first_addon.external_id]["guess_main"] == first.external_id
    # 이름은 '로라' 단서를 갖고 있지만 순서가 정본이다 — 두 번째 본품에 붙는다.
    assert by_ext[second_addon.external_id]["guess_main"] == second.external_id


def test_payload_addon_before_first_main_attaches_to_first_main(app):
    """본품보다 먼저 온 옵션도 버리지 않고 첫 본품에 붙인다."""
    order = _naver_order(_staff())
    early = _link(order, _snapshot(product_name="제로조인트 추가",
                                   product_class="추가구성상품", amount=0))
    main = _link(order, _snapshot(product_name="라홈 로라 240cm", amount=812000))

    payload = build_dock_payload(db_session, order)

    by_ext = {row["external_id"]: row for row in payload["rows"]}
    assert by_ext[early.external_id]["guess_main"] == main.external_id


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


def test_payload_block_layout_uses_spec_axis_and_leaves_ambiguous_unset(app):
    """본품이 앞에 몰려 온 집 — 사양이 갈리면 그 본품에, 단서가 없으면 사람이 선택.

    순서만 쓰면 옵션이 전부 마지막 본품에 몰린다(2026-08-19 실데이터 3집).
    """
    order = _naver_order(_staff())
    molding = _link(order, _snapshot(product_name="라홈 무몰딩 붙박이장 30cm",
                                     option="제품: 로라 몰딩 여닫이 30cm", amount=600000))
    plain = _link(order, _snapshot(product_name="라홈 무몰딩 붙박이장 30cm",
                                   option="제품: 로라 무몰딩 여닫이 30cm", amount=1300000))
    molding_addon = _link(order, _snapshot(product_name="로라 몰딩 여닫이 1cm",
                                           option="길이추가(1cm): 로라 몰딩 여닫이 1cm",
                                           product_class="추가구성상품", amount=11000))
    neutral = _link(order, _snapshot(product_name="제로조인트 추가 (상담)",
                                     option="제로조인트: 제로조인트 추가 (상담)",
                                     product_class="추가구성상품", amount=0))

    payload = build_dock_payload(db_session, order)

    by_ext = {row["external_id"]: row for row in payload["rows"]}
    assert by_ext[molding_addon.external_id]["guess_main"] == molding.external_id
    assert "사양 일치" in by_ext[molding_addon.external_id]["guess_reason"]
    assert by_ext[neutral.external_id]["guess_main"] is None
    assert "선택" in by_ext[neutral.external_id]["guess_reason"]
    assert plain.external_id in {r["external_id"] for r in payload["rows"]}


def test_dock_payload_reports_extra_payment_summary(app):
    """도크가 추가결제 기록(건수·합계)을 싣는다 — 출고가에는 반영돼 있지 않다(T16-F)."""
    from foms.services.integrations.naver_commerce.dock import build_dock_payload

    order = _naver_order(_staff())
    order.structured_data = dict(order.structured_data or {},
                                 pricing={"extra_payments": [
                                     {"external_id": "PO-X1", "amount": 94900},
                                     {"external_id": "PO-X2", "amount": 150000},
                                 ]})
    db_session.commit()
    _link(order, _snapshot(product_name="붙박이장"), order_no="N-DOCK-EXTRA")

    payload = build_dock_payload(db_session, order)
    assert payload["extra_payment_count"] == 2
    assert payload["extra_payment_total"] == 244900


# --------------------------------------------------------------------------- #
# 추가결제 / 재결제 표기 분리 (R1 — 2026-08-24 재결제 케이스 SPEC §4.4)
#
# 같은 숫자가 ADDON 에서는 "더 받은 돈"이고 REPAY 에서는 "다시 받은 돈"(원 결제는
# 환불)이다. 관계와 무관하게 "추가결제"라 부르면 담당자가 예약금·입금에 더해
# 주문 하나 값만큼 총액을 부풀린다. 계산식은 그대로 두고 **표기만** 가른다.
# --------------------------------------------------------------------------- #

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_DOCK_JS = _REPO_ROOT / "static" / "js" / "orders" / "erp-naver-dock.js"
_ORDER_JS_TPL = _REPO_ROOT / "templates" / "orders" / "partials" / "erp_order_js.html"

# 담당자가 눈으로 읽는 ADDON 한 줄 — R1 이 **한 글자도** 바꾸면 안 되는 문구다.
_ADDON_FACT_LINE = (
    "facts.push(['추가결제', "
    "state.extraPaymentAddon.count + '건 · ' + "
    "state.extraPaymentAddon.total.toLocaleString('ko-KR') + '원 (반영은 수동)', false]);"
)
_REPAY_FACT_LINE = (
    "facts.push(['재결제', "
    "state.extraPaymentRepay.count + '건 · ' + "
    "state.extraPaymentRepay.total.toLocaleString('ko-KR') + "
    "'원 — 원 주문 취소분 재결제입니다. 출고가·잔금에 더하지 마세요', "
    "false, 'naver-dock-fact-warn']);"
)


def _squash(text: str) -> str:
    """줄바꿈·들여쓰기를 공백 하나로 눌러 소스 문구를 한 줄로 비교한다."""
    return re.sub(r"\s+", " ", text)


def _order_with_extra_payments(entries: list[dict]) -> Order:
    """추가결제 기록을 심은 네이버 수집 주문 하나(링크 1건 포함).

    도크는 링크가 있어야 payload 를 만든다 — 기록만 심으면 ``None`` 이 온다.
    """
    order = _naver_order(_staff())
    order.structured_data = dict(order.structured_data or {},
                                 pricing={"extra_payments": entries})
    db_session.commit()
    _link(order, _snapshot(product_name="붙박이장"), order_no="N-DOCK-REL")
    return order


def test_dock_payload_splits_repay_only_extra_payments(app):
    """재결제만 있는 주문 — 재결제 칸에만 숫자가 들어가고 추가결제 칸은 0."""
    order = _order_with_extra_payments([
        {"external_id": "PO-R1", "relation": "REPAY", "amount": 812000},
        {"external_id": "PO-R2", "relation": "REPAY", "amount": 798780},
    ])

    payload = build_dock_payload(db_session, order)

    split = payload["extra_payment_by_relation"]
    assert split["repay"] == {"count": 2, "total": 1610780}
    assert split["addon"] == {"count": 0, "total": 0}
    # 합계 필드는 하위호환으로 그대로 — 화면 게이트(hasFacts)가 이 숫자를 본다.
    assert payload["extra_payment_count"] == 2
    assert payload["extra_payment_total"] == 1610780


def test_dock_payload_addon_only_keeps_wording_untouched(app):
    """추가결제만 있는 주문 — 갈라도 추가결제 칸이 곧 합계이고, 문구는 그대로다.

    R1 의 회귀 방지 핵심: 지금까지 담당자가 보던 ADDON 한 줄이 **한 글자도**
    바뀌면 안 된다(바뀌면 "무엇이 달라졌나"를 다시 배워야 한다).
    """
    order = _order_with_extra_payments([
        {"external_id": "PO-A1", "relation": "ADDON", "amount": 94900},
        {"external_id": "PO-A2", "relation": "ADDON", "amount": 150000},
    ])

    payload = build_dock_payload(db_session, order)

    split = payload["extra_payment_by_relation"]
    assert split["addon"] == {"count": 2, "total": 244900}
    assert split["repay"] == {"count": 0, "total": 0}
    assert payload["extra_payment_count"] == 2
    assert payload["extra_payment_total"] == 244900
    assert _ADDON_FACT_LINE in _squash(_DOCK_JS.read_text(encoding="utf-8")), (
        "ADDON 문구가 바뀌었다 — R1 은 재결제 줄만 추가하고 이 줄은 건드리지 않는다"
    )


def test_dock_payload_splits_mixed_relations(app):
    """섞인 주문 — 두 칸이 각각 서고, 합계는 두 칸의 합 그대로다(두 줄 표시의 근거)."""
    order = _order_with_extra_payments([
        {"external_id": "PO-M1", "relation": "ADDON", "amount": 94900},
        {"external_id": "PO-M2", "relation": "REPAY", "amount": 812000},
        {"external_id": "PO-M3", "relation": "REPAY", "amount": 798780},
    ])

    payload = build_dock_payload(db_session, order)

    split = payload["extra_payment_by_relation"]
    assert split["addon"] == {"count": 1, "total": 94900}
    assert split["repay"] == {"count": 2, "total": 1610780}
    assert payload["extra_payment_count"] == 3
    assert payload["extra_payment_total"] == 94900 + 1610780


def test_dock_payload_treats_relationless_legacy_entries_as_addon(app):
    """``relation`` 이 없는 옛 기록은 추가결제 칸으로 — 표기가 바뀌지 않게."""
    order = _order_with_extra_payments([
        {"external_id": "PO-L1", "amount": 94900},
        {"external_id": "PO-L2", "relation": None, "amount": 150000},
    ])

    payload = build_dock_payload(db_session, order)

    split = payload["extra_payment_by_relation"]
    assert split["addon"] == {"count": 2, "total": 244900}
    assert split["repay"] == {"count": 0, "total": 0}


def test_dock_js_says_repay_separately_and_asset_pin_moved():
    """도크 JS 가 재결제를 따로 말하고, 고쳤으니 ``?v`` 핀이 움직였다.

    SW 가 ``staticCacheFirst`` 라 핀을 안 올리면 옛 JS 가 계속 서빙되어
    화면은 여전히 "추가결제"라 말한다(수정이 배포돼도 사람에게 도달하지 않는다).
    """
    source = _squash(_DOCK_JS.read_text(encoding="utf-8"))
    assert _REPAY_FACT_LINE in source
    assert "extraPaymentAddon: extraPaymentBucket(payload, 'addon')" in source
    assert "extraPaymentRepay: extraPaymentBucket(payload, 'repay')" in source

    tpl = _ORDER_JS_TPL.read_text(encoding="utf-8")
    # 핀은 R2(워크벤치 링크)에서 다시 움직였다 — 값은
    # ``test_dock_js_renders_workbench_anchor_and_asset_pin_moved`` 가 못박는다.
    assert "js/orders/erp-naver-dock.js') }}?v=20260902b" in tpl
    assert "css/orders/erp-naver-dock.css') }}?v=20260902a" in tpl


# --------------------------------------------------------------------------- #
# 워크벤치 처리 탭으로 돌아가는 링크 (R2 — 2026-08-24 재결제 케이스 SPEC §5 함정 1 / §6)
#
# 재결제 집은 발주확인과 발송처리 사이에 며칠이 뜬다. 그 사이 `확인 완료 — 큐에서 빼기`
# 를 먼저 누르면 그 집이 목록 두 원천에서 모두 빠져 발송처리 버튼에 갈 길이 사라진다.
# 그 길을 도크 머리말의 **평범한 앵커** 하나로 잇는다.
#
# 다만 도크는 `/edit/<id>` 에 실리고 그 라우트는 ADMIN·MANAGER·STAFF 다. 링크를 무조건
# 내면 STAFF 가 자기가 여는 모든 네이버 주문에서 클릭 두 번으로 불가역 4종 버튼이 무장된
# pane 에 닿는다 — 계약 §0-3 이 규제하는 것은 권한이 아니라 **통로**다.
# --------------------------------------------------------------------------- #

@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


@pytest.fixture()
def workbench_off(monkeypatch):
    """워크벤치 게이트를 끈다(기본값이지만 명시한다 — 옆 테스트의 setenv 에 안 젖게)."""
    monkeypatch.delenv("FOMS_NAVER_WORKBENCH_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_NAVER_WORKBENCH_COHORT", raising=False)
    yield


def _dock_user(role: str) -> User:
    """역할만 다른 도크 사용자 하나(팀은 CS — ERP 편집 권한 조건)."""
    user = User(username=f"dock_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _dock_json(html: str) -> dict:
    """편집 페이지 HTML 에서 도크 전용 JSON 태그를 뜯어 파싱한다.

    ``| tojson`` 이 ``&`` 를 ``\u0026`` 로 이스케이프하므로 주소를 문자열로 그냥
    비교하면 늘 어긋난다 — 파싱해서 값으로 본다.
    """
    match = re.search(r'id="naver-origin-data">(.*?)</script>', html, re.S)
    assert match, "도크 JSON 태그(#naver-origin-data)가 응답에 없다"
    return json.loads(match.group(1))


def _order_with_two_households(owner: User) -> tuple[int, int, int]:
    """집이 둘 붙은 네이버 주문 — 원 주문 집 + 나중에 붙은 재결제 집.

    Returns:
        ``(order_id, 원 주문 집 link_id, 나중에 붙은 집 link_id)``.
    """
    order = _naver_order(owner)
    first = _link(order, _snapshot(product_name="붙박이장", order_no="N-R2-A"),
                  order_no="N-R2-A")
    latest = _link(order, _snapshot(product_name="붙박이장(재결제)", order_no="N-R2-B"),
                   order_no="N-R2-B")
    return order.id, first.id, latest.id


def test_dock_gives_admin_a_link_back_to_the_workbench(app, client, workbench_on):
    """ADMIN 응답에는 워크벤치 처리 탭 주소가 실린다 — 나중에 붙은 집을 가리킨다.

    주문에 집이 둘이면 아직 처리가 남은 쪽은 **나중에 온 집**이다(원 주문 집은 이미
    주문으로 승격돼 있다). 그 집이 §5 함정 1 로 목록에서 사라진 바로 그 집이다.
    """
    admin = _dock_user("ADMIN")
    order_id, first_id, latest_id = _order_with_two_households(admin)
    _login(client, admin)

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)

    payload = _dock_json(html)
    assert payload["workbench_url"] == (
        f"/admin/naver-ingest/triage?tab=work&link_id={latest_id}"
    )
    assert f"link_id={first_id}" not in payload["workbench_url"]


def test_dock_header_names_every_household_and_marks_the_one_the_link_opens(
        app, client, workbench_on):
    """머리말이 집 번호를 **전부** 말하고, 링크가 여는 집을 지목한다 (2026-08-25).

    결함: 머리말은 첫 집 번호("N-R2-A")만 말하는데 `워크벤치에서 열기` 는 나중 집
    ("N-R2-B")을 열었다. 담당자는 A 를 읽고 눌러 B 를 보게 된다 — 집이 둘인 주문에서만
    나타나 눈에 잘 띄지 않는다. payload 두 값이 **같은 행**에서 나오는지까지 못박는다.
    """
    admin = _dock_user("ADMIN")
    order_id, _first_id, latest_id = _order_with_two_households(admin)
    _login(client, admin)

    payload = _dock_json(client.get(f"/edit/{order_id}").get_data(as_text=True))

    assert payload["order_nos"] == ["N-R2-A", "N-R2-B"], "집 번호를 전부 말하지 않는다"
    assert payload["order_no"] == "N-R2-A", "하위호환 키는 첫 집 그대로다"
    # 링크가 여는 집과 머리말이 지목하는 집이 같은 링크에서 나와야 한다.
    assert payload["workbench_order_no"] == "N-R2-B"
    assert payload["workbench_url"].endswith(f"link_id={latest_id}")


def test_dock_single_household_still_reports_one_number(app, client, workbench_on):
    """집이 하나면 예전과 같다 — 목록에 한 개, 표식은 화면에서 뜨지 않는다."""
    admin = _dock_user("ADMIN")
    order = _naver_order(admin)
    _link(order, _snapshot(product_name="붙박이장", order_no="N-SOLO"), order_no="N-SOLO")
    _login(client, admin)

    payload = _dock_json(client.get(f"/edit/{order.id}").get_data(as_text=True))

    assert payload["order_nos"] == ["N-SOLO"]
    assert payload["workbench_order_no"] == "N-SOLO"


def test_dock_js_marks_the_opened_household_only_when_there_are_two():
    """표식은 **집이 둘 이상일 때만** 붙는다 — 한 집짜리에 무게를 더하지 않는다."""
    source = _squash(_DOCK_JS.read_text(encoding="utf-8"))
    assert "var opensHere = nos.length > 1 && state.workbenchUrl" in source
    assert "no === state.workbenchOrderNo" in source
    assert "workbenchOrderNo: payload.workbench_order_no || ''" in source


def test_dock_gives_manager_the_same_link(app, client, workbench_on):
    """MANAGER 도 같은 링크를 받는다(계약 §0-3 예외 없이 두 역할까지)."""
    manager = _dock_user("MANAGER")
    order_id, _first_id, latest_id = _order_with_two_households(manager)
    _login(client, manager)

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert _dock_json(html)["workbench_url"] == (
        f"/admin/naver-ingest/triage?tab=work&link_id={latest_id}"
    )


def test_dock_gives_staff_no_workbench_anchor_at_all(app, client, workbench_on):
    """STAFF 응답에는 **앵커가 0개**다 — 주소가 응답에 아예 실리지 않는다.

    JS 에서 숨기면 응답에 데이터가 남는다(계약 §0-4: 탭을 숨기는 게 아니라 컨텍스트를
    만들지 않는다). 그래서 payload 값과 **응답 본문 전체**를 함께 못박는다.
    """
    staff = _dock_user("STAFF")
    order_id, _first_id, _latest_id = _order_with_two_households(staff)
    _login(client, staff)

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert _dock_json(html)["workbench_url"] is None
    # 처리 탭 주소는 `?tab=work` 가 붙은 것뿐이다(nav 의 네이버 수집 진입구는 인자 없음).
    assert "tab=work" not in html


def test_dock_hides_workbench_link_when_gate_is_off(app, client, workbench_off):
    """게이트가 꺼진 ADMIN 에게도 링크를 내지 않는다 — 그 주소는 옛 화면으로 떨어진다."""
    admin = _dock_user("ADMIN")
    order_id, _first_id, _latest_id = _order_with_two_households(admin)
    _login(client, admin)

    html = client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert _dock_json(html)["workbench_url"] is None
    assert "tab=work" not in html


def test_dock_js_renders_workbench_anchor_and_asset_pin_moved():
    """도크 JS 가 앵커(버튼 아님)를 그리고, 고쳤으니 ``?v`` 핀이 움직였다.

    SW 가 ``staticCacheFirst`` 라 핀을 안 올리면 옛 JS 가 계속 서빙되어 링크가 배포돼도
    사람 화면에는 영영 안 뜬다.
    """
    source = _squash(_DOCK_JS.read_text(encoding="utf-8"))
    assert "var wb = el('a', 'naver-dock-wb', '워크벤치에서 열기 ↗');" in source
    assert "wb.href = state.workbenchUrl;" in source
    assert "wb.target = '_blank';" in source
    assert "workbenchUrl: payload.workbench_url || ''," in source

    tpl = _ORDER_JS_TPL.read_text(encoding="utf-8")
    assert "js/orders/erp-naver-dock.js') }}?v=20260902b" in tpl
    assert "css/orders/erp-naver-dock.css') }}?v=20260902a" in tpl
