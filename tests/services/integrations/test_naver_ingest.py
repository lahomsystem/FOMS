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
    build_structured_data,
    is_collectible,
    map_detail,
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
    assert sd["parties"]["orderer"] == {"name": "김주문", "phone": "010-1111-2222"}


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
