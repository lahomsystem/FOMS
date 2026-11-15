"""AI 직원 새 화면(판 ⑪ — 설계서 2026-11-14-foms-graft 3.10 · 5.2 · 9절) — 화면 구조 · 자리 표시 · 인라인 스타일 0.

완료 기준:
- 스위치 켬 · ADMIN: 200 · 틀(왼쪽 직원 목록 · 가운데 칸 셋 · 오른쪽 실행 기록) · 읽을 API 주소 · 수준 고치기 주소 · 내용 지문 핀으로
  싣는 스크립트 둘(defer) · CSS 하나 · 'AI 시험' 자리(``data-ds-agents-evals``) · '함께 보기' 셋.
- MANAGER: 200 · 수준 고치기 주소 없음 · '비용' 글 없음.
- 'AI 시험' 조각(T16 몫)이 없어도 온전하고, 있으면 그 자리 안에 그려진다.
- 새 파일에 ``style="`` 0 · JS 300줄 아래 · 시공 팀 · 인원 글 없음(D211) · 3 단계 수준 글 없음.
- 스위치 끔(대조군): 옛 화면 그대로(새 화면 자리 없음).
합성 계정 · 합성 항목만(``tests.support.brain_screen_support``).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from jinja2 import ChoiceLoader, DictLoader

from db import db_session
from foms.services.graft_flags import FLAGS
from tests.support.brain_screen_support import world

ROOT = Path(__file__).resolve().parents[2]
NEW_FILES = ("templates/brain/ds/agents.html", "templates/brain/ds/partials/agents_side.html",
             "templates/brain/ds/partials/agents_aside.html", "static/js/brain/ds/ds-agents.js",
             "static/js/brain/ds/ds-agents-kit.js")
PAGE = "/brain?tab=agents"


@pytest.fixture
def ids(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    return {name: user.id for name, user in world(db_session).items()}


def _on(monkeypatch):
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_ENABLED", "1")
    monkeypatch.setenv("FOMS_GRAFT_BRAIN_UI_COHORT", "all")


def _page(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    resp = client.get(PAGE)
    return resp, resp.get_data(as_text=True)


def test_admin_screen_has_its_places(app, ids, monkeypatch):
    _on(monkeypatch)
    resp, body = _page(app, ids["admin"])
    assert resp.status_code == 200 and 'data-ds-section="agents"' in body
    for place in ("data-ds-agents-side", "data-ds-agents-nav", "data-ds-agents-name", "data-ds-agents-tags",
                  "data-ds-agents-reads", "data-ds-agents-tools", "data-ds-agents-duties", "data-ds-agents-evals",
                  "data-ds-agents-failures", "data-ds-agents-usage", "data-ds-agents-aside", "data-ds-agents-trace",
                  'id="dsAgentsRun"', 'id="dsAgentsEvals"', 'id="dsAgentsUsage"'):
        assert place in body, place
    assert 'data-list-url="/api/ai-staff"' in body and 'data-levels-url="/api/ai-staff/levels"' in body
    for title in ("읽는 것 · 쓰는 도구", "쓸 수 있는 할 일 · 자율 수준", "AI 시험", "최근 실패", "실행 기록", "시험 세트",
                  "비용 · 시간"):
        assert title in body, title
    scripts = re.findall(r'<script src="([^"]*ds-agents[^"]*)" defer></script>', body)
    assert [Path(src.split("?")[0]).name for src in scripts] == ["ds-agents-evals.js", "ds-agents-kit.js", "ds-agents.js"]  # T16 조각
    assert all("?v=" in src for src in scripts)  # 내용 지문 핀(asset_url)
    assert re.search(r'href="[^"]*brain-ds-agents\.css\?v=[^"]+"', body)
    assert 'style="' not in body


def test_manager_sees_no_level_editing_and_no_cost(app, ids, monkeypatch):
    _on(monkeypatch)
    resp, body = _page(app, ids["cs_mgr"])
    assert resp.status_code == 200 and "data-ds-agents" in body
    assert "data-levels-url" not in body and "비용" not in body


def test_evals_place_is_whole_without_the_partial_and_fills_with_it(app, ids, monkeypatch):
    _on(monkeypatch)
    loader = app.jinja_loader

    def _with_partial(text):
        monkeypatch.setattr(app, "jinja_loader", ChoiceLoader([
            DictLoader({"brain/ds/partials/agents_evals.html": text}), loader]))
        app.jinja_env.loader = app.create_global_jinja_loader()
        app.jinja_env.cache.clear()
        try:
            return _page(app, ids["admin"])[1]
        finally:
            monkeypatch.setattr(app, "jinja_loader", loader)
            app.jinja_env.loader = app.create_global_jinja_loader()
            app.jinja_env.cache.clear()

    assert re.search(r'data-ds-agents-evals></div>', _with_partial(""))  # 조각이 비면 빈 자리(CSS 가 숨긴다)
    filled = _with_partial('<p data-t16-evals>합성 시험</p>')
    assert re.search(r'data-ds-agents-evals><p data-t16-evals>합성 시험</p></div>', filled)


def test_switch_off_keeps_the_old_screen(app, ids):
    _resp, body = _page(app, ids["admin"])
    assert "data-ds-agents" not in body and "data-ds-shell" not in body


def test_new_files_have_no_inline_style_and_stay_small():
    for name in NEW_FILES:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert 'style="' not in text, name
        for word in ("인원", "÷ 300", "실행 뒤 알림"):  # D211 · 수준 3 없음
            assert word not in text, (name, word)
        if name.endswith(".js"):
            assert len(text.splitlines()) < 300, name
            assert "innerHTML" not in text and "fetch(" not in text, name  # 글은 textContent · 요청은 brain-dom.js 한 곳
    css = (ROOT / "static/css/contexts/brain/ds/brain-ds-agents.css").read_text(encoding="utf-8")
    selectors = re.findall(r"(?m)^([^{}@/\s][^{]*)\{", css)
    for group in selectors:
        for selector in group.split(","):
            assert selector.strip().startswith((".fb-", ".f-app ")), selector


def _kit(expr: str, data: object = None):
    """ds-agents-kit.js 를 가짜 window 에 싣고 식 하나를 돌린다(DOM 은 쓰지 않는다)."""
    script = ("global.window = { FOMS_BRAIN_DOM: { el: function () { return {}; } } };"
              f"require({json.dumps(str(ROOT / 'static/js/brain/ds/ds-agents-kit.js'))});"
              "const kit = window.FOMS_DS_AGENTS_KIT;"
              f"const data = {json.dumps(data, ensure_ascii=False)};"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60,
                         check=True).stdout
    return json.loads(out)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_recent_failure_codes_are_plain_words():
    """R-18 — '최근 실패'에 기계 말(코드)이 그대로 나오지 않는다. 모르는 코드는 '알 수 없는 오류', 빈 코드는 빈 글."""
    codes = ["ACTION_FAILED", "ACTION_PRECONDITION", "claim_expired", "read_failed", "send_provider_error",
             "SOMETHING_NEW", "", None]
    got = _kit("data.map(kit.failureText)", codes)
    assert got[:5] == ["실행하지 못했어요", "주문 상태가 맞지 않았어요", "너무 오래 걸려 멈췄어요", "상담 글을 못 읽었어요",
                       "메모를 올리지 못했어요"]
    assert got[5:] == ["알 수 없는 오류", "", ""]
    assert not any(re.search(r"[A-Za-z_]{3,}", text) for text in got)
