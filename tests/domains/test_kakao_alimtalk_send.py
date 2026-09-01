"""카카오 알림톡 v1 — 발송 계층·이력 기록 테스트 (T2).

DB 픽스처는 tests/conftest.py 의 ``app``(in-memory sqlite) + ``db_session`` 을 쓴다
(tests/domains/test_urgent_call.py 선례). Solapi SDK 는 격리된 호출부
``kakao_alimtalk._solapi_send`` 를 monkeypatch 해 스텁한다 — 네트워크 호출 없음.
"""
import copy
import datetime

import pytest

from db import db_session
from foms.services import kakao_alimtalk as ka
from models import DomainSideEffectOutbox, Order, OrderEvent, User

_MEASURE_SD = {
    "parties": {"customer": {"name": "임다슬", "phone": "010-2473-6730"},
                "orderer": {"name": "라홈시스템"}},
    "schedule": {"measurement": {"date": "2026-08-14", "time": "3시 30분"}},
    "items": [{"product_name": "무몰딩 여닫이"}],
}


def _sd(**overrides) -> dict:
    """실측 예약이 잡힌 유효 sd 사본(부분 덮어쓰기 지원)."""
    sd = copy.deepcopy(_MEASURE_SD)
    sd.update(overrides)
    return sd


def _mk_order(structured_data=None, status="ERPORDER") -> Order:
    """ERP 주문 1건을 커밋한다(별도 세션이 읽어야 하므로 commit 필수)."""
    order = Order(
        received_date=datetime.date(2026, 7, 4),
        customer_name="임다슬",
        phone="010-2473-6730",
        address="Seoul",
        product="가구",
        status=status,
        is_erp_order=True,
        structured_data=structured_data if structured_data is not None else _sd(),
    )
    db_session.add(order)
    db_session.commit()
    return order


def _mk_user(name: str = "홍길동") -> User:
    """발송자 표시명 검증용 사용자 1건."""
    user = User(username=f"u{name}", password="x", name=name, role="STAFF")
    db_session.add(user)
    db_session.commit()
    return user


def _events(order_id: int) -> list[OrderEvent]:
    db_session.expire_all()
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id)
        .order_by(OrderEvent.id.asc())
        .all()
    )


def _history(order_id: int) -> dict:
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    return (order.structured_data or {}).get("alimtalk_measurement") or {}


def _outbox() -> list[DomainSideEffectOutbox]:
    db_session.expire_all()
    return db_session.query(DomainSideEffectOutbox).all()


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


@pytest.fixture
def solapi_env(monkeypatch):
    """공통 자격증명 + 라홈 프로필만 구성(하우드는 미구성 — D3 단계 가동 재현)."""
    monkeypatch.setenv("SOLAPI_API_KEY", "key")
    monkeypatch.setenv("SOLAPI_API_SECRET", "secret")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE", "0212345678")
    monkeypatch.setenv("SOLAPI_PF_ID_LAHOM", "PF-LAHOM")
    monkeypatch.setenv("SOLAPI_TEMPLATE_MEASURE_ID_LAHOM", "TPL-LAHOM")
    monkeypatch.delenv("SOLAPI_PF_ID_HAUD", raising=False)
    monkeypatch.delenv("SOLAPI_TEMPLATE_MEASURE_ID_HAUD", raising=False)
    monkeypatch.delenv("SOLAPI_SENDER_PHONE_LAHOM", raising=False)
    monkeypatch.delenv("SOLAPI_SENDER_PHONE_HAUD", raising=False)


@pytest.fixture
def auto_on(monkeypatch):
    monkeypatch.setenv("FOMS_ALIMTALK_AUTO_ENABLED", "1")


@pytest.fixture
def stub_solapi_ok(monkeypatch):
    """성공 스텁 — 호출 인자를 수집한다."""
    calls: list[dict] = []

    def _fake(**kwargs) -> str:
        calls.append(kwargs)
        return "MSG-1"

    monkeypatch.setattr(ka, "_solapi_send", _fake)
    return calls


@pytest.fixture
def stub_solapi_never(monkeypatch):
    """호출되면 실패시키는 스텁(발송 스킵 검증용)."""

    def _fake(**kwargs):
        raise AssertionError("Solapi 를 호출하면 안 된다")

    monkeypatch.setattr(ka, "_solapi_send", _fake)


# --- 설정·브랜드 판정 (D3) ------------------------------------------------------


