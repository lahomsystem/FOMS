"""새 찾기 · 지식 표 화면(설계서 2026-11-14-foms-graft 5.2 ~ 5.4 · 판 ⑦) — 서버가 그리는 자리 + 순수 계산 node 시험.

- 스위치 켬 + ADMIN: ``?tab=search`` · ``?tab=table`` 이 ``brain/ds/search.html`` 하나로 200 · 인라인 스타일 0 · 스크립트는 defer +
  내용 지문 핀 · 옛 찾기 · 표 스크립트(brain-page.js · brain-table.js)는 싣지 않는다.
- 자리: 왼쪽 유형 묶음 나무(묶음 · 유형 · 수 — 볼 수 있는 것만 센 수) · 큰 찾기 칸 · 유형별 수 칩 · 거르기 여덟(값 목록은 코드 상수
  그대로) · 표 머리 아홉 · 쪽 · 오른쪽 미리 보기. 주소의 유형 · 찾는 말이 그대로 자리에 실린다(?tab=search&q= · ?tab=table&type=).
- 쓰인 곳: ERP 읽기 스위치가 켜진 사람만 미리 보기가 /usage 를 읽는다(data-usage) — 꺼지면 그 표시도 안내도 없다.
- 스위치 끔: 옛 화면 그대로(brain/index.html).
- 순수 계산(``ds-search-view.js``): 줄 모양(상태 · 등급 색 갈래 — 무채색 없음) · 처음 유형 · 수 글 · 다시 볼 날 · 미리 보기 자리 ·
  쓰인 곳 막대 · ERP 칩 · 연결 수 · 속성 칸 고르기 · 쪽 글 · 주소 물음 글.
합성 계정 · 합성 항목만(``tests.support.brain_screen_support``).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest
from flask import template_rendered

from db import db_session
from foms.services.brain.browse import CHECKS, SORTS
from foms.services.brain.constants import BRANDS, CONFIDENCES, GRADES, LAYERS, OBJECT_STATUSES, TYPES
from foms.services.brain.display import display_table
from foms.services.graft_flags import FLAGS
from tests.support.brain_screen_support import world

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "static/js/brain/ds/ds-search-view.js"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
FILTERS = ["type", "layer", "brand", "status", "grade", "confidence", "check", "sort"]
HEADS = ["이름", "쓰는 팀", "브랜드", "상태", "확실한 정도", "등급", "쓰인 횟수", "마지막 확인", "다시 볼 날"]
SCRIPTS = ["brain-view.js", "brain-dom.js", "ds-shell.js", "ds-search-view.js", "ds-search-rows.js", "ds-search-preview.js",
           "ds-search.js"]


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


def _attr_json(body: str, name: str):
    raw = re.search(name + r'="([^"]*)"', body).group(1)
    return json.loads(raw.replace("&#34;", '"').replace("&#39;", "'").replace("&amp;", "&"))


def _between(body: str, start: str, end: str) -> str:
    at = body.index(start)
    return body[at:body.index(end, at)]


# ── 서버가 그리는 자리 ─────────────────────────────────────────────────────
def test_switch_on_admin_draws_search_and_table_in_one_template(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    client = _client(app, ids["admin"])
    for path, mode in (("/brain?tab=search", "search"), ("/brain?tab=table&type=build_rule", "table")):
        resp, body, names = _get(app, client, path)
        assert resp.status_code == 200 and names[0] == "brain/ds/search.html", path
        assert "brain/index.html" not in names
        assert f'data-ds-search-page data-ds-search-mode="{mode}"' in body
        assert 'style="' not in body and "onclick" not in body and "<script>" not in body.split("</head>")[1]
        assert _scripts(body) == SCRIPTS, path
        assert "/brain-page.js?" not in body and "/brain-table.js?" not in body  # 옛 찾기 · 표 스크립트는 싣지 않는다
        assert re.search(r"css/contexts/brain/ds/brain-ds-search\.css\?v=[0-9a-f]{12}", body)
        assert '<aside class="f-aside fb-pc-only fb-search-aside" aria-label="미리 보기" data-ds-search-aside>' in body
        heads = re.findall(r'<th scope="col"[^>]*>([^<]+)</th>', _between(body, "<thead>", "</thead>"))
        assert heads == HEADS
        for attr, value in (("data-search-url", "/api/brain/search"), ("data-table-url", "/api/brain/table"),
                            ("data-page-url", "/brain"), ("data-item-base", "/brain/items/"),
                            ("data-item-api", "/api/brain/items/")):
            assert f'{attr}="{value}"' in body, attr


def test_left_tree_groups_types_and_visible_counts(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain?tab=table&type=build_rule")
    tree = _between(body, 'aria-label="유형 묶음" data-ds-search-tree>', "</nav>")
    groups = [g["key"] for g in display_table()["groups"]]
    assert re.findall(r'data-ds-tree="(\w+)"', tree) == groups
    assert re.findall(r'<details class="fb-tree" data-ds-tree="(\w+)" open>', tree) == ["common"]  # 고른 유형의 묶음만 펼침
    assert re.findall(r'data-ds-type="(\w+)"', tree) == list(TYPES)  # 바깥 자리는 표가 없어 고르지 못한다
    assert re.search(r'data-ds-type="build_rule" aria-current="page">.*?제작 조건<span class="f-count">2</span>', tree)
    assert re.search(r'data-ds-search-all>.*?모든 유형<span class="f-count">7</span>', tree)  # 고르지 않음(지식 표)
    assert tree.count('aria-current="page"') == 1
    assert "fb-tree__type--outside" in tree and "유형 · 묶음은 온톨로지에서 정해요" in tree


def test_search_mode_echoes_the_query_and_hides_filters_and_pager(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain?tab=search&q=%EB%AC%B8%EC%A7%9D")
    assert 'data-start-query="문짝"' in body and 'value="문짝" autocomplete="off" data-ds-search-input' in body
    assert 'data-ds-search-filters hidden' in body and 'data-ds-search-pager hidden' in body
    assert 'aria-label="지식 목록" data-ds-search-list>' in body  # 찾는 말이 있으면 표가 보인다
    chips = _between(body, "data-ds-search-chips>", "</div>")
    assert re.search(r'class="f-chip fb-chip is-selected" href="/brain\?tab=search"\s+data-ds-search-all aria-current="page">', chips)
    empty = _get(app, _client(app, ids["admin"]), "/brain?tab=search")[1]
    assert 'aria-label="지식 목록" data-ds-search-list hidden>' in empty  # 찾을 말이 없으면 빈 표 머리를 숨긴다


def test_type_chips_count_down_and_the_table_type_is_picked(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain?tab=table&type=build_rule")
    chips = _between(body, "data-ds-search-chips>", "</div>")
    pairs = re.findall(r'data-ds-type="(\w+)"[^>]*>.*?<span class="f-strong f-num">(\d+)</span>', chips, re.S)
    counts = [int(n) for _t, n in pairs]
    assert counts == sorted(counts, reverse=True) and all(counts)  # 많은 순 · 0 인 유형은 칩이 없다
    assert ("build_rule", "2") in pairs and ("product_line", "2") in pairs
    assert re.search(r'class="f-chip fb-chip is-selected" href="/brain\?tab=table&amp;type=build_rule"\s+'
                     r'data-ds-type="build_rule" aria-current="page">', chips)
    assert "data-ds-chip-toggle" not in chips  # 열 개 아래면 '그 밖'이 없다
    assert 'data-start-type="build_rule"' in body and _attr_json(body, "data-type-counts")["build_rule"] == 2
    assert _attr_json(body, "data-type-icons")["build_rule"] == "build"


def test_eight_filters_carry_the_code_choice_lists(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain?tab=table&type=spec")
    form = _between(body, '<form class="fb-filters" aria-label="거르기" data-ds-search-filters>', "</form>")
    assert re.findall(r'data-ds-filter="(\w+)"', form) == FILTERS
    assert re.findall(r'<label class="f-label f-small f-muted" for="ds-filter-\w+">([^<]+)</label>', form) == [
        "유형", "쓰는 팀", "브랜드", "상태", "위험 등급", "확실한 정도", "확인", "정렬"]
    wanted = {"type": list(TYPES), "layer": list(LAYERS), "brand": list(BRANDS), "status": list(OBJECT_STATUSES),
              "grade": list(GRADES), "confidence": list(CONFIDENCES), "check": list(CHECKS), "sort": list(SORTS)}
    for name in FILTERS:
        select = _between(form, f'data-ds-filter="{name}">', "</select>")
        values = re.findall(r'<option value="(\w*)"', select)
        assert values == ([] if name in ("type", "sort") else [""]) + wanted[name], name
    assert '<option value="spec" data-label="규격" selected>' in form
    assert form.count(" selected>") == 1


def test_usage_hint_and_preview_reader_follow_the_erp_read_switch(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    client = _client(app, ids["admin"])
    off = _get(app, client, "/brain?tab=search")[1]
    assert "data-usage=" not in off and "지난 2주 동안 어디에 쓰였는지" not in off
    _switch(monkeypatch, "erp_read")
    on = _get(app, client, "/brain?tab=search")[1]
    assert 'data-item-api="/api/brain/items/" data-usage="1"' in on and "지난 2주 동안 어디에 쓰였는지" in on


def test_manager_sees_only_what_their_scope_counts(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    resp, body, names = _get(app, _client(app, ids["cs_mgr"]), "/brain?tab=table&type=drawing_rule")
    assert resp.status_code == 200 and names[0] == "brain/ds/search.html"
    tree = _between(body, 'data-ds-search-tree>', "</nav>")
    assert re.search(r'data-ds-type="drawing_rule"[^>]*>.*?도면 규칙<span class="f-count">0</span>', tree)  # 도면팀 것은 안 센다


@pytest.mark.parametrize("who", ["cs_staff", "viewer"])
def test_people_who_cannot_open_the_screen_still_get_404(app, ids, monkeypatch, who):
    _switch(monkeypatch, "brain_ui")
    assert _client(app, ids[who]).get("/brain?tab=table&type=build_rule").status_code == 404


def test_switch_off_draws_the_old_screen_unchanged(app, ids, monkeypatch):
    resp, body, names = _get(app, _client(app, ids["admin"]), "/brain?tab=table&type=build_rule")
    assert resp.status_code == 200 and names[0] == "brain/index.html"
    assert "data-ds-search-page" not in body and "/brain-table.js?" in body and "/brain-page.js?" in body


# ── 순수 계산(node) ───────────────────────────────────────────────────────
def _node(expr: str, data: object = None):
    script = (f"const v = require({json.dumps(str(VIEW))});"
              f"const data = {json.dumps(data, ensure_ascii=False)};"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60, check=True)
    return json.loads(out.stdout)


def _item(**extra):
    base = {"key": "common/fit", "name": "합성 규칙", "type": "build_rule", "layer": "common", "brand": "COMMON",
            "status": "active", "confidence": "confirmed", "grade": "A", "usage_count": 1204, "checked_at": "2026-10-28",
            "stale_after": "2027-01-26", "stale": False, "needs_check": False}
    return {**base, **extra}


@NODE
def test_row_model_labels_tones_and_flags():
    display = display_table()
    icons = {"build_rule": "build"}
    rows = _node("[v.rowModel(data.a, data.d, data.i), v.rowModel(data.b, data.d, data.i), v.rowModel(data.c, data.d, data.i)]",
                 {"d": display, "i": icons, "a": _item(),
                  "b": _item(status="draft", confidence="observed", grade="B_LIGHT", needs_check=True, stale=True,
                             stale_after="2026-11-12", checked_at=None, usage_count=0),
                  "c": _item(status="retired", type="nope", confidence="evidenced", grade=None, stale_after=None)})
    a, b, c = rows
    assert (a["name"], a["typeLabel"], a["icon"], a["team"], a["brand"], a["status"]) == (
        "합성 규칙", "제작 조건", "build", "공통 바탕", "공통", "사용 중")
    assert (a["statusCls"], a["conf"], a["confIcon"], a["confCls"], a["grade"], a["gradeCls"], a["used"]) == (
        "f-tag-success", "확정", "endorsed", "f-i-primary", "A", "f-tag-minimal f-tag-success", "1,204")
    assert a["due"] == {"text": "2027-01-26", "warn": False} and a["flags"] == []
    assert (b["status"], b["statusCls"], b["confIcon"], b["confCls"], b["grade"], b["gradeCls"]) == (
        "초안", "f-tag-minimal f-tag-primary", "eye-open", "f-i-warning", "B(가벼움)", "f-tag-minimal f-tag-warning")
    assert b["due"] == {"text": "11-12 지남", "warn": True} and b["checked"] == "—" and b["used"] == "0"
    assert b["flags"] == [{"text": "확인 필요", "cls": "f-tag-minimal f-tag-warning"}]
    assert (c["status"], c["statusCls"], c["typeLabel"], c["icon"], c["grade"], c["gradeCls"], c["due"]["text"]) == (
        "은퇴", "f-tag-minimal f-tag-danger", "nope", "circle", "—", "", "—")


@NODE
def test_status_and_grade_tones_are_never_achromatic():
    tones = _node("[v.STATUS_TONES, v.GRADE_TONES]")
    for table in tones:
        for cls in table.values():
            assert re.search(r"f-tag-(primary|success|warning|danger)\b", cls), cls  # 회색(f-tag-minimal 만) 없음
    assert len(set(tones[0].values())) == 3 and len(set(tones[1].values())) == 3
    # 옅은 초록 · 옅은 빨강은 색약 흉내 뒤 색 차가 1 이라 무거운 B 는 꽉 찬 빨강(잰 값은 T4 보고서)
    assert tones[1] == {"A": "f-tag-minimal f-tag-success", "B_LIGHT": "f-tag-minimal f-tag-warning", "B": "f-tag-danger"}


@NODE
def test_start_type_numbers_positions_and_steps():
    order = ["brand", "product_line", "build_rule"]
    got = _node("[v.pickStartType('build_rule', data.c, data.o), v.pickStartType('', data.c, data.o),"
                " v.pickStartType('ext_calculator', data.c, data.o), v.pickStartType('', {}, data.o), v.pickStartType('', {}, []),"
                " v.num(0), v.num(999), v.num(1204), v.num(1234567), v.num('x'),"
                " v.previewPos(3, 10), v.previewPos(-1, 10), v.previewPos(0, 0),"
                " v.stepIndex(0, -1, 4), v.stepIndex(-1, 1, 4), v.stepIndex(3, 1, 4), v.stepIndex(1, 1, 4)]",
                {"c": {"brand": 0, "product_line": 3}, "o": order})
    assert got == ["build_rule", "product_line", "product_line", "brand", "", "0", "999", "1,204", "1,234,567", "0",
                   "10개 중 4", "", "", -1, 0, -1, 2]


@NODE
def test_usage_bars_tones_and_erp_chips():
    got = _node("[v.usageBars({cs_draft: 37, erp_action: 4, chatbot: 12}), v.usageBars({}), v.usageBars(null),"
                " v.toneCls('success'), v.toneCls('nope'), v.shortDay('2026-11-13'), v.shortDay('어제'),"
                " v.erpChip({rel: 'applies_to', type_label: '주문 품목', label: '합성 붙박이장', note: '이름으로 이어져요'}),"
                " v.erpChip({rel: 'at_step', type_label: '주문', label: '합성 재단', note: 'ERP 단계 · 생산'})]")
    assert got[0] == [{"key": "cs_draft", "label": "상담 초안", "n": 37, "pct": 100},
                      {"key": "erp_action", "label": "할 일 제안", "n": 4, "pct": 11},
                      {"key": "chatbot", "label": "물어보기 답", "n": 12, "pct": 32}]  # 판 ⑧ 의 막대 100 · 11 · 32
    assert [b["pct"] for b in got[1]] == [0, 0, 0] and [b["n"] for b in got[2]] == [0, 0, 0]
    assert got[3:7] == ["f-tag-minimal f-tag-success", "f-tag-minimal f-tag-primary", "11-13", "어제"]
    assert got[7] == {"icon": "cube", "text": "주문 품목 · 합성 붙박이장", "note": "이름으로 이어져요"}
    assert got[8] == {"icon": "timeline-bar-chart", "text": "주문 · 합성 재단", "note": "ERP 단계 · 생산"}


@NODE
def test_link_summary_key_fields_pager_and_page_query():
    groups = [{"kind": "applies_to", "direction": "out", "count": 2}, {"kind": "evidence_of", "direction": "in", "count": 3},
              {"kind": "nope", "direction": "out", "count": 1}]
    fields = [{"path": "payload.pref_label", "label": "한글 이름"}, {"path": "payload.min_depth", "label": "깊이"},
              {"path": "checked_at", "label": "확인"}, {"path": "payload.unit", "label": "단위"},
              {"path": "payload.a", "label": "가"}, {"path": "payload.b", "label": "나"}]
    got = _node("[v.linkSummary(data.g, data.d), v.linkSummary(null, data.d),"
                " v.keyFields(data.f).map(f => f.label), v.keyFields(data.f, 1).map(f => f.label),"
                " v.pagerText(1, 25, 1204, '쓰인 횟수 많은 순'), v.pagerText(3, 25, 60, ''), v.pagerText(1, 25, 0, 'x'),"
                " v.pageQuery('search', ' 문짝 '), v.pageQuery('search', ''), v.pageQuery('table', 'build_rule'),"
                " v.pageQuery('table', '')]",
                {"g": groups, "d": display_table(), "f": fields})
    assert got[0] == {"rows": [{"kind": "applies_to", "label": "적용 대상", "n": 2},
                               {"kind": "evidence_of", "label": display_table()["links"]["evidence_of"]["in"], "n": 3},
                               {"kind": "nope", "label": "nope", "n": 1}], "total": 6}
    assert got[1] == {"rows": [], "total": 0}
    assert got[2] == ["깊이", "단위", "가"] and got[3] == ["깊이"]
    assert got[4:7] == ["1,204개 중 1–25 · 쓰인 횟수 많은 순", "60개 중 51–60", "0개"]
    assert got[7:] == ["?tab=search&q=%EB%AC%B8%EC%A7%9D", "?tab=search", "?tab=table&type=build_rule", "?tab=table"]
