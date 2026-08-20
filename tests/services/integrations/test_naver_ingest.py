"""NAVER-INGEST-01 T4: 매핑 + create_order 연동 계약 테스트 (SQLite 레인).

네트워크 없이 저장된 fixture 응답으로 돈다. 고정하는 계약:

* fixture → **링크만** 생성(``COLLECTED``). 주문은 이 단계에서 만들지 않는다(T12).
* **같은 fixture 재실행 시 링크 0건 추가**(멱등) — 앱 선체크와 DB UNIQUE 양쪽.
* 계정이 없어도 수집은 돈다(계정은 주문 생성 시점 계약).
* 매핑 실패는 ``PENDING_REVIEW`` 링크로 남는다(주문 없음은 동일).
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce import ingest as ingest_mod
from foms.services.integrations.naver_commerce.ingest import (
    IngestAccountError,
    resolve_ingest_accounts,
    sync_naver_orders,
)
from foms.services.integrations.naver_commerce.mapping import (
    NaverMappingError,
    SOURCE_MARKER,
    build_order_fields,
    build_payment_info,
    build_structured_data,
    extract_claim,
    extract_shipping_memo,
    is_collectible,
    map_detail,
    map_group,
    parse_order_datetime,
)
from models import DomainSideEffectOutbox, ExternalOrderLink, Order, OrderAssignment, User

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _accounts() -> tuple[User, User]:
    """T0 시스템 계정 2개를 만든다(actor 봇 + 미배정 보류함 owner)."""
    actor = User(username=ingest_mod.ACTOR_USERNAME, password="pw-not-committed",
                 name="네이버 수집봇", role="MANAGER", team="CS", is_active=True)
    owner = User(username=ingest_mod.OWNER_USERNAME, password="pw-not-committed",
                 name="미배정", role="STAFF", team="SALES", is_active=True)
    db_session.add_all([actor, owner])
    db_session.commit()
    return (actor, owner)


def _detail(product_order_id: str = "PO-1", **overrides) -> dict:
    """네이버 상세 응답 1건 fixture (2026-08-13 실응답 구조 기준, 값은 가상)."""
    detail = {
        "order": {
            "orderId": "2026081312345",
            "ordererName": "김주문",
            "ordererTel": "010-1111-2222",
            "orderDate": "2026-08-12T14:23:11.000+09:00",
        },
        "productOrder": {
            "productOrderId": product_order_id,
            "productOrderStatus": "PAYED",
            "productName": "붙박이장 세트",
            "productOption": "색상: 화이트 / 폭: 2400",
            "quantity": 1,
            "totalPaymentAmount": 1250000,
            "shippingDueDate": "2026-08-20",
            "sellerProductCode": "LAHOM-BIB-2400",
            "shippingAddress": {
                "name": "이수취",
                "tel1": "010-3333-4444",
                "baseAddress": "서울특별시 강남구 테헤란로 1",
                "detailedAddress": "101동 1001호",
                "zipCode": "06232",
                "longitude": "127.0276",
                "latitude": "37.4979",
            },
            "takingAddress": {
                "name": "라홈물류", "baseAddress": "경기도 광주시 반품로 9",
            },
        },
    }
    detail["productOrder"].update(overrides)
    return detail


class FakeClient:
    """수집 파이프라인이 부르는 두 메서드만 흉내내는 클라이언트."""

    def __init__(self, changed: list[dict], details: list[dict]):
        self._changed = changed
        self._details = details
        self.detail_calls: list[list[str]] = []

    def get_last_changed_statuses(self, start, end):
        return self._changed

    def get_product_orders(self, ids):
        self.detail_calls.append(list(ids))
        wanted = set(ids)
        return [d for d in self._details
                if d["productOrder"]["productOrderId"] in wanted]


def _changed_entry(product_order_id: str = "PO-1", status: str = "PAYED") -> dict:
    return {"productOrderId": product_order_id, "productOrderStatus": status,
            "lastChangedDate": "2026-08-12T14:24:00.000+09:00"}


def _run(client, **kwargs):
    """수집 1회 실행 + 커밋."""
    from datetime import datetime, timedelta

    start = datetime(2026, 8, 12, 0, 0)
    result = sync_naver_orders(db_session, client=client, start=start,
                               end=start + timedelta(hours=12), **kwargs)
    db_session.commit()
    return result


# --------------------------------------------------------------------------- #
# 순수 매핑
# --------------------------------------------------------------------------- #

def test_recipient_wins_over_orderer_for_customer_fields():
    """대리주문이면 고객은 수취인이다(주문자는 따로 보존)."""
    fields = build_order_fields(_detail(), today="2026-08-13")
    assert fields["customer_name"] == "이수취"
    assert fields["phone"] == "010-3333-4444"
    sd = build_structured_data(_detail())
    # ORDERER-AXIS-01: orderer 는 발주사 자리(항상 라홈), 주문한 사람은 buyer 로 간다.
    assert sd["parties"]["orderer"] == {"name": "라홈"}
    assert sd["parties"]["buyer"] == {"name": "김주문", "phone": "010-1111-2222"}


def test_address_is_base_plus_detail():
    """주소는 baseAddress + detailedAddress 결합이다."""
    fields = build_order_fields(_detail(), today="2026-08-13")
    assert fields["address"] == "서울특별시 강남구 테헤란로 1 101동 1001호"


def test_option_text_is_preserved_verbatim():
    """v1 은 옵션을 파싱하지 않는다 — 원문 그대로 보관(스펙 §7 Q2)."""
    fields = build_order_fields(_detail(), today="2026-08-13")
    assert fields["options"] == "색상: 화이트 / 폭: 2400"


def test_taking_address_is_dropped():
    """takingAddress 는 반품 수거지(자사 주소)라 고객 정보로 새면 안 된다."""
    sd = build_structured_data(_detail())
    blob = repr(sd)
    assert "라홈물류" not in blob and "반품로" not in blob


def test_naver_coordinates_never_reach_order_fields():
    """좌표는 Order 로 가지 않는다 — 주문서 주소 기준이라 실주소와 다를 수 있다."""
    fields = build_order_fields(_detail(), today="2026-08-13")
    assert "lat" not in fields and "lng" not in fields
    assert "geocode_status" not in fields
    # 참고용으로 structured_data 에만 남는다.
    sd = build_structured_data(_detail())
    assert sd["naver"]["latitude"] == "37.4979"


def test_order_date_becomes_kst_date_and_time():
    """orderDate 는 KST 기준 날짜/시각으로 나뉜다."""
    assert parse_order_datetime("2026-08-12T14:23:11.000+09:00") == ("2026-08-12", "14:23")
    # UTC 로 와도 KST 로 환산한다.
    assert parse_order_datetime("2026-08-12T23:30:00.000Z") == ("2026-08-13", "08:30")
    # 파싱 실패는 빈 값(호출자가 오늘 날짜로 대체).
    assert parse_order_datetime("이상한값") == ("", None)


def test_shipping_memo_comes_from_product_order():
    """배송메모 실위치는 productOrder.shippingMemo 다.

    실측(2026-08-14 스테이징 42건): shippingAddress 에는 그 키가 아예 없다. 그 자리만
    읽던 초기 구현은 메모를 통째로 잃고 있었다(빈 값이라 화면에도 안 떴다).
    """
    detail = _detail(shippingMemo="문 앞에 놓아주세요")
    assert extract_shipping_memo(detail) == "문 앞에 놓아주세요"
    assert build_structured_data(detail)["naver"]["shipping_memo"] == "문 앞에 놓아주세요"


def test_shipping_memo_absent_is_empty_not_error():
    """메모 없는 주문이 다수다 — 없으면 빈 문자열이고 매핑은 정상 진행된다."""
    assert extract_shipping_memo(_detail()) == ""
    assert build_structured_data(_detail())["naver"]["shipping_memo"] == ""


def test_group_keeps_every_distinct_shipping_memo():
    """묶음 안에서 메모가 다르면 전부 남긴다(대표 것만 쓰면 조용히 유실된다)."""
    lead = _detail("PO-G1", shippingMemo="문 앞에 놓아주세요", totalPaymentAmount=900000)
    addon = _detail("PO-G2", shippingMemo="부재 시 경비실", totalPaymentAmount=30000)
    same = _detail("PO-G3", shippingMemo="문 앞에 놓아주세요", totalPaymentAmount=10000)
    _fields, structured = map_group([addon, lead, same], today="2026-08-14")
    # 대표(금액 최대) 메모가 먼저, 중복은 제거.
    assert structured["naver"]["shipping_memo"] == "문 앞에 놓아주세요\n부재 시 경비실"


def test_claim_is_detected_even_when_status_is_payed():
    """취소 요청은 productOrderStatus 로 안 보인다 — claimStatus 가 정본이다.

    2026-08-14 스테이징 실물: status=PAYED · claimStatus=CANCEL_REQUEST 인 건이 있었다.
    """
    detail = _detail(claimStatus="CANCEL_REQUEST", claimType="CANCEL")
    detail["cancel"] = {"cancelReason": "SIMPLE_INTENT_CHANGED",
                        "claimRequestDate": "2026-08-13T19:20:18.219+09:00"}
    claim = extract_claim(detail)
    assert claim["status"] == "CANCEL_REQUEST"
    assert claim["label"] == "취소 요청"
    assert claim["blocking"] is True
    assert claim["reason"] == "SIMPLE_INTENT_CHANGED"
    # structured_data 에도 남는다(신규 수집분).
    assert build_structured_data(detail)["naver"]["claim"]["blocking"] is True


def test_claim_from_current_claim_block():
    """cancel 이 없고 currentClaim.cancel 로만 오는 형태도 읽는다."""
    detail = _detail()
    detail["currentClaim"] = {"cancel": {"claimStatus": "RETURN_REQUEST",
                                         "cancelReason": "BROKEN"}}
    claim = extract_claim(detail)
    assert claim["status"] == "RETURN_REQUEST" and claim["blocking"] is True


def test_no_claim_is_not_blocking():
    """평범한 주문은 클레임이 없다 — 빈 상태가 경고로 둔갑하면 안 된다."""
    claim = extract_claim(_detail())
    assert claim["status"] == "" and claim["blocking"] is False and claim["label"] == ""


def test_claim_reject_does_not_block():
    """취소 거부는 정상 진행 건이다 — 막으면 진짜 주문을 못 만든다."""
    assert extract_claim(_detail(claimStatus="CANCEL_REJECT"))["blocking"] is False


def test_secondary_phone_is_preserved():
    """보조 연락처(tel2)는 첫 번호가 안 될 때 유일한 단서다 — 버리면 못 구한다."""
    detail = _detail()
    detail["productOrder"]["shippingAddress"]["tel2"] = "010-9999-8888"
    sd = build_structured_data(detail)
    assert sd["parties"]["customer"]["phone2"] == "010-9999-8888"
    # Order.phone 은 여전히 tel1 이다(대표 연락처 규칙 불변).
    assert build_order_fields(detail, today="2026-08-13")["phone"] == "010-3333-4444"


def test_payment_details_are_captured():
    """결제일·수단·단가·할인·쿠폰·정산예정액 — 지금까지 결제금액 하나만 쓰고 버렸다."""
    detail = _detail(unitPrice=50000, optionPrice=4500, productDiscountAmount=11000,
                     expectedSettlementAmount=46686,
                     appliedCoupons=[{"couponClassCode": "NMP_PRD_DUP_DCNT",
                                      "couponDiscountAmount": 11000}])
    detail["order"]["paymentDate"] = "2026-08-14T16:27:12.156+09:00"
    detail["order"]["paymentMeans"] = "신용카드"
    payment = build_payment_info(detail)
    assert payment["means"] == "신용카드"
    assert payment["unit_price"] == 50000 and payment["option_price"] == 4500
    assert payment["product_discount_amount"] == 11000
    assert payment["expected_settlement_amount"] == 46686
    assert payment["coupons"] == [{"class_code": "NMP_PRD_DUP_DCNT",
                                   "discount_amount": 11000}]


def test_product_identifiers_are_kept():
    """상품 식별자·유입경로는 나중 자동화의 기초다(당장 업무엔 안 쓴다)."""
    naver = build_structured_data(_detail(productId="11839531137",
                                          originalProductId="11784768368",
                                          itemNo="3773410379",
                                          inflowPath="검색>쇼핑검색"))["naver"]
    assert naver["product_id"] == "11839531137"
    assert naver["original_product_id"] == "11784768368"
    assert naver["item_no"] == "3773410379"
    assert naver["inflow_path"] == "검색>쇼핑검색"


def test_source_marker_is_stamped():
    """수집분은 structured_data 로 식별 가능해야 한다."""
    assert build_structured_data(_detail())["source"] == SOURCE_MARKER


def test_missing_required_field_raises_mapping_error():
    """필수 값이 없으면 주문을 만들 수 없다(쓰레기 주문 방지)."""
    broken = _detail()
    broken["productOrder"]["shippingAddress"]["baseAddress"] = ""
    broken["productOrder"]["shippingAddress"]["detailedAddress"] = ""
    with pytest.raises(NaverMappingError) as exc:
        map_detail(broken, today="2026-08-13")
    assert "address" in str(exc.value)


def test_only_payed_entries_are_collectible():
    """변경분은 상태 이벤트 전부라 PAYED 만 후보다."""
    assert is_collectible(_changed_entry(status="PAYED")) is True
    assert is_collectible(_changed_entry(status="DELIVERED")) is False
    assert is_collectible({}) is False


# --------------------------------------------------------------------------- #
# 계정 정책
# --------------------------------------------------------------------------- #

def test_missing_system_accounts_block_ingest(app):
    """T0 계정이 없으면 수집을 시작하지 않는다."""
    with pytest.raises(IngestAccountError):
        resolve_ingest_accounts(db_session)


def test_inactive_owner_blocks_ingest(app):
    """보류함 owner 가 비활성이면 거부한다(create_order owner 계약과 동일)."""
    actor, owner = _accounts()
    owner.is_active = False
    db_session.commit()
    with pytest.raises(IngestAccountError):
        resolve_ingest_accounts(db_session)


# --------------------------------------------------------------------------- #
# 수집 파이프라인
# --------------------------------------------------------------------------- #

def test_sweep_collects_without_creating_any_order(app):
    """T12: 수집은 링크만 남긴다 — 주문은 만들지 않는다."""
    _accounts()
    client = FakeClient([_changed_entry()], [_detail()])
    result = _run(client)

    assert (result.changed, result.candidates, result.collected) == (1, 1, 1)
    assert db_session.query(Order).count() == 0, "수집 단계에서 주문이 생기면 안 된다"
    link = db_session.query(ExternalOrderLink).one()
    assert (link.channel, link.external_id, link.sync_status) == ("NAVER", "PO-1", "COLLECTED")
    assert link.order_id is None
    assert link.raw_snapshot["productOrder"]["sellerProductCode"] == "LAHOM-BIB-2400"


def test_collection_works_without_system_accounts(app):
    """계정이 아직 없어도 수집은 멈추지 않는다(계정은 주문 생성 시점에만 필요)."""
    result = _run(FakeClient([_changed_entry()], [_detail()]))

    assert result.collected == 1
    assert db_session.query(ExternalOrderLink).one().sync_status == "COLLECTED"


def test_no_geocode_outbox_until_an_order_exists(app):
    """주문이 없으니 지오코딩 예약도 없다(큐를 미리 채우지 않는다)."""
    _accounts()
    _run(FakeClient([_changed_entry()], [_detail()]))
    assert db_session.query(DomainSideEffectOutbox).count() == 0


def test_rerun_with_same_fixture_adds_no_link(app):
    """멱등: 같은 구간·같은 fixture 를 3회 돌려도 링크는 1건이다."""
    _accounts()
    for _ in range(3):
        client = FakeClient([_changed_entry()], [_detail()])
        result = _run(client)
    assert db_session.query(Order).count() == 0
    assert db_session.query(ExternalOrderLink).count() == 1
    # 2회차부터는 상세 조회 자체를 하지 않는다(호출 절약).
    assert result.skipped == 1 and result.fetched == 0


def test_unique_constraint_backstops_concurrent_duplicate(app):
    """앱 선체크를 통과해도 DB UNIQUE 가 중복을 막고 skip 으로 센다."""
    _accounts()
    _run(FakeClient([_changed_entry()], [_detail()]))
    # 선체크를 우회하도록 링크만 지우고(주문은 남김) 같은 건을 다시 넣는다 =
    # 동시 실행이 같은 창에서 겹친 상황과 동치.
    db_session.query(ExternalOrderLink).delete()
    db_session.add(ExternalOrderLink(channel="NAVER", external_id="PO-1", sync_status="COLLECTED"))
    db_session.commit()
    result = _run(FakeClient([_changed_entry()], [_detail()]))
    assert db_session.query(ExternalOrderLink).count() == 1
    assert result.collected == 0


def test_non_payed_changes_are_ignored(app):
    """결제완료가 아닌 상태 변경은 후보가 아니다."""
    _accounts()
    result = _run(FakeClient([_changed_entry(status="DELIVERED")], [_detail()]))
    assert (result.candidates, result.collected) == (0, 0)
    assert db_session.query(Order).count() == 0


def test_mapping_failure_records_pending_review_without_order(app):
    """매핑 실패는 주문을 만들지 않고 보류 링크만 남긴다."""
    _accounts()
    broken = _detail("PO-BAD")
    broken["productOrder"]["shippingAddress"]["baseAddress"] = ""
    broken["productOrder"]["shippingAddress"]["detailedAddress"] = ""
    result = _run(FakeClient([_changed_entry("PO-BAD")], [broken]))

    assert result.pending_review == 1 and result.collected == 0
    assert db_session.query(Order).count() == 0
    link = db_session.query(ExternalOrderLink).one()
    assert link.sync_status == "PENDING_REVIEW"
    assert link.order_id is None
    assert "address" in (link.failure_reason or "")
    assert link.raw_snapshot is not None, "재처리를 위해 원본은 보존해야 한다"


def test_dry_run_touches_nothing(app):
    """dry-run 은 조회까지만 하고 주문·링크를 만들지 않는다."""
    _accounts()
    result = _run(FakeClient([_changed_entry()], [_detail()]), dry_run=True)
    assert result.fetched == 1 and result.collected == 0
    assert db_session.query(Order).count() == 0
    assert db_session.query(ExternalOrderLink).count() == 0


def test_batch_of_mixed_details(app):
    """여러 건 중 정상은 만들고 깨진 건은 보류로 갈라진다."""
    _accounts()
    good, other = _detail("PO-A"), _detail("PO-B")
    broken = _detail("PO-C")
    broken["productOrder"]["productName"] = ""
    client = FakeClient(
        [_changed_entry("PO-A"), _changed_entry("PO-B"), _changed_entry("PO-C")],
        [good, other, broken],
    )
    result = _run(client)
    assert (result.collected, result.pending_review) == (2, 1)
    assert db_session.query(Order).count() == 0
    assert db_session.query(ExternalOrderLink).count() == 3


def test_site_keeps_the_foms_shape_so_the_erp_form_cannot_duplicate_the_detail():
    """``address_detail`` 을 따로 남기면 ERP 편집 화면이 주소를 두 번 붙인다.

    FOMS 정본 형태는 ``address_full == address_main`` · ``address_detail == ''`` 이다
    (``order_geocode.sync_site_address`` 가 모든 저장에서 그렇게 맞춘다). 수집이 detail 을
    따로 남기면, ERP 편집 폼은 로드할 때 ``full + ' ' + detail`` 로 한 칸에 합치므로
    이미 detail 을 품은 full 뒤에 detail 이 한 번 더 붙는다 — 저장하면 그대로 굳는다
    (2026-08-14 운영 실측: ``… 103동 605호 103동 605호``).
    """
    site = build_structured_data(_detail())["site"]

    assert site["address_full"] == "서울특별시 강남구 테헤란로 1 101동 1001호"
    assert site["address_main"] == site["address_full"]
    assert site["address_detail"] == ""
    # 우편번호는 주소 문자열이 아니라 별도 값이라 그대로 보존한다.
    assert site["zip_code"] == "06232"


# --------------------------------------------------------------------------- #
# 본품만 품목으로 만든다 + 귀속은 수집 순서 (2026-08-18 사용자 확정)
# --------------------------------------------------------------------------- #

def _main(pid: str, name: str, *, amount: int, quantity: int = 1, option: str = "") -> dict:
    """본품 상세(추가구성상품이 아닌 productClass)."""
    detail = _detail(pid, productName=name, totalPaymentAmount=amount, quantity=quantity,
                     productOption=option)
    detail["productOrder"]["productClass"] = "조합형옵션상품"
    return detail


def _addon(pid: str, name: str, *, amount: int, quantity: int = 1, option: str = "") -> dict:
    """추가옵션 상세(수납구성·EP마감·길이추가 등)."""
    detail = _detail(pid, productName=name, totalPaymentAmount=amount, quantity=quantity,
                     productOption=option)
    detail["productOrder"]["productClass"] = "추가구성상품"
    return detail


def test_items_are_mains_only_and_keep_group_total():
    """추가옵션은 항목이 되지 않는다 — 항목은 본품 수만큼, 금액은 잃지 않는다.

    실사례(2026-08-18 스테이징 `2026081822487841`): 상품주문 14건이 항목 14행이 돼
    규격을 채울 본품 행을 찾기 어려웠다. 본품 2행 + 나머지는 본품에 귀속.
    """
    main1 = _main("PO-M1", "로라 무몰딩 180cm", amount=1_115_800, quantity=2,
                  option="사이즈: 180（몰딩）")
    addon1 = _addon("PO-A1", "TYPE C", amount=60_000, quantity=2, option="수납구성: TYPE C")
    addon2 = _addon("PO-A2", "로라 몰딩 1cm", amount=6_260, quantity=2,
                    option="길이추가(1cm): 로라 몰딩 여닫이 1cm")
    main2 = _main("PO-M2", "로라 무몰딩 30cm", amount=1_314_600, quantity=14,
                  option="제품: 로라 몰딩 여닫이 30cm")
    addon3 = _addon("PO-A3", "TYPE F", amount=20_000, option="수납구성: TYPE F")

    details = [main1, addon1, addon2, main2, addon3]
    fields, structured = map_group(details, today="2026-08-18")

    items = structured["items"]
    assert [i["naver_product_order_id"] for i in items] == ["PO-M2", "PO-M1"], \
        "대표(금액 최대 본품)가 1번, 본품만 항목"
    assert all(i["naver_role"] == "main" for i in items)
    # 금액 보존: 본품 + 귀속 옵션 합계
    by_id = {i["naver_product_order_id"]: i for i in items}
    assert by_id["PO-M1"]["price"] == 1_115_800 + 60_000 + 6_260
    assert by_id["PO-M2"]["price"] == 1_314_600 + 20_000
    assert sum(i["price"] for i in items) == fields["payment_amount"]
    assert structured["totals"]["items_total"] == fields["payment_amount"]


def test_addons_attach_to_the_preceding_main_in_collection_order():
    """귀속 정본은 **수집 순서**다 — 본품 다음 줄부터 다음 본품 전까지가 그 본품 옵션."""
    details = [
        _main("PO-M1", "본품 A", amount=1_000_000),
        _addon("PO-A1", "옵션 A1", amount=10_000),
        _addon("PO-A2", "옵션 A2", amount=20_000),
        _main("PO-M2", "본품 B", amount=900_000),
        _addon("PO-B1", "옵션 B1", amount=30_000),
    ]
    _fields, structured = map_group(details, today="2026-08-18")
    by_id = {i["naver_product_order_id"]: i for i in structured["items"]}
    assert [a["naver_product_order_id"] for a in by_id["PO-M1"]["naver_addons"]] == \
        ["PO-A1", "PO-A2"]
    assert [a["naver_product_order_id"] for a in by_id["PO-M2"]["naver_addons"]] == ["PO-B1"]


def test_addon_before_any_main_is_not_lost():
    """본품보다 먼저 온 추가옵션도 항목을 만들지 않고 첫 본품에 붙는다."""
    details = [
        _addon("PO-A0", "먼저 온 옵션", amount=5_000),
        _main("PO-M1", "본품", amount=800_000),
    ]
    _fields, structured = map_group(details, today="2026-08-18")
    items = structured["items"]
    assert len(items) == 1 and items[0]["naver_product_order_id"] == "PO-M1"
    assert [a["naver_product_order_id"] for a in items[0]["naver_addons"]] == ["PO-A0"]
    assert items[0]["price"] == 805_000


def test_block_layout_attributes_addons_by_spec_axis():
    """본품이 앞에 몰려 온 집(`M M a a`)은 순서로 못 가른다 — 사양 축으로 붙인다.

    실데이터 `2026081435531421`: 몰딩 본품 + 무몰딩 본품 뒤에 1cm 두 종류가 온다.
    순서만 보면 몰딩 1cm 이 무몰딩 본품에 붙어 총폭·경고가 함께 틀어졌다.
    """
    molding = _main("PO-M1", "라홈 무몰딩 붙박이장 로라 30cm", amount=600_000, quantity=6,
                    option="제품: 로라 몰딩 여닫이 30cm / 손잡이: 푸쉬타입")
    plain = _main("PO-M2", "라홈 무몰딩 붙박이장 로라 30cm", amount=1_300_000, quantity=13,
                  option="제품: 로라 무몰딩 여닫이 30cm / 손잡이: 푸쉬타입")
    molding_addon = _addon("PO-A1", "로라 몰딩 여닫이 (푸쉬) 1cm", amount=11_000, quantity=11,
                           option="길이추가(1cm): 로라 몰딩 여닫이 (푸쉬) 1cm")
    plain_addon = _addon("PO-A2", "로라 무몰딩 여닫이(푸쉬) 1cm", amount=10_000, quantity=10,
                         option="길이추가(1cm): 로라 무몰딩 여닫이(푸쉬) 1cm")
    neutral = _addon("PO-A3", "제로조인트 추가 (상담)", amount=0,
                     option="제로조인트: 제로조인트 추가 (상담)")

    fields, structured = map_group([molding, plain, molding_addon, plain_addon, neutral],
                                   today="2026-08-19")

    by_id = {i["naver_product_order_id"]: i for i in structured["items"]}
    assert [a["naver_product_order_id"] for a in by_id["PO-M1"]["naver_addons"]] == \
        ["PO-A1", "PO-A3"], "몰딩 1cm 은 몰딩 본품에 · 축 없는 옵션은 첫 본품에"
    assert [a["naver_product_order_id"] for a in by_id["PO-M2"]["naver_addons"]] == ["PO-A2"]
    assert sum(i["price"] for i in structured["items"]) == fields["payment_amount"], \
        "귀속이 미정이어도 금액은 어딘가에 붙어 합계가 보존된다"