def test_is_configured_requires_common_keys(monkeypatch):
    monkeypatch.delenv("SOLAPI_API_KEY", raising=False)
    monkeypatch.setenv("SOLAPI_API_SECRET", "secret")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE", "0212345678")
    assert ka.is_configured() is False
    monkeypatch.setenv("SOLAPI_API_KEY", "key")
    assert ka.is_configured() is True


def test_is_configured_ignores_brand_keys(solapi_env, monkeypatch):
    """브랜드 프로필 미구성은 공통 설정 판정에 영향 없다(단계 가동)."""
    monkeypatch.delenv("SOLAPI_PF_ID_LAHOM", raising=False)
    assert ka.is_configured() is True


def test_resolve_brand_lahom_by_orderer_name():
    assert ka.resolve_brand({"parties": {"orderer": {"name": "라홈시스템"}}}) == "LAHOM"


def test_resolve_brand_defaults_to_haud():
    assert ka.resolve_brand({"parties": {"orderer": {"name": "제이큐브이앤씨"}}}) == "HAUD"
    assert ka.resolve_brand({"parties": {"orderer": {"name": ""}}}) == "HAUD"
    assert ka.resolve_brand(None) == "HAUD"


def test_brand_config_none_when_pair_incomplete(solapi_env, monkeypatch):
    assert ka.brand_config("LAHOM") == {"pf_id": "PF-LAHOM", "template_id": "TPL-LAHOM"}
    assert ka.brand_config("HAUD") is None
    monkeypatch.setenv("SOLAPI_PF_ID_HAUD", "PF-HAUD")  # 템플릿 키 없음 → 여전히 None
    assert ka.brand_config("HAUD") is None


# --- 발신번호 브랜드 분기 (T14) --------------------------------------------------


def test_sender_phone_prefers_brand_env(solapi_env, monkeypatch):
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_LAHOM", "15660792")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_HAUD", "15660703")
    assert ka.sender_phone("LAHOM") == "15660792"
    assert ka.sender_phone("HAUD") == "15660703"


def test_sender_phone_falls_back_to_legacy_env(solapi_env):
    """브랜드 전용 번호 미등록 → 구 단일 env 로 폴백(기존 동작 보존)."""
    assert ka.sender_phone("LAHOM") == "0212345678"
    assert ka.sender_phone("HAUD") == "0212345678"


def test_is_configured_accepts_brand_only_sender(solapi_env, monkeypatch):
    """구 env 없이 브랜드 번호만 있어도 공통 설정은 완료로 본다."""
    monkeypatch.delenv("SOLAPI_SENDER_PHONE", raising=False)
    assert ka.is_configured() is False
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_LAHOM", "15660792")
    assert ka.is_configured() is True
    assert ka.is_configured("LAHOM") is True
    assert ka.is_configured("HAUD") is False  # 그 브랜드로는 아직 발송 불가


def test_send_uses_brand_sender_phone(db, solapi_env, monkeypatch, stub_solapi_ok):
    """라홈 발주사 주문은 라홈 대표번호로 발신한다(T14)."""
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_LAHOM", "15660792")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_HAUD", "15660703")
    order = _mk_order()

    assert ka.send_alimtalk(order.id) == {"sent": True, "error": None}
    assert stub_solapi_ok[0]["from_"] == "15660792"


def test_send_uses_haud_sender_phone(db, solapi_env, monkeypatch, stub_solapi_ok):
    """하우드 발주사 주문은 하우드 대표번호로 발신한다(T14)."""
    monkeypatch.setenv("SOLAPI_PF_ID_HAUD", "PF-HAUD")
    monkeypatch.setenv("SOLAPI_TEMPLATE_MEASURE_ID_HAUD", "TPL-HAUD")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_LAHOM", "15660792")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_HAUD", "15660703")
    order = _mk_order(_sd(parties={"customer": {"name": "임다슬", "phone": "010-2473-6730"},
                                   "orderer": {"name": "제이큐브이앤씨"}}))

    assert ka.send_alimtalk(order.id) == {"sent": True, "error": None}
    assert stub_solapi_ok[0]["from_"] == "15660703"
    assert stub_solapi_ok[0]["pf_id"] == "PF-HAUD"


