"""새 온톨로지 화면(판 ⑩ — 설계서 2026-11-14-foms-graft 3.2 · 3.8 · 5.2 ~ 5.4) — 서버가 그리는 자리 · 보기 둘 · 순수 함수.

- 스위치 켬: ``?tab=onto`` · ``?tab=map`` 이 ``brain/ds/onto.html`` 하나로 200(ADMIN · 화면 여는 MANAGER) · 왼쪽 · 가운데 · 오른쪽 자리 ·
  인라인 스타일 0 · 스크립트는 defer + 내용 지문 핀 · 옛 온톨로지 스크립트(brain-onto*.js · brain-page.js)는 싣지 않는다.
- 유형 지도 보기: 옛 조각(tab_map.html) · brain-map.js · brain.css 를 그대로 싣고, 그림 라이브러리는 <script> 로 싣지 않는다.
- 순수 함수(node): 진짜 API 값으로 왼쪽 목록(ERP 칸은 erp 가 있을 때만) · ERP 물건 머리 줄 · 속성 '지금 칸'은 API 값 그대로 ·
  점수(켜기 전 → 지금) · 아직 못 푸는 질문 · 주소의 고른 것.
- 스위치 끔: 옛 화면 그대로.
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
from foms.services.brain.ontology_view import ontology_erp_type, ontology_summary
from foms.services.brain.scope import viewer_of
from foms.services.erp_ontology.objects import OBJECT_TYPES, ORDER_PROPS
from foms.services.graft_flags import FLAGS
from tests.support.brain_screen_support import TODAY, world

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "static/js/brain/ds/ds-onto-view.js"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
OLD_DOM_SCRIPTS = ("brain-onto.js", "brain-onto-view.js", "brain-page.js")


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


def _switch(monkeypatch, short):
    monkeypatch.setenv(f"{FLAGS[short]}_ENABLED", "1")
    monkeypatch.setenv(f"{FLAGS[short]}_COHORT", "all")


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


BASE = ["brain-view.js", "brain-dom.js", "ds-shell.js", "ds-onto-view.js", "ds-onto-kit.js"]


def test_switch_on_draws_the_onto_view_in_its_places(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    for who in ("admin", "cs_mgr"):
        resp, body, names = _get(app, _client(app, ids[who]), "/brain?tab=onto")
        assert resp.status_code == 200 and names[0] == "brain/ds/onto.html", who
        assert 'style="' not in body and "onclick" not in body and "<script>" not in body.split("</head>")[1]
        places = ['aria-label="온톨로지 목록" data-ds-onto-side', "data-ds-onto-find", "data-ds-onto-nav", 'id="ds-main"',
                  'data-ds-onto data-ds-onto-view="onto"', "data-ds-onto-detail", 'aria-label="능력 질문" data-ds-onto-aside',
                  "data-ds-onto-cq", "data-ds-onto-source hidden"]
        assert [body.index(p) for p in places] == sorted(body.index(p) for p in places), who
        assert 'data-onto-url="/api/brain/ontology"' in body and 'data-page-url="/brain"' in body
        assert "여기서는 보기만 해요. 종류 · 칸은 설계서와 코드로만 바꿔요." in body
        assert _scripts(body) == BASE + ["ds-onto-detail.js", "ds-onto.js"], who
        assert not [n for n in OLD_DOM_SCRIPTS + ("brain-map.js",) if f"/{n}?" in body]
        assert "contexts/brain/brain.css" not in body and "vendor/cytoscape" not in body
        assert re.search(r"css/contexts/brain/ds/brain-ds-onto\.css\?v=[0-9a-f]{12}", body)
        side = body[body.index("data-ds-onto-side"):body.index("</nav>", body.index("data-ds-onto-side"))]
        assert 'href="/brain?tab=map" data-ds-nav="map"' in side and 'href="/brain?tab=onto" data-ds-nav="onto"' in side


def test_map_view_loads_the_old_map_part_as_is(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    resp, body, names = _get(app, _client(app, ids["admin"]), "/brain?tab=map")
    assert resp.status_code == 200 and names[0] == "brain/ds/onto.html"
    assert 'data-ds-onto-view="map"' in body and "data-ds-onto-detail" not in body and 'style="' not in body
    assert "data-brain-map-canvas" in body and "data-brain-map-type=" in body and "연결 종류(선 색)" in body
    assert re.search(r"css/contexts/brain/brain\.css\?v=[0-9a-f]{12}", body)
    scripts = _scripts(body)
    assert scripts == BASE + ["ds-onto.js", "ds-onto-map.js", "brain-map.js"]  # 이음새가 그림 스크립트보다 먼저
    assert not [t for t in re.findall(r"<(?:script|link)[^>]*>", body) if "vendor/cytoscape" in t]  # 열 때만 import()
    assert re.search(r'data-cytoscape-url="/static/vendor/cytoscape-3\.34\.4\.esm\.min\.js\?v=[0-9a-f]{12}"', body)
    assert 'data-type-map-url="/api/brain/type-map"' in body
    side = body[body.index("data-ds-onto-side"):body.index("</nav>", body.index("data-ds-onto-side"))]
    assert re.search(r'is-selected" href="/brain\?tab=map"[^>]*aria-current="page"', side)


def test_switch_off_keeps_the_old_screen(app, ids):
    client = _client(app, ids["admin"])
    for tab in ("onto", "map"):
        resp, body, names = _get(app, client, f"/brain?tab={tab}")
        assert resp.status_code == 200 and names[0] == "brain/index.html", tab
        assert "data-ds-onto" not in body and "brain-onto.js" in body and "ds-onto" not in body


# ── 순수 함수(node) — 진짜 API 값으로 ─────────────────────────────────────
def _node(expr: str, data: object = None):
    """node 로 순수 함수를 부른다 — 값은 표준 입력으로(명령 줄 길이 상한을 넘지 않게)."""
    script = (f"const v = require({json.dumps(str(VIEW))});"
              "const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], input=json.dumps(data, ensure_ascii=False), capture_output=True,
                         text=True, encoding="utf-8", timeout=60, check=True).stdout
    return json.loads(out)


@pytest.fixture
def summaries(app, ids):
    from models import User

    viewer = viewer_of(db_session.get(User, ids["admin"]))
    return {"off": ontology_summary(db_session, viewer, today=TODAY),
            "on": ontology_summary(db_session, viewer, today=TODAY, erp=True)}


@NODE
def test_nav_model_draws_erp_parts_only_when_the_api_sends_them(summaries):
    off, on = _node("[v.navModel(data.off), v.navModel(data.on)]", summaries)
    assert off["erp"] is None and [d["kind"] for d in off["defs"]] == ["links", "actions", "cq"]
    assert [d["label"] for d in on["defs"]] == ["연결 종류", "할 일 종류", "동작 종류", "능력 질문"]
    assert [t["type"] for t in on["erp"]] == [o.type for o in OBJECT_TYPES]
    assert on["erp"][0] == {"type": "erp:order", "label": "주문", "sub": "orders", "icon": "cube"}
    assert off["kinds"] == sum(len(g["types"]) for g in summaries["off"]["groups"])
    assert [g["label"] for g in off["groups"]] == [g["label"] for g in summaries["off"]["groups"]]
    cq = summaries["on"]["cq"]
    assert on["defs"][-1]["count"] == f"{cq['covered']} / {cq['total']}"
    assert off["defs"][0]["count"] == str(len(summaries["off"]["links"]))
    assert _node("v.defaultPick(null)") == {"kind": "type", "id": "product_line"}
    assert (_node("[v.defaultPick(data.off), v.defaultPick(data.on)]", summaries)
            == [{"kind": "type", "id": "product_line"}, {"kind": "erp", "id": "erp:order"}])


@NODE
def test_score_change_and_left_questions_from_the_api(summaries):
    got = _node("[v.score(data.off.cq), v.score(data.on.cq), v.fails(data.on.cq, 5)]", summaries)
    off, on, left = got
    cq = summaries["on"]["cq"]
    assert off["before"] is None and off["change"] == ""
    assert on["before"] == cq["covered_before"] == summaries["off"]["cq"]["covered"]
    assert on["change"] == f"ERP 재료를 세기 전 {cq['covered_before']} → 지금 {cq['covered']}"
    assert on["text"] == f"{cq['covered']} / {cq['total']}"
    not_covered = [r for r in cq["rows"] if not r["covered"]]
    assert left["total"] == len(not_covered) and [r["id"] for r in left["rows"]] == [r["id"] for r in not_covered[:5]]
    assert all(row["missing"] for row in left["rows"])


@NODE
def test_erp_detail_text_uses_the_api_columns_as_is():
    detail = ontology_erp_type("order")
    got = _node("[v.erpMeta(data), data.props.map(p => [p.column, v.accessTone(p.access)]),"
                " data.actions.map(a => [v.levelTone(a), v.whereIcon(a.where)])]", detail)
    meta, props, actions = got
    assert meta == ["표 orders + JSONB 칸 structured_data", "새 표 없음", f"가림 {detail['masked']}칸",
                    f"능력 질문 {len(detail['cq'])}개가 씀"]
    assert [c for c, _t in props] == [p.column for p in ORDER_PROPS]  # '지금 칸'은 정본 칸 그대로(목업 옛 칸 아님)
    assert not [c for c, _t in props if c in ("orders.status", "orders.customer_name", "orders.phone", "orders.address")]
    tones = dict(zip([p.access for p in ORDER_PROPS], [t for _c, t in props]))
    assert tones["read"] == "" and tones["masked"] == "warning" and tones["money"] == "danger" and tones["action"] == "primary"
    assert len(actions) == len(detail["actions"]) and all(icon != "info-sign" for _tone, icon in actions)
    customer = _node("v.erpMeta(data)", ontology_erp_type("customer"))
    assert customer[0] == "표 orders + JSONB 칸 structured_data.parties.customer" and "가림" not in " ".join(customer)


@NODE
def test_pick_in_the_address_and_nav_filter():
    got = _node("[v.pickFromQuery('?tab=onto&kind=erp&id=erp:visit'), v.pickFromQuery('?kind=links'),"
                " v.pickFromQuery('?kind=bogus&id=x'), v.pickFromQuery('?kind=type'), v.pickFromQuery(''),"
                " v.pickQuery({kind: 'erp', id: 'erp:order'}), v.pickQuery({kind: 'cq', id: 'all'}),"
                " v.matches('주문 품목', '품목'), v.matches('주문', '현장'), v.matches('아무거나', '  '),"
                " v.typeSub({count: 3, standard: 'schema:Product', layers: ['공통'], cq: ['A1', 'A2']}),"
                " v.cardinalityText({direction: 'out', min: 0, max: null}), v.cardinalityText({direction: 'in'}),"
                " v.rangeText({unit: 'mm', low: 10, high: null}),"
                " v.endsText({types: {spec: {label: '규격'}}}, {common: '공통'}, [{type: 'spec'}, {group: 'common'}])]")
    assert got[0] == {"kind": "erp", "id": "erp:visit"} and got[1] == {"kind": "links", "id": "all"}
    assert got[2] is None and got[3] is None and got[4] is None
    assert got[5] == "tab=onto&kind=erp&id=erp%3Aorder" and got[6] == "tab=onto&kind=cq"
    assert got[7:10] == [True, False, True]
    assert got[10] == "3개 · 표준 schema:Product · 층 공통 · 능력 질문 2개가 필요"
    assert got[11] == "0 ~ 여럿" and got[12] == "" and got[13] == "mm · 10 이상"
    assert got[14] == "규격 · 공통 전체"


def test_onto_scripts_bind_once_and_draw_bars_without_inline_style():
    kit = (ROOT / "static/js/brain/ds/ds-onto-kit.js").read_text(encoding="utf-8")
    main = (ROOT / "static/js/brain/ds/ds-onto.js").read_text(encoding="utf-8")
    seam = (ROOT / "static/js/brain/ds/ds-onto-map.js").read_text(encoding="utf-8")
    assert "el('progress'" in kit and "__FOMS_DS_ONTO_BOUND" in main and "__FOMS_DS_ONTO_MAP_BOUND" in seam
    assert "window.FOMS_BRAIN_CTX = {" in seam and "fire('brain:tab', { tab: 'map' })" in seam
    for path in sorted((ROOT / "static/js/brain/ds").glob("ds-onto*.js")):
        lines = path.read_text(encoding="utf-8").splitlines()
        code = " ".join(line for line in lines if not line.strip().startswith(("*", "//", "/**")))  # 주석 줄은 빼고 코드만
        assert "fetch(" not in code and ".innerHTML" not in code and ".style." not in code, path.name
        assert "import(" not in code, path.name  # 그림 라이브러리는 옛 brain-map.js 만 부른다
        assert len(lines) <= 300, path.name
