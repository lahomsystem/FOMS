"""생산 첫 화면 '날 고르기'(설계서 §15.6, 2026-11-14) · 레일 생산 단추 셸 조각 교체.

- ② 첫 응답은 고른 날 장 하나만 그린다(예전 D5 = 15장 다 보내고 보이기/숨기기). 다른 날은 같은 주소 ``?view=day&day=`` 조각.
  파트 판(part_board)도 그 날만. 파트 계정 · 관리자 '도면 카드' 탭 · 읽기 전용 모두.
- ③ 생산 첫 화면은 셸 조각(``view=fragment`` + 셸 머리글)을 내고, erp-shell.js 가 조각 교체 · 미리 받기 대상으로 안다.
  다시 실행돼도 안전하게(화면마다 한 번 · 전역 리스너 한 번) 짠 JS 를 정적으로 본다.

대조군: 고른 날이 아닌 날의 손님 이름은 첫 응답에 없고 그 날 조각에는 있다(조각이 비어서 통과하는 것을 막는다) ·
JS 판정은 고치기 전 꼴(기억 없음 · 실패 글 없음 · 무조건 묶기)로 되돌린 사본에서 실패해야 한다.
"""
from __future__ import annotations

import datetime
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.services.common import erp_navigation_contract as enc
from foms.services.datetime_kst import get_today_kst
from tests.domains.test_production_parts_screen import _files, _get, _login, _order, _seed_day, _user

ROOT = Path(__file__).resolve().parents[2]
HOME = "/erp/production/home"
JS_DIR = ROOT / "static/js/production"
DAYS_JS = JS_DIR / "foms-production-home-days.js"
HOME_JS = JS_DIR / "foms-production-home.js"
SHELL_JS = ROOT / "static/js/runtime/erp-shell.js"
OFFLINE = "연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요."


@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


def _pane_keys(html: str) -> list[str]:
    return re.findall(r'data-foms-home-daypane="([^"]+)"', html)


def _seed_two_days(me, park) -> None:
    """오늘(한빛 3장 · 늘봄 2장) + 모레(모레집 4장) — 모레 카드는 첫 응답에 없어야 한다.
    (모레집 줄 자체는 오늘 장 아래 '미리 보기'에 설 수 있다 — 카드 열쇠 ``om/`` 로 가른다.)"""
    _seed_day(me, park)
    _order("모레집", _files("om", 4), day=2)


# --------------------------------------------------------------------------- #
# ② 고른 날만 — 파트 계정 · 관리자 '도면 카드' · 읽기 전용
# --------------------------------------------------------------------------- #
def test_part_account_first_response_has_only_chosen_day_and_day_fragment_brings_another(client, cohort):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    _seed_two_days(me, park)
    _login(client, me)
    html = _get(client, HOME)
    assert _pane_keys(html) == [_day(0)]
    assert html.count('data-pp-pane="') == 1 and html.count("data-pp-card ") == 5
    assert 'data-key="om/' not in html  # 다른 날 카드 0(미리 보기 줄은 카드가 아니다)
    assert html.count('data-foms-home-daybtn="') == 15  # 띠 단추 · 숫자는 그대로 다 있다
    later_btn = re.search(rf'data-foms-home-daybtn="{_day(2)}".*?</a>', html, re.S).group(0)
    assert "<b>1</b><small> / 1</small>" in later_btn  # 띠 숫자는 모든 날을 센다
    # 겉틀(확인 창 · 크게 보기 · 설정)은 화면에 한 번 — 조각에는 없다
    assert html.count('id="foms-part-confirm-modal"') == 1 and html.count("data-pp-viewer") == 1

    resp = client.get(HOME + f"?day={_day(2)}&view=day")
    frag = resp.get_data(as_text=True)
    assert resp.status_code == 200 and resp.headers["X-FOMS-HOME-DAY"] == _day(2)
    assert _pane_keys(frag) == [_day(2)] and frag.count("data-pp-card ") == 4 and "모레집" in frag
    assert "한빛" not in frag and "data-pp-viewer" not in frag and "foms-part-confirm-modal" not in frag
    assert 'data-pp-act="take"' in frag  # 쓸 수 있는 사람의 단추가 조각에도 그대로(확인 창은 페이지의 것을 쓴다)
    assert 'class="fph-pane__now"' in frag  # 파트 계정 날짜 탭 = 판 + 지금 장


