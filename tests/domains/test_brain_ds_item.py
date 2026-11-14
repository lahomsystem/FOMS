"""새 지식 카드 화면(설계서 2026-11-14-foms-graft 5.2 ~ 5.4 · 판 ⑧) — 서버가 그리는 자리 · 옛 스크립트가 쓰는 갈고리 · 스위치.

- 스위치 켬 + ADMIN: ``/brain/items/<키>`` 가 ``brain/ds/item.html`` 로 200 · 인라인 스타일 0 · 스크립트는 defer + 내용 지문 핀.
- 자리: 길 표시 · 머리(유형 · 이름 · 층 · 상태 · 기다리는 수정) · 탭 넷(옛 탭 단추 id 그대로 — 그림 위젯 스크립트가 듣는다,
  뇌 보기는 숨겨 그림) · 속성 표 · 연결된 지식 · 오른쪽 수정 기록 + 제안 단추(액션 이름 · 글은 서버 목록) · 고칠 말 칸.
- 옛 스크립트 갈고리: brain-item-actions.js 의 뿌리 [data-brain-card](data-current · 제안 주소 · 표시 표) · id="brain-card-propose"
  (다시 확인 '틀림 — 고치기' · 미리 보기 [고칠 말 제안]이 오는 자리) · 이웃 지도 · 뇌 보기 partial 은 옛 것 그대로 + brain.css.
- 쓰인 곳: ERP 읽기 스위치가 켜진 사람만 칸 · 주소가 있다. 꺼지면 없다.
- 볼 수 없는 카드 · 없는 카드 · 못 여는 사람은 404 그대로. 스위치 끔: 옛 카드 그대로(brain/item.html).
합성 계정 · 합성 항목만(``tests.support.brain_screen_support``).
"""

from __future__ import annotations

import re
from contextlib import contextmanager

import pytest
from flask import template_rendered

from db import db_session
from foms.services.brain import actions
from foms.services.graft_flags import FLAGS
from tests.support.brain_screen_support import world

SCRIPTS = ["brain-view.js", "brain-dom.js", "ds-shell.js", "brain-review-view.js", "ds-search-view.js", "ds-item.js",
           "brain-item-actions.js", "brain-graph-view.js", "brain-neighbours.js", "brain3d-core.js", "brain3d-tab.js"]


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


def _scripts(body: str) -> list[str]:
    return re.findall(r'<script src="/static/js/brain/(?:ds/)?([\w-]+\.js)\?v=[0-9a-f]{12}" defer></script>', body)


def _between(body: str, start: str, end: str) -> str:
    at = body.index(start)
    return body[at:body.index(end, at)]


