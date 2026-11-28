"""생산 도면 펜 기록 — 바닥(일꾼 ⓐ): 스위치 · 문 · 계정 칸 둘 · 첨부 분류 '생산' · 표 · 마이그레이션(SQLite 레인).

설계서 ``docs/specs/2026-11-28-production-pen-record_SPEC.md`` §3-1 · §4 · §5 · §9-1 · §9-5 약속 1 · 6(사장님 답 3 · 5 · 13 · 17).
PG 왕복 · 유일 제약은 ``tests/postgres/test_production_pen_record_pg.py``. 이름은 모두 지어낸 값이다(박반장 · 김재단 · 정하늘).

되돌리면 실패: 스위치 기본이 켜짐 · 반장이 칸 없이 씀 · 다른 팀이 칸만 켜고 씀 · 관리자가 칸 없이 씀 · 관리자가 칸을 켜도 비워짐 ·
스위치 꺼진 화면에서 저장하면 칸이 지워짐 · 다른 팀이 '생산'으로 올림 · '생산'이 '실측'으로 풀림 · 템플릿 플래그가 꺼짐에도 참 ·
꺼짐인데 사용자 관리 · 주문 첨부 분류에 새 마크업이 보임.
대조군: 생산팀 · 관리자의 '생산' 올리기는 200 · 칸을 안 건드린 저장은 감사 글 없음 · 꺼짐에서도 서버는 '생산' 분류를 받음.
"""
from __future__ import annotations

