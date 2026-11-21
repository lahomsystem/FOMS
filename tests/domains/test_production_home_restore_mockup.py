"""생산 첫 화면 — 시안 안 3 대로 되돌리기(2026-11-21 사용자 결정, 견주기 시안 docs/design/mockups/tablet-production-home-restore-compare.html Ⓑ).

① 시공일 띠는 늘 한 줄에 하루씩(CSS 시험은 test_production_home_fixes 의 띠 시험) ② 위 탭 = 날짜 · 내 공정 · 바뀐 것 · 찾기 —
'도면 카드' 탭은 그날 제목 옆 [도면 카드로 보기](관리자 · 읽기 전용 + 태블릿)로, 옛 보드 [보드 →] 는 태블릿 첫 화면에서 뺐다
(보드 화면은 PC · 폰 메뉴의 생산 화면으로 남는다) ③ 생산 화면(첫 화면 · 전체 화면 시트)에서만 레일의 계산기 · 회사 지식 · 알림을
CSS 로 숨기고 알림 종은 위 줄로 — 레일 조각은 모든 화면에서 같은 글이다.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from foms.services.common.erp_navigation_contract import ERP_PRIMARY_NAV_PATHS
from foms.services.datetime_kst import get_today_kst
from foms.services.foms_split_view import _CALCULATOR_ITEM
from tests.domains.test_production_parts_screen import _files, _get, _login, _order, _seed_day, _user, cohort  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
HOME = "/erp/production/home"
BOARD = "/erp/production/dashboard"
HOME_CSS = ROOT / "static/css/contexts/production/home.css"
SHEET_CSS = ROOT / "static/css/contexts/production/sheet.css"
TABLET = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {"


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


def _nav(html: str) -> str:
    nav = html[html.index('class="foms-prod-home__nav"'):]
    return nav[: nav.index("</nav>")]


def _tabs(html: str) -> list[str]:
    return [re.sub(r"<small[^>]*>.*?</small>|<[^>]+>", "", m).strip() for m in re.findall(r'<a class="foms-prod-home__navtab[^"]*"[^>]*>(.*?)</a>', _nav(html), re.S)]


def _parts_links(html: str) -> list[str]:
    return re.findall(r'<a class="fph-pane__cards" data-foms-home-partslink href="([^"]+)">도면 카드로 보기<svg', html)


def _rail(html: str) -> str:
    rail = html[html.index('<nav class="foms-tablet-rail"'):]
    return rail[: rail.index("</nav>") + len("</nav>")]


def _tablet_rules(css: str) -> str:
    return "\n".join(part.split("\n}\n", 1)[0] for part in css.split(TABLET)[1:])


# --------------------------------------------------------------------------- #
# ② 위 탭
# --------------------------------------------------------------------------- #
def test_태블릿_위_탭은_넷이고_도면_카드_보드가_없다_파트_계정은_셋(client, cohort):
    _order("한빛", _files("oa", 2))
    _login(client, _user("관리자", team="CS", role="ADMIN"))
    for url in (HOME, HOME + "?tab=steps", HOME + "?tab=changes", HOME + "?tab=all"):
        html = _get(client, url)
        assert _tabs(html) == ["날짜", "내 공정", "바뀐 것", "찾기"], url
        assert "data-foms-home-partstab" not in html and "data-foms-home-board" not in html and f'href="{BOARD}"' not in _nav(html)
    _login(client, _user("김재단", part="cut"))  # 파트 계정은 '내 공정' 이 원래 없다(D50) — 셋
    assert _tabs(_get(client, HOME)) == ["날짜", "바뀐 것", "찾기"]


def test_도면_카드_화면은_주소로_그대로_열리고_날짜_탭이_켜진다(client, cohort):
    me, park = _user("김재단", part="cut"), _user("박재단", part="cut")
    _seed_day(me, park)
    _login(client, _user("관리자", team="CS", role="ADMIN"))
    html = _get(client, HOME + f"?tab=parts&part=cut&day={_day(0)}")
    assert 'data-foms-home-tab="parts"' in html and "data-pp-card " in html and 'data-pp-pane="' in html
    on = re.findall(r'<a class="foms-prod-home__navtab is-on"[^>]*>([^<]+)', _nav(html))
    assert on == ["날짜"] and _parts_links(html) == []  # 카드 화면에는 단추가 없다(판만)


# --------------------------------------------------------------------------- #
# ② [도면 카드로 보기]
# --------------------------------------------------------------------------- #
def test_도면_카드로_보기는_관리자_읽기_전용_태블릿에_고른_날_그대로(client, cohort):
    _order("한빛", _files("oa", 2))
    _order("모레집", _files("om", 1), day=2)
    for who in (_user("관리자", team="CS", role="ADMIN"), _user("상담", team="CS"), _user("생산사람")):
        _login(client, who)
        html = _get(client, HOME)
        assert _parts_links(html) == [f"{HOME}?tab=parts&amp;part=cut&amp;day={_day(0)}"]
        # 단추는 그날 제목 줄 안(제목 · 작은 글 다음) — 띠에서 다른 날을 고르면 장을 바꿔 끼우며 단추의 날도 바뀐다
        h2 = re.search(r'<h2 class="fph-pane__h">.*?</h2>', html, re.S).group(0)
        assert h2.index("</small>") < h2.index("data-foms-home-partslink")
        assert _parts_links(_get(client, HOME + f"?day={_day(2)}")) == [f"{HOME}?tab=parts&amp;part=cut&amp;day={_day(2)}"]
        frag = _get(client, HOME + f"?day={_day(2)}&view=day")
        assert _parts_links(frag) == [f"{HOME}?tab=parts&amp;part=cut&amp;day={_day(2)}"]
    # 대조군: 단추가 가는 주소가 실제로 그날 카드 화면이다
    cards = _get(client, HOME + f"?tab=parts&part=cut&day={_day(2)}")
    assert f'data-pp-pane="{_day(2)}"' in cards


def test_도면_카드로_보기는_파트_계정_PC_폰에는_없다(client, cohort):
    _order("한빛", _files("oa", 2))
    _login(client, _user("김재단", part="cut"))  # 파트 계정 — 카드가 날짜 탭에 바로 나온다
    html = _get(client, HOME)
    assert _parts_links(html) == [] and "data-pp-card " in html
    admin = _user("관리자", team="CS", role="ADMIN")
    _login(client, admin, ptr="fine")  # 마우스 PC
    assert _parts_links(_get(client, HOME)) == []
    _login(client, admin)  # 폰 — 화면 긴 변 844 < 992 라 가로로 돌려도 카드를 못 본다
    client.set_cookie("foms_scr", "844", domain="localhost")
    assert _parts_links(_get(client, HOME)) == []
    client.set_cookie("foms_scr", "1176", domain="localhost")  # 대조군: 같은 사람 · 태블릿
    assert len(_parts_links(_get(client, HOME))) == 1


def test_도면_카드로_보기_꼴은_장갑_크기와_글자_배율(client) -> None:
    css = HOME_CSS.read_text(encoding="utf-8")
    rule = css.split(".fph-pane__cards {", 1)[1].split("}", 1)[0]
    assert "margin-left: auto;" in rule and "min-height: 44px;" in rule  # 제목 줄 오른쪽 끝 · 44px(D5)
    assert "font-size: calc(15px * var(--foms-fs, 1));" in rule


# --------------------------------------------------------------------------- #
# ③ 알림 종 — 위 줄
# --------------------------------------------------------------------------- #
def _bell(html: str, ns: str) -> str:
    m = re.search(rf'<button type="button" class="{ns}__btn {ns}__bell" data-foms-notif-open [^>]*>.*?</button>', html, re.S)
    assert m, ns
    return m.group(0)


def test_알림_종은_제목_줄_다시_받기_묶음에_레일과_같은_훅(client, cohort):
    _order("한빛", _files("oa", 1))
    _login(client, _user("관리자", team="CS", role="ADMIN"))
    html = _get(client, HOME)
    tools = html[html.index('class="foms-prod-home__tools"'):]
    tools = tools[: tools.index("</header>")]
    bell = _bell(tools, "foms-prod-home")
    # 레일 종과 같은 훅 — 여는 시트 · 미읽음 배지(공유 수를 mobile-notification.js 가 모든 배지에 그린다)
    assert 'aria-controls="erp-mobile-notification-sheet"' in bell and 'aria-haspopup="dialog"' in bell
    assert '<span class="foms-prod-home__bell-badge" data-foms-notif-badge hidden aria-hidden="true">0</span>' in bell
    rail_bell = re.search(r"<button[^>]*foms-tablet-rail__notify[^>]*>", _rail(html)).group(0)
    assert "data-foms-notif-open" in rail_bell and 'aria-controls="erp-mobile-notification-sheet"' in rail_bell
    # 시안 Ⓑ 순서: 받음 표시 · 종 · 글자 손잡이 · [다시 받기]
    order = [tools.index(k) for k in ("data-foms-home-sync", "data-foms-notif-open", "data-foms-fs-ctl", "data-foms-home-reload")]
    assert order == sorted(order)
    js = (ROOT / "static/js/foms/mobile-notification.js").read_text(encoding="utf-8")
    assert "document.querySelectorAll('[data-foms-notif-badge]')" in js and "closest('[data-foms-notif-open]')" in js


def test_전체_화면_시트도_위_줄에_종(client, cohort):
    order = _order("한빛", _files("oa", 1))
    _login(client, _user("관리자", team="CS", role="ADMIN"))
    html = _get(client, f"/erp/production/sheet/{order.id}")
    bar = html[html.index('class="foms-prod-page__bar"'):]
    bar = bar[: bar.index("</header>")]
    assert "data-foms-notif-badge" in _bell(bar, "foms-prod-page")
    assert "foms-prod-page-wrap" in html  # 몸통 표식 — sheet.css 가 이것으로 레일 셋을 숨긴다


def test_종은_가로_태블릿에서_레일이_보일_때만() -> None:
    for path, ns in ((HOME_CSS, "foms-prod-home"), (SHEET_CSS, "foms-prod-page")):
        css = path.read_text(encoding="utf-8")
        assert f".{ns}__btn.{ns}__bell {{ display: none; position: relative; width: 56px; padding: 0; }}" in css
        assert f".{ns}__bell-badge[hidden] {{ display: none; }}" in css
        show = f"body:has(.foms-tablet-rail) .{ns}__btn.{ns}__bell {{ display: inline-flex; }}"
        assert css.count(show) == 1 and show in _tablet_rules(css), path.name


# --------------------------------------------------------------------------- #
# ③ 레일 — 글은 모든 화면이 같고 생산 화면에서만 CSS 로 셋을 숨긴다
# --------------------------------------------------------------------------- #
def test_레일_글은_생산_첫_화면과_다른_화면이_바이트까지_같다(client, cohort):
    _order("한빛", _files("oa", 1))
    _login(client, _user("관리자", team="CS", role="ADMIN"))
    home = _rail(_get(client, HOME))
    # 같은 생산 강조(옛 보드) — 바이트까지 같다
    assert home == _rail(_get(client, BOARD))
    # 다른 탭 화면 — 강조 칸만 다르다(강조 표식을 지우면 같다)
    other = _rail(_get(client, "/erp/shipment"))

    def _plain(rail: str) -> str:
        return rail.replace(" is-active", "").replace('aria-current="page"', "")

    assert home != other and _plain(home) == _plain(other)
    # 숨길 셋은 글에 그대로 있다(지우면 레일 줄이기 규칙 · 칸 수가 화면마다 달라진다)
    assert f'href="{_CALCULATOR_ITEM["href"]}"' in home and "foms-tablet-rail__notify" in home
    tpl = (ROOT / "templates/partials/shared/foms_tablet_rail.html").read_text(encoding="utf-8")
    assert "production" not in tpl.split("<nav", 1)[1] and "prod-home" not in tpl  # 조각에 생산 갈래가 없다


def test_레일_셋은_생산_화면_몸통이_있을_때만_숨긴다() -> None:
    for path, marker in ((HOME_CSS, ".foms-prod-home-page"), (SHEET_CSS, ".foms-prod-page-wrap")):
        css = path.read_text(encoding="utf-8")
        hide = (f'  body:has({marker}) .foms-tablet-rail__menu > a[href="{_CALCULATOR_ITEM["href"]}"],\n'
                f"  body:has({marker}) .foms-tablet-rail > .foms-graft-rail,\n"
                f"  body:has({marker}) .foms-tablet-rail > .foms-tablet-rail__notify {{ display: none; }}")
        assert css.count(hide) == 1 and hide in _tablet_rules(css), path.name
        # 레일을 건드리는 규칙은 숨김 셋 + 종 보이기 하나뿐(다른 칸 · 레일 크기 규칙을 바꾸지 않는다)
        code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        assert len([ln for ln in code.splitlines() if "foms-tablet-rail" in ln]) == 4, path.name
    # 몸통 표식은 그 화면에만 있다
    body = (ROOT / "templates/production/partials/home_body.html").read_text(encoding="utf-8")
    assert "foms-prod-home-page" in body
    users = [p.relative_to(ROOT).as_posix() for p in (ROOT / "templates").rglob("*.html")
             if re.search(r"foms-prod-home-page|foms-prod-page-wrap", p.read_text(encoding="utf-8"))]
    assert sorted(users) == ["templates/production/partials/home_body.html", "templates/production/sheet.html"]
    # 다른 CSS 는 레일 알림 · 계산기를 숨기지 않는다
    for p in (ROOT / "static/css").rglob("*.css"):
        if p in (HOME_CSS, SHEET_CSS):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        assert 'a[href="/wdcalculator"]' not in text, p


# --------------------------------------------------------------------------- #
# 옛 보드 — 태블릿 첫 화면 문만 뺐고 화면 · 다른 문은 남는다(사용자 "필요없으면 삭제" → 필요해서 남김)
# --------------------------------------------------------------------------- #
def test_옛_보드는_PC_폰_메뉴의_생산_화면으로_남는다(client, cohort):
    assert BOARD in ERP_PRIMARY_NAV_PATHS  # PC 위 메뉴 · 레일 계약 · 셸 조각 대상
    shell = (ROOT / "templates/partials/shared/erp_mobile_shell.html").read_text(encoding="utf-8")
    assert "url_for('erp_production_page.erp_production_dashboard')" in shell  # 폰 아래 메뉴(생산팀 밖)
    sub = (ROOT / "templates/partials/shared/erp_sub_nav.html").read_text(encoding="utf-8")
    assert "url_for('erp_production_page.erp_production_dashboard')" in sub  # PC 위 메뉴
    _login(client, _user("관리자", team="CS", role="ADMIN"))
    resp = client.get(BOARD)
    assert resp.status_code == 200 and "foms-prod-home-page" not in resp.get_data(as_text=True)