def test_switch_on_draws_the_new_card_with_its_places(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    resp, body, names = _get(app, _client(app, ids["admin"]), "/brain/items/common/door")
    assert resp.status_code == 200 and names[0] == "brain/ds/item.html" and "brain/item.html" not in names
    assert 'style="' not in body and "onclick" not in body and "<script>" not in body.split("</head>")[1]
    assert _scripts(body) == SCRIPTS
    assert re.search(r"css/contexts/brain/brain\.css\?v=[0-9a-f]{12}", body)
    assert re.search(r"css/contexts/brain/ds/brain-ds-item\.css\?v=[0-9a-f]{12}", body)
    crumbs = _between(body, '<nav class="f-breadcrumbs" aria-label="길 표시">', "</nav>")
    assert re.findall(r'<a href="([^"]+)">([^<]+)</a>', crumbs) == [("/brain?tab=search", "회사 지식"),
                                                                     ("/brain?tab=table&amp;type=product_line", "제품 라인")]
    assert '<span class="f-current">여닫이 문짝</span>' in crumbs
    assert re.search(r'<h1 class="f-h3">여닫이 문짝</h1>\s*<span class="f-small f-muted">공통 바탕</span>', body)
    assert '<span class="f-tag f-tag-success">사용 중</span>' in body
    assert '<p class="f-large fb-item-text">합성 설명 고친 문짝</p>' in body
    tabs = re.findall(r'<button class="f-tab" id="(brain-card-\w+-btn)"[^>]*data-ds-item-tab="(\w+)"', body)
    assert tabs == [("brain-card-main-btn", "main"), ("brain-card-history-btn", "history"),
                    ("brain-card-neighbours-btn", "neighbours"), ("brain-card-brain3d-btn", "brain3d")]
    assert re.search(r'data-ds-item-tab="brain3d" data-brain-tab-name="brain3d" data-brain3d-tab-item hidden', body)
    panels = re.findall(r'id="(brain-card-\w+)" role="tabpanel"[^>]*data-ds-item-panel="(\w+)"( hidden)?', body)
    assert panels == [("brain-card-main", "main", ""), ("brain-card-history", "history", " hidden"),
                      ("brain-card-neighbours", "neighbours", " hidden"), ("brain-card-brain3d", "brain3d", " hidden")]
    # 그림 위젯은 옛 partial 그대로(card_neighbours.html · card_brain3d.html — 1걸음 목록 · 숨겨 둔 3D 칸)
    assert 'data-brain-nb data-around-url="/api/brain/around"' in body and "data-brain-nb-list" in body
    assert '<div class="brain3d" data-brain3d' in body and 'data-points-url="/api/brain/points"' in body and "그림 읽는 법" in body
    assert not re.search(r"<(?:script|link)[^>]*vendor/(?:cytoscape|three)", body)  # 라이브러리는 탭을 열 때만 import()


def test_glance_props_and_links_are_server_drawn(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain/items/common/fit")
    props = _between(body, '<section class="f-section" aria-label="속성">', "</section>")
    rows = re.findall(r'<th scope="row" class="f-td-nw f-muted">([^<]+)</th>', props)
    assert rows[0] == "조건 꼴"  # 그 유형 속성 틀의 눈에 띄는 칸이 먼저
    assert rows[-11:] == ["브랜드", "쓰는 팀", "확실한 정도", "위험 등급", "유효 기간", "마지막 확인", "다시 볼 날", "비슷한 말", "근거",
                          "볼 수 있는 사람", "쓰인 횟수"]
    assert "유형 '제작 조건' 의 칸" in props and "data-brain-card-more" in props and "자세히 보기" in props
    assert "AI 상담 · 챗봇이 4번 썼어요" in props
    links = _between(body, '<section class="f-section" aria-label="연결된 지식">', "</section>")
    assert re.findall(r'class="f-col f-gap4 brain-link--(\w+)"', links) == ["applies_to", "requires"]
    assert '<a class="f-ellipsis" href="/brain/items/common/door">여닫이 문짝</a>' in links
    assert 'data-ds-item-open="neighbours"' in links
    head = _between(body, "data-ds-item-tags>", "</div>")
    assert "낡음 — 다시 확인할 때" in head and "승인을 기다리는 수정 1개" in head and 'href="/brain?tab=inbox"' in head


def test_aside_is_the_proposal_root_with_server_named_actions(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain/items/common/door")
    aside = _between(body, '<aside class="f-aside fb-item-aside"', "</aside>")
    assert body.count("data-brain-card") == 2  # 뿌리 하나(+ 자세히 보기의 data-brain-card-more)
    for hook in ('data-brain-key="common/door"', 'data-brain-version="2"', 'data-current="{', 'data-display="{',
                 'data-proposals-url="/api/brain/proposals"', 'data-inbox-page="/brain?tab=inbox"',
                 'data-rollback-action="item_rollback"', 'data-item-base="/brain/items/"',
                 'id="brain-card-propose"', "data-brain-propose-form hidden", "data-brain-propose-fields",
                 "data-brain-propose-title", "data-brain-propose-status", "data-brain-rollback-status",
                 'name="reason"', "data-brain-propose-submit", "data-brain-propose-cancel"):
        assert hook in aside, hook
    labels = {a["name"]: a["label"] for a in actions.specs()}
    opened = re.findall(r'data-brain-propose-open="(\w+)"[^>]*>(?:<span[^>]*></span>)?([^<]+)</button>', aside)
    assert opened == [(n, labels[n]) for n in ("propose_edit", "propose_retire", "propose_delete")]
    assert "옛 판으로 되돌리기 제안" in aside and "data-ds-item-rollback hidden" in aside
    assert re.findall(r'data-brain-rollback-to="(\d+)">([^<]+)<', aside) == [("1", labels["item_rollback"] + " — 버전 1")]
    assert re.findall(r'<span class="f-strong">버전 (\d+)</span>', aside) == ["2", "1"]
    assert "어느 단추도 바로 바꾸지 않아요" in aside
    fields = re.findall(r'data-brain-field="([\w.]+)"', aside)
    assert fields[:4] == ["name", "text", "valid_from", "valid_to"] and len(fields) > 4  # + 그 유형 속성 틀 칸


def test_retired_card_has_no_retire_button_and_one_version_has_no_rollback(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    client = _client(app, ids["admin"])
    old = _get(app, client, "/brain/items/common/old")[1]
    assert re.findall(r'data-brain-propose-open="(\w+)"', old) == ["propose_edit", "propose_delete"]
    assert '<span class="f-tag f-tag-minimal f-tag-danger">은퇴</span>' in old  # 은퇴는 빨강 옅은 바탕(무채색 아님)
    fresh = _get(app, client, "/brain/items/common/fresh")[1]
    assert "data-ds-item-rollback-toggle" not in fresh and "data-brain-rollback-to" not in fresh


def test_usage_section_follows_the_erp_read_switch(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    client = _client(app, ids["admin"])
    off = _get(app, client, "/brain/items/common/door")[1]
    assert "data-usage-url" not in off and "data-ds-item-usage" not in off and "fb-item-grid--usage" not in off
    _switch(monkeypatch, "erp_read")
    on = _get(app, client, "/brain/items/common/door")[1]
    assert 'data-ds-item data-usage-url="/api/brain/items/common/door/usage"' in on
    assert 'aria-label="쓰인 곳" data-ds-item-usage' in on and "fb-item-grid fb-item-grid--usage" in on
    assert "data-ds-item-usage-status" in on


@pytest.mark.parametrize(("who", "path"), [("cs_mgr", "/brain/items/drawing/rule"), ("admin", "/brain/items/common/nope"),
                                           ("cs_staff", "/brain/items/common/door"), ("viewer", "/brain/items/common/door")])
def test_cards_you_cannot_see_stay_404(app, ids, monkeypatch, who, path):
    _switch(monkeypatch, "brain_ui")
    assert _client(app, ids[who]).get(path).status_code == 404


def test_manager_sees_the_new_card_for_what_their_scope_allows(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    resp, body, names = _get(app, _client(app, ids["dr_mgr"]), "/brain/items/drawing/rule")
    assert resp.status_code == 200 and names[0] == "brain/ds/item.html" and "문짝 도면 규칙" in body


def test_switch_off_draws_the_old_card_unchanged(app, ids, monkeypatch):
    resp, body, names = _get(app, _client(app, ids["admin"]), "/brain/items/common/door")
    assert resp.status_code == 200 and names[0] == "brain/item.html"
    assert "data-ds-item" not in body and 'data-bs-target="#brain-card-neighbours"' in body
