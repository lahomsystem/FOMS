"""생산 첫 화면 '내 공정' 탭 오른쪽 판 — 배선 시험(설계서 ``docs/specs/2026-11-21-production-my-steps-panel_SPEC.md`` §3-5 · §6).

④ 쓰기 길 셋(공정 · 불량 · 보류)을 진짜 서버 조각 위에서 Node 로 돌려 확인(tests/support/production_home_steps_node_checks.js)
⑤ 쿼리 수 — '내 공정' 탭 계약 새로(주문 4 대 12 · 차이 ≤2 · 절대 = 실측 + 30%), 판을 그려도 0개 더함
⑥ CSS(반반 · 문 밖은 숨김 · 짧은 판 · [끝]은 늘 판 안 · 글자 손잡이) · 핀
판 자료 · 문 · 마크업은 test_production_home_step_panel.py.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import event

from db import engine
from tests.support.production_home_step_panel_seed import (
    HOME,
    SHELL,
    STEPS_JS,
    TABLET,
    add_order,
    get_html,
    login,
    panel_url,
    seed_cut_queue,
    set_cookies,
)

ROOT = Path(__file__).resolve().parents[2]
NODE_CHECK = ROOT / "tests/support/production_home_steps_node_checks.js"
PANE_CHECK = ROOT / "tests/support/production_home_steppane_node_checks.js"
PANE_JS = "js/production/foms-production-home-steppane.js"


@pytest.fixture()
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


# --------------------------------------------------------------------------- #
# ④ 쓰기 길 셋 — 진짜 조각 위에서 Node 로
# --------------------------------------------------------------------------- #
def test_끝_불량_보류는_지금_API_길을_부른다_Node(client, cohort, tmp_path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    login(client)
    a, b, c, d, e = seed_cut_queue()
    set_cookies(client, TABLET)
    frag = get_html(client, HOME + "?tab=steps&view=fragment", SHELL)
    page = tmp_path / "steps.html"
    page.write_text(frag, encoding="utf-8")
    # 고르지 않은 줄(보류 한지우)의 판은 누를 때 받는 조각 — 서버가 그린 진짜 조각을 가짜 fetch 가 돌려준다
    held = tmp_path / f"panel_{c.id}.html"
    held.write_text(get_html(client, panel_url("cut", c.id)), encoding="utf-8")
    want = {"first": a.id, "first_name": "박서준", "hold": c.id, "next": b.id, "key": "cut", "label": "재단", "pin": None,
            "other_tab": "edge", "other_url": f"{HOME}?tab=steps&order={e.id}", "panels": {str(c.id): str(held)}}
    proc = subprocess.run([node, str(NODE_CHECK), str(page), json.dumps(want, ensure_ascii=False)], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr
    # 서버 쪽 길: 세 주소가 지금 있는 POST 길이다(새 쓰기 길 0)
    rules = {(r.rule, m) for r in client.application.url_map.iter_rules() for m in (r.methods or ())}
    for tail in ("steps", "defect", "hold"):
        assert (f"/api/orders/<int:order_id>/production/{tail}", "POST") in rules, tail
    js = (ROOT / "static" / STEPS_JS).read_text(encoding="utf-8")
    assert re.findall(r"'/api/[^']*'", js) == ["'/api/orders/'"] and "/production/steps'" in js
    assert "/production/defect" not in js and "/production/hold" not in js  # 불량 · 보류는 지금 시트 JS 몫


def test_판_하나_받기_마지막_누름_실패_다시_해_보기_옮겨_간_줄_Node(client, cohort, tmp_path) -> None:
    """고른 판만 그리고 다른 줄 판은 누를 때 받는다(2026-11-22) — 늦은 응답 버림 · 실패 글 · [다시 해 보기] · 404 · 끼운 판 묶기."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    login(client)
    a, b, c, d, e = seed_cut_queue()
    set_cookies(client, TABLET)
    page = tmp_path / "steps.html"
    page.write_text(get_html(client, HOME + "?tab=steps&view=fragment", SHELL), encoding="utf-8")
    panels = {}
    for o in (b, c, d):
        f = tmp_path / f"panel_{o.id}.html"
        f.write_text(get_html(client, panel_url("cut", o.id)), encoding="utf-8")
        panels[str(o.id)] = str(f)
    want = {"b": b.id, "d": d.id, "extra": c.id, "key": "cut", "panels": panels}
    proc = subprocess.run([node, str(PANE_CHECK), str(page), json.dumps(want, ensure_ascii=False)], capture_output=True,
                          text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr
    js = (ROOT / "static" / PANE_JS).read_text(encoding="utf-8")
    assert "/api/" not in js and "addEventListener" not in js  # 읽기만 · 리스너 없음(셸 교체로 다시 돌아도 쌓이지 않는다)
    assert "if (window.FomsProdStepPanes) { return; }" in js and len(js.splitlines()) <= 300
    proc = subprocess.run([node, "--check", str(ROOT / "static" / PANE_JS)], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_새_JS_는_화면에_한_번_묶고_문서_리스너는_없다() -> None:
    js = (ROOT / "static" / STEPS_JS).read_text(encoding="utf-8")
    assert "root.getAttribute('data-foms-home-steps-bound') === '1'" in js
    # 확인 창(Esc 문서 리스너)을 뺐다(2026-11-22) — 셸 교체를 건너는 것은 되돌리기 상태뿐(window.__FOMS_PROD_STEPS_BOUND)
    assert "window.__FOMS_PROD_STEPS_BOUND" in js and "document.addEventListener(" not in js and "window.addEventListener(" not in js
    assert "var UNDO_MS = 8000;" in js and "var GUARD_MS = 600;" in js and "data-foms-step-modal" not in js
    assert "try {" in js and "result.ok" in js  # 응답 규약: 성공 판정은 공용 쓰기 래퍼 · data.success
    assert "data.success !== false" in js
    assert len(js.splitlines()) <= 300
    node = shutil.which("node")
    if node:
        proc = subprocess.run([node, "--check", str(ROOT / "static" / STEPS_JS)], capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------- #
# ⑤ 쿼리 수 — '내 공정' 탭 계약(판을 그려도 0개 더함)
# --------------------------------------------------------------------------- #
# 실측(2026-11-21, SQLite 레인, 파트 없는 생산팀): 판 없음(PC) small 9 · big 9, 판 있음(태블릿) small 9 · big 9 → 차이 0, 판 더함 0.
STEPS_ALLOWED_DELTA = 2
STEPS_ABS_QUERY_CAP = 11  # 실측 9 + 30%


def _count(fn):
    counter = {"n": 0}

    def _before(conn, cursor, statement, params, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, counter["n"]


def test_내_공정_탭_쿼리_수는_주문이_늘어도_같고_판은_0개_더한다(client, cohort) -> None:
    login(client)
    for i in range(4):
        add_order(f"적은{i}", i % 3, done=("cut",) if i % 2 else (), pngs=2)
    counts = {}
    for label, cookies in (("plain", {"foms_ptr": "fine", "foms_vw": "wide"}), ("panel", TABLET)):
        set_cookies(client, cookies)
        assert client.get(HOME + "?tab=steps").status_code == 200  # warmup
        resp, n = _count(lambda: client.get(HOME + "?tab=steps"))
        assert resp.status_code == 200 and ("data-foms-step-pane" in resp.get_data(as_text=True)) == (label == "panel")
        counts[(label, "small")] = n
    for i in range(8):
        add_order(f"많은{i}", i % 5, done=("cut", "edge") if i % 3 == 0 else (), hold="자재" if i == 5 else None, pngs=3)
    for label, cookies in (("plain", {"foms_ptr": "fine", "foms_vw": "wide"}), ("panel", TABLET)):
        set_cookies(client, cookies)
        resp, n = _count(lambda: client.get(HOME + "?tab=steps"))
        body = resp.get_data(as_text=True)
        assert "많은7" in body
        counts[(label, "big")] = n
        if label == "panel":  # 고른 줄 판만(공정 줄마다 하나) — 다른 줄 판은 누를 때 받는다(2026-11-22)
            assert body.count('data-foms-step-pane="') == body.count("fph-q fph-q--sp has-sp") == 3
    for label in ("plain", "panel"):
        delta = counts[(label, "big")] - counts[(label, "small")]
        assert delta <= STEPS_ALLOWED_DELTA, (label, counts)
        assert counts[(label, "big")] <= STEPS_ABS_QUERY_CAP, (label, counts)
    assert counts[("panel", "big")] == counts[("plain", "big")], f"판이 쿼리를 더했어요: {counts}"


def test_판_하나_조각_쿼리_수는_주문이_늘어도_같고_다_그린_탭을_넘지_않는다(client, cohort) -> None:
    """판 하나 받기(view=panel)는 같은 행을 읽고 판 하나만 그린다 — 쿼리 수는 정해져 있고 주문 수와 상관없다."""
    login(client)
    set_cookies(client, TABLET)
    first = add_order("처음", 1)
    for i in range(3):
        add_order(f"적은{i}", 2 + i)
    url = HOME + f"?tab=steps&order={first.id}&view=panel&step=cut"
    assert client.get(url).status_code == 200  # warmup
    _, small = _count(lambda: client.get(url))
    for i in range(12):
        add_order(f"많은{i}", i % 5, done=("cut",) if i % 3 == 0 else (), pngs=3)
    resp, big = _count(lambda: client.get(url))
    assert resp.status_code == 200 and resp.get_data(as_text=True).count('data-foms-step-pane="') == 1
    _, full = _count(lambda: client.get(HOME + "?tab=steps"))
    assert big - small <= STEPS_ALLOWED_DELTA and big <= full <= STEPS_ABS_QUERY_CAP, (small, big, full)


# --------------------------------------------------------------------------- #
# ⑥ CSS — 반반 · 문 밖은 숨김 · 짧은 판 · 글자 손잡이 · 핀
# --------------------------------------------------------------------------- #
TABLET_MQ = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {"


def _panel_block(css: str) -> str:
    start = css.index("/* ── 내 공정 오른쪽 판")
    tail = css[start:]
    return tail[: tail.index("/* ── 가로 태블릿(터치) 제목 줄")]


def test_판_CSS_반반_문_밖은_숨김_끝_단추는_늘_판_안() -> None:
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    block = _panel_block(css)
    base, tablet = block.split(TABLET_MQ, 1)
    # 문 밖(세로 · 폰 · PC): 판 칸 · 보류 알약 숨김, 목록 감싸개는 없는 것과 같다 — 지금 줄 [끝] 그대로
    assert ".fph-q__list { display: contents; }" in base and ".fph-q__panes, .fph-qr__holdtag { display: none; }" in base
    assert "body.erp-mobile-v2-layout" not in base
    # 가로 터치 + 모바일 v2: 반반(목업 .split[data-rec]) · 줄 [끝] 숨김 · 고른 줄 3px 남색
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); grid-template-rows: minmax(0, 1fr);" in tablet
    assert "clamp(" not in block
    assert ".fph-q--sp .fph-qr__done, body.erp-mobile-v2-layout .fph-q--sp .fph-qr__hold { display: none; }" in tablet
    assert ".fph-q--sp .fph-qr.is-on { border: 3px solid var(--fph-brand); background: var(--fph-brand-50); }" in tablet
    rules = re.findall(r"^[ \t]+([^@{}\s][^{]*)\{", re.sub(r"/\*.*?\*/", "", tablet, flags=re.S), re.M)
    assert all(sel.strip().startswith(("body.erp-mobile-v2-layout", ".fph-sp")) for r in rules for sel in r.split(",")), rules
    # 페이지 = 화면 키(화면 크기 배율로 나눔), 줄 칸만 굴러가고 판 아래 묶음은 줄지 않는다 → [끝]은 늘 판 안 · 화면 안
    assert ".foms-prod-home.fph-has-sp { height: calc(100dvh / var(--foms-ui-zoom, 1)); min-height: 0; display: flex; flex-direction: column; overflow: hidden; }" in tablet
    assert ".fph-sp__bot { flex-shrink: 0;" in base and ".fph-sp__top { flex: 1 1 auto; min-height: 0;" in base
    assert "overflow-y: auto" in base.split(".fph-sp__top {", 1)[1].split("}", 1)[0]
    assert ".fph-sp__pic { flex: 1 1 auto; min-height: 96px;" in base  # 그림이 남는 키를 모두(빈 칸 없음) · 최소 96
    # 목업 값: 이름 26/800 · [끝] 96 · 28/800 · [불량] [보류] 48 · 다음 손님 15
    for frag in ("font-size: calc(26px * var(--foms-fs, 1)); font-weight: 800;", ".fph-sp__done { min-height: 96px;",
                 "font-size: calc(28px * var(--foms-fs, 1)); font-weight: 800;", ".fph-sp__act { min-height: 48px;",
                 ".fph-sp__next { margin: 0; font-size: calc(15px * var(--foms-fs, 1));"):
        assert frag in block, frag
    # 짧은 판(판 키 560 아래) = [끝] 72 · 칸 사이 8 — 키를 재는 컨테이너는 판 칸
    assert "container: fph-sp / size;" in tablet
    short = tablet.split("@container fph-sp (max-height: 559.98px) {", 1)[1].split("}\n  }", 1)[0]
    assert ".fph-sp__done, .fph-sp__hold { min-height: 72px;" in short and "gap: 8px" in short
    # 글자는 모두 손잡이를 따른다
    assert not re.findall(r"font-size:\s*\d+px", block)
    # 이 블록은 마지막 가로 태블릿 블록(제목 줄) 앞 — 그 블록 계약(test_production_tablet_mockup_fit)을 안 건드린다
    assert css.rindex(TABLET_MQ) > css.index("/* ── 내 공정 오른쪽 판")


def test_핀과_화면_HTML(client, cohort) -> None:
    styles = (ROOT / "templates/production/partials/home_styles.html").read_text(encoding="utf-8")
    assert "home.css') }}?v=20261123s" in styles and "{% if part_board %}" in styles  # parts.css = 도면 카드 판만(11-22 확인 창 뺌)
    early = (ROOT / "templates/production/partials/home_early.html").read_text(encoding="utf-8")
    assert f"filename='{STEPS_JS}') }}}}?v=20261122t" in early
    login(client)
    seed_cut_queue()
    set_cookies(client, TABLET)
    assert "home.css?v=20261123s" in get_html(client, HOME + "?tab=steps")
