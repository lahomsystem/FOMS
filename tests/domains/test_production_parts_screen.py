"""생산 파트 도면 카드 화면 — 설계서 §15.6 · §15.7 '템플릿 렌더' · 'JS' · '작은 그림 길'(P15-5).

같은 주소(``/erp/production/home``)에서 파트 계정 + 태블릿(모바일 v2 셸 + ``foms_ptr`` 터치)이면 날짜 탭의 장마다 카드 판이
더 그려지고, 관리자 · 읽기 전용 직원은 '도면 카드' 탭(``?tab=parts&part=``)으로 본다. 규칙을 되돌리면 실패하게 짠다.
대조군: 관리자 · 파트 없는 생산 계정의 날짜 탭은 '도면 카드' 탭 단추 하나만 빼고 지금과 같다 · 마우스 기기(``fine``)는 카드 0 ·
세로는 CSS 로 지금 장(카드 판 숨김) · 남의 주문 · 옛 key · 그림 아닌 파일은 작은 그림 403/404.
"""
from __future__ import annotations

import colorsys
import datetime
import io
import re
import shutil
import subprocess
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Order, PartnerOrg, ProductionPartMark, User

ROOT = Path(__file__).resolve().parents[2]
HOME = "/erp/production/home"
PARTS_JS = ROOT / "static/js/production/foms-production-parts.js"
VIEWER_JS = ROOT / "static/js/production/foms-production-parts-viewer.js"
SYNC_JS = ROOT / "static/js/production/foms-production-parts-sync.js"
PARTS_CSS = ROOT / "static/css/contexts/production/parts.css"
TPL_DIR = ROOT / "templates/production/partials"
_seq = count(1)
_MONEY = "4,812,300"  # 시드 주문 금액 — 화면 어디에도 나오면 안 된다(D7)


