"""ERP add_order 자동저장 엔드포인트 계약.

핵심 불변식:
- 자동저장은 draft를 승격하지 않는다(status='DRAFT', meta.draft=True 유지).
- 내용이 미약하면 서버 draft를 생성하지 않는다(order_id=None).
- GET은 생성하지 않고 복원용 상태만 반환한다.
- discard는 세션 draft를 소프트 삭제한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash


def _login(client, app, username: str = "autosave_user") -> None:
    from db import db_session
    from models import User

    with app.app_context():
        if not db_session.query(User).filter_by(username=username).first():
            db_session.add(
                User(
                    username=username,
                    password=generate_password_hash("admin"),
                    role="ADMIN",
                    team="CS",
                    name="Autosave User",
                )
            )
            db_session.commit()
    client.post(
        "/login",
        data={"username": username, "password": "admin"},
        follow_redirects=True,
    )


def _structured(name: str = "", phone: str = "", address: str = "", items=None) -> dict:
    return {
        "entity_type": "order_structured",
        "schema_version": 1,
        "parties": {"customer": {"name": name, "phone": phone}},
        "site": {"address_full": address, "address_main": address, "address_detail": ""},
        "schedule": {},
        "items": items or [],
    }


def _autosave(client, structured, token="tok-1", **extra):
    body = {"draft_token": token, "structured_data": structured}
    body.update(extra)
    return client.post(
        "/api/orders/erp/draft/autosave",
        data=json.dumps(body),
        content_type="application/json",
    )


def test_autosave_empty_does_not_create_draft(client, app) -> None:
    _login(client, app, "autosave_empty_user")
    resp = _autosave(client, _structured(), token="tok-empty")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["order_id"] is None  # 내용 미약 → 서버 draft 미생성


def test_autosave_meaningful_creates_draft_without_promotion(client, app) -> None:
    from db import db_session
    from models import Order

    _login(client, app, "autosave_meaningful_user")
    resp = _autosave(
        client,
        _structured(name="고명옥", phone="010-1234-5678", address="서울시 강남구"),
        token="tok-meaningful",
        received_date="2026-06-30",
        notes="현장 메모",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    order_id = data["order_id"]
    assert order_id

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        # 승격 금지: draft 상태 그대로.
        assert order.status == "DRAFT"
        assert (order.structured_data or {}).get("meta", {}).get("draft") is True
        assert order.structured_data["parties"]["customer"]["name"] == "고명옥"
        assert order.notes == "현장 메모"


def test_autosave_repeated_reuses_same_draft(client, app) -> None:
    from db import db_session
    from models import Order

    _login(client, app, "autosave_reuse_user")
    first = _autosave(client, _structured(name="첫입력", phone="010-1"), token="tok-reuse")
    second = _autosave(
        client, _structured(name="첫입력 수정", phone="010-1", address="대전"), token="tok-reuse"
    )
    id1 = first.get_json()["order_id"]
    id2 = second.get_json()["order_id"]
    assert id1 and id1 == id2  # 세션 draft 재사용 → 행 폭증 없음

    with app.app_context():
        order = db_session.query(Order).filter_by(id=id1).one()
        # 같은 행을 제자리 갱신: 최신 입력이 반영된다.
        assert order.structured_data["parties"]["customer"]["name"] == "첫입력 수정"
        assert order.structured_data["site"]["address_full"] == "대전"


def test_get_draft_empty_when_none(client, app) -> None:
    _login(client, app, "autosave_get_empty_user")
    resp = client.get("/api/orders/erp/draft?draft_token=tok-none")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["draft"] is None


def test_get_draft_reports_content_for_restore(client, app) -> None:
    _login(client, app, "autosave_get_user")
    _autosave(
        client,
        _structured(name="복원대상", phone="010-9999-0000", address="부산"),
        token="tok-restore",
    )
    resp = client.get("/api/orders/erp/draft?draft_token=tok-restore")
    data = resp.get_json()
    assert data["draft"] is not None
    assert data["draft"]["has_content"] is True
    assert data["draft"]["order_id"]
    # 상대시간 TZ-안전: epoch ms 제공(서버 UTC·브라우저 KST 시차 오표시 방지).
    assert isinstance(data["draft"]["updated_at_ms"], int)


def test_autosave_local_storage_key_scoped_by_user(app) -> None:
    """공유 PC PII 유출 방지: localStorage 키는 user id suffix + legacy key purge."""
    js = (Path(__file__).resolve().parents[2] / "static/js/orders/erp-order-autosave.js").read_text(
        encoding="utf-8"
    )
    add_order = (Path(__file__).resolve().parents[2] / "templates/orders/add_order.html").read_text(
        encoding="utf-8"
    )
    erp_js = (
        Path(__file__).resolve().parents[2] / "templates/orders/partials/erp_order_js.html"
    ).read_text(encoding="utf-8")

    assert 'data-current-user-id="{{ current_user.id if current_user else \'\' }}"' in add_order
    assert "function localStorageKey()" in js
    assert 'LS_KEY_PREFIX + ":u" + uid' in js
    assert "purgeLegacyLocalStorage()" in js
    assert "localStorage.removeItem(LEGACY_LS_KEY)" in js
    assert "erp-order-autosave.js') }}?v=20260630f" in erp_js


def test_autosave_suspends_after_explicit_save() -> None:
    """정상 저장 후 페이지 이탈이 localStorage를 다시 쓰지 않게 _suspended 가드 존재.

    버그: 저장 직후 visibilitychange/beforeunload의 saveLocal이 clearLocal 이후
    내용을 재기록 → 다음 진입 시 정상 저장건이 미저장 복원 배너로 오인.
    """
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-order-autosave.js").read_text(encoding="utf-8")
    assert "var _suspended = false;" in js
    assert "_suspended = true;" in js  # erp:order-saved에서 중단
    # 모든 기록 진입점이 가드.
    for fn in ("function saveLocal()", "function saveServer()", "function saveEditLocal()", "function beaconFlush()"):
        idx = js.index(fn)
        assert "if (_suspended) return;" in js[idx: idx + 200], f"{fn} missing _suspended guard"
    # 재입력 시 해제.
    sidx = js.index("function schedule()")
    assert "_suspended = false;" in js[sidx: sidx + 200]


def test_edit_mode_autosave_wiring() -> None:
    """저장된 주문 편집(edit_order)에도 autosave 작업본+복원이 배선됐는지(JS+템플릿)."""
    root = Path(__file__).resolve().parents[2]
    js = (root / "static/js/orders/erp-order-autosave.js").read_text(encoding="utf-8")
    edit_order = (root / "templates/orders/edit_order.html").read_text(encoding="utf-8")
    # JS: edit 모드 경로 존재.
    assert "function isEditMode()" in js
    assert "function saveEditLocal()" in js
    assert "function editLocalStorageKey()" in js
    assert "maybeOfferEditRestore" in js
    assert '"local-edit"' in js
    # 편집 작업본은 localStorage만(라이브 주문 PUT 금지) — saveServer를 edit에서 호출하지 않음.
    assert "라이브 주문" in js
    # edit_order가 autosave 스크립트를 로드하고 draft 모드를 끈다.
    assert 'erp_order_js.html' in edit_order
    assert "window.__ERP_ORDER_DRAFT_MODE = false" in edit_order


def _consult_default_item() -> dict:
    """ERP 폼 기본 품목 1행: 사용자 미입력, 상담 기본값만 채워진 상태."""
    return {
        "product_name": "",
        "spec": "",
        "price": "",
        "internal": "상담",
        "color": "상담",
        "handle": "상담",
        "option_detail": "상담",
        "misc": "상담",
    }


def test_autosave_consult_defaults_not_meaningful(client, app) -> None:
    """기본 '상담' 품목만 있는 빈 폼은 서버 draft를 만들지 않아야 한다(데이터 유실 RCA).

    color/handle/misc/option_detail 기본값 '상담'을 내용으로 오판하면, 빈 폼 자동저장이
    기존 draft를 덮어써 작성분이 사라진다(production 재현 버그).
    """
    _login(client, app, "autosave_consult_user")
    resp = _autosave(
        client,
        _structured(items=[_consult_default_item()]),
        token="tok-consult",
    )
    assert resp.status_code == 200
    assert resp.get_json()["order_id"] is None  # 상담 기본값은 내용 아님 → draft 미생성


def test_autosave_empty_does_not_overwrite_existing_content(client, app) -> None:
    """핵심 회귀 방어: 내용 있는 draft를 빈 자동저장이 덮어쓰지 못한다."""
    from db import db_session
    from models import Order

    _login(client, app, "autosave_nodowngrade_user")
    # 1) 실제 내용으로 draft 생성.
    created = _autosave(
        client,
        _structured(name="홍길동", phone="010-1111-2222", address="서울시 종로구"),
        token="tok-nodown",
    )
    order_id = created.get_json()["order_id"]
    assert order_id

    # 2) 빈 폼(상담 기본값만) 자동저장 → 덮어쓰기 금지.
    resp = _autosave(
        client,
        _structured(items=[_consult_default_item()]),
        token="tok-nodown",
    )
    body = resp.get_json()
    assert body["success"] is True
    assert body.get("skipped") == "no_downgrade"

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        # 작성분 보존.
        assert order.structured_data["parties"]["customer"]["name"] == "홍길동"
        assert order.structured_data["site"]["address_full"] == "서울시 종로구"


def test_restore_banner_excluded_from_alert_autodismiss(app) -> None:
    """복원 배너는 script.js 5초 자동닫힘에서 제외돼야 한다(bug #1)."""
    root = Path(__file__).resolve().parents[2]
    tab = (root / "templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    script = (root / "static/js/runtime/script.js").read_text(encoding="utf-8")
    assert 'id="erp-restore-banner"' in tab
    assert "data-foms-no-autodismiss" in tab
    assert ".alert:not([data-foms-no-autodismiss])" in script


def test_discard_soft_deletes_draft(client, app) -> None:
    from db import db_session
    from models import Order

    _login(client, app, "autosave_discard_user")
    created = _autosave(
        client, _structured(name="버릴주문", phone="010-5", address="인천"), token="tok-discard"
    )
    order_id = created.get_json()["order_id"]

    discard = client.post(
        "/api/orders/erp/draft/discard",
        data=json.dumps({"draft_token": "tok-discard"}),
        content_type="application/json",
    )
    assert discard.status_code == 200
    assert discard.get_json()["success"] is True

    with app.app_context():
        order = db_session.query(Order).filter_by(id=order_id).one()
        assert order.status == "DELETED"
        assert order.deleted_at

    # 세션 분리 → GET은 다시 None.
    after = client.get("/api/orders/erp/draft?draft_token=tok-discard")
    assert after.get_json()["draft"] is None