import importlib.util
import io
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from db import Base, db_session
from foms.api.files.common import ATTACHMENT_CATEGORIES, normalize_attachment_category, resolve_attachment_category
from foms.services.context_processors import inject_foms_flags
from foms.services.files.upload_authz import category_upload_allowed, parse_upload_folder, validate_upload_key
from foms.services.orders.delete_retention import _assert_fk_coverage, _referring_fks
from foms.services.orders.drawing_key_safety import is_own_order_key
from foms.services.production import pen_record
from foms.services.production import part_constants as pc
from models import Order, OrderAttachment, ProductionDrawingNote, SecurityLog, User
from tests.domains.test_admin_user_production_part import (  # noqa: F401 — _reset_rate_limits 는 자동 fixture
    _admin_client,
    _edit,
    _login,
    _make_user,
    _reset_rate_limits,
    _user,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "versions" / "prodpen_01_pen_record.py"
SWITCH = pen_record.SWITCH_ENV
_STRONG_PW = "Abcdef12"


@pytest.fixture
def switch_on(monkeypatch):
    monkeypatch.setenv(SWITCH, "on")


@pytest.fixture(autouse=True)
def _switch_off_by_default(monkeypatch):
    monkeypatch.delenv(SWITCH, raising=False)


def _person(role="STAFF", team="PRODUCTION", **fields):
    values = dict(role=role, team=team, is_active=True, partner_org_id=None, production_lead=None,
                  production_pen_write=None, production_pen_first=None)
    values.update(fields)
    return SimpleNamespace(**values)


# --------------------------------------------------------------------------- #
# 스위치 · 문(약속 1)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", [None, "", "off", "false", "0"])
def test_switch_is_off_by_default_and_for_off_words(monkeypatch, value):
    if value is not None:
        monkeypatch.setenv(SWITCH, value)
    assert SWITCH == "FOMS_PRODUCTION_PEN_RECORD"
    assert pen_record.enabled() is False


@pytest.mark.parametrize("value", ["on", "true", "1"])
def test_switch_turns_on(monkeypatch, value):
    monkeypatch.setenv(SWITCH, value)
    assert pen_record.enabled() is True


def test_write_gate_four_doors(monkeypatch):
    marked = _person(production_pen_write=True)
    assert pen_record.can_write(marked) is False  # ① 스위치 꺼짐 — 켠 사람도 못 쓴다
    monkeypatch.setenv(SWITCH, "on")
    assert pen_record.can_write(_person(production_lead=True)) is False  # ② 칸 꺼진 반장(3번 답 "따로 정한 사람만")
    assert pen_record.can_write(_person(team="CS", production_pen_write=True)) is False  # ③ 다른 팀이 칸만 켬
    assert pen_record.can_write(_person(team="DRAWING", production_pen_write=True)) is False
    assert pen_record.can_write(marked) is True  # ④ 켠 사람
    assert pen_record.can_write(_person(production_lead=True, production_pen_write=True)) is True


def test_write_gate_still_needs_production_write_right(switch_on):
    for blocked in (_person(production_pen_write=True, is_active=False),
                    _person(production_pen_write=True, role="VIEWER"),
                    _person(production_pen_write=True, partner_org_id=7),
                    None):
        assert pen_record.can_write(blocked) is False


def test_admin_needs_the_box_too(switch_on):
    """13번 답 "관리자도 칸을 켜야 씀" — 관리자는 팀이 무엇이든 칸만 켜면 쓴다."""
    assert pen_record.can_write(_person(role="ADMIN", team="CS")) is False
    assert pen_record.can_write(_person(role="ADMIN", team="CS", production_pen_write=True)) is True
    assert pen_record.can_write(_person(role="ADMIN", team=None, production_pen_write=True)) is True


def test_sees_note_first_is_its_own_box(monkeypatch):
    first = _person(production_pen_first=True)
    assert pen_record.sees_note_first(first) is False  # 스위치 꺼짐
    monkeypatch.setenv(SWITCH, "on")
    assert pen_record.sees_note_first(first) is True
    assert pen_record.sees_note_first(_person(production_pen_write=True)) is False  # 쓰기 칸과 따로(5번 답)
    assert pen_record.sees_note_first(_person(team="CS", production_pen_first=True)) is False
    assert pen_record.sees_note_first(_person(role="ADMIN", team="CS", production_pen_first=True)) is True
    assert pen_record.sees_note_first(None) is False


def test_switch_is_read_in_one_place_only():
    literals = (f'"{SWITCH}"', f"'{SWITCH}'")  # 설명 글의 이름은 세지 않는다 — 읽는 글자(문자열)만
    hits = [p for p in (ROOT / "foms").rglob("*.py") if any(lit in p.read_text(encoding="utf-8") for lit in literals)]
    assert [p.relative_to(ROOT).as_posix() for p in hits] == ["foms/services/production/pen_record.py"]


def test_template_flag_follows_the_switch(app, monkeypatch):
    with app.test_request_context("/"):
        flags = inject_foms_flags()
        assert flags["flag_pen_record"] is False and flags["flag_floor_alarm"] is False
        monkeypatch.setenv(SWITCH, "on")
        assert inject_foms_flags()["flag_pen_record"] is True
        assert inject_foms_flags()["flag_floor_alarm"] is False  # 현장 알람 스위치와 따로


def test_context_processor_stays_inside_the_ratchet():
    src = (ROOT / "foms/services/context_processors.py").read_text(encoding="utf-8")
    assert len(src.splitlines()) < 500 and "**production_template_flags()" in src


# --------------------------------------------------------------------------- #
# 계정 칸 읽기(part_constants)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("team, role, checked, expected", [
    ("PRODUCTION", "STAFF", True, True),
    ("PRODUCTION", "MANAGER", True, True),
    ("CS", "ADMIN", True, True),
    (None, "ADMIN", True, True),
    ("CS", "STAFF", True, None),
    ("SALES", "MANAGER", True, None),
    ("PRODUCTION", "STAFF", False, None),
    ("CS", "ADMIN", False, None),
])
def test_pen_flag_for_keeps_production_and_admin_only(team, role, checked, expected):
    assert pc.pen_flag_for(team, role, checked) is expected


def test_account_readers_check_team_or_admin():
    assert pc.account_pen_write(_person(production_pen_write=True)) is True
    assert pc.account_pen_write(_person(team="CS", production_pen_write=True)) is False  # 팀을 바꿨는데 값이 남은 행
    assert pc.account_pen_first(_person(role="ADMIN", team="CS", production_pen_first=True)) is True
    assert pc.account_pen_write(_person()) is False and pc.account_pen_write(None) is False
    # 반장 칸 동작은 그대로다 — 관리자 예외는 펜 칸에만
    assert pc.production_lead_for_team("CS", True) is None
    assert pc.account_production_lead(_person(role="ADMIN", team="CS", production_lead=True)) is False


