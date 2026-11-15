"""새 승인 대기 화면 틀(설계서 2026-11-14-foms-graft 5.2 ~ 5.5 · 판 ⑥ · ⑫) — 서버가 그리는 자리 · 길잡이 · 숫자 띠 · 스크립트.

- 스위치 켬 + ADMIN: ``?tab=inbox`` · ``recheck`` · ``releases`` 가 ``brain/ds/inbox.html`` 하나로 200 · 보기마다 고른 길잡이 줄 ·
  인라인 스타일 0 · 스크립트는 defer + 내용 지문 핀 · 옛 화면을 그리는 스크립트(옛 class)는 싣지 않는다(순수 계산만).
- 왼쪽 길잡이: 모두(수) · 지식 고침 ① ~ ⑥ · 점검(다시 확인 수 · 판 · 기록 · 나중에 볼 것) · 폰 안내.
- 숫자 띠: 오늘 결정할 것 · 어림 · AI 할 일 제안(T8 이 수를 알려 주기 전엔 숨김) · 지식 고침.
- T8 약속 자리: 왼쪽 inbox_erp_nav.html · 가운데 inbox_erp_section.html(없으면 빈 자리 — 화면 온전) · 옆 창 · 폰 목록.
- 지식 칸은 회사 지식 화면을 여는 사람(``ds_nav.screen``)에게만 — AI 할 일 제안만 보는 사람(T8)은 자리만 남는다.
- 스위치 끔: 옛 화면 그대로.
합성 계정 · 합성 항목만(``tests.support.brain_screen_support``).
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager

import pytest
from flask import g, render_template, template_rendered
from jinja2 import ChoiceLoader, DictLoader

from db import db_session
from foms.services.graft_flags import FLAGS
from tests.support.brain_screen_support import world

VIEWS = ("inbox", "recheck", "releases")
BIN_NAV = ["names", "content", "decide", "mark", "calc", "rules", "later"]
OLD_DOM_SCRIPTS = ("brain-page.js", "brain-inbox.js", "brain-inbox-card.js", "brain-inbox-bins.js", "brain-inbox-table.js",
                   "brain-inbox-question.js", "brain-recheck.js", "brain-releases.js")


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


def _switch(monkeypatch, short, cohort="all"):
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


def _side(body: str) -> str:
    start = body.index('<nav class="f-side fb-pc-only" aria-label="승인 대기 길잡이">')
    return body[start:body.index("</nav>", start)]


def _scripts(body: str) -> list[str]:
    return re.findall(r'<script src="/static/js/brain/(?:ds/)?([\w-]+\.js)\?v=[0-9a-f]{12}" defer></script>', body)


def test_switch_on_admin_draws_the_three_views_with_their_nav(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    client = _client(app, ids["admin"])
    current = {"inbox": "모두", "recheck": "다시 확인", "releases": "판 · 기록"}
    for view in VIEWS:
        resp, body, names = _get(app, client, f"/brain?tab={view}")
        assert resp.status_code == 200 and names == ["brain/ds/inbox.html"], view
        assert f'data-ds-inbox data-ds-inbox-view="{view}"' in body
        assert 'style="' not in body and "onclick" not in body and "<script>" not in body.split("</head>")[1]
        side = _side(body)
        assert re.findall(r'data-ds-inbox-bin-nav="(\w+)"', side) == BIN_NAV
        assert re.findall(r'class="f-nav-heading">([^<]+)<', side) == ["지식 고침", "점검"]
        picked = re.findall(r'<a class="f-nav-item[^"]*is-selected[^"]*"[^>]*aria-current="page"[^>]*>(?:<span[^>]*></span>)?([^<]+)', side)
        assert picked == [current[view]], (view, picked)
        assert re.search(r'data-ds-nav="inbox">.*?모두<span class="f-count" data-ds-count="inbox">1</span>', side)
        assert re.search(r'다시 확인<span class="f-count" data-ds-count="recheck">2</span>', side)
        assert "휴대폰에서는 칸 하나만 바뀌는 제안만 승인할 수 있어요." in side
        assert re.search(r"css/contexts/brain/ds/brain-ds-inbox\.css\?v=[0-9a-f]{12}", body)


def test_inbox_view_has_the_number_strip_the_knowledge_section_and_the_t8_places(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain?tab=inbox")
    strip = body[body.index("data-ds-inbox-strip"):body.index("data-ds-inbox-erp")]
    assert re.findall(r'<span class="f-small f-muted">([^<]+)</span><span class="f-h4 f-num"', strip) == [
        "오늘 결정할 것", "어림", "AI 할 일 제안", "지식 고침"]
    assert 'data-ds-inbox-stat="today">1<' in strip and 'data-ds-inbox-stat="knowledge">1<' in strip
    assert '<span class="f-row-nw f-gap4" data-ds-inbox-stat-box="actions" hidden>' in strip  # T8 이 알려 주기 전엔 숨김
    assert "어림 = 한 장에 드는 시간 × 장 수" in strip
    assert '<div class="fb-inbox-erp" data-ds-inbox-erp></div>' in body  # T8 조각이 없으면 빈 자리
    assert body.index("data-ds-inbox-erp") < body.index('aria-label="지식 고침" data-ds-inbox-know')
    assert "묶음마다 한 줄 · 열면 그 묶음 카드만 보여요" in body and "data-ds-inbox-bulk hidden" in body
    assert '<aside class="f-aside fb-inbox-aside" aria-label="제안 자세히" data-ds-inbox-aside hidden></aside>' in body
    assert '<ol class="f-col fb-phone-list" data-ds-phone-list></ol>' in body
    assert "폰에서는 한 칸 고침만 승인해요" in body and "PC 에서 볼 것" in body
    _switch(monkeypatch, "actions")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain?tab=inbox")
    assert "폰에서는 한 칸 고침 · ERP 할 일만 승인해요" in body


def test_screen_values_and_scripts_match_each_view(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    client = _client(app, ids["admin"])
    _resp, body, _n = _get(app, client, "/brain?tab=inbox")
    for attr, value in (("data-inbox-url", "/api/brain/inbox"), ("data-proposals-url", "/api/brain/proposals"),
                        ("data-bulk-url", "/api/brain/proposals/bulk-apply"), ("data-recheck-url", "/api/brain/recheck"),
                        ("data-recheck-confirm-url", "/api/brain/recheck/confirm"),
                        ("data-releases-url", "/api/brain/releases"), ("data-page-url", "/brain"),
                        ("data-item-base", "/brain/items/"), ("data-is-admin", "1"), ("data-knowledge-count", "1")):
        assert f'{attr}="{value}"' in body, attr
    display = json.loads(re.search(r'data-display="([^"]+)"', body).group(1).replace("&#34;", '"').replace("&#39;", "'")
                         .replace("&amp;", "&"))
    actions = json.loads(re.search(r'data-actions="([^"]+)"', body).group(1).replace("&#34;", '"').replace("&#39;", "'")
                         .replace("&amp;", "&"))
    assert "types" in display and {"apply", "edit_apply", "reject", "recheck"} <= {a["name"] for a in actions}
    assert set(re.search(r'data-wide-bins="([^"]*)"', body).group(1).split()) == {"names", "mark", "calc", "rules"}
    want = {"inbox": ["brain-view.js", "brain-dom.js", "ds-shell.js", "brain-review-view.js", "ds-inbox-view.js",
                      "ds-inbox-kit.js", "ds-inbox-card.js", "ds-inbox-table.js", "ds-inbox-question.js",
                      "ds-inbox-phone.js", "ds-inbox-act.js", "ds-inbox.js"],
            "recheck": ["brain-view.js", "brain-dom.js", "ds-shell.js", "brain-review-view.js", "ds-inbox-view.js",
                        "ds-inbox-kit.js", "ds-inbox-recheck.js", "ds-inbox.js"],
            "releases": ["brain-view.js", "brain-dom.js", "ds-shell.js", "brain-review-view.js", "ds-inbox-view.js",
                         "ds-inbox-kit.js", "ds-inbox-releases.js", "ds-inbox.js"]}
    for view in VIEWS:
        _resp, body, _n = _get(app, client, f"/brain?tab={view}")
        assert _scripts(body) == want[view], view
        assert not [name for name in OLD_DOM_SCRIPTS if f"/{name}?" in body], view  # 옛 DOM 스크립트는 싣지 않는다
    recheck = _get(app, client, "/brain?tab=recheck")[1]
    assert "data-ds-recheck-line" in recheck and "data-ds-recheck>" in recheck and "data-ds-inbox-know" not in recheck
    releases = _get(app, client, "/brain?tab=releases")[1]
    assert "data-ds-releases>" in releases and "data-ds-releases-prev disabled" in releases


def test_manager_gets_no_admin_flag_and_only_the_name_bin_as_a_table(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    resp, body, names = _get(app, _client(app, ids["cs_mgr"]), "/brain?tab=releases")
    assert resp.status_code == 200 and names == ["brain/ds/inbox.html"]
    assert 'data-is-admin="0"' in body and 'data-wide-bins="names"' in body


def test_open_bin_in_the_address_selects_its_nav_line(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain?tab=inbox&bin=content")
    side = _side(body)
    assert re.search(r'class="f-nav-item fb-nav-item--muted is-selected" href="/brain\?tab=inbox&amp;bin=content"\s+'
                     r'data-ds-inbox-bin-nav="content" aria-current="page">', side)
    assert 'data-ds-nav="inbox"' in side and side.count('aria-current="page"') == 1


@pytest.fixture
def t8_partials(app, monkeypatch):
    """T8 조각 둘을 지어낸 글로 끼운다(실제 파일은 T8 이 만든다) — 끝나면 템플릿 캐시를 비운다."""
    fake = DictLoader({"brain/ds/partials/inbox_erp_nav.html": '<p data-t8-nav="1">T8 길잡이</p>',
                       "brain/ds/partials/inbox_erp_section.html": '<section data-t8-section="1">T8 칸</section>'})
    monkeypatch.setattr(app.jinja_env, "loader", ChoiceLoader([fake, app.jinja_env.loader]))
    if app.jinja_env.cache is not None:
        app.jinja_env.cache.clear()
    yield
    if app.jinja_env.cache is not None:
        app.jinja_env.cache.clear()


def test_t8_partials_land_in_their_places(app, ids, monkeypatch, t8_partials):
    _switch(monkeypatch, "brain_ui")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain?tab=inbox")
    side = _side(body)
    assert side.index("모두") < side.index('data-t8-nav="1"') < side.index("지식 고침")
    erp = body[body.index("data-ds-inbox-erp>"):body.index("</div>", body.index("data-ds-inbox-erp>"))]
    assert 'data-t8-section="1"' in erp
    assert body.index('data-t8-section="1"') < body.index("data-ds-inbox-know")
    recheck = _get(app, _client(app, ids["admin"]), "/brain?tab=recheck")[1]
    assert 'data-t8-nav="1"' in _side(recheck) and 'data-t8-section="1"' not in recheck  # 가운데 칸은 승인 대기 보기만


def test_knowledge_parts_need_the_knowledge_screen(app, ids):
    """AI 할 일 제안만 보는 사람(T8 이 ds_nav.screen=False 로 그린다) — 지식 칸 · 지식 읽기 주소 없이 자리만."""
    from models import User

    admin = db_session.get(User, ids["admin"])
    nav = {"section": "inbox", "screen": False, "inbox_count": None, "tabs": [], "phone_tabs": []}
    with app.test_request_context("/brain?tab=inbox"):
        g.current_user = admin
        body = render_template("brain/ds/inbox.html", page="inbox", ds_nav=nav)
    assert "data-ds-inbox-view=\"inbox\"" in body and "data-inbox-url" not in body and "data-display" not in body
    assert "data-ds-inbox-know" not in body and "data-ds-inbox-bin-nav" not in body and "data-ds-phone-pc-toggle" not in body
    assert "data-ds-inbox-aside hidden" in body and "data-ds-phone-list" in body and "data-ds-inbox-erp" in body
    assert 'data-ds-inbox-stat="knowledge"' not in body and 'style="' not in body


def test_switch_off_keeps_the_old_screen(app, ids, monkeypatch):
    client = _client(app, ids["admin"])
    for view in VIEWS:
        resp, body, names = _get(app, client, f"/brain?tab={view}")
        assert resp.status_code == 200 and names == ["brain/index.html"], view
        assert "data-ds-inbox" not in body and f'data-start-tab="{view}"' in body
        assert "brain-inbox.js" in body and "ds-inbox" not in body
