"""알림톡 발송 채널 확정 (T15 ③) — 서비스·API 계약 테스트.

접수 시점 벤더 type 은 항상 ``ATA`` 이고 카톡이 실패해야 ``SMS``/``LMS`` 로 바뀐다. 그래서
발송 직후엔 '문자로 나갔는지'를 알 수 없고, 1분 뒤에 **한 번** 물어 이력에 굳힌다.
벤더 조회는 격리 호출부 ``kakao_alimtalk._solapi_lookup_channel`` 을 monkeypatch 해
스텁한다(네트워크 0 — ``_solapi_send`` 선례).
"""
import copy
import datetime

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import kakao_alimtalk as ka
from foms.services.datetime_kst import now_utc_naive
from models import Order, SecurityLog, User

_CONFIRM = "/api/kakao/alimtalk/confirm-channel"

_MEASURE_SD = {
    "parties": {"customer": {"name": "임다슬", "phone": "010-2473-6730"},
                "orderer": {"name": "라홈시스템"}},
    "schedule": {"measurement": {"date": "2026-08-14", "time": "3시 30분"}},
    "items": [{"product_name": "무몰딩 여닫이"}],
}


def _mk_order(structured_data=None) -> Order:
    order = Order(
        received_date=datetime.date(2026, 7, 4),
        customer_name="임다슬",
        phone="010-2473-6730",
        address="Seoul",
        product="가구",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=structured_data if structured_data is not None
        else copy.deepcopy(_MEASURE_SD),
    )
    db_session.add(order)
    db_session.commit()
    return order


def _seed_history(order: Order, *, age_seconds: int = 120, **overrides) -> Order:
    """발송 이력 1건을 심는다(기본 = 2분 전에 성공 발송, 채널 미확정)."""
    sent_at = now_utc_naive() - datetime.timedelta(seconds=age_seconds)
    record = {
        "sent_at": sent_at.isoformat(),
        "message_id": "MSG-1",
        "dedupe_key": "alimtalk:measure:1:2026-08-14:3시 30분",
        "error": None,
        "sent_by": None,
        "sent_by_name": None,
        "channel": None,
        "channel_checked_at": None,
    }
    record.update(overrides)
    sd = copy.deepcopy(order.structured_data or {})
    sd["alimtalk_measurement"] = record
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    return order


def _history(order_id: int) -> dict:
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    return (order.structured_data or {}).get("alimtalk_measurement") or {}


def _login(client, username: str, role: str = "STAFF") -> int:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team="CS",
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role
    return uid


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


@pytest.fixture
def solapi_env(monkeypatch):
    monkeypatch.setenv("SOLAPI_API_KEY", "key")
    monkeypatch.setenv("SOLAPI_API_SECRET", "secret")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE", "0212345678")
    monkeypatch.setenv("SOLAPI_PF_ID_LAHOM", "PF-LAHOM")
    monkeypatch.setenv("SOLAPI_TEMPLATE_MEASURE_ID_LAHOM", "TPL-LAHOM")


@pytest.fixture
def stub_lookup(monkeypatch):
    """조회 결과를 조작할 수 있는 스텁 — ``calls`` 로 호출 여부를 검증한다."""
    state = {"result": "SMS", "calls": []}

    def _fake(message_id):
        state["calls"].append(message_id)
        outcome = state["result"]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(ka, "_solapi_lookup_channel", _fake)
    return state


@pytest.fixture
def stub_lookup_never(monkeypatch):
    def _fake(message_id):
        raise AssertionError("벤더를 호출하면 안 된다")

    monkeypatch.setattr(ka, "_solapi_lookup_channel", _fake)


# --- 서비스 계층 -----------------------------------------------------------------


def test_confirm_marks_text_channel(db, solapi_env, stub_lookup):
    """벤더가 SMS 로 답하면 '문자로 나갔다'가 이력에 굳는다."""
    order = _seed_history(_mk_order())

    result = ka.confirm_channel(order.id)

    assert result["channel"] == "SMS" and result["checked"] is True
    assert result["cached"] is False and result["error"] is None
    history = _history(order.id)
    assert history["channel"] == "SMS" and history["channel_checked_at"]
    assert ka.is_text_channel(history["channel"]) is True
    assert stub_lookup["calls"] == ["MSG-1"]


def test_confirm_marks_kakao_channel(db, solapi_env, stub_lookup):
    order = _seed_history(_mk_order())
    stub_lookup["result"] = "ATA"

    assert ka.confirm_channel(order.id)["channel"] == "ATA"
    assert ka.is_text_channel(_history(order.id)["channel"]) is False


def test_confirm_is_idempotent(db, solapi_env, stub_lookup):
    """이미 확정된 건은 벤더를 다시 부르지 않는다(페이지를 열 때마다 조회 금지)."""
    order = _seed_history(_mk_order())
    ka.confirm_channel(order.id)

    again = ka.confirm_channel(order.id)

    assert again == {"channel": "SMS", "checked": True, "cached": True, "error": None}
    assert stub_lookup["calls"] == ["MSG-1"]