# --------------------------------------------------------------------------- #
# 사용자 관리 — 추가 · 고치기 · 비움 · 감사 · 화면
# --------------------------------------------------------------------------- #
def _pen(uid):
    user = _user(uid)
    return user.production_pen_write, user.production_pen_first


def test_edit_saves_both_boxes_and_other_team_clears_them(app, switch_on):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    shown = {"production_pen_fields": "1"}
    assert _edit(admin, uid, **shown, production_pen_write="on").status_code == 302
    assert _pen(uid) == (True, None)
    assert _edit(admin, uid, **shown, production_pen_write="on", production_pen_first="on").status_code == 302
    assert _pen(uid) == (True, True)
    assert _edit(admin, uid, **shown).status_code == 302  # 체크를 끄면 비운다
    assert _pen(uid) == (None, None)
    assert _edit(admin, uid, **shown, production_pen_write="on", production_pen_first="on").status_code == 302
    assert _edit(admin, uid, **shown, team="CS", production_pen_write="on", production_pen_first="on").status_code == 302
    assert _pen(uid) == (None, None)  # 생산팀이 아니면 비운다


def test_admin_account_keeps_the_boxes(app, switch_on):
    admin = _admin_client(app)
    uid = _make_user(role="ADMIN", team="CS")
    shown = {"production_pen_fields": "1"}
    assert _edit(admin, uid, **shown, production_pen_write="on", production_pen_first="on").status_code == 302
    assert _pen(uid) == (True, True)
    assert _user(uid).production_lead is None
    assert _edit(admin, uid, **shown, production_pen_write="on", production_lead="on").status_code == 302
    assert (_pen(uid), _user(uid).production_lead) == ((True, None), None)  # 반장 칸은 지금처럼 관리자에게 안 남는다
    assert _edit(admin, uid, **shown, role="STAFF", production_pen_write="on").status_code == 302
    assert _pen(uid) == (None, None)  # 관리자에서 내리면(다른 팀 STAFF) 비운다


def test_form_without_the_boxes_keeps_values(app, switch_on, monkeypatch):
    """스위치가 꺼진 화면(칸 묶음 · 표지 없음)에서 저장해도 칸을 지우지 않는다 — 팀을 바꾸면 같은 규칙으로 비운다."""
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    assert _edit(admin, uid, production_pen_fields="1", production_pen_write="on", production_pen_first="on").status_code == 302
    monkeypatch.delenv(SWITCH)
    assert _edit(admin, uid, name="이름만").status_code == 302
    assert _pen(uid) == (True, True)
    assert _edit(admin, uid, team="CS").status_code == 302
    assert _pen(uid) == (None, None)


def test_add_user_saves_boxes_for_production_and_admin_only(app, switch_on):
    admin = _admin_client(app)
    base = {"password": _STRONG_PW, "name": "새 사람", "production_pen_fields": "1",
            "production_pen_write": "on", "production_pen_first": "on"}
    for username, role, team in (("pen_new_prod", "STAFF", "PRODUCTION"), ("pen_new_cs", "STAFF", "CS"),
                                 ("pen_new_admin", "ADMIN", "CS")):
        resp = admin.post("/admin/users/add", data={**base, "username": username, "role": role, "team": team})
        assert resp.status_code == 302
    plain = {k: v for k, v in base.items() if not k.startswith("production_pen_w") and k != "production_pen_first"}
    assert admin.post("/admin/users/add", data={**plain, "username": "pen_new_plain", "role": "STAFF",
                                                "team": "PRODUCTION"}).status_code == 302
    db_session.remove()
    got = {u.username: (u.production_pen_write, u.production_pen_first)
           for u in db_session.query(User).filter(User.username.like("pen_new_%"))}
    assert got == {"pen_new_prod": (True, True), "pen_new_cs": (None, None), "pen_new_admin": (True, True),
                   "pen_new_plain": (None, None)}


def test_approve_keeps_pending_user_boxes_empty(app):
    admin = _admin_client(app)
    pending = User(username="pen_pend", password="x", name="정하늘", role="VIEWER", team="PRODUCTION", is_active=True,
                   approval_status="PENDING")
    db_session.add(pending)
    db_session.commit()
    assert admin.post(f"/admin/users/approve/{pending.id}", data={"role": "STAFF", "team": "PRODUCTION"}).status_code == 302
    saved = _user(pending.id)
    assert (saved.approval_status, saved.production_pen_write, saved.production_pen_first) == ("ACTIVE", None, None)