# --------------------------------------------------------------------------- #
# 시드
# --------------------------------------------------------------------------- #
def _user(name: str, *, team: str | None = "PRODUCTION", role: str = "STAFF", part: str | None = None,
          partner_org_id: int | None = None) -> tuple[int, str, str]:
    user = User(username=f"pps_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part, partner_org_id=partner_org_id)
    db_session.add(user)
    db_session.commit()
    return user.id, user.username, user.role


def _login(client, who: tuple[int, str, str], *, ptr: str = "coarse") -> None:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = who
    client.set_cookie("foms_ptr", ptr, domain="localhost")


@pytest.fixture
def cohort(monkeypatch):
    """모바일 v2 셸 코호트(모두) — 태블릿 표면의 서버 문 하나."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _files(prefix: str, n: int, ext: str = "png") -> list[dict]:
    return [{"key": f"{prefix}/d{j}.{ext}", "filename": f"d{j}.{ext}", "sheet_id": f"{prefix}-s{j}"} for j in range(n)]


def _order(name: str, files: list[dict], *, stage: str = "PRODUCTION", day: int = 0) -> Order:
    when = (get_today_kst() + datetime.timedelta(days=day)).isoformat()
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": name, "phone": "010-0000-0000"}},
          "schedule": {"construction": {"date": when}}, "drawing_current_files": files,
          "items": [{"product_name": "붙박이장", "spec_width": "2400", "unit_price": 4812300, "price": "4,812,300"}],
          "payment": {"total_amount": 4812300, "total_display": _MONEY}}
    order = Order(received_date=when, customer_name=name, phone="010-0000-0000", address="서울", product="붙박이장",
                  status=stage, is_erp_order=True, erp_stage_code=stage, erp_construction_date=when, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order


def _mark(order: Order, key: str, part: str, state: str, *, picked: tuple | None = None, done: tuple | None = None,
          names: tuple[str | None, str | None] = (None, None), sheet_id: str | None = None) -> None:
    db_session.add(ProductionPartMark(
        order_id=order.id, drawing_key=key, part=part, state=state, sheet_id=sheet_id,
        picked_by_user_id=picked[0] if picked else None, picked_by_name=names[0],
        done_by_user_id=done[0] if done else None, done_by_name=names[1],
        updated_by_user_id=(done or picked)[0] if (done or picked) else None, updated_at=now_utc_naive(),
    ))
    db_session.commit()


def _seed_day(me: tuple, park: tuple) -> dict:
    """오늘 생산 주문 둘(3장 · 2장) + 도면 기다림 하나 — 김재단 맡음 1 · 박재단 맡음 1 · 김재단 끝 1 · 박재단 기본 1 · 안 봄 1."""
    a = _order("한빛", _files("oa", 3))
    b = _order("늘봄", _files("ob", 2))
    wait = _order("오하람", [], stage="DRAWING")
    _mark(a, "oa/d0.png", "cut", "NEED", picked=me, names=("김재단", None))
    _mark(a, "oa/d1.png", "cut", "NEED", picked=park, names=("박재단", None))
    _mark(a, "oa/d2.png", "cut", "DONE", picked=me, done=me, names=("김재단", "김재단"))
    _mark(b, "ob/d0.png", "cut", "BASIC", done=park, names=(None, "박재단"))
    return {"a": a.id, "b": b.id, "wait": wait.id}


def _today_pane(html: str) -> str:
    key = get_today_kst().isoformat()
    return html.split(f'data-foms-home-daypane="{key}"')[1].split("data-foms-home-daypane=")[0]


def _parts_block(pane: str) -> str:
    return pane.split('class="fph-parts"')[1].split('class="fph-pane__now"')[0]


def _get(client, url: str) -> str:
    resp = client.get(url)
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


# --------------------------------------------------------------------------- #
# 파트 계정 + 코호트
# --------------------------------------------------------------------------- #
def test_cut_account_sees_cards_view_buttons_bulk_and_one_modal(client, cohort):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    ids = _seed_day(me, park)
    _login(client, me)
    html = _get(client, HOME)
    pane = _today_pane(html)
    block = _parts_block(pane)

    assert block.count("data-pp-card ") == 5  # 확정 도면 한 장 = 카드 한 장(3 + 2)
    for view in ("all", "need", "done"):
        assert f'data-pp-view="{view}"' in block
    # 칸 숫자 = 내 것(작업 필요 = 내가 맡은 장, 완료 = 내가 끝낸 장)
    assert 'data-pp-count="all">5<' in block and 'data-pp-count="need">1<' in block and 'data-pp-count="done">1<' in block
    assert 'data-pp-act="bulk"' in block and "<span>남은 <span data-pp-count=\"unseen\">1</span>장 모두 기본</span>" in block
    assert block.count('data-pp-act="basic"') == 1 and block.count('data-pp-act="take"') == 1  # 안 본 장 하나
    assert "박재단 맡음" in block and "pp-st-taken" in block  # 남이 맡은 장 = 분홍 배지, 단추 없음
    assert "기본 · 박재단" in block and "재단 끝 · 김재단" in block
    # 지금 장은 그대로 그려 두고(세로 = 지금 화면) 감싼다
    assert 'class="fph-pane__now"' in pane and "fph-dr" in pane.split('class="fph-pane__now"')[1]
    assert 'class="fph-date has-parts"' in html
    # 맨 아래 '도면·컨펌 기다림' 연두 칩
    assert "pp-wait" in block and "오하람" in block and f"#{ids['wait']}" in block
    # 위 줄 = 파트 이름 + 내 이름, '내 공정' 탭 없음(D50)
    assert '<h1 class="foms-prod-home__title">재단 <span class="foms-prod-home__me">김재단</span></h1>' in html
    assert ">내 공정 <small>" not in html
    # 확인 창 하나 · id 겹침 0 · 금액 0
    assert html.count('id="foms-part-confirm-modal"') == 1
    ids_all = re.findall(r'\sid="([^"]+)"', html)
    assert len(ids_all) == len(set(ids_all)), [i for i in set(ids_all) if ids_all.count(i) > 1]
    assert _MONEY not in html and "4812300" not in html
    # 쓰기 JS · 보기 JS · CSS 핀
    assert "foms-production-parts.js') }}" not in html  # (렌더 결과에는 Jinja 가 없다 — 아래가 진짜 단언)
    assert re.search(r"js/production/foms-production-parts\.js\?v=\d{8}[a-z]\"", html)
    assert re.search(r"js/production/foms-production-parts-viewer\.js\?v=\d{8}[a-z]\"", html)
    assert re.search(r"css/contexts/production/parts\.css\?v=\d{8}[a-z]\"", html)


def test_other_part_has_no_basic_and_no_other_part_buttons(client, cohort):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    asm = _user("이조립", part="assemble")
    _seed_day(me, park)
    _login(client, asm)
    html = _get(client, HOME)
    block = _parts_block(_today_pane(html))
    assert block.count("data-pp-card ") == 5
    assert 'data-pp-act="basic"' not in block and 'data-pp-act="bulk"' not in block  # '기본'은 재단에만(D49)
    assert block.count('data-pp-act="take"') == 5 and "내가 조립" in block
    assert "시공 3건 · 도면 나온 2집" in block  # 그 밖 파트 장 머리(시공 = 그날 주문 전부, 도면 나온 집 = 카드가 선 집)
    # 다른 파트 한 줄은 누를 수 없는 글 — 그 안에 단추 0, 재단 낱말(끝 · 기본 · 중 · 안 봄)이 선다
    for line in re.findall(r'<span class="fph-dr__by pp-by">(.*?)</span></span>\s*<div class="pp-actbox"', block, re.S):
        assert "<button" not in line and "<a " not in line
    assert "<i>재단</i> 중" in block and "<i>재단</i> 기본" in block and "<i>재단</i> 안 봄" in block
    # 남의 파트 단추 0 — 카드 단추는 내 파트 동작 넷뿐이고 JS 설정의 파트는 내 파트
    acts = set(re.findall(r'data-pp-act="([a-z]+)"', html))
    assert acts <= {"take", "basic", "done", "undo", "bulk"}
    assert "&#34;part&#34;: &#34;assemble&#34;" in html


def test_part_account_steps_tab_hidden_and_redirected_on_any_device(client, cohort):
    me = _user("김재단", part="cut")
    _order("한빛", _files("oa", 1))
    for ptr in ("coarse", "fine"):
        _login(client, me, ptr=ptr)
        html = _get(client, HOME + "?tab=steps")
        assert 'data-foms-home-tab="date"' in html and ">내 공정 <small>" not in html
    # 대조군: 파트 없는 생산 계정은 '내 공정' 탭 그대로
    _login(client, _user("생산사람"))
    html = _get(client, HOME + "?tab=steps")
    assert 'data-foms-home-tab="steps"' in html and ">내 공정 <small>" in html


def test_part_account_on_mouse_device_gets_no_cards(client, cohort):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    _seed_day(me, park)
    _login(client, me, ptr="fine")
    html = _get(client, HOME)
    assert "data-pp-card" not in html and "fph-parts" not in html and "parts.css" not in html
    assert "foms-part-confirm-modal" not in html and "foms-production-parts" not in html
    assert '<h1 class="foms-prod-home__title">생산</h1>' in html


# --------------------------------------------------------------------------- #
# 관리자 · 읽기 전용 '도면 카드' 탭(D55)
# --------------------------------------------------------------------------- #
def test_admin_parts_tab_has_picker_and_chosen_part_buttons(client, cohort):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    _seed_day(me, park)
    _login(client, _user("관리자", team="CS", role="ADMIN"))
    date_html = _get(client, HOME)
    assert "data-foms-home-partstab" in date_html and "data-pp-card" not in date_html  # 날짜 탭은 지금 그대로 + 탭 하나

    html = _get(client, HOME + "?tab=parts&part=cut")
    pane = _today_pane(html)
    assert 'data-foms-home-tab="parts"' in html and 'class="fph-pane__now"' not in pane  # 고른 파트 한 판만
    picker = pane.split('class="pp-parts"')[1].split("</nav>")[0]
    assert [p for p in ("재단", "엣지", "조립", "검수") if f">{p}</a>" in picker] == ["재단", "엣지", "조립", "검수"]
    assert re.search(r'class="pp-part is-on"[^>]*tab=parts&amp;part=cut', picker)
    # 관리자 칸 숫자 = 그 파트 전체(맡은 장 둘 · 끝난 장 둘), 남이 맡은 장도 [재단 완료] 단추가 있다
    assert 'data-pp-count="need">2<' in pane and 'data-pp-count="done">2<' in pane
    assert pane.count('data-pp-act="done"') == 2 and pane.count('data-pp-act="undo"') == 2
    assert html.count('id="foms-part-confirm-modal"') == 1 and "foms-production-parts.js?v=" in html

    html = _get(client, HOME + "?tab=parts&part=assemble")
    pane = _today_pane(html)
    assert "내가 조립" in pane and 'data-pp-act="basic"' not in pane
    assert '"part": "assemble"' in html.replace("&#34;", '"')


def test_readonly_staff_sees_badges_only_no_modal_no_write_binding(client, cohort):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    _seed_day(me, park)
    _login(client, _user("상담", team="CS"))
    html = _get(client, HOME + "?tab=parts&part=cut")
    pane = _today_pane(html)
    assert pane.count("data-pp-card ") == 5
    assert 'data-pp-act="' not in html and '<button type="button" class="foms-prod-home__btn' not in pane.split("pp-grid")[1]
    assert "foms-part-confirm-modal" not in html and "data-pp-modal" not in html
    # P15-7: 카드 고치기(parts.js 의 window.FomsPartsCards)를 30초 받아 오기가 같이 쓰므로 읽기 전용에도 싣는다 —
    # 확인 창이 없어 누름 · 쓰기는 묶이지 않는다(test_production_part_marks_sync.py 가 정적으로 본다).
    assert "foms-production-parts.js?v=" in html and "foms-production-parts-viewer.js?v=" in html
    assert "foms-production-parts-sync.js?v=" in html
    assert "작업 필요 · 김재단" in pane and "작업 필요 · 박재단" in pane and "기본 · 박재단" in pane


def test_parts_tab_needs_tablet_and_staff(client, cohort):
    _order("한빛", _files("oa", 1))
    admin = _user("관리자", team="CS", role="ADMIN")
    _login(client, admin, ptr="fine")  # 마우스 PC — 탭 없음, 주소로 와도 날짜
    html = _get(client, HOME + "?tab=parts")
    assert "data-foms-home-partstab" not in html and 'data-foms-home-tab="date"' in html and "data-pp-card" not in html
    _login(client, _user("김재단", part="cut"))  # 파트 계정은 '도면 카드' 탭이 아니라 날짜 탭에서 본다
    html = _get(client, HOME + "?tab=parts")
    assert "data-foms-home-partstab" not in html and 'data-foms-home-tab="date"' in html and "data-pp-card" in html


# --------------------------------------------------------------------------- #
# 대조군 — 파트 없는 계정의 날짜 탭은 탭 단추 하나만 빼고 지금과 같다
# --------------------------------------------------------------------------- #
def _normalize(html: str) -> str:
    html = re.sub(r'data-loaded-at="[^"]*"', "", html)
    html = re.sub(r"\d\d:\d\d 에 받음|\d\d:\d\d 에 받은", "HH:MM", html)
    html = re.sub(r'content="[0-9a-f]{20,}[^"]*"', "", html)  # csrf 토큰
    return re.sub(r'nonce="[^"]*"', "", html)


@pytest.mark.parametrize("who", ["admin", "prod"])
def test_date_tab_html_equals_before_except_parts_tab(client, cohort, monkeypatch, who):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    _seed_day(me, park)
    account = _user("관리자", team="CS", role="ADMIN") if who == "admin" else _user("생산사람")
    _login(client, account)
    now = _normalize(_get(client, HOME))
    tab_line = re.search(r'\n\s*<a class="foms-prod-home__navtab" data-foms-home-partstab [^\n]*</a>', now)
    assert tab_line, "태블릿 코호트 직원에게는 '도면 카드' 탭이 있어야 한다"
    # 파트 규칙을 끈 화면 = P15-5 전 화면(판 · 탭 · '내 공정' 숨김 모두 없음)
    monkeypatch.setattr("foms.web.production.home.part_view_mode", lambda user: "none")
    before = _normalize(_get(client, HOME))
    assert now.replace(tab_line.group(0), "") == before
    assert ">내 공정 <small>" in now and "fph-pane__now" not in now and "parts.css" not in now


# --------------------------------------------------------------------------- #
# 세로 · PC 는 CSS 로 지금 장 — 카드 판은 태블릿 가로 미디어쿼리 안에서만 보인다
# --------------------------------------------------------------------------- #
def test_parts_css_shows_board_only_in_tablet_landscape():
    css = PARTS_CSS.read_text(encoding="utf-8")
    head, _, rest = css.partition("@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {")
    media, _, tail = rest.partition("\n}\n")
    assert ".fph-parts { display: none; }" in head
    assert ".fph-parts { display: flex;" in media and ".fph-date.has-parts .fph-pane__now { display: none; }" in media
    assert "fph-pane__now" not in head and "fph-pane__now" not in tail  # 세로 · PC 에서는 지금 장을 숨기지 않는다


def test_parts_css_fonts_tokens_and_no_achromatic_badges():
    css = PARTS_CSS.read_text(encoding="utf-8")
    sizes = re.findall(r"font-size:\s*([^;}]+)", css)
    assert sizes and all(re.fullmatch(r"calc\((\d+)px \* var\(--foms-fs, 1\)\)", s.strip()) for s in sizes), sizes
    assert min(int(re.search(r"(\d+)px", s).group(1)) for s in sizes) >= 13
    for token in ("--fph-need-50: #c5c9ff", "--fph-taken-50: #eecbda", "--fph-taken-700: #7a3f5c", "--fph-done-50: #a7f3d0",
                  "--fph-done-700: #047857", "--fph-basic-50: #ccedff", "--fph-basic-700: #075985", "--fph-wait-50: #eeebb2",
                  "--fph-wait-700: #57571f"):
        assert token in css
    tokens = dict(re.findall(r"(--fph-[a-z]+-\d+):\s*(#[0-9a-f]{6})", css))
    for sel in (".fph-wi.pp-st-need", ".fph-wi.pp-st-taken", ".fph-wi.pp-st-done", ".fph-wi.pp-st-basic", ".fph-wi.pp-wait"):
        rule = re.search(re.escape(sel) + r" \{([^}]*)\}", css).group(1)
        bg = tokens[re.search(r"background: var\((--fph-[a-z]+-\d+)\)", rule).group(1)]
        _, _, sat = colorsys.rgb_to_hls(*(int(bg[i:i + 2], 16) / 255 for i in (1, 3, 5)))
        assert sat >= 0.3, f"{sel} 배지 바탕이 무채색이에요(D52): {bg} 채도 {sat:.2f}"
    assert "style=" not in (TPL_DIR / "home_parts.html").read_text(encoding="utf-8")
    for name in ("home_parts.html", "home_parts_overlays.html"):
        src = (TPL_DIR / name).read_text(encoding="utf-8")
        assert "style=" not in src and "<script" not in src and "onclick" not in src


def test_home_template_pins_parts_assets():
    # 전체 페이지(home.html)와 셸 조각(home_fragment.html)이 같은 두 조각을 싣는다 — 핀은 한 곳
    tpl = "".join((ROOT / f"templates/production/partials/home_{name}.html").read_text(encoding="utf-8")
                  for name in ("styles", "scripts"))
    for rel in ("templates/production/home.html", "templates/production/partials/home_fragment.html"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "home_styles.html" in text and "home_scripts.html" in text and "home_body.html" in text, rel
    assert re.search(r"css/contexts/production/parts\.css'\) \}\}\?v=\d{8}[a-z]", tpl)
    assert re.search(r"js/production/foms-production-parts-viewer\.js'\) \}\}\?v=\d{8}[a-z]\" defer", tpl)
    assert re.search(r"js/production/foms-production-parts\.js'\) \}\}\?v=\d{8}[a-z]\" defer", tpl)
    assert re.search(r"js/production/foms-production-parts-sync\.js'\) \}\}\?v=\d{8}[a-z]\" defer", tpl)


# --------------------------------------------------------------------------- #
# JS
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path", [PARTS_JS, VIEWER_JS, SYNC_JS], ids=["parts", "viewer", "sync"])
def test_parts_js_syntax_and_size(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) < 300, f"{path.name} {len(lines)}줄 — 새 JS 300줄 래칫"
    assert "window.__FOMS_PROD_PARTS_BOUND" in "\n".join(lines)
    assert "location.reload" not in "\n".join(lines)
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def _function_body(src: str, name: str) -> str:
    start = src.index(f"function {name}(")
    depth, i = 0, src.index("{", start)
    for j in range(i, len(src)):
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        if depth == 0:
            return src[i:j + 1]
    raise AssertionError(name)


def test_writes_only_go_through_confirm_modal_run_button():
    src = PARTS_JS.read_text(encoding="utf-8")
    # 쓰기 요청을 만드는 곳은 post() 하나, post() 를 부르는 곳은 send() 하나, send() 를 부르는 곳은 확인 창 실행 단추 하나
    assert len(re.findall(r"fomsMutationFetch\s*\|\||fetch\(u, o\)", src)) == 2 and "fetch(u, o)" in _function_body(src, "post")
    calls = [m.start() for m in re.finditer(r"(?<![\w.])post\(", src)]
    assert len(calls) == 2 and "post(req.url" in _function_body(src, "send")  # 정의 1 + 부름 1
    send_calls = [line for line in src.splitlines() if re.search(r"(?<![\w.])(?<!function )send\(\)", line)]
    assert send_calls == ["    if (t.closest('[data-pp-modal-run]')) { send(); return; }"]
    assert "body.success === true" in _function_body(src, "handle")
    viewer = VIEWER_JS.read_text(encoding="utf-8")
    assert not re.search(r"fetch\s*\(|fomsMutationFetch|XMLHttpRequest|sendBeacon", viewer), "보기 JS 에 쓰기 요청이 있으면 안 된다"
    sync = SYNC_JS.read_text(encoding="utf-8")
    assert not re.search(r"POST|fomsMutationFetch|XMLHttpRequest|sendBeacon|part-marks/basic", sync), "받아 오기 JS 는 읽기만"



# --------------------------------------------------------------------------- #
# 작은 그림 길
# --------------------------------------------------------------------------- #
class _FakeStorage:
    """원본 바이트를 key 로 돌려주고, 작은 그림 저장을 기억하는 가짜 저장소."""

    def __init__(self, files: dict[str, bytes]):
        self.files = dict(files)
        self.reads: list[str] = []
        self.puts: dict[str, bytes] = {}

    def object_exists(self, key):
        return key in self.puts

    def read_file_bytes(self, key):
        self.reads.append(key)
        return self.puts.get(key) or self.files.get(key)

    def put_private_bytes(self, key, data, content_type):
        assert content_type == "image/jpeg"
        self.puts[key] = data
        return True


def _transparent_png(w: int = 1500, h: int = 600) -> bytes:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))  # 투명(그냥 RGB 로 바꾸면 검정이 된다)
    for x in range(w // 3, 2 * w // 3):
        for y in range(h // 3, 2 * h // 3, 7):
            img.putpixel((x, y), (20, 20, 20, 255))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def storage(monkeypatch):
    fake = _FakeStorage({"oa/d0.png": _transparent_png(), "oa/d1.png": _transparent_png(), "ob/d0.png": _transparent_png(),
                         "oc/d0.pdf": b"%PDF-1.4"})
    monkeypatch.setattr("foms.web.production.part_thumb.get_storage", lambda: fake)
    return fake


def _thumb(client, order_id: int, key: str):
    return client.get(f"/erp/production/parts/thumb/{order_id}?key={key}")


def test_thumb_is_white_backed_720_jpeg_cached_once(client, storage):
    order = _order("한빛", _files("oa", 2))
    _login(client, _user("김재단", part="cut"))
    resp = _thumb(client, order.id, "oa/d0.png")
    assert resp.status_code == 200 and resp.mimetype == "image/jpeg"
    cc = resp.headers["Cache-Control"]
    assert "immutable" in cc and "max-age=2592000" in cc and "private" in cc
    img = Image.open(io.BytesIO(resp.data))
    assert img.size == (720, 288)
    assert all(v >= 250 for v in img.convert("RGB").getpixel((0, 0)))  # 투명 칸 = 흰색(검정 함정 아님)
    assert all(v >= 250 for v in img.convert("RGB").getpixel((719, 287)))
    assert list(storage.puts) == ["oa/pthumb720_d0.png.jpg"]
    storage.reads.clear()
    again = _thumb(client, order.id, "oa/d0.png")
    assert again.status_code == 200 and again.data == resp.data
    assert storage.reads == ["oa/pthumb720_d0.png.jpg"]  # 두 번째는 저장본만 — 원본을 다시 읽지 않는다


def test_thumb_refuses_other_order_old_key_non_image_and_outsiders(client, storage):
    a, b, pdf = _order("한빛", _files("oa", 1)), _order("늘봄", _files("ob", 1)), _order("서류", _files("oc", 1, ext="pdf"))
    a_id, b_id, pdf_id, a_sd = a.id, b.id, pdf.id, dict(a.structured_data)
    a, b, pdf = SimpleNamespace(id=a_id), SimpleNamespace(id=b_id), SimpleNamespace(id=pdf_id)
    _login(client, _user("김재단", part="cut"))
    assert _thumb(client, a.id, "ob/d0.png").status_code == 404  # 남의 주문 key
    assert _thumb(client, a.id, "oa/d1.png").status_code == 404  # 지금 확정 도면이 아닌 key(교체된 옛 key 꼴)
    assert _thumb(client, pdf.id, "oc/d0.pdf").status_code == 404  # 그림이 아닌 파일 → 카드는 파일 표
    assert _thumb(client, a.id, "").status_code == 404
    assert _thumb(client, 999999, "oa/d0.png").status_code == 404
    # 교체: 같은 주문 확정 도면이 새 key 로 바뀌면 옛 key 는 404
    sd = a_sd
    sd["drawing_current_files"] = [{"key": "oa/d1.png", "filename": "d1.png"}]
    db_session.query(Order).filter(Order.id == a.id).update({"structured_data": sd})
    db_session.commit()
    assert _thumb(client, a.id, "oa/d0.png").status_code == 404 and _thumb(client, a.id, "oa/d1.png").status_code == 200
    assert _thumb(client, b.id, "ob/d0.png").status_code == 200  # 대조군
    # 협력사 계정 · 켜진 프리랜서는 앞 문지기가 먼저 돌려보낸다(그림 바이트 0)
    org = PartnerOrg(name=f"협력{next(_seq)}")
    db_session.add(org)
    db_session.commit()
    _login(client, _user("협력직원", team=None, role="PARTNER", partner_org_id=org.id))
    refused = _thumb(client, b.id, "ob/d0.png")
    assert refused.status_code in (302, 403) and refused.mimetype != "image/jpeg"  # 협력사 문지기가 먼저 돌려보낸다
    fl = _user("프리영업", team="SALES")
    save_freelancer(db_session, fl[0], {"match_name": f"프리{next(_seq)}", "start_month": "2020-01", "tax_type": "NONE",
                                        "active": True}, base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    _login(client, fl)
    refused = _thumb(client, b.id, "ob/d0.png")
    assert refused.status_code in (302, 403, 404) and refused.mimetype != "image/jpeg"  # 프리랜서 문지기(남의 주문)
    # 우리 직원이라도 생산 첫 화면을 볼 수 없는 팀이면 이 길의 문지기가 403
    _login(client, _user("도면사람", team="DRAWING"))
    assert _thumb(client, b.id, "ob/d0.png").status_code == 403


def test_cards_point_images_at_thumb_route_lazily(client, cohort):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    ids = _seed_day(me, park)
    _order("서류", _files("oc", 1, ext="pdf"))
    _login(client, me)
    block = _parts_block(_today_pane(_get(client, HOME)))
    imgs = re.findall(r'<img class="pp-thumb" src="([^"]+)" loading="lazy"', block)
    assert len(imgs) == 5 and f"/erp/production/parts/thumb/{ids['a']}?key=oa/d0.png" in [i.replace("%2F", "/") for i in imgs]
    assert 'class="pp-img pp-file" href="/api/files/view/oc/d0.pdf"' in block and "<b>PDF</b>" in block


def test_replaced_drawing_line_and_cap_notice(client, cohort, monkeypatch):
    """바뀐 도면(D56) 한 줄 · 200장 캡은 조용히 자르지 않고 글로 알린다(§15.6 안전 캡)."""
    me = _user("김재단", part="cut")
    order = _order("한빛", _files("oa", 3))
    # 옛 판(교체돼 지금 확정 도면에 없는 key)에 같은 시트 신원으로 재단 끝 — 새 판 카드에 전 판 진행 한 줄
    _mark(order, "oa/old0.png", "cut", "DONE", picked=me, done=me, names=("김재단", "김재단"), sheet_id="oa-s0")
    _login(client, me)
    block = _parts_block(_today_pane(_get(client, HOME)))
    assert block.count('class="pp-replaced"') == 1 and "바뀐 도면 · 전 판 재단 끝(김재단)" in block
    assert 'data-pp-count="unseen">3<' in block  # 새 판은 안 봄부터
    monkeypatch.setattr("foms.services.production.part_board.PART_BOARD_CARD_CAP", 2)
    block = _parts_block(_today_pane(_get(client, HOME)))
    assert block.count("data-pp-card ") == 2 and "더 있는 1장은 안 보여요" in block
    assert 'data-pp-count="all">3<' in block  # 숫자는 캡과 무관하게 모두 센다
