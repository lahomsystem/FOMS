"""WIZ-SEND-01 T5: 초안 발송 이력(OrderDraft.send_history) 저장 + 주문 승계.

마법사 4단계는 **주문 행이 생기기 전에** 실측 PUSH·예약안내 알림톡을 보낼 수 있다.
그 흔적이 살아남는 자리가 ``OrderDraft.send_history`` 이고(``payload`` 는 매 autosave 마다
클라이언트가 통째로 덮는다), 주문 등록 시 새 주문 ``structured_data`` 로 승계된다.

가장 값비싼 계약은 D4' 다 — 승계는 ``create_order`` **앞의 순수 dict 병합**이고(뒤에서
``flag_modified`` 로 쓰면 REV-99 EXTERNAL writer 가 늘어난다), 등록 직후 첫 저장의 자동
발송이 **같은 예약 안내를 고객에게 한 번 더** 보내지 않게 막는 것은 이력의
``draft_schedule`` 일정 서명이다(멱등키 재작성이 아니다).
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash

from foms.services.order_draft_service import (
    SEND_KIND_ALIMTALK,
    SEND_KIND_CHANNEL_MEASURE,
    OrderDraftNotFoundError,
    get_draft_send_history,
    record_draft_send,
)


@pytest.fixture
def wizard_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")


def _make_user(username: str):
    from db import db_session
    from models import User

    existing = db_session.query(User).filter_by(username=username).first()
    if existing is not None:
        return existing
    user = User(
        username=username,
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="Send History User",
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_draft(user_id: int, draft_key: str):
    from db import db_session
    from models import OrderDraft

    row = OrderDraft(
        user_id=user_id,
        draft_key=draft_key,
        step=4,
        payload={"schema_version": 1, "step": 4, "data": {}},
        schema_version=1,
        expires_at=datetime.now() + timedelta(days=7),
    )
    db_session.add(row)
    db_session.commit()
    return row


def _alimtalk_entry(
    *,
    dedupe_key: str,
    message_id: str | None,
    error: str | None,
    draft_schedule: str | None = None,
) -> dict:
    """초안 발송 이력 entry(주문 정본 키 + ``draft_schedule`` 서명)."""
    return {
        "draft_schedule": draft_schedule,
        "sent_at": "2026-09-02T01:00:00" if error is None else None,
        "message_id": message_id,
        "dedupe_key": dedupe_key,
        "error": error,
        "sent_by": 7,
        "sent_by_name": "테스터",
        "channel": None,
        "channel_checked_at": None,
    }


def _channel_entry() -> dict:
    return {
        "pushed": True,
        "pushed_at": "2026-09-02T01:05:00",
        "pushed_by": 7,
        "files_count": 3,
        "group_id": "grp-1",
    }


def _login(client, app, username: str) -> None:
    with app.app_context():
        _make_user(username)
    client.post(
        "/login",
        data={"username": username, "password": "admin"},
        follow_redirects=True,
    )


def _submit_payload(
    *, measurement_date: str = "2026-09-20", measurement_time: str = "14:00"
) -> dict:
    return {
        "schema_version": 1,
        "step": 4,
        "data": {
            "customer_name": "승계테스트",
            "phone": "010-1234-5678",
            "address": "서울시 강남구",
            "received_date": "2026-09-02",
            "items": [
                {
                    "product_name": "붙박이장",
                    "spec_rows": [
                        {"spec_width": "3000", "spec_depth": "600", "spec_height": "2300"}
                    ],
                }
            ],
            "schedule": {
                "measurement_date": measurement_date,
                "measurement_time": measurement_time,
            },
        },
    }


# --- 5-1/5-2: 컬럼 + 서비스 계약 -------------------------------------------------


def test_order_draft_has_send_history_column(app) -> None:
    """서버 전용 이력 컬럼이 실제 테이블에 있어야 한다(마이그레이션 ↔ 모델 정합)."""
    from sqlalchemy import inspect

    from db import engine

    columns = {c["name"] for c in inspect(engine).get_columns("order_drafts")}
    assert "send_history" in columns


def test_record_and_get_roundtrip(app) -> None:
    """두 kind 를 각각 기록하면 둘 다 남는다(뒤에 쓴 것이 앞을 지우지 않는다)."""
    from db import db_session

    user = _make_user("sendhist_roundtrip")
    _make_draft(user.id, "new.roundtrip")

    alimtalk = _alimtalk_entry(dedupe_key="alimtalk:measure:0:2026-09-20:14:00",
                               message_id="MSG-1", error=None)
    record_draft_send(
        db_session,
        draft_key="new.roundtrip",
        user_id=user.id,
        kind=SEND_KIND_ALIMTALK,
        entry=alimtalk,
    )
    record_draft_send(
        db_session,
        draft_key="new.roundtrip",
        user_id=user.id,
        kind=SEND_KIND_CHANNEL_MEASURE,
        entry=_channel_entry(),
    )
    db_session.commit()

    history = get_draft_send_history(db_session, draft_key="new.roundtrip", user_id=user.id)
    assert set(history) == {SEND_KIND_ALIMTALK, SEND_KIND_CHANNEL_MEASURE}
    assert history[SEND_KIND_ALIMTALK] == alimtalk
    assert history[SEND_KIND_CHANNEL_MEASURE] == _channel_entry()


def test_get_send_history_returns_empty_dict_when_absent(app) -> None:
    from db import db_session

    user = _make_user("sendhist_absent")
    _make_draft(user.id, "new.absent")
    assert get_draft_send_history(db_session, draft_key="new.absent", user_id=user.id) == {}
    assert get_draft_send_history(db_session, draft_key="new.nope", user_id=user.id) == {}


def test_get_send_history_returns_copy(app) -> None:
    """호출자가 반환값을 고쳐도 저장된 이력은 오염되지 않는다."""
    from db import db_session

    user = _make_user("sendhist_copy")
    _make_draft(user.id, "new.copy")
    record_draft_send(
        db_session,
        draft_key="new.copy",
        user_id=user.id,
        kind=SEND_KIND_ALIMTALK,
        entry=_alimtalk_entry(dedupe_key="k", message_id="M", error=None),
    )
    db_session.commit()

    first = get_draft_send_history(db_session, draft_key="new.copy", user_id=user.id)
    first[SEND_KIND_ALIMTALK]["message_id"] = "TAMPERED"
    second = get_draft_send_history(db_session, draft_key="new.copy", user_id=user.id)
    assert second[SEND_KIND_ALIMTALK]["message_id"] == "M"


def test_record_rejects_unknown_kind(app) -> None:
    from db import db_session

    user = _make_user("sendhist_badkind")
    _make_draft(user.id, "new.badkind")
    with pytest.raises(ValueError):
        record_draft_send(
            db_session,
            draft_key="new.badkind",
            user_id=user.id,
            kind="sms_blast",
            entry={"x": 1},
        )
    assert get_draft_send_history(db_session, draft_key="new.badkind", user_id=user.id) == {}


def test_record_rejects_non_dict_entry(app) -> None:
    from db import db_session

    user = _make_user("sendhist_badentry")
    _make_draft(user.id, "new.badentry")
    with pytest.raises(ValueError):
        record_draft_send(
            db_session,
            draft_key="new.badentry",
            user_id=user.id,
            kind=SEND_KIND_ALIMTALK,
            entry=["not", "a", "dict"],  # type: ignore[arg-type]
        )


def test_foreign_draft_is_not_writable_or_readable(app) -> None:
    """남의 초안에는 쓰지도(예외) 읽지도(빈 dict) 못한다."""
    from db import db_session
    from models import OrderDraft

    owner = _make_user("sendhist_owner")
    stranger = _make_user("sendhist_stranger")
    _make_draft(owner.id, "new.owned")

    with pytest.raises(OrderDraftNotFoundError):
        record_draft_send(
            db_session,
            draft_key="new.owned",
            user_id=stranger.id,
            kind=SEND_KIND_ALIMTALK,
            entry=_alimtalk_entry(dedupe_key="k", message_id="M", error=None),
        )
    db_session.rollback()

    assert get_draft_send_history(db_session, draft_key="new.owned", user_id=stranger.id) == {}
    row = (
        db_session.query(OrderDraft)
        .filter_by(user_id=owner.id, draft_key="new.owned")
        .one()
    )
    assert row.send_history in (None, {})


def test_record_does_not_move_if_match_token(app) -> None:
    """서버 전용 쓰기가 updated_at(If-Match 토큰)을 흔들면 다음 autosave 가 409 로 튕긴다."""
    from db import db_session

    user = _make_user("sendhist_ifmatch")
    row = _make_draft(user.id, "new.ifmatch")
    before = row.updated_at

    record_draft_send(
        db_session,
        draft_key="new.ifmatch",
        user_id=user.id,
        kind=SEND_KIND_ALIMTALK,
        entry=_alimtalk_entry(dedupe_key="k", message_id="M", error=None),
    )
    db_session.commit()
    db_session.expire_all()

    history = get_draft_send_history(db_session, draft_key="new.ifmatch", user_id=user.id)
    assert history[SEND_KIND_ALIMTALK]["message_id"] == "M"
    from foms.services.order_draft_service import get_draft

    assert get_draft(db_session, user.id, "new.ifmatch").updated_at == before


# --- 5-3: 제출 시 승계 -----------------------------------------------------------


def _put_draft(client, key: str, payload: dict) -> None:
    response = client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": 4, "payload": payload}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.get_data(as_text=True)


def _submit(client, key: str) -> int:
    response = client.post(
        "/api/erp/order-draft/submit",
        data=json.dumps({"draft_key": key}),
        content_type="application/json",
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["data"]["order_id"]


def test_submit_inherits_alimtalk_entry_verbatim_and_suppresses_resend(
    client, app, wizard_enabled
) -> None:
    """이력은 **무변환 복사**되고, 중복 차단은 일정 서명이 성립시킨다(D4')."""
    from db import db_session
    from models import Order, User

    from foms.services.kakao_alimtalk import (
        _already_sent,
        build_dedupe_key,
        build_draft_schedule_signature,
    )

    username = "sendhist_submit_ok"
    _login(client, app, username)
    key = "new.submit-ok"
    _put_draft(client, key, _submit_payload())

    draft_dedupe = "alimtalk:measure:draft:new.submit-ok:manual:deadbeef"
    entry = _alimtalk_entry(
        dedupe_key=draft_dedupe,
        message_id="MSG-OK",
        error=None,
        draft_schedule="2026-09-20:14:00",
    )
    with app.app_context():
        uid = db_session.query(User).filter_by(username=username).one().id
        record_draft_send(
            db_session, draft_key=key, user_id=uid, kind=SEND_KIND_ALIMTALK, entry=entry
        )
        db_session.commit()

    order_id = _submit(client, key)

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        sd = order.structured_data or {}
        # 무변환 복사 — 멱등키는 초안이 만든 값 그대로다.
        assert sd[SEND_KIND_ALIMTALK] == entry
        # 새 주문 sd 의 일정 서명이 이력의 서명과 같다 = 같은 안내가 이미 도달했다.
        assert build_draft_schedule_signature(sd) == entry["draft_schedule"]
        auto_key = build_dedupe_key(int(order_id), sd)
        assert auto_key is not None and auto_key != draft_dedupe
        assert _already_sent(order, auto_key) is True


def test_inherited_history_allows_resend_after_schedule_change(
    client, app, wizard_enabled
) -> None:
    """실측 일정이 바뀌면 서명이 달라져 자동 재발송이 정상 동작해야 한다."""
    from db import db_session
    from models import Order, User

    from foms.services.kakao_alimtalk import _already_sent, build_dedupe_key

    username = "sendhist_submit_reschedule"
    _login(client, app, username)
    key = "new.submit-reschedule"
    _put_draft(client, key, _submit_payload())

    with app.app_context():
        uid = db_session.query(User).filter_by(username=username).one().id
        record_draft_send(
            db_session,
            draft_key=key,
            user_id=uid,
            kind=SEND_KIND_ALIMTALK,
            entry=_alimtalk_entry(
                dedupe_key="alimtalk:measure:draft:x:manual:1",
                message_id="MSG-OK",
                error=None,
                draft_schedule="2026-09-20:14:00",
            ),
        )
        db_session.commit()

    order_id = _submit(client, key)

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        moved = copy.deepcopy(order.structured_data or {})
        moved["schedule"]["measurement"] = {"date": "2026-09-27", "time": "14:00"}
        order.structured_data = moved
        assert _already_sent(order, build_dedupe_key(int(order_id), moved)) is False


def test_submit_inherits_failed_history_without_suppressing(
    client, app, wizard_enabled
) -> None:
    """실패 이력도 그대로 승계되지만 재발송을 막지는 않는다."""
    from db import db_session
    from models import Order, User

    from foms.services.kakao_alimtalk import _already_sent, build_dedupe_key

    username = "sendhist_submit_fail"
    _login(client, app, username)
    key = "new.submit-fail"
    _put_draft(client, key, _submit_payload())

    failed = _alimtalk_entry(
        dedupe_key="alimtalk:measure:draft:x:manual:2",
        message_id=None,
        error="no_valid_phone",
        draft_schedule="2026-09-20:14:00",
    )
    with app.app_context():
        uid = db_session.query(User).filter_by(username=username).one().id
        record_draft_send(
            db_session, draft_key=key, user_id=uid, kind=SEND_KIND_ALIMTALK, entry=failed
        )
        db_session.commit()

    order_id = _submit(client, key)

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        sd = order.structured_data or {}
        assert sd[SEND_KIND_ALIMTALK] == failed
        assert _already_sent(order, build_dedupe_key(int(order_id), sd)) is False


def test_submit_copies_channel_push_history_unchanged(client, app, wizard_enabled) -> None:
    """채널톡 이력은 무변환 복사된다."""
    from db import db_session
    from models import Order, User

    username = "sendhist_submit_channel"
    _login(client, app, username)
    key = "new.submit-channel"
    _put_draft(client, key, _submit_payload())

    entry = _channel_entry()
    with app.app_context():
        uid = db_session.query(User).filter_by(username=username).one().id
        record_draft_send(
            db_session,
            draft_key=key,
            user_id=uid,
            kind=SEND_KIND_CHANNEL_MEASURE,
            entry=entry,
        )
        db_session.commit()

    order_id = _submit(client, key)

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        sd = order.structured_data or {}
        assert sd.get(SEND_KIND_CHANNEL_MEASURE) == entry
        assert SEND_KIND_ALIMTALK not in sd


def test_submit_without_send_history_leaves_structured_data_clean(
    client, app, wizard_enabled
) -> None:
    """이력이 없으면 승계는 아무것도 하지 않는다(빈 키를 심지 않는다)."""
    from db import db_session
    from models import Order

    _login(client, app, "sendhist_submit_none")
    key = "new.submit-none"
    _put_draft(client, key, _submit_payload())
    order_id = _submit(client, key)

    with app.app_context():
        sd = db_session.query(Order).filter_by(id=order_id).one().structured_data or {}
        assert SEND_KIND_ALIMTALK not in sd
        assert SEND_KIND_CHANNEL_MEASURE not in sd


def test_submit_inherits_history_when_no_measure_schedule(client, app, wizard_enabled) -> None:
    """일정이 없으면 서명이 None 이라 억제도 없다 — 이력만 흔적으로 남는다."""
    from db import db_session
    from models import Order, User

    from foms.services.kakao_alimtalk import (
        _already_sent,
        build_dedupe_key,
        build_draft_schedule_signature,
    )

    username = "sendhist_submit_nosched"
    _login(client, app, username)
    key = "new.submit-nosched"
    payload = copy.deepcopy(_submit_payload())
    payload["data"]["schedule"] = {}
    _put_draft(client, key, payload)

    original = "alimtalk:measure:draft:x:manual:3"
    with app.app_context():
        uid = db_session.query(User).filter_by(username=username).one().id
        record_draft_send(
            db_session,
            draft_key=key,
            user_id=uid,
            kind=SEND_KIND_ALIMTALK,
            entry=_alimtalk_entry(
                dedupe_key=original, message_id="MSG-NS", error=None, draft_schedule=None
            ),
        )
        db_session.commit()

    order_id = _submit(client, key)

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        sd = order.structured_data or {}
        assert build_dedupe_key(int(order_id), sd) is None
        assert build_draft_schedule_signature(sd) is None
        assert sd[SEND_KIND_ALIMTALK]["dedupe_key"] == original
        # None == None 으로 잘못 맞아떨어져 억제되면 안 된다.
        assert _already_sent(order, None) is False


def test_submit_deletes_draft_after_inheriting(client, app, wizard_enabled) -> None:
    """승계는 초안 삭제보다 먼저 일어난다 — 순서가 뒤집히면 이력이 통째로 사라진다."""
    from db import db_session
    from models import Order, OrderDraft, User

    username = "sendhist_submit_order"
    _login(client, app, username)
    key = "new.submit-order"
    _put_draft(client, key, _submit_payload())

    with app.app_context():
        uid = db_session.query(User).filter_by(username=username).one().id
        record_draft_send(
            db_session,
            draft_key=key,
            user_id=uid,
            kind=SEND_KIND_ALIMTALK,
            entry=_alimtalk_entry(
                dedupe_key="old", message_id="MSG-D", error=None,
                draft_schedule="2026-09-20:14:00",
            ),
        )
        db_session.commit()

    order_id = _submit(client, key)

    with app.app_context():
        assert (
            db_session.query(OrderDraft).filter_by(draft_key=key).one_or_none() is None
        )
        sd = db_session.query(Order).filter_by(id=order_id).one().structured_data or {}
        assert sd[SEND_KIND_ALIMTALK]["message_id"] == "MSG-D"


# --- D4' 전제: create_order 는 미지의 최상위 sd 키를 보존한다 ----------------------


def test_create_order_preserves_unknown_top_level_structured_keys(app) -> None:
    """승계를 ``create_order`` **앞** dict 병합으로 옮길 수 있는 유일한 근거를 고정한다.

    ``_prepare_structured`` 가 deepcopy 후 가산만 한다는 성질이 깨지면 D4' 승계가
    조용히 증발한다(REV-99 때문에 뒤에서 다시 쓸 수도 없다). 실제 ``create_order`` 를
    태워 새 주문 sd 에 두 이력 키가 살아 있는지 본다.
    """
    from db import db_session
    from models import Order

    from foms.services.orders.order_create import create_order

    user = _make_user("sendhist_prepare_structured")
    alimtalk = _alimtalk_entry(
        dedupe_key="alimtalk:measure:draft:pure:manual:9",
        message_id="MSG-P",
        error=None,
        draft_schedule="2026-09-20:14:00",
    )
    channel = _channel_entry()
    structured = {
        "parties": {"customer": {"name": "병합테스트", "phone": "010-1111-2222"}},
        "schedule": {"measurement": {"date": "2026-09-20", "time": "14:00"}},
        SEND_KIND_ALIMTALK: alimtalk,
        SEND_KIND_CHANNEL_MEASURE: channel,
    }
    order = create_order(
        db_session,
        actor_user_id=user.id,
        owner_user_id=user.id,
        order_fields=dict(
            received_date="2026-09-02",
            received_time="10:00",
            customer_name="병합테스트",
            phone="010-1111-2222",
            address="서울시 강남구",
            product="붙박이장",
            status="RECEIVED",
        ),
        structured_data=structured,
        is_erp_order=True,
    )
    db_session.commit()

    saved = db_session.query(Order).filter_by(id=order.id).one().structured_data or {}
    assert saved[SEND_KIND_ALIMTALK] == alimtalk
    assert saved[SEND_KIND_CHANNEL_MEASURE] == channel


# --- 저장 라우트 보존 계약 -------------------------------------------------------


def test_structured_put_preserves_alimtalk_history_key() -> None:
    """폼 저장이 알림톡 이력을 지우면 승계한 멱등키가 첫 저장에서 사라져 중복 발송이 난다.

    폼 payload 는 이 두 키를 렌더하지도 보내지도 않으므로, 보존 목록에 없으면
    ``o.structured_data = deepcopy(structured_data)`` 통째 대입에서 조용히 증발한다.
    """
    from foms.api.erp_orders_structured import _preserve_operational_structured_state

    old_sd = {
        SEND_KIND_ALIMTALK: {"dedupe_key": "alimtalk:measure:42:2026-09-20:14:00",
                             "message_id": "MSG", "error": None},
        SEND_KIND_CHANNEL_MEASURE: {"pushed": True},
        "parties": {"customer": {"name": "고객"}},
    }
    incoming = {"parties": {"customer": {"name": "고객"}}}  # 폼이 실제로 보내는 모양
    _preserve_operational_structured_state(old_sd, incoming)

    assert incoming[SEND_KIND_ALIMTALK] == old_sd[SEND_KIND_ALIMTALK]
    assert incoming[SEND_KIND_CHANNEL_MEASURE] == old_sd[SEND_KIND_CHANNEL_MEASURE]


def test_manual_send_still_dispatches_after_inheritance(
    client, app, wizard_enabled, monkeypatch: pytest.MonkeyPatch
) -> None:
    """승계 이력이 있어도 **수동** 발송은 실제로 나가고, 자동 발송만 억제된다.

    수동 라우트는 매번 새 uuid 멱등키를 만들어 키 축을 일부러 비껴간다. 서명 축이
    수동까지 막으면 사용자는 "발송됨"을 보는데 고객에게는 아무것도 가지 않는다.
    """
    from db import db_session
    from models import Order, User

    from foms.services import kakao_alimtalk as ka

    username = "sendhist_manual_after_inherit"
    _login(client, app, username)
    key = "new.submit-manual"
    _put_draft(client, key, _submit_payload())

    with app.app_context():
        uid = db_session.query(User).filter_by(username=username).one().id
        record_draft_send(
            db_session,
            draft_key=key,
            user_id=uid,
            kind=SEND_KIND_ALIMTALK,
            entry=_alimtalk_entry(
                dedupe_key="alimtalk:measure:draft:x:manual:4",
                message_id="MSG-OK",
                error=None,
                draft_schedule="2026-09-20:14:00",
            ),
        )
        db_session.commit()

    order_id = _submit(client, key)

    calls: list[dict] = []

    def _fake_dispatch(sd):
        calls.append(sd)
        return "MSG-NEW", None

    monkeypatch.setattr(ka, "_dispatch", _fake_dispatch)
    monkeypatch.setattr(ka, "_ineligible_reason", lambda order, sd: None)

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()

        auto = ka.send_alimtalk_in_session(
            db_session, order, dedupe_key="alimtalk:measure:auto:new"
        )
        assert auto == {"sent": True, "error": None}
        assert calls == []  # 자동은 서명 축에서 억제

        manual = ka.send_alimtalk_in_session(
            db_session,
            order,
            manual_by=uid,
            dedupe_key=f"alimtalk:measure:{order_id}:manual:zzz",
        )
        assert manual == {"sent": True, "error": None}
        assert len(calls) == 1  # 수동은 실제로 나갔다
        db_session.rollback()