def test_audit_says_boxes_turned_on_and_off(app, switch_on):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    shown = {"production_pen_fields": "1"}
    assert _edit(admin, uid, **shown, production_pen_write="on").status_code == 302
    assert _edit(admin, uid, **shown, production_pen_write="on", production_pen_first="on").status_code == 302
    assert _edit(admin, uid, **shown).status_code == 302
    assert _edit(admin, uid, **shown, name="이름만").status_code == 302  # 대조군: 칸 그대로면 칸 글 없음
    db_session.remove()
    rows = (db_session.query(SecurityLog).filter(SecurityLog.action == "USER_UPDATE", SecurityLog.target_id == uid)
            .order_by(SecurityLog.id).all())
    assert [r.message for r in rows] == [
        f"사용자 #{uid} 수정: 펜 기록 쓰기 끔 → 켬",
        f"사용자 #{uid} 수정: 생산 기록 먼저 보기 끔 → 켬",
        f"사용자 #{uid} 수정: 펜 기록 쓰기 켬 → 끔, 생산 기록 먼저 보기 켬 → 끔",
        f"사용자 #{uid} 정보 수정",
    ]
    assert rows[0].detail["changes"] == {"production_pen_write": {"from": False, "to": True}}


def test_forms_show_boxes_only_when_switch_is_on(app, monkeypatch):
    admin = _admin_client(app)
    uid = _make_user(team="PRODUCTION")
    off_edit = admin.get(f"/admin/users/edit/{uid}").get_data(as_text=True)
    off_add = admin.get("/admin/users/add").get_data(as_text=True)
    for html in (off_edit, off_add):  # 꺼짐 = 새 마크업 0
        assert "production_pen" not in html and "펜 기록" not in html and "data-production-lead-field" in html
    monkeypatch.setenv(SWITCH, "on")
    assert _edit(admin, uid, production_pen_fields="1", production_pen_write="on").status_code == 302
    edit = admin.get(f"/admin/users/edit/{uid}").get_data(as_text=True)
    add = admin.get("/admin/users/add").get_data(as_text=True)
    assert 'name="production_pen_write" checked>' in edit and 'name="production_pen_first">' in edit
    assert 'name="production_pen_write">' in add and 'name="production_pen_first">' in add
    for html in (edit, add):
        assert '<input type="hidden" name="production_pen_fields" value="1">' in html
        assert "켠 사람만 도면에 펜으로 적을 수 있어요." in html and "켠 사람은 생산 기록이 든 도면이 먼저 보여요." in html


def test_admin_templates_have_no_inline_style_for_pen_boxes():
    for name in ("add_user.html", "edit_user.html"):
        src = (ROOT / "templates/auth" / name).read_text(encoding="utf-8")
        block = src[src.index("{% if flag_pen_record %}"):][:1600]
        block = block[:block.index("{% endif %}", block.index("production_pen_first"))]
        assert "style=" not in block and block.count("data-production-pen-field") == 2, name


# --------------------------------------------------------------------------- #
# 첨부 분류 '생산'(§5)
# --------------------------------------------------------------------------- #
def test_category_normalizes_and_folder_resolves():
    assert "production" in ATTACHMENT_CATEGORIES
    assert normalize_attachment_category(" Production ") == "production"
    assert resolve_attachment_category("orders/12/production", None) == "production"
    assert resolve_attachment_category("", "production") == "production"
    ok, order_id, folder, category, _err = parse_upload_folder("orders/12/production")
    assert (ok, order_id, folder, category) == (True, 12, "orders/12/production", "production")
    assert validate_upload_key("orders/12/production/ab_d.png", 12)[:2] == (True, "production")
    # 지우는 길: 자기 주문의 '생산' 그림도 "자기 주문 폴더"다(안 넣으면 저장소에서 영영 안 지워진다)
    assert is_own_order_key(12, "orders/12/production/ab_d.png") is True
    assert is_own_order_key(12, "orders/13/production/ab_d.png") is False