def test_admin_parts_tab_and_readonly_day_fragment(client, cohort):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    _seed_two_days(me, park)
    _login(client, _user("관리자", team="CS", role="ADMIN"))
    html = _get(client, HOME + "?tab=parts&part=edge")
    assert _pane_keys(html) == [_day(0)] and 'data-key="om/' not in html
    # '도면 카드' 탭의 날 링크는 탭 · 파트를 싣는다(조각 주소도 같은 링크에서 나온다)
    link = re.search(rf'<a [^>]*data-foms-home-daybtn="{_day(2)}"[^>]*>', html).group(0)
    assert f'href="{HOME}?tab=parts&amp;part=edge&amp;day={_day(2)}"' in link
    frag = _get(client, HOME + f"?tab=parts&part=edge&day={_day(2)}&view=day")
    assert _pane_keys(frag) == [_day(2)] and frag.count("data-pp-card ") == 4
    assert 'class="fph-pane__now"' not in frag and "내가 엣지" in frag  # '도면 카드' 탭 = 판만, 고른 파트
    assert re.search(r'class="pp-part is-on"[^>]*part=edge&amp;day=' + _day(2), frag)

    _login(client, _user("상담", team="CS"))  # 읽기 전용 — 조각에도 쓰기 단추가 없다
    frag = _get(client, HOME + f"?tab=parts&part=cut&day={_day(2)}&view=day")
    assert frag.count("data-pp-card ") == 4 and 'data-pp-act="' not in frag


def test_plain_account_and_mouse_pc_get_day_fragment_without_board(client, cohort):
    """대조군: 파트 없는 계정 · 마우스 PC 는 판 없이 그 날 줄만(조각 길은 같다)."""
    _order("오늘집", _files("ot", 1))
    _order("모레집", [], stage="DRAWING", day=2)  # 도면 기다림 — 미리 보기에 안 서고 그 날 장에만
    _login(client, _user("생산"), ptr="fine")
    html = _get(client, HOME)
    assert _pane_keys(html) == [_day(0)] and "모레집" not in html and "data-pp-card" not in html
    frag = _get(client, HOME + f"?day={_day(2)}&view=day")
    assert "모레집" in frag and "data-pp-card" not in frag and "오늘집" not in frag


# --------------------------------------------------------------------------- #
# ③ 셸 조각 — 서버
# --------------------------------------------------------------------------- #
def test_home_serves_shell_fragment_with_its_css_and_scripts(client, cohort):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    _seed_two_days(me, park)
    _login(client, me)
    resp = client.get(HOME + "?view=fragment", headers={enc.ERP_SHELL_REQUEST_HEADER: "1"})
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200 and resp.headers.get(enc.ERP_FRAGMENT_RESPONSE_HEADER) == "1"
    assert "<!DOCTYPE" not in body and "<body" not in body and "data-foms-prod-home" in body
    for asset in ("home.css?v=", "parts.css?v=", "foms-production-home.js?v=", "foms-production-home-days.js?v=",
                  "foms-production-parts-viewer.js?v=", "foms-production-parts.js?v=", "foms-production-parts-sync.js?v="):
        assert asset in body, asset
    assert _pane_keys(body) == [_day(0)]
    assert body.index("foms-production-home-days.js?v=") < body.index("data-foms-prod-home")  # 조각 맨 앞(먼저 묶임)
    # 전체 페이지: 날 고르기 JS 는 머리에 — 공용 defer 스크립트(셸 · 메뉴 …)보다 먼저 돈다(죽은 누름 구간 줄이기)
    page = _get(client, HOME)
    assert page.index("foms-production-home-days.js?v=") < page.index("</head>") < page.index("js/runtime/erp-shell.js?v=")
    # 대조군: 셸 머리글이 없으면 온전한 페이지(view=fragment 만으로는 조각이 아니다)
    full = client.get(HOME + "?view=fragment")
    assert full.headers.get(enc.ERP_FRAGMENT_RESPONSE_HEADER) != "1" and "<!DOCTYPE" in full.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# JS 정적 — 날 고르기