def test_send_skips_when_brand_sender_missing(db, solapi_env, monkeypatch, stub_solapi_never):
    """해당 브랜드로 쓸 발신번호가 하나도 없으면 발송하지 않는다(빈 from_ 방지)."""
    monkeypatch.delenv("SOLAPI_SENDER_PHONE", raising=False)
    monkeypatch.setenv("SOLAPI_SENDER_PHONE_HAUD", "15660703")
    order = _mk_order()

    assert ka.send_alimtalk(order.id) == {"sent": False, "error": "not_configured"}


# --- send_alimtalk --------------------------------------------------------------


def test_send_records_history_and_event(db, solapi_env, stub_solapi_ok):
    order = _mk_order()
    result = ka.send_alimtalk(order.id)

    assert result == {"sent": True, "error": None}
    assert stub_solapi_ok[0]["to"] == "01024736730"
    assert stub_solapi_ok[0]["pf_id"] == "PF-LAHOM"
    assert stub_solapi_ok[0]["template_id"] == "TPL-LAHOM"
    assert stub_solapi_ok[0]["from_"] == "0212345678"
    assert stub_solapi_ok[0]["variables"]["#{고객명}"] == "임다슬"

    history = _history(order.id)
    assert history["message_id"] == "MSG-1"
    assert history["error"] is None and history["sent_at"]
    assert history["dedupe_key"] == f"alimtalk:measure:{order.id}:2026-08-14:3시 30분"

    events = _events(order.id)
    assert [e.event_type for e in events] == ["ALIMTALK_SENT"]


def test_send_manual_records_sent_by(db, solapi_env, stub_solapi_ok):
    order = _mk_order()
    sender = _mk_user("홍길동")
    ka.send_alimtalk(order.id, manual_by=sender.id,
                     dedupe_key="alimtalk:measure:x:manual:abc")

    history = _history(order.id)
    assert history["sent_by"] == sender.id
    # 칩은 추가 요청 없이 sd 만 읽어 그린다 — 이름이 여기 없으면 화면에 못 뜬다(T15).
    assert history["sent_by_name"] == "홍길동"
    assert history["dedupe_key"] == "alimtalk:measure:x:manual:abc"
    assert _events(order.id)[0].created_by_user_id == sender.id


def test_send_records_channel_unresolved(db, solapi_env, stub_solapi_ok):
    """발송 직후 채널은 미확정이다 — 카톡이 실패해야 벤더가 문자로 바꾼다(T15)."""
    order = _mk_order()
    ka.send_alimtalk(order.id)

    history = _history(order.id)
    assert history["channel"] is None
    assert history["channel_checked_at"] is None
    # 자동 발송은 보낸 사람이 없다 — 화면은 '자동 발송'으로 표기한다.
    assert history["sent_by"] is None and history["sent_by_name"] is None


def test_send_manual_unknown_user_keeps_name_empty(db, solapi_env, stub_solapi_ok):
    """지워진 사용자 id 로 기록돼도 발송·이력이 깨지지 않는다(이름만 빈다)."""
    order = _mk_order()
    ka.send_alimtalk(order.id, manual_by=999999)

    assert _history(order.id)["sent_by_name"] is None


def test_send_no_phone_records_failed(db, solapi_env, stub_solapi_never):
    order = _mk_order(_sd(parties={"customer": {"name": "임다슬", "phone": "1234"},
                                  "orderer": {"name": "라홈시스템"}}))
    result = ka.send_alimtalk(order.id)

    assert result == {"sent": False, "error": "no_valid_phone"}
    assert _history(order.id)["error"] == "no_valid_phone"
    assert [e.event_type for e in _events(order.id)] == ["ALIMTALK_FAILED"]


def test_send_without_measure_date_is_not_eligible(db, solapi_env, stub_solapi_never):
    order = _mk_order(_sd(schedule={"measurement": {"date": "상담", "time": ""}}))
    assert ka.send_alimtalk(order.id)["error"] == "not_eligible"


def test_send_brand_profile_missing_skips(db, solapi_env, stub_solapi_never):
    """하우드 발주사 + 하우드 프로필 미구성 → 발송 스킵 + 실패 이력(D3 단계 가동)."""
    order = _mk_order(_sd(parties={"customer": {"name": "임다슬", "phone": "010-2473-6730"},
                                   "orderer": {"name": "제이큐브이앤씨"}}))
    result = ka.send_alimtalk(order.id)

    assert result == {"sent": False, "error": "brand_profile_missing"}
    assert _history(order.id)["error"] == "brand_profile_missing"
    assert [e.event_type for e in _events(order.id)] == ["ALIMTALK_FAILED"]


