"""작성 중인 초안 목록 — API + 화면 계약 (2026-09-11).

초안은 TTL 이 지나면 조용히 사라지는데(``new.*`` 7일) 목록 라우트가 없어 화면을 한 번
떠난 사용자는 그것을 되찾을 방법이 아예 없었다. 2026-09-02·09-03·09-10 세 건이 그렇게
유실됐고, 09-10 건은 채널톡 발송까지 끝난 뒤였다.

경위: ``docs/plans/2026-09-11-erporder-channel-push-missing-order-ledger.md``
설계: ``docs/plans/2026-09-11-draft-list-and-audit-rollback-spec.md`` T2
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[2]
LIST_URL = "/api/erp/order-draft/list"


@pytest.fixture
def wizard_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")


def _user(app, username: str) -> int:
    from db import db_session
    from models import User

    with app.app_context():
        row = db_session.query(User).filter_by(username=username).first()
        if row is None:
            row = User(
                username=username,
                password=generate_password_hash("admin"),
                role="ADMIN",
                team="CS",
                name=username,
            )
            db_session.add(row)
            db_session.commit()
        return int(row.id)


def _login(client, username: str) -> None:
    client.post(
        "/login",
        data={"username": username, "password": "admin"},
        follow_redirects=True,
    )


def _make_draft(
    app,
    user_id: int,
    draft_key: str,
    *,
    name: str = "이광일",
    address: str = "서울 중구 동호로14길 35",
    step: int = 4,
    expires_in_days: int = 7,
    order_id: int | None = None,
    send_history: dict | None = None,
    updated_shift_minutes: int = 0,
) -> None:
    from db import db_session
    from models import OrderDraft

    now = datetime.datetime.utcnow()
    items = [
        {"product_name": "부엌가구", "attachments": [{"tmp_key": "a"}, {"tmp_key": "b"}]},
        {"product_name": "아일랜드", "attachments": []},
    ]
    with app.app_context():
        db_session.add(
            OrderDraft(
                user_id=user_id,
                order_id=order_id,
                draft_key=draft_key,
                step=step,
                schema_version=1,
                payload={
                    "schema_version": 1,
                    "step": step,
                    "data": {"customer_name": name, "address": address, "items": items},
                },
                send_history=send_history,
                updated_at=now - datetime.timedelta(minutes=updated_shift_minutes),
                expires_at=now + datetime.timedelta(days=expires_in_days),
            )
        )
        db_session.commit()


def _get(client):
    res = client.get(LIST_URL)
    return res, json.loads(res.data.decode("utf-8"))


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
def test_list_returns_own_open_drafts_newest_first(app, client, wizard_enabled):
    uid = _user(app, "draftlist_owner")
    _make_draft(app, uid, "new.older", name="먼저 쓴 건", updated_shift_minutes=30)
    _make_draft(app, uid, "new.newer", name="나중 건", updated_shift_minutes=1)
    _login(client, "draftlist_owner")

    res, body = _get(client)
    assert res.status_code == 200
    assert body["success"] is True
    keys = [row["draft_key"] for row in body["data"]["drafts"]]
    assert keys == ["new.newer", "new.older"], "최신순이 아니다"


def test_list_excludes_other_users_drafts(app, client, wizard_enabled):
    mine = _user(app, "draftlist_mine")
    theirs = _user(app, "draftlist_theirs")
    _make_draft(app, mine, "new.mine")
    _make_draft(app, theirs, "new.theirs")
    _login(client, "draftlist_mine")

    _, body = _get(client)
    keys = [row["draft_key"] for row in body["data"]["drafts"]]
    assert keys == ["new.mine"], "남의 초안이 보인다"


def test_list_excludes_promoted_and_expired(app, client, wizard_enabled):
    from db import db_session
    from models import Order

    uid = _user(app, "draftlist_filters")
    with app.app_context():
        order = Order(
            received_date="2026-09-11",
            customer_name="이미 등록",
            phone="010-0000-0000",
            address="Seoul",
            product="Kitchen",
            status="RECEIVED",
            is_erp_order=True,
            structured_data={},
        )
        db_session.add(order)
        db_session.commit()
        order_id = int(order.id)

    _make_draft(app, uid, "new.alive")
    _make_draft(app, uid, "edit.promoted", order_id=order_id)
    _make_draft(app, uid, "new.expired", expires_in_days=-1)
    _login(client, "draftlist_filters")

    _, body = _get(client)
    keys = [row["draft_key"] for row in body["data"]["drafts"]]
    assert keys == ["new.alive"], f"주문이 된 초안·만료분이 섞였다: {keys}"


def test_row_shape_and_send_badge(app, client, wizard_enabled):
    uid = _user(app, "draftlist_shape")
    _make_draft(
        app,
        uid,
        "new.sent",
        send_history={
            "channeltalk_push_measure_room": {"pushed": True, "sent_at": "2026-09-10T01:40:55"}
        },
    )
    _login(client, "draftlist_shape")

    _, body = _get(client)
    row = body["data"]["drafts"][0]
    assert row["customer_name"] == "이광일"
    assert row["address"] == "서울 중구 동호로14길 35"
    assert row["step"] == 4
    assert row["items_count"] == 2
    assert row["files_count"] == 2, "payload 에 적힌 첨부 수"
    assert row["has_send_history"] is True, "발송했는데 등록 안 한 초안 표시가 없다"
    # 시각 표시는 서버가 KST 로 만들어 보낸다(클라이언트가 naive UTC 를 파싱하면 9시간 밀린다).
    assert row["updated_label"] and len(row["updated_label"]) == 11
    assert isinstance(row["expires_in_days"], int)


def test_draft_without_send_history_has_no_badge(app, client, wizard_enabled):
    """음성 대조군 — 발송 이력이 없으면 배지가 서지 않는다."""
    uid = _user(app, "draftlist_nobadge")
    _make_draft(app, uid, "new.quiet")
    _login(client, "draftlist_nobadge")

    _, body = _get(client)
    assert body["data"]["drafts"][0]["has_send_history"] is False


def test_list_requires_login(app, client, wizard_enabled):
    res = client.get(LIST_URL)
    assert res.status_code in (302, 401), res.status_code


def test_list_is_gated_by_wizard_flag(app, client, monkeypatch):
    """마법사 자격이 없으면 목록도 없다(초안 라우트 5종과 같은 게이트)."""
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "false")
    uid = _user(app, "draftlist_nogate")
    _make_draft(app, uid, "new.hidden")
    _login(client, "draftlist_nogate")

    res = client.get(LIST_URL)
    ok = res.status_code == 200 and json.loads(res.data.decode("utf-8")).get("success") is True
    assert not ok, "마법사 게이트 밖인데 목록이 나왔다"


# --------------------------------------------------------------------------
# 화면
# --------------------------------------------------------------------------
def test_dashboard_registers_assets_with_pins() -> None:
    """CSS 는 대시보드 페이지에, JS 는 셸 스크립트 등록부에.

    ERP 셸은 본문만 조각으로 갈아끼우므로 JS 를 ``dashboard.html`` 의 scripts 블록에 두면
    탭을 옮겨 돌아온 화면에서는 아예 돌지 않는다. ``erp-dashboard-entry.js`` 와 같은
    ``/erp/`` 게이트에 함께 둔다.
    """
    page = (ROOT / "templates/orders/dashboard.html").read_text(encoding="utf-8")
    assert "css/components/foms-draft-resume.css" in page
    css_line = [line for line in page.splitlines() if "foms-draft-resume.css" in line][0]
    assert "?v=20260911a" in css_line
    assert "draft_resume.js" not in page, "조각 교체 경로에서 안 도는 자리에 실렸다"

    # CSS 는 조각(dashboard_main.html)에도 실려야 한다. 셸은 조각 HTML 에서 <link> 를
    # 뽑아 먼저 로드하므로, 전체 페이지에만 있으면 탭 첫 진입에서 스타일 없는 줄이
    # 번쩍인다(tests/domains/test_shell_fragment_css_fouc_audit.py 가 강제).
    fragment = (ROOT / "templates/orders/partials/dashboard_main.html").read_text(
        encoding="utf-8"
    )
    frag_css_line = [
        line for line in fragment.splitlines() if "foms-draft-resume.css" in line
    ][0]
    assert "?v=20260911a" in frag_css_line, "조각과 전체 페이지의 핀이 갈렸다"

    scripts = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(
        encoding="utf-8"
    )
    script_line = [line for line in scripts.splitlines() if "draft_resume.js" in line][0]
    assert "defer" in script_line, "렌더 차단 스크립트 금지(perf G1)"
    assert "?v=20260911a" in script_line
    assert scripts.index("erp-dashboard-entry.js") < scripts.index("draft_resume.js")


def test_placeholder_is_hidden_by_default() -> None:
    bar = (ROOT / "templates/orders/partials/draft_resume_bar.html").read_text(encoding="utf-8")
    assert 'id="foms-draft-resume-bar"' in bar
    assert 'id="foms-draft-resume-sheet"' in bar
    # 0건이면 아무것도 안 보인다 — 서버는 hidden 으로만 그린다.
    assert 'id="foms-draft-resume" hidden' in bar


def test_both_mobile_v2_surfaces_include_the_bar() -> None:
    """타워·큐 **두 분기 모두**에 실려야 한다.

    모바일 홈의 기본 표면은 타워다(``tower_mode = mobile_v2 and not drill and not chunk``,
    foms/web/orders/dashboard.py:433). 처음에 큐 분기에만 넣어 스테이징 실화면에서
    배너가 아예 뜨지 않았다 — 템플릿 파일에 마크업이 있다는 계약만으로는 못 잡힌 결함이라
    두 분기를 이름으로 못박는다.
    """
    include = "orders/partials/draft_resume_bar.html"
    for rel in (
        "templates/orders/partials/dashboard_mobile_tower.html",
        "templates/orders/partials/dashboard_mobile_v2_body.html",
    ):
        surface = (ROOT / rel).read_text(encoding="utf-8")
        assert include in surface, f"{rel} 에 초안 되찾기 줄이 없다"
        # 마크업은 조각 한 곳에만 있어야 한다(복제하면 한쪽만 고치게 된다).
        assert 'id="foms-draft-resume"' not in surface


def test_resume_js_is_safe_and_silent() -> None:
    js = (ROOT / "static/js/foms/draft_resume.js").read_text(encoding="utf-8")
    # 고객명·주소가 그대로 들어오는 자리다 — innerHTML 금지(주석에는 그 단어가 나온다).
    code_lines = [
        line
        for line in js.splitlines()
        if not line.lstrip().startswith(("*", "//", "/*"))
    ]
    assert not any("innerHTML" in line for line in code_lines)
    assert "createTextNode" in js
    # 홈 화면을 막지 않는다(권한 없음·네트워크 실패는 조용히 접는다).
    assert ".catch(function () {" in js
    assert "body.success !== true" in js
    # 0건이면 그리지 않는다.
    assert "if (!drafts.length) {" in js
    assert "/api/erp/order-draft/list" in js
    # 셸 조각 교체 뒤에도 다시 채운다(같은 엘리먼트를 두 번 채우지는 않는다).
    assert "foms:erp-shell-fragment-swapped" in js
    assert "foms:main-content-swapped" in js
    assert "root.fomsDraftResumeBound" in js


def test_resume_css_has_touch_target() -> None:
    css = (ROOT / "static/css/components/foms-draft-resume.css").read_text(encoding="utf-8")
    assert ".foms-draft-resume__bar" in css
    assert css.count("min-height: 44px") >= 2, "터치 영역 기준(44px)이 빠졌다"
