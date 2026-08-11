"""카카오 알림톡 v1 — 수동 발송 API 계약 테스트 (T4).

Solapi 는 격리 호출부 ``kakao_alimtalk._solapi_send`` 를 monkeypatch 해 스텁한다(네트워크 0).
권한 실패는 ``role_required`` 규약대로 302 redirect 다(JSON 403 아님 — 데코레이터 선례).
"""
import copy
import datetime
import re

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services import kakao_alimtalk as ka
from models import Order, User

_PREVIEW = "/api/kakao/alimtalk/preview"
_SEND = "/api/kakao/alimtalk/send-manual"

_MEASURE_SD = {
    "parties": {"customer": {"name": "임다슬", "phone": "010-2473-6730"},
                "orderer": {"name": "라홈시스템"}},
    "schedule": {"measurement": {"date": "2026-08-14", "time": "3시 30분"}},
    "items": [{"product_name": "무몰딩 여닫이"}],
}


def _sd(**overrides) -> dict:
    sd = copy.deepcopy(_MEASURE_SD)
    sd.update(overrides)
    return sd


def _mk_order(structured_data=None) -> Order:
    order = Order(
        received_date=datetime.date(2026, 7, 4),
        customer_name="임다슬",
        phone="010-2473-6730",
        address="Seoul",
        product="가구",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=structured_data if structured_data is not None else _sd(),
    )
    db_session.add(order)
    db_session.commit()
    return order


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


def _history(order_id: int) -> dict:
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    return (order.structured_data or {}).get("alimtalk_measurement") or {}


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


@pytest.fixture
def solapi_env(monkeypatch):
    """공통 자격증명 + 라홈 발신프로필 구성."""
    monkeypatch.setenv("SOLAPI_API_KEY", "key")
    monkeypatch.setenv("SOLAPI_API_SECRET", "secret")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE", "0212345678")
    monkeypatch.setenv("SOLAPI_PF_ID_LAHOM", "PF-LAHOM")
    monkeypatch.setenv("SOLAPI_TEMPLATE_MEASURE_ID_LAHOM", "TPL-LAHOM")


@pytest.fixture
def stub_solapi_ok(monkeypatch):
    calls: list[dict] = []

    def _fake(**kwargs) -> str:
        calls.append(kwargs)
        return "MSG-1"

    monkeypatch.setattr(ka, "_solapi_send", _fake)
    return calls


@pytest.fixture
def stub_solapi_never(monkeypatch):
    def _fake(**kwargs):
        raise AssertionError("Solapi 를 호출하면 안 된다")

    monkeypatch.setattr(ka, "_solapi_send", _fake)


# --- 권한 -----------------------------------------------------------------------


def test_preview_requires_login(client, db):
    order = _mk_order()
    response = client.get(f"{_PREVIEW}/{order.id}")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_send_manual_requires_login(client, db, stub_solapi_never):
    order = _mk_order()
    response = client.post(f"{_SEND}/{order.id}")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_send_manual_rejects_viewer_role(client, db, solapi_env, stub_solapi_never):
    """VIEWER 는 발송 권한 없음 — 핸들러 진입 전 차단(발송 0)."""
    _login(client, "alimtalk-viewer", role="VIEWER")
    order_id = _mk_order().id

    response = client.post(f"{_SEND}/{order_id}")

    assert response.status_code == 302
    assert _history(order_id) == {}


# --- preview --------------------------------------------------------------------


def test_preview_matches_render_preview(client, db, solapi_env):
    _login(client, "alimtalk-preview")
    order = _mk_order()
    expected = ka.render_preview(order.structured_data)

    response = client.get(f"{_PREVIEW}/{order.id}")

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["success"] is True and body["error"] is None
    assert body["data"]["text"] == expected
    assert body["data"]["eligible"] is True
    assert body["data"]["ineligible_reason"] is None
    assert body["data"]["configured"] is True
    assert body["data"]["last"] is None


def test_preview_includes_last_history(client, db, solapi_env, stub_solapi_ok):
    """직전 발송 이력이 있으면 preview 가 그대로 실어 준다(재발송 확인 모달용)."""
    _login(client, "alimtalk-preview-last")
    order = _mk_order()
    order_id = order.id
    ka.send_alimtalk(order_id, manual_by=1, dedupe_key="alimtalk:measure:x:manual:abc")
    db_session.expire_all()  # 실제 요청은 매번 close 된 세션으로 시작한다(close_db teardown)

    body = client.get(f"{_PREVIEW}/{order_id}").get_json()

    assert body["data"]["last"]["message_id"] == "MSG-1"
    assert body["data"]["last"]["dedupe_key"] == "alimtalk:measure:x:manual:abc"