def test_send_classifies_vendor_error(db, solapi_env, monkeypatch):
    def _boom(**kwargs):
        raise Exception("InsufficientBalance", "잔액이 부족합니다")

    monkeypatch.setattr(ka, "_solapi_send", _boom)
    order = _mk_order()
    assert ka.send_alimtalk(order.id) == {"sent": False, "error": "balance"}
    assert [e.event_type for e in _events(order.id)] == ["ALIMTALK_FAILED"]


def test_send_classifies_network_error(db, solapi_env, monkeypatch):
    def _boom(**kwargs):
        raise ConnectionError("connection reset")

    monkeypatch.setattr(ka, "_solapi_send", _boom)
    order = _mk_order()
    assert ka.send_alimtalk(order.id)["error"] == "network"


def test_send_not_configured_skips(db, monkeypatch, stub_solapi_never):
    monkeypatch.delenv("SOLAPI_API_KEY", raising=False)
    order = _mk_order()
    assert ka.send_alimtalk(order.id) == {"sent": False, "error": "not_configured"}


# --- maybe_send_measure_alimtalk (자동 트리거) ----------------------------------


def test_maybe_send_dedupe_second_call_noop(db, solapi_env, auto_on, stub_solapi_ok):
    """저장 경로는 선점만 한다. Solapi 호출은 handler 몫이라 0회, 두 번째 저장도 행 1개."""
    order = _mk_order()
    ka.maybe_send_measure_alimtalk(order.id)
    ka.maybe_send_measure_alimtalk(order.id)

    assert stub_solapi_ok == []
    rows = _outbox()
    assert len(rows) == 1
    assert rows[0].effect_type == "ALIMTALK_SEND"
    assert rows[0].dedupe_key == f"alimtalk:measure:{order.id}:2026-08-14:3시 30분"
    assert rows[0].status == "PENDING"
    assert rows[0].source_domain == "ORDER_EVENT" and rows[0].order_event_id
    assert [e.event_type for e in _events(order.id)] == ["ALIMTALK_FAILED"]
    assert _events(order.id)[0].payload.get("error") == "in_flight"


def test_maybe_send_new_schedule_sends_again(db, solapi_env, auto_on, stub_solapi_ok):
    """일정 변경 = 새 멱등키 → outbox 행 하나 더(발송은 handler)."""
    order = _mk_order()
    ka.maybe_send_measure_alimtalk(order.id)

    changed = _sd()
    changed["schedule"]["measurement"]["date"] = "2026-08-20"
    order = db_session.get(Order, order.id)
    order.structured_data = changed
    db_session.commit()
    ka.maybe_send_measure_alimtalk(order.id)

    assert stub_solapi_ok == []
    assert len(_outbox()) == 2
    assert {row.status for row in _outbox()} == {"PENDING"}


def test_maybe_send_flag_off_noop(db, solapi_env, monkeypatch, stub_solapi_never):
    monkeypatch.delenv("FOMS_ALIMTALK_AUTO_ENABLED", raising=False)
    order = _mk_order()
    ka.maybe_send_measure_alimtalk(order.id)
    assert _outbox() == [] and _events(order.id) == []


def test_maybe_send_draft_order_noop(db, solapi_env, auto_on, stub_solapi_never):
    order = _mk_order(status="DRAFT")
    ka.maybe_send_measure_alimtalk(order.id)
    assert _outbox() == [] and _events(order.id) == []


def test_maybe_send_meta_draft_noop(db, solapi_env, auto_on, stub_solapi_never):
    sd = _sd()
    sd["meta"] = {"draft": True}
    order = _mk_order(sd)
    ka.maybe_send_measure_alimtalk(order.id)
    assert _outbox() == [] and _events(order.id) == []


def test_maybe_send_soft_deleted_order_noop(db, solapi_env, auto_on, stub_solapi_never):
    """휴지통(soft delete) 주문은 자동 발송 대상이 아니다 — 수동 API 의 404 와 같은 기준."""
    order = _mk_order()
    order.deleted_at = datetime.datetime(2026, 7, 4, 1, 2, 3)
    db_session.commit()
    ka.maybe_send_measure_alimtalk(order.id)
    assert _outbox() == [] and _events(order.id) == []


