"""WIZ-SEND-01 T3: 마법사 초안 발송 라우트 계약.

고정하는 것:

1. **게이트** — 비로그인·VIEWER 는 어떤 초안 발송도 못 한다.
2. **소유 검증** — 남의 ``draft_key`` 로는 미리보기도 발송도 되지 않는다(404, 존재 노출 없음).
3. **자격 사유** — 미자격 초안은 발송하지 않고 사유 코드를 돌려준다.
4. **이력** — 발송 성공은 ``OrderDraft.send_history`` 에 남는다(payload 가 아니라 — autosave
   가 payload 를 통째로 덮기 때문).
5. **재전송 규율** — 실측 PUSH 재전송은 변경 메모(1~500자) 없이는 400.
6. **manifest 등재** — POST 2종이 write guard · order mutation policy 양쪽에 있다.
"""

from __future__ import annotations

import datetime
import json
import pathlib

import pytest
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.security import generate_password_hash

import foms.api.erp_order_draft_send as send_api
import foms.services.channel_draft_push as draft_push
import foms.services.kakao_alimtalk as ka
from db import db_session
from foms.services.datetime_kst import now_utc_naive
from models import OrderDraft, SecurityLog, User

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ALIMTALK_SEND = "/api/erp/order-draft/alimtalk/send"
_ALIMTALK_PREVIEW = "/api/erp/order-draft/alimtalk/preview"
_PUSH_SEND = "/api/erp/order-draft/channel-push/send"
_PUSH_PREVIEW = "/api/erp/order-draft/channel-push/preview"


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture
def wizard_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")


@pytest.fixture
def solapi_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """알림톡 발송 자격을 갖춘 환경(라홈 프로필까지 구성)."""
    monkeypatch.setenv("SOLAPI_API_KEY", "key")
    monkeypatch.setenv("SOLAPI_API_SECRET", "secret")
    monkeypatch.setenv("SOLAPI_SENDER_PHONE", "0212345678")
    monkeypatch.setenv("SOLAPI_PF_ID_LAHOM", "PF-LAHOM")
    monkeypatch.setenv("SOLAPI_TEMPLATE_MEASURE_ID_LAHOM", "TPL-LAHOM")


