"""새 회사 지식 화면 틀(설계서 2026-11-14-foms-graft 5.2 · 5.5) — 스위치 끔은 옛 화면 그대로, 켬은 혼자 서는 새 틀.

- 끔(처음 값 · 다른 사람만 켬): ``brain/index.html`` · ``brain/item.html`` · ``brain/ask.html`` 이 그대로 그려진다.
- 켬: 탭마다 그 화면 템플릿 하나(5.2 표) · 위 줄 · 본문 자리 · 폰 아래 탭 · 인라인 스타일 0 · 스크립트는 defer + 내용 지문 핀 ·
  Bootstrap · erp-pro.css · 전역 메뉴를 싣지 않음 · CSRF · 긴급 빨간 창 · 공지 확인 창(사용자 결정 #7).
- 승인 대기 수 고침 주소(``data-badge-url``)는 ``actions`` 스위치가 켜진 사람에게만.
합성 계정 · 합성 항목만(``tests.support.brain_screen_support``).
"""

from __future__ import annotations

import re
from contextlib import contextmanager

import pytest
from flask import template_rendered

from pathlib import Path

from jinja2 import ChoiceLoader, DictLoader

from db import db_session
from foms.services.graft_flags import FLAGS
from tests.support.brain_screen_support import world


@pytest.fixture
def ids(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    return {name: user.id for name, user in world(db_session).items()}


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _switch(monkeypatch, short, cohort):
    monkeypatch.setenv(f"{FLAGS[short]}_ENABLED", "1")
    monkeypatch.setenv(f"{FLAGS[short]}_COHORT", str(cohort))


@contextmanager
def _rendered(app):
    names: list[str] = []

    def record(sender, template, context, **extra):
        names.append(template.name)

    template_rendered.connect(record, app)
    try:
        yield names
    finally:
        template_rendered.disconnect(record, app)


def _get(app, client, path):
    with _rendered(app) as names:
        resp = client.get(path)
    return resp, resp.get_data(as_text=True), names


ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "templates/brain/ds/layout.html"
LAYOUT_HEAD = ROOT / "templates/partials/shared/layout_head.html"
SHELL_CSS = ROOT / "static/css/contexts/brain/ds/brain-ds-shell.css"
SHELL_JS = ROOT / "static/js/brain/ds/ds-shell.js"

OLD = {"/brain?tab=search": "brain/index.html", "/brain?tab=agents": "brain/index.html",
       "/brain/items/common/door": "brain/item.html", "/brain/ask": "brain/ask.html"}
NEW = {"/brain?tab=inbox": ("brain/ds/inbox.html", "inbox"), "/brain?tab=recheck": ("brain/ds/inbox.html", "inbox"),
       "/brain?tab=releases": ("brain/ds/inbox.html", "inbox"), "/brain?tab=search": ("brain/ds/search.html", "search"),
       "/brain?tab=table": ("brain/ds/search.html", "search"), "/brain?tab=onto": ("brain/ds/onto.html", "onto"),
       "/brain?tab=map": ("brain/ds/onto.html", "onto"), "/brain?tab=ask": ("brain/ds/ask.html", "ask"),
       "/brain?tab=agents": ("brain/ds/agents.html", "agents"), "/brain?tab=nope": ("brain/ds/search.html", "search"),
       "/brain/items/common/door": ("brain/ds/item.html", "search"), "/brain/ask": ("brain/ds/ask.html", "ask")}


@pytest.mark.parametrize("cohort", [None, "999999"])
def test_switch_off_or_someone_else_draws_the_old_screens(app, ids, monkeypatch, cohort):
    if cohort:
        _switch(monkeypatch, "brain_ui", cohort)
    client = _client(app, ids["admin"])
    for path, template in OLD.items():
        resp, body, names = _get(app, client, path)
        assert resp.status_code == 200 and names[0] == template, (path, names)
        assert "data-ds-shell" not in body and not any(n.startswith("brain/ds/") for n in names)
    _resp, body, _names = _get(app, client, "/brain?tab=agents")
    assert 'data-start-tab="search"' in body  # 옛 화면은 agents 탭을 모른다 — 지금처럼 찾기


def test_switch_on_draws_one_template_per_tab(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui", ids["admin"])
    client = _client(app, ids["admin"])
    for path, (template, section) in NEW.items():
        resp, body, names = _get(app, client, path)
        assert resp.status_code == 200 and names[0] == template, (path, names)
        assert "brain/index.html" not in names and "admin/layout.html" not in names
        assert f'data-ds-section="{section}"' in body, path
        current = re.findall(r'<a [^>]*data-ds-tab="([a-z]+)"[^>]*aria-current="page"', body)
        assert current and set(current) == {section}, (path, current)


def test_new_frame_has_its_places_and_no_global_bundle(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui", "all")
    resp, body, names = _get(app, _client(app, ids["admin"]), "/brain?tab=inbox")
    assert resp.status_code == 200 and names == ["brain/ds/inbox.html"]
    assert body.lstrip().startswith("<!DOCTYPE html>")
    assert '<div class="f-app f-shell fb-shell" data-ds-shell' in body
    assert '<nav class="f-navbar fb-navbar" aria-label="위 줄">' in body
    assert '<nav class="f-side fb-pc-only" aria-label="승인 대기 길잡이">' in body  # 왼쪽 길잡이(inbox 보기 셋)
    assert 'data-ds-main' in body and '<nav class="fb-tabbar" aria-label="아래 탭" data-ds-tabbar>' in body
    tabbar = body[body.index("data-ds-tabbar"):body.index("data-ds-me-panel")]
    assert re.findall(r'data-ds-tab="([a-z]+)"', tabbar) == ["inbox", "search", "ask"] and "data-ds-me-toggle" in tabbar
    assert re.findall(r'data-ds-me-link="([a-z]+)"', body) == ["recheck", "releases"]  # 폰에서도 다시 확인 · 판으로
    top = body[body.index('aria-label="위 줄"'):body.index("data-ds-main")]
    assert re.findall(r'data-ds-tab="([a-z]+)"', top) == ["inbox", "search", "ask", "onto", "agents"]
    assert 'action="/brain"' in top and 'name="q"' in top and 'value="search"' in top
    assert 'style="' not in body and "onclick" not in body
    for banned in ("bootstrap", "erp-pro.css", "font-awesome", "layout-global-nav", "data-foms-nav-brain"):
        assert banned not in body.lower(), banned
    assert '<meta name="csrf-token"' in body
    for tag in re.findall(r"<script\b[^>]*\bsrc=[^>]*>", body):
        if "https://cdn.socket.io/4.5.4/socket.io.min.js" in tag:  # 긴급 호출 소켓 — 바깥 꾸러미는 integrity 로 핀
            assert " defer" in tag and 'integrity="sha384-' in tag and 'crossorigin="anonymous"' in tag, tag
            continue
        assert " defer" in tag and re.search(r"\?v=[0-9a-f]{12}\"", tag), tag
    assert re.search(r"js/measurement/map-urgent-bridge\.js\?v=[0-9a-f]{12}\" defer", body)  # 머무는 동안 오는 긴급 호출
    for asset in ("css/contexts/brain/ds/foms-ds.css", "css/contexts/brain/ds/brain-ds-shell.css",
                  "js/brain/brain-view.js", "js/brain/brain-dom.js", "js/brain/ds/ds-shell.js"):
        assert re.search(re.escape(asset) + r"\?v=[0-9a-f]{12}\"", body), asset
    assert body.index("js/brain/brain-dom.js") < body.index("js/brain/ds/ds-shell.js")


def test_urgent_red_popup_and_notice_popup_are_wired(app, ids, monkeypatch):
    """긴급 호출 빨간 창 받는 쪽 + 공지 확인 창(사용자 결정 #7 — 새 화면에서도 뜬다)."""
    _switch(monkeypatch, "brain_ui", "all")
    _resp, body, _names = _get(app, _client(app, ids["cs_mgr"]), "/brain?tab=search")
    head = body[:body.index("</head>")]
    shared = re.search(r"foms-urgent-alert\.css'\) \}\}\?v=(\w+)\"", LAYOUT_HEAD.read_text(encoding="utf-8")).group(1)
    assert f"css/components/foms-urgent-alert.css?v={shared}" in head  # 전역 머리와 같은 주소 · 같은 핀(w6-13)
    assert head.index("js/foms/urgent-sound.js") < head.index("js/foms/foms-urgent-alert.js")
    assert "js/foms/notification-write.js" in head
    assert "data-foms-notice-popup" in body and "/api/notices?view=popup" in body
    assert re.search(r"js/foms/foms-notice-popup\.js\?v=[0-9a-f]{12}\" defer", body)
    assert "css/components/foms-notice.css" in body


def test_badge_url_only_when_actions_switch_is_on(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui", "all")
    client = _client(app, ids["admin"])
    _resp, body, _n = _get(app, client, "/brain?tab=inbox")
    assert "data-badge-url" not in body
    assert re.findall(r'data-ds-count="inbox">(\d+)<', body)  # 서버가 센 지식 수
    _switch(monkeypatch, "actions", "all")
    _resp, body, _n = _get(app, client, "/brain?tab=inbox")
    assert 'data-badge-url="/api/erp-actions/badge"' in body


def test_chat_only_staff_sees_only_the_ask_tab(app, ids, monkeypatch):
    from tests.support.brain_chat_support import chat_on

    chat_on(db_session, stage="all")
    _switch(monkeypatch, "brain_ui", "all")
    client = _client(app, ids["cs_staff"])
    first = client.get("/brain")
    assert first.status_code == 302 and first.headers["Location"].endswith("/brain/ask")  # 보내기 규칙 그대로
    resp, body, names = _get(app, client, "/brain/ask")
    assert resp.status_code == 200 and names[0] == "brain/ds/ask.html"
    assert re.findall(r'data-ds-tab="([a-z]+)"', body) == ["ask", "ask"]  # 위 줄 · 아래 탭 모두 물어보기만
    assert 'href="/brain/ask" data-ds-tab="ask"' in body and "data-ds-search" not in body
    assert "data-ds-count" not in body


# ── 점검 2차(11-15) — 공용 틀 ─────────────────────────────────────────────
def test_urgent_alert_css_pin_is_bound_to_the_global_head():
    """w6-13 — 새 틀의 긴급 창 CSS 는 전역 머리와 같은 방식(url_for + 손 핀) · 같은 값. 한쪽만 올리면 여기서 빨개진다."""
    pattern = r"\{\{ url_for\('static', filename='css/components/foms-urgent-alert\.css'\) \}\}\?v=(\w+)\""
    head_pins = re.findall(pattern, LAYOUT_HEAD.read_text(encoding="utf-8"))
    mine = re.findall(pattern, LAYOUT.read_text(encoding="utf-8"))
    assert len(head_pins) == 1 and mine == head_pins


def test_search_box_hint_names_only_what_it_finds():
    """w1-14 — 위 줄 찾기 칸은 지식 · 유형만 찾는다('할 일 이름'은 찾지 않는다)."""
    text = LAYOUT.read_text(encoding="utf-8")
    assert 'placeholder="지식 · 유형"' in text and "할 일 이름" not in text


def test_phone_breakpoint_is_one_rule_for_css_and_scripts():
    """w3-06 — 폰 모습은 991.98px 아래(FOMS 다른 화면과 같다). 틀 CSS 의 폰 @media 와 window.FOMS_DS_SHELL.PHONE_QUERY 가 같은 글.
    44px 규칙(w3-07 · 08)은 그 @media 안에 있고 PC 규칙 밖이다."""
    css = SHELL_CSS.read_text(encoding="utf-8")
    medias = re.findall(r"@media ([^{]+)\{", css)
    assert [m.strip() for m in medias] == ["(max-width: 991.98px)"]
    query = re.search(r"var PHONE_QUERY = '([^']+)';", SHELL_JS.read_text(encoding="utf-8")).group(1)
    assert query == medias[0].strip()
    phone = css[css.index("@media"):]
    for rule in (".fb-shell .f-tab { height: 44px; min-width: 44px;", ".fb-shell a.f-nav-item,", ".fb-shell .f-btn { min-width: 44px; }", ".fb-shell a.f-chip",
                 ".fb-shell .f-breadcrumbs a", ".fb-shell .f-table td a", "details > summary:not(.f-nav-item)"):
        assert rule in phone, rule
    pc = re.sub(r"/\*.*?\*/", "", css[:css.index("@media")], flags=re.S)
    assert "44px" not in pc  # PC(마우스) 크기는 그대로


def test_tabbar_height_is_one_token():
    """w5-04 — 아래 탭 줄 높이는 토큰 하나(--fb-tabbar-h, 목업 4 + 52 + 12)를 줄 · '나' 창 · 바닥 여백이 같이 쓴다."""
    css = SHELL_CSS.read_text(encoding="utf-8")
    assert "--fb-tabbar-h: 68px;" in css
    assert "height: calc(var(--fb-tabbar-h) + env(safe-area-inset-bottom, 0px));" in css
    assert "bottom: calc(var(--fb-tabbar-h) + 8px + env(safe-area-inset-bottom, 0px));" in css
    assert "76px" not in css


def test_phone_header_subtitle_block_renders_inside_the_white_header(app, ids, monkeypatch):
    """w3-22 — 화면이 {% block page_sub %} 를 채우면 위 줄(흰 머리) 안 제목 아래 한 줄. 안 채우면 자리도 없다."""
    _switch(monkeypatch, "brain_ui", "all")
    client = _client(app, ids["admin"])
    _resp, body, _names = _get(app, client, "/brain?tab=search")
    assert "data-ds-nav-sub" not in body
    loader = app.jinja_loader
    child = '{% extends "brain/ds/layout.html" %}{% block page_sub %} 합성 부제 {% endblock %}'
    monkeypatch.setattr(app, "jinja_loader", ChoiceLoader([DictLoader({"brain/ds/search.html": child}), loader]))
    app.jinja_env.loader = app.create_global_jinja_loader()
    app.jinja_env.cache.clear()
    try:
        _resp, body, _names = _get(app, client, "/brain?tab=search")
    finally:
        monkeypatch.setattr(app, "jinja_loader", loader)
        app.jinja_env.loader = app.create_global_jinja_loader()
        app.jinja_env.cache.clear()
    navbar = body[body.index('aria-label="위 줄"'):body.index("</nav>")]
    assert '<span class="fb-nav-sub" data-ds-nav-sub>합성 부제</span>' in navbar
    css = SHELL_CSS.read_text(encoding="utf-8")
    assert re.search(r"\.fb-nav-sub \{ display: none; \}", css)  # PC 에서는 숨는다
    assert ".fb-nav-sub { display: block; flex: 1 0 100%;" in css[css.index("@media"):]
