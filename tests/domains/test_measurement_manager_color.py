"""실측 한눈 목록 담당자 색 띠 + 번호(V1, 2026-09-24) 계약.

- 색 칸 배정: 영업팀(SALES·MEASURE 표기) 활성 사용자 id 순위 % 8 + 1 — 8명까지 안 겹친다.
  명부 밖 이름은 crc32 예비, 담당 없음은 0.
- 묶음·탭은 같은 data-mgr-color·번호를 단다(번호 = 오늘 목록에서 담당이 처음 나온 순서).
- CSS 는 덧붙이기만(8칸 정의), 칸 0 은 규칙 없음, 시간 칩 색은 안 건드린다.
"""

from __future__ import annotations

import random
import re
import zlib
from pathlib import Path

from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.measurement.manager_color import (
    MANAGER_COLOR_SLOT_COUNT,
    build_manager_color_slots,
    load_manager_color_slots,
    manager_color_slot,
)
from foms.services.measurement.visit_check import build_measurement_glance_groups
from models import User
from tests.domains.test_measurement_mobile_glance import _get, _glance, _prepare, _seed_three

ROOT = Path(__file__).resolve().parents[2]
GLANCE_CSS = "static/css/contexts/measurement/measurement-mobile-glance.css"
MOBILE_LIST = "templates/measurement/partials/mobile_list.html"
APPEND_MARKER = "/* ══ 담당자 색 띠 + 번호(V1"

PALETTE = {
    1: "#be123c", 2: "#a21caf", 3: "#7e22ce", 4: "#0f766e",
    5: "#4d7c0f", 6: "#713f12", 7: "#7a5245", 8: "#475569",
}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")


# ------------------------------------------------------------ A. 칸 배정(순수 함수)

def test_slots_follow_sales_roster_id_order_and_are_stable():
    users = [(30, "박영업", "SALES"), (10, "김영업", "SALES"), (20, "이영업", "MEASURE"),
             (15, "회계", "ACCOUNTING"), (25, "최영업", " sales ")]
    slots = build_manager_color_slots(users)
    assert slots == {"김영업": 1, "이영업": 2, "최영업": 3, "박영업": 4}
    shuffled = users[:]
    random.Random(7).shuffle(shuffled)
    assert build_manager_color_slots(shuffled) == slots, "입력 순서와 무관(id 순위)"


def test_no_collision_up_to_eight_then_wraps():
    users = [(i, f"영업{i}", "SALES") for i in range(1, 10)]
    slots = build_manager_color_slots(users)
    first_eight = [slots[f"영업{i}"] for i in range(1, 9)]
    assert sorted(first_eight) == list(range(1, MANAGER_COLOR_SLOT_COUNT + 1))
    assert slots["영업9"] == 1, "9번째는 칸이 모자라 1로 돈다(번호가 구분자)"


def test_duplicate_name_keeps_first_and_key_is_trim_lower():
    slots = build_manager_color_slots([(1, " Kim ", "SALES"), (2, "kim", "SALES"), (3, "Lee", "SALES")])
    assert slots == {"kim": 1, "lee": 2}
    assert manager_color_slot("  KIM", slots) == 1


def test_unknown_name_falls_back_to_stable_crc32_and_unassigned_is_zero():
    slots = {"김영업": 1}
    expected = zlib.crc32("자유입력".encode("utf-8")) % MANAGER_COLOR_SLOT_COUNT + 1
    assert manager_color_slot("자유입력", slots) == expected
    assert manager_color_slot("자유입력", None) == expected
    for empty in ("", "-", "  ", None):
        assert manager_color_slot(empty, slots) == 0


def test_glance_groups_carry_color_slot_and_order_no():
    rows = [
        {"id": 1, "manager_name": "최진호"},
        {"id": 2, "manager_name": "김도윤"},
        {"id": 3, "manager_name": ""},
        {"id": 4, "manager_name": "최진호"},
    ]
    groups = build_measurement_glance_groups(rows, {"최진호": 5, "김도윤": 2})
    assert [(g["manager_name"], g["color_slot"], g["order_no"]) for g in groups] == [
        ("최진호", 5, 1), ("김도윤", 2, 2), ("담당 미정", 0, 0), ("최진호", 5, 1),
    ]


def test_load_manager_color_slots_is_one_query(app):
    with app.app_context():
        for i in range(5):
            db_session.add(User(username=f"mgr_color_q{i}", password=generate_password_hash("x"),
                                role="STAFF", team="SALES", name=f"색담당{i}", is_active=True))
        db_session.add(User(username="mgr_color_off", password=generate_password_hash("x"),
                            role="STAFF", team="SALES", name="퇴사자", is_active=False))
        db_session.commit()
        counter = {"n": 0}

        def _before(*_a, **_k):
            counter["n"] += 1

        event.listen(engine, "before_cursor_execute", _before)
        try:
            slots = load_manager_color_slots(db_session)
        finally:
            event.remove(engine, "before_cursor_execute", _before)
        assert counter["n"] == 1
        assert "퇴사자" not in slots
        got = [slots[f"색담당{i}"] for i in range(5)]
        assert got == sorted(got) and len(set(got)) == 5