@pytest.fixture
def stub_solapi(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Solapi 호출을 가로채 인자를 모은다(실제 발송 금지)."""
    calls: list[dict] = []

    def _fake(**kwargs) -> str:
        calls.append(kwargs)
        return "MSG-DRAFT-1"

    monkeypatch.setattr(ka, "_solapi_send", _fake)
    return calls


@pytest.fixture
def stub_channel(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """채널톡 설정을 켜고 전송 호출을 가로챈다."""
    calls: list[dict] = []

    def _fake(**kwargs) -> dict:
        calls.append(kwargs)
        return {"success": True, "message_id": "CH-1"}

    monkeypatch.setattr(draft_push, "is_configured", lambda: True)
    monkeypatch.setattr(send_api, "channel_is_configured", lambda: True)
    monkeypatch.setattr(draft_push, "send_group_message", _fake)
    return calls


def _make_user(username: str, *, role: str = "STAFF") -> int:
    user = db_session.query(User).filter_by(username=username).one_or_none()
    if user is None:
        user = User(
            username=username,
            password=generate_password_hash("pw"),
            role=role,
            team="CS",
            name=f"{username}-표시명",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
    return user.id


def _login(client, username: str, *, role: str = "STAFF") -> int:
    uid = _make_user(username, role=role)
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role
    return uid


def _payload(*, with_schedule: bool = True, attachments: list[dict] | None = None) -> dict:
    data = {
        "customer_name": "초안고객",
        # 브랜드 판정(resolve_brand)은 발주사명으로 한다 — 라홈 프로필만 구성된 환경에서
        # 발송 자격을 갖추려면 발주사가 라홈이어야 한다.
        "orderer": "라홈",
        "phone": "010-2222-3333",
        "address": "서울시 마법사구 1",
        "items": [{
            "product_name": "붙박이장",
            "spec_rows": [{"spec_width": "3000", "spec_depth": "600", "spec_height": "2400"}],
            "attachments": attachments or [],
        }],
        "schedule": {"measurement_date": "2026-09-10", "measurement_time": "오전"}
        if with_schedule else {},
    }
    return {"schema_version": 1, "step": 4, "data": data}


def _make_draft(uid: int, key: str, *, payload: dict | None = None) -> int:
    row = OrderDraft(
        user_id=uid,
        draft_key=key,
        step=4,
        payload=payload if payload is not None else _payload(),
        schema_version=1,
        expires_at=datetime.datetime.now() + datetime.timedelta(days=7),
    )
    db_session.add(row)
    db_session.commit()
    return row.id


def _history(draft_id: int) -> dict:
    db_session.expire_all()
    row = db_session.get(OrderDraft, draft_id)
    return row.send_history if isinstance(row.send_history, dict) else {}


def _age_history(draft_id: int, kind: str) -> None:
    """직전 발송 시각을 과거로 밀어 '의도적 재전송'을 재현한다(연타 방어 창 밖)."""
    db_session.expire_all()
    row = db_session.get(OrderDraft, draft_id)
    history = dict(row.send_history)
    history[kind] = {
        **history[kind],
        "sent_at": (now_utc_naive() - datetime.timedelta(minutes=5)).isoformat(),
    }
    row.send_history = history
    flag_modified(row, "send_history")
    db_session.commit()


def _post(client, url: str, body: dict):
    return client.post(url, data=json.dumps(body), content_type="application/json")


# --------------------------------------------------------------------------
# 게이트
# --------------------------------------------------------------------------
def test_anonymous_cannot_send(client, app, wizard_enabled):
    """비로그인은 초안 발송 라우트에 닿지 못한다."""
    for url in (_ALIMTALK_SEND, _PUSH_SEND):
        resp = _post(client, url, {"draft_key": "new.anon"})
        assert resp.status_code in (401, 403, 302), (url, resp.status_code)


def test_viewer_is_blocked(client, app, wizard_enabled):
    """VIEWER 는 발송 권한이 없다(PC 수동 발송과 같은 역할 집합)."""
    uid = _login(client, "draft_send_viewer", role="VIEWER")
    draft_id = _make_draft(uid, "new.viewer")
    for url in (_ALIMTALK_SEND, _PUSH_SEND):
        resp = _post(client, url, {"draft_key": "new.viewer"})
        # role_required 는 302(리다이렉트), 운영에서는 정책 가드가 403 JSON 을 낸다.
        assert resp.status_code in (302, 403), (url, resp.status_code)
    assert _history(draft_id) == {}


def test_unknown_draft_key_is_404(client, app, wizard_enabled, solapi_env, stub_channel):
    """없는 초안은 404 — 미리보기·발송 모두."""
    _login(client, "draft_send_missing")
    assert client.get(f"{_ALIMTALK_PREVIEW}?draft_key=new.nope").status_code == 404
    assert client.get(f"{_PUSH_PREVIEW}?draft_key=new.nope").status_code == 404
    assert _post(client, _ALIMTALK_SEND, {"draft_key": "new.nope"}).status_code == 404
    assert _post(client, _PUSH_SEND, {"draft_key": "new.nope"}).status_code == 404


def test_other_users_draft_is_not_reachable(client, app, wizard_enabled, solapi_env, stub_solapi):
    """남의 draft_key 로는 발송되지 않는다(존재 여부도 노출하지 않는 404)."""
    owner = _make_user("draft_send_owner")
    _make_draft(owner, "new.owned")
    _login(client, "draft_send_intruder")

    assert client.get(f"{_ALIMTALK_PREVIEW}?draft_key=new.owned").status_code == 404
    resp = _post(client, _ALIMTALK_SEND, {"draft_key": "new.owned"})
    assert resp.status_code == 404
    assert stub_solapi == []


# --------------------------------------------------------------------------
# 알림톡
# --------------------------------------------------------------------------
def test_alimtalk_preview_reports_ineligible_reason(client, app, wizard_enabled, solapi_env):
    """실측 일정이 없는 초안은 미리보기가 사유(``not_eligible``)를 말한다."""
    uid = _login(client, "draft_send_preview")
    _make_draft(uid, "new.noschedule", payload=_payload(with_schedule=False))

    resp = client.get(f"{_ALIMTALK_PREVIEW}?draft_key=new.noschedule")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["eligible"] is False
    assert data["ineligible_reason"] == "not_eligible"
    assert data["configured"] is True
    assert data["last"] is None
    assert data["text"]  # 사유 확인용 본문은 함께 준다


def test_alimtalk_send_blocked_when_ineligible(client, app, wizard_enabled, solapi_env, stub_solapi):
    """미자격 초안은 발송하지 않고 사유만 돌려준다(이력도 남기지 않는다)."""
    uid = _login(client, "draft_send_ineligible")
    draft_id = _make_draft(uid, "new.ineligible", payload=_payload(with_schedule=False))

    resp = _post(client, _ALIMTALK_SEND, {"draft_key": "new.ineligible"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["error"] == "not_eligible"
    assert body["data"]["sent"] is False
    assert stub_solapi == []
    assert _history(draft_id) == {}


def test_alimtalk_send_records_history_on_draft(client, app, wizard_enabled, solapi_env, stub_solapi):
    """발송 성공은 ``OrderDraft.send_history`` 에 정본 키 모양으로 남는다."""
    uid = _login(client, "draft_send_ok")
    draft_id = _make_draft(uid, "new.sendok")

    resp = _post(client, _ALIMTALK_SEND, {"draft_key": "new.sendok"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["sent"] is True
    assert len(stub_solapi) == 1

    entry = _history(draft_id)["alimtalk_measurement"]
    assert entry["message_id"] == "MSG-DRAFT-1"
    assert entry["error"] is None
    assert entry["sent_at"]
    assert entry["sent_by"] == uid
    assert entry["sent_by_name"] == "draft_send_ok-표시명"
    assert entry["draft_schedule"] == "2026-09-10:오전"
    assert entry["dedupe_key"].startswith("alimtalk:measure:draft:new.sendok:manual:")
    # payload 는 클라이언트 소유다 — 이력이 거기 섞이면 다음 autosave 에 사라진다.
    db_session.expire_all()
    assert "alimtalk_measurement" not in db_session.get(OrderDraft, draft_id).payload["data"]


def test_alimtalk_send_is_audited(client, app, wizard_enabled, solapi_env, stub_solapi):
    """고객에게 나간 초안 발송은 구조화 감사로 남는다(대상=order_draft)."""
    uid = _login(client, "draft_send_audit")
    draft_id = _make_draft(uid, "new.audit")

    _post(client, _ALIMTALK_SEND, {"draft_key": "new.audit"})

    db_session.expire_all()
    log = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "ALIMTALK_DRAFT_SENT")
        .order_by(SecurityLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.target_type == "order_draft"
    assert log.target_id == draft_id
    assert log.user_id == uid
    assert (log.detail or {}).get("sent") is True
    assert "초안 알림톡 발송" in log.message


def test_duplicate_alimtalk_click_is_rejected(client, app, wizard_enabled, solapi_env, stub_solapi):
    """같은 초안 연타는 두 번 나가지 않는다(중복 창 안 = 409)."""
    uid = _login(client, "draft_send_dup")
    _make_draft(uid, "new.dup")

    assert _post(client, _ALIMTALK_SEND, {"draft_key": "new.dup"}).status_code == 200
    second = _post(client, _ALIMTALK_SEND, {"draft_key": "new.dup"})
    assert second.status_code == 409
    assert second.get_json()["error"] == "duplicate_request"
    assert len(stub_solapi) == 1


# --------------------------------------------------------------------------
# 실측 PUSH
# --------------------------------------------------------------------------
def test_channel_push_sends_body_without_attachments(client, app, wizard_enabled, stub_channel):
    """첨부 0건이어도 본문은 전송된다(첨부는 있으면 얹는 것이지 전송 조건이 아니다)."""
    uid = _login(client, "draft_push_nofiles")
    draft_id = _make_draft(uid, "new.push0")

    resp = _post(client, _PUSH_SEND, {"draft_key": "new.push0"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["files_count"] == 0

    assert len(stub_channel) == 1
    sent = stub_channel[0]
    assert sent["files"] == []
    assert "초안" in sent["plain_text"]  # 등록 전 안내 머리말(D5)
    # 가리킬 주문이 없으므로 주문 상세 링크는 붙지 않는다(D5).
    assert "주문 상세 보기" not in sent["plain_text"]
    assert all("주문 보기" not in block["value"] for block in sent["blocks"])
    assert sent["bot_name"] == "FOMSdraft_push_nofiles-표시명"

    entry = _history(draft_id)["channeltalk_push_measure_room"]
    assert entry["pushed"] is True
    assert entry["message_id"] == "CH-1"
    assert entry["is_modified"] is False


def test_channel_push_resend_requires_change_note(client, app, wizard_enabled, stub_channel):
    """재전송은 변경 메모 없이는 400(PC 채널톡 경로와 같은 규칙)."""
    uid = _login(client, "draft_push_resend")
    draft_id = _make_draft(uid, "new.push-resend")

    assert _post(client, _PUSH_SEND, {"draft_key": "new.push-resend"}).status_code == 200
    _age_history(draft_id, "channeltalk_push_measure_room")

    missing = _post(client, _PUSH_SEND, {"draft_key": "new.push-resend"})
    assert missing.status_code == 400
    assert missing.get_json()["error"] == "change_note_required"
    assert len(stub_channel) == 1

    too_long = _post(client, _PUSH_SEND,
                     {"draft_key": "new.push-resend", "change_note": "가" * 501})
    assert too_long.status_code == 400
    assert too_long.get_json()["error"] == "change_note_too_long"

    ok = _post(client, _PUSH_SEND, {"draft_key": "new.push-resend", "change_note": "일정 변경"})
    assert ok.status_code == 200
    assert len(stub_channel) == 2
    assert "[수정]" in stub_channel[1]["plain_text"]

    entry = _history(draft_id)["channeltalk_push_measure_room"]
    assert entry["is_modified"] is True
    assert entry["change_log"][-1]["note"] == "일정 변경"


def test_channel_push_preview_counts_files(client, app, wizard_enabled, stub_channel, monkeypatch):
    """미리보기는 서버가 조립한 본문과 실제 전송될 첨부 수를 말한다."""
    uid = _login(client, "draft_push_preview")
    _make_draft(uid, "new.push-preview", payload=_payload(attachments=[
        {"tmp_key": "order-drafts/1/new/a.jpg", "filename": "a.jpg"},
        {"tmp_key": "order-drafts/1/new/b.txt", "filename": "b.txt"},  # 이미지/동영상 아님
    ]))

    class _Storage:
        def object_exists(self, key: str) -> bool:
            return True

        def get_file_type(self, filename: str) -> str:
            return "image" if filename.endswith(".jpg") else "file"

        def get_download_url(self, key: str, expires_in: int = 3600) -> str:
            return f"https://signed.example/{key}?e={expires_in}"

    monkeypatch.setattr(draft_push, "get_storage", lambda: _Storage())

    resp = client.get(f"{_PUSH_PREVIEW}?draft_key=new.push-preview")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["files_count"] == 1
    assert data["configured"] is True
    assert "주문 상세 보기" not in data["text"]


def test_channel_push_failure_leaves_no_history(client, app, wizard_enabled, monkeypatch):
    """전송이 안 됐으면 이력을 남기지 않는다(가짜 발송 흔적 금지)."""
    uid = _login(client, "draft_push_fail")
    draft_id = _make_draft(uid, "new.push-fail")

    monkeypatch.setattr(draft_push, "is_configured", lambda: True)
    monkeypatch.setattr(send_api, "channel_is_configured", lambda: True)
    monkeypatch.setattr(draft_push, "send_group_message",
                        lambda **kwargs: {"success": False, "message_id": None})

    resp = _post(client, _PUSH_SEND, {"draft_key": "new.push-fail"})
    assert resp.status_code == 502
    assert resp.get_json()["error"] == "not_sent"
    assert _history(draft_id) == {}


# --------------------------------------------------------------------------
# manifest 등재
# --------------------------------------------------------------------------
@pytest.mark.parametrize("manifest_name", [
    "foms_write_guard_manifest.json",
    "foms_order_mutation_policy_manifest.json",
])
def test_send_routes_are_registered_in_manifests(manifest_name):
    """POST 2종은 write guard · order mutation policy manifest 양쪽에 등재된다."""
    manifest = json.loads(
        (_REPO_ROOT / "docs" / "harness" / manifest_name).read_text(encoding="utf-8")
    )
    routes = manifest["routes"]
    for endpoint in (
        "erp_order_draft_send.api_draft_alimtalk_send",
        "erp_order_draft_send.api_draft_channel_push_send",
    ):
        assert endpoint in routes, f"{manifest_name} 미등재: {endpoint}"
        assert routes[endpoint]["mode"] == "guard"