def test_confirm_stops_after_empty_vendor_answer(db, solapi_env, stub_lookup):
    """벤더가 그 메시지를 모른다고 해도 '물어봤다'는 남는다 — 무한 재조회 차단."""
    order = _seed_history(_mk_order())
    stub_lookup["result"] = None

    result = ka.confirm_channel(order.id)

    assert result["channel"] is None and result["checked"] is True
    assert _history(order.id)["channel_checked_at"]
    assert ka.confirm_channel(order.id)["cached"] is True
    assert stub_lookup["calls"] == ["MSG-1"]


def test_confirm_too_early_does_not_call_vendor(db, solapi_env, stub_lookup_never):
    """발송 1분이 지나지 않았으면 아직 벤더가 채널을 바꾸지 않았다."""
    order = _seed_history(_mk_order(), age_seconds=5)

    result = ka.confirm_channel(order.id)

    assert result["error"] == "too_early" and result["checked"] is False
    assert _history(order.id)["channel_checked_at"] is None


def test_confirm_skips_failed_send(db, solapi_env, stub_lookup_never):
    order = _seed_history(_mk_order(), error="invalid_phone", message_id=None,
                          sent_at=None)

    assert ka.confirm_channel(order.id)["error"] == "nothing_to_confirm"


def test_confirm_skips_when_never_sent(db, solapi_env, stub_lookup_never):
    order = _mk_order()

    assert ka.confirm_channel(order.id)["error"] == "nothing_to_confirm"


def test_confirm_vendor_failure_keeps_history_intact(db, solapi_env, stub_lookup):
    """조회가 실패하면 아무것도 쓰지 않는다 — 다음 기회에 다시 물을 수 있어야 한다."""
    order = _seed_history(_mk_order())
    stub_lookup["result"] = TimeoutError("timeout")

    result = ka.confirm_channel(order.id)

    assert result["error"] == "network" and result["checked"] is False
    assert _history(order.id)["channel_checked_at"] is None


def test_confirm_requires_configuration(db, monkeypatch, stub_lookup_never):
    """벤더 설정이 없으면 조회하지 않고 사유를 표면화한다."""
    for name in ("SOLAPI_API_KEY", "SOLAPI_API_SECRET", "SOLAPI_SENDER_PHONE",
                 "SOLAPI_SENDER_PHONE_LAHOM", "SOLAPI_SENDER_PHONE_HAUD"):
        monkeypatch.delenv(name, raising=False)
    order = _seed_history(_mk_order())

    assert ka.confirm_channel(order.id)["error"] == "not_configured"


# --- API 계약 --------------------------------------------------------------------


def test_confirm_route_requires_login(client, db, stub_lookup_never):
    order_id = _seed_history(_mk_order()).id
    response = client.post(f"{_CONFIRM}/{order_id}")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_confirm_route_rejects_viewer_role(client, db, solapi_env, stub_lookup_never):
    _login(client, "channel-viewer", role="VIEWER")
    order_id = _seed_history(_mk_order()).id

    response = client.post(f"{_CONFIRM}/{order_id}")

    assert response.status_code == 302
    assert _history(order_id)["channel_checked_at"] is None


def test_confirm_route_unknown_order_is_404(client, db, solapi_env, stub_lookup_never):
    _login(client, "channel-404")
    response = client.post(f"{_CONFIRM}/99999999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "order_not_found"


def test_confirm_route_writes_audit_once(client, db, solapi_env, stub_lookup):
    """확정한 호출만 감사에 남는다 — 캐시 반환은 소음이라 남기지 않는다."""
    _login(client, "channel-ok")
    order_id = _seed_history(_mk_order()).id

    response = client.post(f"{_CONFIRM}/{order_id}")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["channel"] == "SMS" and body["data"]["checked"] is True

    client.post(f"{_CONFIRM}/{order_id}")  # 두 번째는 캐시 반환

    logs = db_session.query(SecurityLog).filter(
        SecurityLog.action == "ALIMTALK_CHANNEL_CONFIRMED").all()
    assert len(logs) == 1
    assert "문자 대체발송" in (logs[0].message or "")


def test_confirm_route_soft_errors_are_200(client, db, solapi_env, stub_lookup_never):
    """아직 확인할 수 없는 상태는 오류가 아니다 — 화면은 칩을 그대로 둔다."""
    _login(client, "channel-early")
    order_id = _seed_history(_mk_order(), age_seconds=5).id

    response = client.post(f"{_CONFIRM}/{order_id}")

    assert response.status_code == 200
    assert response.get_json()["error"] == "too_early"


def test_confirm_route_not_configured_is_503(client, db, monkeypatch, stub_lookup_never):
    for name in ("SOLAPI_API_KEY", "SOLAPI_API_SECRET", "SOLAPI_SENDER_PHONE",
                 "SOLAPI_SENDER_PHONE_LAHOM", "SOLAPI_SENDER_PHONE_HAUD"):
        monkeypatch.delenv(name, raising=False)
    _login(client, "channel-unset")
    order_id = _seed_history(_mk_order()).id

    response = client.post(f"{_CONFIRM}/{order_id}")

    assert response.status_code == 503
    assert response.get_json()["error"] == "not_configured"