def test_preview_reports_ineligible_reason(client, db, solapi_env):
    """실측일이 없으면 미자격 사유를 준다(버튼 비활성 근거)."""
    _login(client, "alimtalk-preview-inelig")
    order = _mk_order(_sd(schedule={"measurement": {"date": "상담", "time": ""}}))

    body = client.get(f"{_PREVIEW}/{order.id}").get_json()

    assert body["data"]["eligible"] is False
    assert body["data"]["ineligible_reason"] == "not_eligible"


def test_preview_unknown_order_404(client, db, solapi_env):
    _login(client, "alimtalk-preview-404")
    response = client.get(f"{_PREVIEW}/999999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "order_not_found"


# --- send-manual ----------------------------------------------------------------


def test_send_manual_not_configured_returns_503(client, db, monkeypatch, stub_solapi_never):
    monkeypatch.delenv("SOLAPI_API_KEY", raising=False)
    _login(client, "alimtalk-unconfigured")
    order = _mk_order()

    response = client.post(f"{_SEND}/{order.id}")

    assert response.status_code == 503
    body = response.get_json()
    assert body["success"] is False and body["error"] == "not_configured"
    assert _history(order.id) == {}


def test_send_manual_records_sent_by_and_manual_key(client, db, solapi_env, stub_solapi_ok):
    """발송자 user_id 가 이력에 남고, 멱등키는 매번 새 manual 형식이다(D2)."""
    uid = _login(client, "alimtalk-send")
    order = _mk_order()
    order_id = order.id

    response = client.post(f"{_SEND}/{order_id}")

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body == {"success": True, "data": {"sent": True, "error": None}, "error": None}
    assert len(stub_solapi_ok) == 1

    history = _history(order_id)
    assert history["sent_by"] == uid and history["message_id"] == "MSG-1"
    assert re.fullmatch(rf"alimtalk:measure:{order_id}:manual:[0-9a-f-]{{36}}", history["dedupe_key"])


def test_send_manual_resend_uses_new_key(client, db, solapi_env, stub_solapi_ok):
    """수동 재발송은 멱등키로 막지 않는다 — 두 번째도 발송된다(D2)."""
    _login(client, "alimtalk-resend")
    order = _mk_order()
    order_id = order.id

    first = client.post(f"{_SEND}/{order_id}").get_json()
    first_key = _history(order_id)["dedupe_key"]
    second = client.post(f"{_SEND}/{order_id}").get_json()

    assert first["data"]["sent"] is True and second["data"]["sent"] is True
    assert len(stub_solapi_ok) == 2
    assert _history(order_id)["dedupe_key"] != first_key


def test_send_manual_ignores_client_text(client, db, solapi_env, stub_solapi_ok):
    """클라이언트가 text 를 보내도 무시하고 서버 저장본으로 재렌더한다(스펙 §6.4 F2)."""
    _login(client, "alimtalk-ignore-text")
    order = _mk_order()

    response = client.post(f"{_SEND}/{order.id}", json={"text": "해킹된 본문", "to": "01099998888"})

    assert response.status_code == 200, response.get_data(as_text=True)
    sent = stub_solapi_ok[0]
    assert sent["to"] == "01024736730"  # 저장본 고객 번호
    assert sent["variables"]["#{고객명}"] == "임다슬"
    assert "해킹된 본문" not in "".join(sent["variables"].values())
    assert "text" not in sent


def test_send_manual_failure_returns_error_envelope(client, db, solapi_env, monkeypatch):
    """벤더 실패도 200 + success=False 로 사유를 돌려준다(UI 한 줄 표시용)."""
    def _boom(**kwargs):
        raise ConnectionError("timeout")

    monkeypatch.setattr(ka, "_solapi_send", _boom)
    _login(client, "alimtalk-send-fail")
    order = _mk_order()
    order_id = order.id

    body = client.post(f"{_SEND}/{order_id}").get_json()

    assert body == {"success": False, "data": {"sent": False, "error": "network"}, "error": "network"}
    assert _history(order_id)["error"] == "network"


def test_send_manual_unknown_order_404(client, db, solapi_env, stub_solapi_never):
    _login(client, "alimtalk-send-404")
    response = client.post(f"{_SEND}/999999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "order_not_found"