# ------------------------------------------------------------ B. HTTP 렌더

def _tag(glance: str, pattern: str) -> str:
    m = re.search(pattern, glance)
    assert m, pattern
    return m.group(0)


def test_render_groups_and_tabs_share_color_and_number(client, monkeypatch):
    today = _prepare(client, monkeypatch)
    for uname, team in (("김도윤", "SALES"), ("최진호", "MEASURE")):
        db_session.add(User(username=f"mc_{uname}", password=generate_password_hash("x"),
                            role="STAFF", team=team, name=uname, is_active=True))
    db_session.commit()
    _seed_three(today)
    expected = load_manager_color_slots(db_session)
    glance = _glance(_get(client))

    seen = {}
    for name in ("최진호", "김도윤"):
        grp = _tag(glance, r'<div class="foms-meas-glance__grp[^"]*" data-meas-glance-grp="%s"[^>]*>' % name)
        tab = _tag(glance, r'<button[^>]*data-meas-glance-tab="%s"[^>]*>' % name)
        g_slot = re.search(r'data-mgr-color="(\d)"', grp).group(1)
        t_slot = re.search(r'data-mgr-color="(\d)"', tab).group(1)
        assert g_slot == t_slot == str(expected[name])
        seen[name] = g_slot
        # 번호 칸: 탭과 띠에 같은 숫자
        g_no = re.search(r'data-meas-glance-grp="%s".*?foms-meas-glance__mno" aria-hidden="true">(\d+)<' % name,
                         glance, re.S).group(1)
        t_no = re.search(r'data-meas-glance-tab="%s"[^>]*>\s*<span class="foms-meas-glance__tab-n">'
                         r'<span class="foms-meas-glance__mno" aria-hidden="true">(\d+)<' % name, glance).group(1)
        assert g_no == t_no
    assert seen["최진호"] != seen["김도윤"], "같은 날 두 담당은 다른 색"
    nos = re.findall(r'<button[^>]*data-meas-glance-tab="[^"]+"[^>]*>\s*<span class="foms-meas-glance__tab-n">'
                     r'<span class="foms-meas-glance__mno" aria-hidden="true">(\d+)<', glance)
    assert nos == ["1", "2"], "번호 = 오늘 탭 순서"
    all_tab = _tag(glance, r'<button[^>]*data-meas-glance-tab=""[^>]*>')
    assert "data-mgr-color" not in all_tab


def test_unassigned_group_has_slot_zero_and_no_number(client, monkeypatch):
    from tests.domains.test_measurement_mobile_glance import _add_order

    today = _prepare(client, monkeypatch)
    _add_order(today, customer="미정고객", manager="", phone=None)
    glance = _glance(_get(client))
    grp = _tag(glance, r'<div class="foms-meas-glance__grp[^"]*" data-meas-glance-grp="담당 미정"[^>]*>')
    assert 'data-mgr-color="0"' in grp
    assert "foms-meas-glance__mno" not in glance


# ------------------------------------------------------------ C. 템플릿·CSS 계약

def test_template_marks_groups_and_tabs_without_inline_style():
    tpl = _read(MOBILE_LIST)
    assert 'data-mgr-color="{{ t.slot }}"' in tpl
    assert 'data-mgr-color="{{ g.color_slot|default(0) }}"' in tpl
    assert tpl.count('class="foms-meas-glance__mno" aria-hidden="true"') == 2
    assert "style=" not in tpl


def test_css_defines_eight_slots_appended_at_end():
    css = _read(GLANCE_CSS)
    assert css.count(APPEND_MARKER) == 1
    head, added = css.split(APPEND_MARKER, 1)
    assert "data-mgr-color" not in head, "기존 규칙은 그대로 — 끝에 덧붙이기만"
    for n, hex_ in PALETTE.items():
        assert re.search(r'\[data-mgr-color="%d"\] \{ --mgr: %s;' % (n, hex_), added), n
    assert '[data-mgr-color="0"] {' not in added and '[data-mgr-color="9"]' not in added
    assert "foms-meas-glance__time" not in added, "시간 칩 색은 건드리지 않는다"
    assert "box-shadow: inset 5px 0 0 var(--mgr);" in added
    assert "box-shadow: inset 0 -4px 0 var(--mgr);" in added
    assert "margin-top: 12px;" in added
    assert "::-webkit-progress-value" in added


def test_unknown_manager_takes_free_slot_not_colliding_with_roster():
    """명부 밖 이름(외주 등)은 그날 쓰이지 않은 칸을 받는다 — 명부 담당과 같은 색이 되지 않는다."""
    from foms.services.measurement.visit_check import build_measurement_glance_groups

    slots = {"김영업": 1, "이영업": 2}
    rows = [
        {"manager_name": "김영업", "structured_data": {}},
        {"manager_name": "외주실측팀", "structured_data": {}},
        {"manager_name": "이영업", "structured_data": {}},
    ]
    groups = build_measurement_glance_groups(rows, color_slots=slots)
    by_name = {g["manager_name"]: g["color_slot"] for g in groups}
    assert by_name["김영업"] == 1 and by_name["이영업"] == 2
    assert by_name["외주실측팀"] not in (1, 2) and by_name["외주실측팀"] >= 1