def test_maybe_send_status_deleted_order_noop(db, solapi_env, auto_on, stub_solapi_never):
    """status='DELETED' 로 덮인 주문(legacy 일괄 삭제 경로)도 발송하지 않는다."""
    order = _mk_order(status="DELETED")
    ka.maybe_send_measure_alimtalk(order.id)
    assert _outbox() == [] and _events(order.id) == []


def test_maybe_send_without_measure_date_noop(db, solapi_env, auto_on, stub_solapi_never):
    order = _mk_order(_sd(schedule={"measurement": {"date": "", "time": ""}}))
    ka.maybe_send_measure_alimtalk(order.id)
    assert _outbox() == [] and _events(order.id) == []


def test_maybe_send_brand_missing_keeps_slot_open(
    db, solapi_env, auto_on, stub_solapi_ok, monkeypatch
):
    """브랜드 프로필 미구성은 슬롯을 소진하지 않는다 — env 설정 후 같은 일정이 발송된다."""
    order = _mk_order(_sd(parties={"customer": {"name": "임다슬", "phone": "010-2473-6730"},
                                   "orderer": {"name": "제이큐브이앤씨"}}))
    ka.maybe_send_measure_alimtalk(order.id)
    ka.maybe_send_measure_alimtalk(order.id)

    assert stub_solapi_ok == []
    assert _outbox() == []  # 멱등 슬롯 미소진
    assert [e.event_type for e in _events(order.id)] == ["ALIMTALK_FAILED"]  # 반복 저장 스팸 억제
    assert _history(order.id)["error"] == "brand_profile_missing"

    monkeypatch.setenv("SOLAPI_PF_ID_HAUD", "PF-HAUD")
    monkeypatch.setenv("SOLAPI_TEMPLATE_MEASURE_ID_HAUD", "TPL-HAUD")
    ka.maybe_send_measure_alimtalk(order.id)

    assert stub_solapi_ok == []
    rows = _outbox()
    assert len(rows) == 1 and rows[0].status == "PENDING"
    # 선점은 이력을 덮지 않는다. 스킵 이벤트 + in_flight 앵커가 나란히 남는다.
    assert _history(order.id)["error"] == "brand_profile_missing"
    events = _events(order.id)
    assert [e.event_type for e in events] == ["ALIMTALK_FAILED", "ALIMTALK_FAILED"]
    assert [e.payload.get("error") for e in events] == ["brand_profile_missing", "in_flight"]


def test_maybe_send_invalid_phone_keeps_slot_open(db, solapi_env, auto_on, stub_solapi_ok):
    """전화 불량도 슬롯 미소진 — 번호를 고치면 같은 일정으로 자동 발송된다."""
    order = _mk_order(_sd(parties={"customer": {"name": "임다슬", "phone": "1234"},
                                   "orderer": {"name": "라홈시스템"}}))
    ka.maybe_send_measure_alimtalk(order.id)

    assert stub_solapi_ok == [] and _outbox() == []
    assert _history(order.id)["error"] == "no_valid_phone"

    db_session.expire_all()
    stored = db_session.get(Order, order.id)
    fixed = copy.deepcopy(stored.structured_data)
    fixed["parties"]["customer"]["phone"] = "010-2473-6730"
    stored.structured_data = fixed
    db_session.commit()
    ka.maybe_send_measure_alimtalk(order.id)

    assert stub_solapi_ok == []
    rows = _outbox()
    assert len(rows) == 1 and rows[0].status == "PENDING"
    assert _history(order.id)["error"] == "no_valid_phone"


def test_maybe_send_never_raises(db, solapi_env, auto_on, monkeypatch, stub_solapi_never):
    def _boom(*args, **kwargs):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(ka, "enqueue_side_effect", _boom)
    order = _mk_order()
    ka.maybe_send_measure_alimtalk(order.id)  # 예외 전파 없음


def test_maybe_send_failure_keeps_outbox_pending(db, solapi_env, auto_on, monkeypatch):
    """저장 경로는 Solapi 를 부르지 않는다. 실패 재시도는 handler+워커 몫."""
    def _boom(**kwargs):
        raise ConnectionError("timeout")

    monkeypatch.setattr(ka, "_solapi_send", _boom)
    order = _mk_order()
    ka.maybe_send_measure_alimtalk(order.id)

    rows = _outbox()
    assert len(rows) == 1 and rows[0].status == "PENDING"
    assert [e.event_type for e in _events(order.id)] == ["ALIMTALK_FAILED"]
    assert _events(order.id)[0].payload.get("error") == "in_flight"