def test_upload_ticket_key_lands_in_production_folder():
    from foms.services.orders.upload_ticket import _derive_object_key

    assert _derive_object_key(5, "production", "a.png").startswith("orders/5/production/")


def test_category_policy_is_production_write():
    assert category_upload_allowed(_person(), "production") is True
    assert category_upload_allowed(_person(role="ADMIN", team="CS"), "production") is True
    for other in (_person(team="CS"), _person(team="SALES"), _person(team="DRAWING"), _person(team="CONSTRUCTION"),
                  _person(role="VIEWER"), None):
        assert category_upload_allowed(other, "production") is False
    assert category_upload_allowed(_person(team="CS"), "measurement") is True  # 대조군: 다른 분류는 그대로


def _order() -> Order:
    order = Order(received_date=date.today().strftime("%Y-%m-%d"), customer_name="정하늘", phone="010-0000-0000",
                  address="가짜시", product="붙박이장", status="PRODUCTION", is_erp_order=True,
                  structured_data={"workflow": {"stage": "PRODUCTION"}})
    db_session.add(order)
    db_session.commit()
    return order


def _upload(client, order_id: int, category: str = "production"):
    return client.post(f"/api/orders/{order_id}/attachments",
                       data={"file": (io.BytesIO(b"fake-image-bytes"), "pen.jpg"), "category": category},
                       content_type="multipart/form-data")


@pytest.mark.parametrize("team", ["CS", "SALES", "DRAWING"])
def test_other_team_cannot_upload_as_production(app, team):
    order_id = _order().id
    client = app.test_client()
    _login(client, _make_user(team=team))
    resp = _upload(client, order_id)
    assert resp.status_code == 403 and resp.get_json()["success"] is False
    assert db_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).count() == 0


@pytest.mark.parametrize("role, team", [("STAFF", "PRODUCTION"), ("ADMIN", "CS")])
def test_production_and_admin_can_upload_as_production_even_with_switch_off(app, role, team):
    order_id = _order().id
    client = app.test_client()
    _login(client, _make_user(role=role, team=team))
    resp = _upload(client, order_id)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    saved = db_session.get(OrderAttachment, resp.get_json()["attachment"]["id"])
    assert saved.category == "production"


def test_screen_label_maps_say_production():
    from foms.services import channel_wam_attachments as wam
    from foms.services import erp_mobile_order_display as mobile

    assert wam.CATEGORY_LABELS["production"] == "Production" and wam.CATEGORY_PRIORITY["production"] > wam.CATEGORY_PRIORITY["as"]
    src = Path(mobile.__file__).read_text(encoding="utf-8")
    assert src.count('"production": "생산",') == 2
    shared = (ROOT / "static/js/orders/erp-order-shared.js").read_text(encoding="utf-8")
    assert "production: '생산'" in shared and "c === 'as' || c === 'production') return c;" in shared
    assert "if (!list.length && key === 'production') return '';" in shared  # PC 화면은 빈 '생산' 무리를 안 그린다
    for js in ("static/js/orders/dashboard/erp-dashboard-core.js", "static/js/cs/as-dashboard.js",
               "static/js/construction/dashboard.js"):
        text_ = (ROOT / js).read_text(encoding="utf-8")
        assert "production: { label: '생산', icon: 'fa-pen-nib' }" in text_, js
        assert "c === 'as' || c === 'production') return c;" in text_, js
        assert "key !== 'production' || (__attachmentsByCategory.production || []).length" in text_, js  # 그림이 있을 때만 탭


def test_order_category_select_has_production_only_when_switch_is_on(app, monkeypatch):
    for name in ("erp_order_tab.html", "erp_order_tab_mobile.html"):
        src = (ROOT / "templates/orders/partials" / name).read_text(encoding="utf-8")
        assert '{% if flag_pen_record %}<option value="production">생산</option>{% endif %}' in src, name
    piece = app.jinja_env.from_string('{% if flag_pen_record %}<option value="production">생산</option>{% endif %}')
    with app.test_request_context("/"):
        assert piece.render(**inject_foms_flags()) == ""
        monkeypatch.setenv(SWITCH, "on")
        assert piece.render(**inject_foms_flags()) == '<option value="production">생산</option>'