# --------------------------------------------------------------------------- #
def _day_js_problems(src: str) -> list[str]:
    """날 고르기 JS 의 약속 — 빈 목록이면 통과."""
    problems = []
    select = src[src.index("function selectDay("):]
    select = select[:select.index("\n  }\n") + 4]
    if not ("markDay(key)" in select and select.index("markDay(key)") < select.index("fetchDay(key, href)")):
        problems.append("누르는 즉시 켜짐 표시를 먼저 바꾸지 않는다")
    if not ("if (dayPane(key)) {" in select and select.index("if (dayPane(key)) {") < select.index("fetchDay(key, href)")):
        problems.append("받은 날을 기억하지 않는다(다시 누르면 또 받는다)")
    if "panesBox.appendChild(pane)" not in src:
        problems.append("받은 장을 화면에 남기지 않는다")
    if f"var OFFLINE_TEXT = '{OFFLINE}';" not in src or "setDayBusy(false, OFFLINE_TEXT)" not in src:
        problems.append("실패하면 정해진 연결 안내 글을 띄우지 않는다")
    if "dayLoad.hidden = !on" not in src or "setDayBusy(true)" not in src:
        problems.append("받는 동안 표시가 없다")
    cached = select[select.index("if (dayPane(key)) {"):] if "if (dayPane(key)) {" in select else ""
    cached = cached[:cached.index("}") + 1] if cached else ""
    fetch_fn = src[src.index("function fetchDay("):src.index("function selectDay(")]
    if ("dropDayRequest();" not in cached or not fetch_fn.split("{", 1)[1].lstrip().startswith("dropDayRequest();")
            or ".abort()" not in src or "if (seq !== dayReq.seq" not in src):
        problems.append("받는 중에 또 누르면 앞 요청을 버리지 않는다(마지막 누름만)")
    if "res.headers.get(DAY_HEADER) !== key" not in src or "var DAY_HEADER = 'X-FOMS-HOME-DAY';" not in src:
        problems.append("받은 장이 고른 날인지 보지 않는다")
    if "url.searchParams.set('view', DAY_VIEW)" not in src or "var DAY_VIEW = 'day';" not in src:
        problems.append("조각 길(view=day)을 쓰지 않는다")
    if "window.history.replaceState(" not in src or "syncRenderedUrl" not in src:
        problems.append("주소의 day= 를 replaceState 로 남기지 않는다")
    if ("root.getAttribute('data-foms-home-days-bound') === '1') { return; }" not in src
            or src.count("root.addEventListener(") != 1):
        problems.append("같은 화면에 두 번 묶을 수 있다")
    if re.search(r"(?<![\w.])(const|let)\s", src):
        problems.append("셸 교체로 다시 실행되면 const/let 이 깨진다 — var 만")
    if "document.addEventListener(" in src or "window.addEventListener(" in src or "setInterval(" in src:
        problems.append("화면마다 도는 파일이 전역 리스너 · 타이머를 단다")
    return problems