# --------------------------------------------------------------------------- #
# 표 production_drawing_notes · 계정 칸 모델
# --------------------------------------------------------------------------- #
def _note(order_id: int, **fields) -> ProductionDrawingNote:
    values = dict(order_id=order_id, drawing_key="orders/1/drawing/a.png", objects=[], base_w=1478, base_h=1040)
    values.update(fields)
    return ProductionDrawingNote(**values)


def test_note_table_defaults_and_unique_per_drawing(app):
    order_id = _order().id
    db_session.add(_note(order_id, objects=[{"type": "pen", "points": [1, 2, 3, 4], "stroke": "#e11d1d", "strokeWidth": 5}],
                         updated_by_name="김재단", drawing_no=2, sheet_id="s1"))
    db_session.commit()
    row = db_session.query(ProductionDrawingNote).filter_by(order_id=order_id).one()
    assert (row.version, row.attachment_id, row.objects[0]["type"]) == (1, None, "pen")
    assert row.created_at is not None and row.updated_at is not None
    db_session.add(_note(order_id, drawing_key="orders/1/drawing/b.png"))  # 다른 장은 된다
    db_session.commit()
    db_session.add(_note(order_id))
    with pytest.raises(IntegrityError, match="UNIQUE|unique"):
        db_session.commit()
    db_session.rollback()


def test_note_table_shape_matches_spec():
    table = ProductionDrawingNote.__table__
    uniques = {c.name: tuple(col.name for col in c.columns) for c in table.constraints if c.name and c.name.startswith("uq_")}
    assert uniques == {"uq_production_drawing_notes_order_key": ("order_id", "drawing_key")}
    fks = {fk.parent.name: (fk.column.table.name, (fk.ondelete or "").upper()) for fk in table.foreign_keys}
    assert fks == {"order_id": ("orders", "CASCADE"), "attachment_id": ("order_attachments", "SET NULL"),
                   "updated_by_user_id": ("users", "SET NULL"), "created_by_user_id": ("users", "SET NULL")}
    assert table.c.objects.nullable is False and table.c.version.nullable is False
    assert ("production_drawing_notes", "order_id", "CASCADE") in _referring_fks()
    _assert_fk_coverage()  # 하드 삭제(삭제 보존)가 이 표를 처리한다
    for column in ("production_pen_write", "production_pen_first"):
        col = User.__table__.c[column]
        assert col.nullable is True and col.server_default is None and col.default is None and col.index is not True


# --------------------------------------------------------------------------- #
# 마이그레이션 prodpen_01_pen_record(SQLite 왕복 — PG 는 tests/postgres)
# --------------------------------------------------------------------------- #
def _migration():
    spec = importlib.util.spec_from_file_location("prodpen_01_unit", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_is_the_single_head_on_basic_parts():
    module = _migration()
    assert (module.revision, module.down_revision) == ("prodpen_01_pen_record", "prodpart_03_basic_parts")
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    assert "prodpen_01_pen_record" in {r.revision for r in script.iterate_revisions(heads[0], "base")}
    assert module.UNIQUE == "uq_production_drawing_notes_order_key" and module.TABLE == ProductionDrawingNote.__tablename__


def test_migration_round_trip_on_sqlite():
    module = _migration()
    engine = create_engine("sqlite://")
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        for name in ("users", "orders", "order_attachments"):
            Base.metadata.tables[name].create(conn)
        conn.execute(text("ALTER TABLE users DROP COLUMN production_pen_write"))
        conn.execute(text("ALTER TABLE users DROP COLUMN production_pen_first"))
        before = {c["name"] for c in inspect(conn).get_columns("users")}
        module.upgrade()
        assert {c["name"] for c in inspect(conn).get_columns("users")} == before | {"production_pen_write", "production_pen_first"}
        model_cols = {c.name for c in ProductionDrawingNote.__table__.columns}
        assert {c["name"] for c in inspect(conn).get_columns("production_drawing_notes")} == model_cols
        assert [u["column_names"] for u in inspect(conn).get_unique_constraints("production_drawing_notes")] == [
            ["order_id", "drawing_key"]]
        module.downgrade()
        assert "production_drawing_notes" not in inspect(conn).get_table_names()
        assert {c["name"] for c in inspect(conn).get_columns("users")} == before