def test_day_pick_js_keeps_its_promises():
    assert _day_js_problems(DAYS_JS.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("old, new, expect", [
    ("    if (dayPane(key)) {\n", "    if (false) {\n", "기억하지 않는다"),
    ("setDayBusy(false, OFFLINE_TEXT)", "setDayBusy(false, '')", "연결 안내 글"),
    ("      dropDayRequest();\n      setDayBusy(false);", "      setDayBusy(false);", "앞 요청"),
    ("  var DAY_VIEW = 'day';", "  const DAY_VIEW = 'day';", "var 만"),
    ("  if (!root || root.getAttribute('data-foms-home-days-bound') === '1') { return; }\n", "  if (!root) { return; }\n",
     "두 번 묶을"),
])
def test_day_pick_js_negative_controls(old, new, expect):
    src = DAYS_JS.read_text(encoding="utf-8")
    assert src.count(old) >= 1, old
    problems = _day_js_problems(src.replace(old, new))
    assert any(expect in p for p in problems), problems


def test_home_js_binds_globals_once_and_screen_once():
    src = HOME_JS.read_text(encoding="utf-8")
    assert "if (!root || root.getAttribute('data-foms-home-bound') === '1') { return; }" in src
    once = src[src.index("if (!G.once) {"):]
    for needle in ("window.addEventListener('resize'", "window.addEventListener('online'",
                   "window.addEventListener('offline'", "window.setInterval("):
        assert src.count(needle) == 1 and needle in once, needle  # 문서에 한 번
    assert "selectDay" not in src and "data-foms-home-daybtn" not in src  # 날 고르기는 한 파일만 묶는다(두 번 토글 금지)
    assert not re.search(r"(?<![\w.])(const|let)\s", src)
    # [다시 받기]는 셸이 있으면 캐시 없이 셸 조각으로, 화면 탭은 누르는 즉시 켜짐
    assert "shell.navigateByShell(reload.href, { bypassCache: true, replaceHistory: true })" in src
    assert "n.classList.toggle('is-on', n === navTab)" in src


@pytest.mark.parametrize("name, guard", [
    ("foms-production-parts-viewer.js", "if (bound.viewer === root) { return; }"),
    ("foms-production-parts.js", "if (bound.write === root || board.root !== root) { return; }"),
    ("foms-production-parts-sync.js", "if (bound.sync === root) { return; }"),
])
def test_parts_scripts_rebind_on_new_screen_only(name, guard):
    """셸 교체로 새 화면이 오면 새 화면에 묶고(옛 '한 번만' 가드는 새 화면을 버렸다), 문서 리스너 · 타이머는 하나."""
    src = (JS_DIR / name).read_text(encoding="utf-8")
    assert guard in src
    assert src.count("document.addEventListener(") <= 2 and "window.addEventListener(" not in src
    if "document.addEventListener(" in src:
        assert "if (!bound.viewerDoc) {" in src  # viewer 만 문서 리스너(Esc · 카드 고침)를 문서에 한 번
    assert not re.search(r"(?<![\w.])(const|let)\s", src)


def test_day_links_are_not_swapped_by_shell_and_reload_bypasses_cache():
    tpl = (ROOT / "templates/production/partials/home_date.html").read_text(encoding="utf-8")
    links = re.findall(r"<a [^>]*data-foms-home-daybtn[^>]*>", tpl)
    assert len(links) == 2 and all('data-foms-erp-no-shell="1"' in a and 'href="{{ home_href(tab, ' in a for a in links)
    assert "<button" not in tpl
    body = (ROOT / "templates/production/partials/home_body.html").read_text(encoding="utf-8")
    assert 'data-foms-home-reload data-foms-erp-no-shell="1" href=' in body


# --------------------------------------------------------------------------- #
# ③ 셸 — erp-shell.js
# --------------------------------------------------------------------------- #
def test_shell_swaps_and_prefetches_production_home():
    src = SHELL_JS.read_text(encoding="utf-8")
    assert "var LINKED_FRESH_PATHS = ['/erp/production/home'];" in src
    sub = src[src.index("function isSubordinateShellFragmentPath(url)"):src.index("function isShellFragmentSwapUrl(url)")]
    assert "LINKED_FRESH_PATHS.indexOf(p) >= 0" in sub  # 조각 교체 대상
    assert "LINKED_FRESH_PATHS.indexOf(path) >= 0 ? FRESH_TTL_MS" in src  # 생산 첫 화면도 60초 신선도
    linked = src[src.index("function visibleLinkedFreshPaths()"):src.index("function isFragmentReadyPath(url)")]
    assert "getClientRects().length > 0" in linked and "p === cur" in linked  # 보이는 링크 · 지금 화면 제외
    idle = src[src.index("function scheduleIdlePrimaryPrefetch()"):src.index("function onAnchorHoverFocus(ev)")]
    fresh = src[src.index("function runFreshHeartbeat()"):src.index("function onShellActivity()")]
    focus = src[src.index("function refreshFreshTtlSurfaces()"):src.index("document.addEventListener('visibilitychange'")]
    for name, block in (("첫 웜업", idle), ("fresh 하트비트", fresh), ("복귀 재수혈", focus)):
        assert "visibleLinkedFreshPaths()" in block, name
    # 9탭 계약은 그대로(생산 첫 화면은 9탭 밖 하위 조각) · 보드는 여전히 FRESH
    assert "/erp/production/home" not in enc.ERP_FRAGMENT_READY_PATHS
    layout = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(encoding="utf-8")
    assert "js/runtime/erp-shell.js') }}?v=20261114a" in layout


def test_rail_production_button_goes_to_home_href():
    """레일 생산 단추 주소 = 셸이 조각 교체로 아는 주소(같은 문자열이어야 셸이 가로챈다)."""
    from foms.services.production.home_access import PRODUCTION_HOME_PATH

    src = SHELL_JS.read_text(encoding="utf-8")
    assert f"'{PRODUCTION_HOME_PATH}'" in src


@pytest.mark.parametrize("name", ["foms-production-home.js", "foms-production-home-days.js", "foms-production-parts.js",
                                  "foms-production-parts-viewer.js", "foms-production-parts-sync.js"])
def test_home_js_syntax_and_300_line_ratchet(name):
    path = JS_DIR / name
    assert len(path.read_text(encoding="utf-8").splitlines()) < 300, name
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    proc = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_shell_js_syntax():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    proc = subprocess.run([node, "--check", str(SHELL_JS)], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr


def test_home_urls_are_built_in_one_place():
    """주소(tab · part · day)는 home_href 매크로 한 곳 — 템플릿 · JS 가 따로 짓지 않는다(viewer 의 옛 날 주소 짓기 제거)."""
    tpl_dir = ROOT / "templates/production"
    pages = [tpl_dir / "home.html", *sorted((tpl_dir / "partials").glob("home_*.html"))]  # 첫 화면 몸통 · 조각
    builders = [p.relative_to(ROOT).as_posix() for p in pages
                if "url_for('erp_production_page.erp_production_home'" in p.read_text(encoding="utf-8")]
    assert builders == ["templates/production/partials/home_date_macros.html"], builders
    for name in ("home_body.html", "home_date.html", "home_parts.html"):
        assert "import home_href" in (tpl_dir / "partials" / name).read_text(encoding="utf-8"), name
    viewer = (JS_DIR / "foms-production-parts-viewer.js").read_text(encoding="utf-8")
    assert "keepPartsTabUrl" not in viewer and "?tab=parts&part=" not in viewer
    assert "'?day='" not in HOME_JS.read_text(encoding="utf-8")


def test_home_href_rules(client, cohort):
    _order("오늘집", _files("ot", 1))
    _login(client, _user("관리자", team="CS", role="ADMIN"))
    html = _get(client, HOME + f"?tab=parts&part=edge&day={_day(1)}")
    reload = re.search(r'<a [^>]*data-foms-home-reload[^>]*>', html).group(0)
    assert f'href="{HOME}?tab=parts&amp;part=edge&amp;day={_day(1)}"' in reload
    edge = re.search(r'<a class="pp-part[^"]*"[^>]*>엣지</a>', html).group(0)
    assert f'href="{HOME}?tab=parts&amp;part=edge&amp;day={_day(1)}"' in edge
    steps = _get(client, HOME + "?tab=steps")
    assert f'data-foms-home-reload data-foms-erp-no-shell="1" href="{HOME}?tab=steps"' in steps  # 날 · 파트 없음


def test_press_feedback_bar_height_and_lazy_paint_css():
    home = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    parts = (ROOT / "static/css/contexts/production/parts.css").read_text(encoding="utf-8")
    assert ".fph-sd:active, .fph-sf:active {" in home and ".foms-prod-home__navtab:active {" in home
    assert ".pp-part:active {" in parts
    wide = home.split("@media (min-width: 992px) {", 1)[1].split("}\n}", 1)[0]
    assert ".foms-prod-home__bar { flex-wrap: nowrap; }" in wide  # 제목 줄 한 줄 고정 — 자리 이동 없음
    assert "top: var(--fph-bar-h, 73px);" in home
    assert ".pp-card { content-visibility: auto; contain-intrinsic-size: auto 312px; }" in parts
    assert "content-visibility: auto;" in home.split(".fph-dr {", 1)[1].split("}", 1)[0]
    assert 'loading="lazy"' in (ROOT / "templates/production/partials/home_parts.html").read_text(encoding="utf-8")
    js = HOME_JS.read_text(encoding="utf-8")
    assert "t.closest('.foms-prod-home__navtab, .pp-part')" in js  # 누르는 즉시 켜짐(화면 탭 · 파트 고르기)
