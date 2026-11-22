"""생산팀 첫 화면 리뷰·실측 고침 시험 — :mod:`tests.domains.test_production_home_tabs` 에서 옮겼다(파일 500줄 래칫).

공용 도우미(``_make_user`` · ``_add_order`` · ``_pane`` · ``ROOT`` · ``HOME``)는 원래 파일에서 가져온다.
"""

from __future__ import annotations

import datetime
import re

from foms.api.production.orders import _PRODUCTION_STEP_DEFS
from foms.services.datetime_kst import get_today_kst
from foms.services import production_home_read_model
from foms.services import production_home_days as production_home_days_module
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import (
    production_home_counts,
    production_home_stage,
    production_home_step_queues,
)
from tests.domains.test_production_home_tabs import HOME, ROOT, _add_order, _make_user, _pane


# ── 리뷰 고침 묶음(원장 §16 R1·R2·R3·R5·R10, 2026-11-10) ──

def _reload_href(html: str) -> str:
    return re.search(r'data-foms-home-reload[^>]*? href="([^"]*)"', html).group(1)


def test_보류는_생산_단계만_도면_컨펌_보류는_기다림() -> None:
    steps = [{"key": "cut", "label": "재단", "done": False, "now": False}]
    assert production_home_stage("PRODUCTION", False, steps, True) == ("보류", "생산", "prod")
    assert production_home_stage("도면", False, steps, True) == ("도면 기다림", "도면팀", "wait")
    assert production_home_stage("CONFIRM", False, steps, True) == ("컨펌 기다림", "영업", "wait")
    assert production_home_stage("CONSTRUCTION", True, steps, True) == ("제작 완료", "시공 대기", "done")


def test_내_공정_탭_숫자는_공정_줄_합과_같다_보류_run_없음_포함(client) -> None:
    _make_user(client, "tabs_prod_r1", "PRODUCTION")
    _add_order("PRODUCTION", "보류런없음", 0, hold=True)
    _add_order("PRODUCTION", "보류런있음", 0, steps_done=("cut",), with_run=True, hold=True)
    _add_order("DRAWING", "도면보류", 0, hold=True)
    _add_order("PRODUCTION", "재단차례", 0, with_run=True)
    _add_order("PRODUCTION", "아직대기", 0)
    _add_order("PRODUCTION", "다끝남", 0, steps_done=tuple(k for k, _ in _PRODUCTION_STEP_DEFS), with_run=True)

    steps_html = client.get(HOME + "?tab=steps").get_data(as_text=True)
    lane_counts = [int(n) for n in re.findall(r'data-foms-home-steptab="[a-z]+"[^>]*>[^<]+<small>(\d+)</small>', steps_html)]
    assert len(lane_counts) == 4 and sum(lane_counts) == 3  # 재단 = 보류런없음·재단차례, 엣지 = 보류런있음
    assert f">내 공정 <small>{sum(lane_counts)}</small></a>" in steps_html
    cut_q = steps_html.split('data-foms-home-stepq="cut"')[1].split('data-foms-home-stepq="edge"')[0].split("fph-q__nextlist")[0]
    assert "보류런없음" in cut_q and "재단차례" in cut_q and "도면보류" not in steps_html
    # 날짜 탭: 도면 단계 보류는 큰 줄이 아니라 도면·컨펌 기다림 칸, 큰 줄 클래스 = 제작 대기 w · 만드는 중/보류 p · 검수 끝 f
    date_html = client.get(HOME).get_data(as_text=True)
    assert f">내 공정 <small>{sum(lane_counts)}</small></a>" in date_html
    pane = _pane(date_html, get_today_kst().isoformat())
    assert "만들 것 5 · <span class=\"fph-dwst is-late\">도면 5/6 내려옴</span>" in pane and ">도면·컨펌 기다림 1 <small>" in pane
    big = {m.group(2).strip(): m.group(1) for m in re.finditer(
        r'<a class="fph-dr is-([wfp])[^"]*"[^>]*>.*?fph-dr__nm"><b>([^<]+)</b> <small>', pane, re.S)}
    assert big == {"보류런없음": "p", "보류런있음": "p", "재단차례": "p", "아직대기": "w", "다끝남": "f"}
    assert "도면보류" in pane.split("fph-wg")[1]


def test_바뀐_것_숫자에_취소_주문이_모든_탭에서_든다(client) -> None:
    _make_user(client, "tabs_prod_r2", "PRODUCTION")
    _add_order("PRODUCTION", "만드는주문", 2, with_run=True)
    _add_order("PRODUCTION", "취소된주문", 2, deleted=True)
    changes = client.get(HOME + "?tab=changes").get_data(as_text=True)
    inbox_n = changes.count("data-foms-home-inbox=")
    assert inbox_n == 1
    for url in (HOME, HOME + "?tab=steps", HOME + "?tab=all", HOME + "?tab=changes"):
        html = client.get(url).get_data(as_text=True)
        assert f'>바뀐 것 <small class="is-hot">{inbox_n}</small></a>' in html, url
    assert production_home_counts([{"has_changes": True}, {}], 2)["changed"] == 3


def test_다시_받기_주소는_직접_고른_날만_붙인다(client) -> None:
    _make_user(client, "tabs_prod_r3", "PRODUCTION")
    _add_order("PRODUCTION", "사흘뒤", 3)  # 오늘이 비어 자동으로 사흘 뒤 장이 열린다
    today_key = get_today_kst().isoformat()
    auto = client.get(HOME).get_data(as_text=True)
    assert 'aria-current="true"' in auto.split(f'data-foms-home-daybtn="{(get_today_kst() + datetime.timedelta(days=3)).isoformat()}"')[1].split("</a>")[0]
    assert _reload_href(auto) == HOME
    assert _reload_href(client.get(HOME + f"?day={today_key}").get_data(as_text=True)) == f"{HOME}?day={today_key}"
    assert _reload_href(client.get(HOME + "?day=recent").get_data(as_text=True)) == f"{HOME}?day=recent"
    assert _reload_href(client.get(HOME + "?day=뭐지").get_data(as_text=True)) == HOME
    assert _reload_href(client.get(HOME + "?tab=steps").get_data(as_text=True)) == f"{HOME}?tab=steps"
    days = production_home_days([], datetime.date(2026, 11, 11))
    assert days["auto"] and not production_home_days([], datetime.date(2026, 11, 11), "2026-11-11")["auto"]


def test_지난_시공일_장은_안_읽은_수가_있으면_없어요를_숨기고_단추에_같이(client, monkeypatch) -> None:
    _make_user(client, "tabs_prod_r5", "PRODUCTION")
    monkeypatch.setattr(production_home_read_model, "PRODUCTION_KANBAN_MAX_ROWS", 1)
    _add_order("PRODUCTION", "오늘대기", 0)
    _add_order("PRODUCTION", "옛주문하나", -20)
    _add_order("PRODUCTION", "옛주문둘", -30)
    html = client.get(HOME + "?day=past").get_data(as_text=True)
    past = _pane(html, "past")
    assert "더 오래된 2건은 안 보여요" in past and "이 날은 시공이 없어요." not in past
    assert "옛주문하나" not in past
    btn = html.split('data-foms-home-daybtn="past"')[1].split("</a>")[0]
    assert btn.endswith(">지난 시공일 0건<small>2건 더</small>")  # 안 읽은 수는 둘째 줄 작은 글(M5)
    # 시공일 없음 장은 안 읽은 수가 없으니 '없어요' 그대로, 단추는 한 줄(small 없음)
    assert "이 날은 시공이 없어요." in _pane(client.get(HOME + "?day=none").get_data(as_text=True), "none")
    none_btn = html.split('data-foms-home-daybtn="none"')[1].split("</a>")[0]
    assert none_btn.endswith(">시공일 없음 0건") and "<small>" not in none_btn
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".fph-sf small { display: block; font-size: calc(12px * var(--foms-fs, 1));" in css


def test_작업_시트_뒤로_단추는_생산이고_같은_출처_홈에서만_주소를_되돌린다() -> None:
    sheet = (ROOT / "templates/production/sheet.html").read_text(encoding="utf-8")
    back = sheet.split('class="foms-prod-page__back"')[1].split("</a>")[0]
    assert "data-foms-prod-back" in back and back.endswith(">생산") and "전체 주문" not in back
    js = (ROOT / "static/js/production/foms-production-sheet-page.js").read_text(encoding="utf-8")
    assert "document.referrer" in js and "from.origin !== window.location.origin" in js
    assert "from.pathname !== home.pathname" in js and "if (!back || !document.referrer) { return; }" in js


def test_제목_줄_탭은_보드_없이_찾기로_끝나고_레일_생산이_첫_화면(client, monkeypatch) -> None:
    """D19(11-10): 태블릿 레일 '생산' 은 첫 화면으로 가고 강조된다. 11-21 사용자 ②: 탭 끝 옛 보드 [보드 →] 는 태블릿 첫 화면에서
    뺐다(보드 화면 · 주소는 PC · 폰 메뉴의 생산 화면으로 남는다 — test_production_home_restore_mockup 이 남은 길을 본다)."""
    user = _make_user(client, "tabs_prod_board", "PRODUCTION")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    html = client.get(HOME).get_data(as_text=True)
    nav = html[html.index('class="foms-prod-home__nav"'):]
    nav = nav[: nav.index("</nav>")]
    assert "data-foms-home-board" not in nav and "/erp/production/dashboard" not in nav and "navtab--out" not in nav
    assert nav.rstrip().endswith(">찾기</a>")
    assert "home.css?v=20261122y" in html
    # 제목 줄 오른쪽 묶음: 받음 표시 · 글자 손잡이 · [다시 받기] 가 한 묶음이라 줄이 넘쳐도 같이 내려간다(② 빈 줄 없이)
    tools = html[html.index('class="foms-prod-home__tools"'):]
    tools = tools[: tools.index("</header>")]
    assert "data-foms-home-sync" in tools and "data-foms-fs-ctl" in tools and "data-foms-home-reload" in tools
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".foms-prod-home__tools { margin-left: auto; display: flex;" in css
    # 띠: 하루짜리 빈 줄만 '· 없음', 묶음 줄(지난 7일 · 그 뒤)은 날짜 글이 길어 안 붙인다
    strip = html[html.index('class="fph-strip"'):]
    strip = strip[: strip.index("</aside>")]
    recent = re.search(r'data-foms-home-daybtn="recent".*?</a>', strip, re.S).group(0)
    assert "없음" not in recent
    rail = html[html.index('class="foms-tablet-rail"'):]
    rail = rail[: rail.index("</nav>")]
    prod = re.search(r'<a\s+class="foms-tablet-rail__item[^"]*"\s+href="([^"]+)"\s+title="생산"[^>]*>', rail)
    assert prod and prod.group(1) == HOME and "is-active" in prod.group(0)
    assert 'data-foms-rail-match="/erp/production"' in prod.group(0)
    assert "navtab--out" not in css  # 보드 단추 꼴도 같이 뺐다


def test_공정_줄과_곧_올_것은_시공일_빠른_순() -> None:
    """M2(11-11): 지난 날 → 앞날 → 시공일 없음, 같은 날은 주문 번호 순. 보류도 같은 규칙."""
    def _row(rid: int, date: str | None, stage: str, *, hold: bool = False) -> dict:
        now = stage == "재단 중"
        return {"id": rid, "construction_date": date, "home_view": "prod", "home_stage": stage, "hold_active": hold,
                "home_steps": [{"key": "cut", "done": False, "now": now}, {"key": "edge", "done": False, "now": False}]}

    rows = [_row(5, "2026-11-05", "재단 중"), _row(1, "2026-11-17", "재단 중"), _row(9, None, "보류", hold=True),
            _row(4, "2026-10-31", "보류", hold=True), _row(2, "2026-11-05", "재단 중"), _row(3, "2026-10-27", "재단 중"),
            _row(8, None, "제작 대기"), _row(7, "2026-11-20", "제작 대기"), _row(6, "2026-11-01", "제작 대기")]
    cut = production_home_step_queues(rows)["queues"][0]
    assert [r["id"] for r in cut["rows"]] == [3, 4, 2, 5, 1, 9]
    assert [r["id"] for r in cut["incoming"]] == [6, 7, 8]
    edge = production_home_step_queues(rows)["queues"][1]
    assert [r["id"] for r in edge["incoming"]] == [3, 2, 5, 1]  # 재단 줄에서 보류만 뺀 같은 순서


def test_날짜_장은_그날_주문만_미리_보기와_밀린_것이_없다(client) -> None:
    """설계서 2026-11-22-production-drawing-arrival-upgrade §5-2(사장님 "시공일 기준 메인 날짜에는 당일 것만"): 예전 M4(11-11)
    미리 보기(뒤 장들 만들 것 6줄) · 밀린 것(지난 7일)을 뺐다. 주문이 적은 날은 아래가 빈다(사장님 승인)."""
    today = datetime.date(2026, 11, 11)

    def _row(rid: int, date: str | None) -> dict:
        return {"id": rid, "construction_date": date, "home_view": "prod", "home_stage": "제작 대기", "home_steps": []}

    recent7 = [_row(100 + i, "2026-11-08") for i in range(7)]
    on13 = [_row(20 + i, "2026-11-13") for i in range(7)]
    rows = recent7 + on13 + [_row(10, "2026-11-12"), _row(11, "2026-11-12"), _row(30, "2026-11-21"),
                             _row(40, "2026-12-01"), _row(50, "2026-10-01"), _row(60, None)]
    days = production_home_days(rows, today)
    by = {b["key"]: b for b in days["panes"]}
    assert all("previews" not in b for b in days["panes"])
    assert [r["id"] for r in by["2026-11-12"]["make_rows"]] == [10, 11]  # 그날 주문만
    assert [r["id"] for r in by["2026-11-11"]["make_rows"]] == [] and by["2026-11-11"]["total"] == 0
    assert [r["id"] for r in by["recent"]["make_rows"]] == [100 + i for i in range(7)]
    assert not hasattr(production_home_days_module, "PREVIEW_MAX_ROWS")
    # 화면: 오늘 장에 지난 7일 주문 · 다른 날 주문이 없고, 미리 보기 · 밀린 것 머리도 없다
    _make_user(client, "tabs_prod_m4", "PRODUCTION")
    _add_order("PRODUCTION", "밀린주문", -3)
    _add_order("PRODUCTION", "모레주문", 2)
    pane = _pane(client.get(HOME + f"?day={get_today_kst().isoformat()}").get_data(as_text=True), get_today_kst().isoformat())
    assert "밀린주문" not in pane and "모레주문" not in pane and "이 날은 시공이 없어요." in pane
    assert "미리 보기" not in pane and "밀린 것" not in pane and "fph-pane__g--next" not in pane
    for tpl in ("home_day_pane.html", "home_pc_day_pane.html"):
        assert "previews" not in (ROOT / "templates/production/partials" / tpl).read_text(encoding="utf-8"), tpl


def test_날짜_장_큰_줄_긴_이름은_말줄임으로_줄고_주문_번호는_밖에_남는다(client) -> None:
    """M6(11-11): 글자 150% 에서 긴 이름이 말줄임 없이 잘리고 #번호까지 밀려 사라졌다 — flex 칸엔 text-overflow 가 안 먹는다."""
    _make_user(client, "tabs_prod_m6", "PRODUCTION")
    order = _add_order("PRODUCTION", "아주긴상호이름가구인테리어주식회사본점", 0)
    pane = _pane(client.get(HOME).get_data(as_text=True), get_today_kst().isoformat())
    # 시공일 표는 이름 칸 안 맨 뒤(11-21) — 이름(b)만 줄고 번호 · 시공일은 안 줄어든다
    assert (f'<span class="fph-dr__nm"><b>아주긴상호이름가구인테리어주식회사본점</b> <small>#{order.id}</small>'
            '<span class="fph-due is-today" data-foms-home-due><i>시공</i><b>오늘 ' in pane)
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".fph-dr__nm > b { min-width: 0; overflow: hidden; text-overflow: ellipsis; font-weight: inherit; }" in css
    assert ".fph-dr__nm > small { flex-shrink: 0;" in css


def test_만들_것_줄에_발주사와_영업_담당을_이름_줄_오른쪽에_보인다(client) -> None:
    """사용자 11-11 "태블릿 생산 탭 메인 > 발주사, 영업 담당 표기": 날짜 큰 줄 · 내 공정 줄만. 빈 쪽은 빼고 둘 다 없으면 안 그린다."""
    _make_user(client, "tabs_prod_by", "PRODUCTION")
    both = _add_order("PRODUCTION", "둘다있음", 0, with_run=True, orderer="한샘대리점", manager="김영업")
    only_o = _add_order("PRODUCTION", "발주만", 0, with_run=True, orderer="리바트")
    only_m = _add_order("PRODUCTION", "담당만", 0, with_run=True, manager="이담당")
    none = _add_order("PRODUCTION", "둘다없음", 0, with_run=True, manager="-")
    _add_order("DRAWING", "도면주문", 0, orderer="작은칸발주", manager="작은칸담당")
    o, m = '<span class="fph-by is-o"><i>발주</i> {}</span>', '<span class="fph-by is-m"><i>담당</i> {}</span>'
    want = {both.id: o.format("한샘대리점") + " " + m.format("김영업"), only_o.id: o.format("리바트"), only_m.id: m.format("이담당")}
    date = client.get(HOME).get_data(as_text=True)
    pane = _pane(date, get_today_kst().isoformat())
    steps = client.get(HOME + "?tab=steps").get_data(as_text=True)
    cut = steps.split('data-foms-home-stepq="cut"')[1].split('data-foms-home-stepq="edge"')[0].split("fph-q__nextlist")[0]
    for oid, text in want.items():
        assert re.search(rf'<small>#{oid}</small><span class="fph-due[^"]*" data-foms-home-due>.*?</span></span>'
                         rf'<span class="fph-dr__by">{re.escape(text)}</span></span>', pane)
        assert f'<small>#{oid}</small></b><span class="fph-qr__by">{text}</span></div>' in cut
    assert re.search(rf'<small>#{none.id}</small><span class="fph-due[^"]*" data-foms-home-due>.*?</span></span></span>', pane) and f'<small>#{none.id}</small></b></div>' in cut
    assert pane.count('class="fph-dr__by"') == 3 and cut.count('class="fph-qr__by"') == 3
    # 작은 칸(기다림)에는 발주사가 없다. 영업 담당은 막힌 까닭 줄에 한 번(2026-11-22 §5-2 '까닭 · 도면 담당 · 영업 담당')
    assert "작은칸발주" not in date and "도면주문" in pane.split("fph-wg")[1]
    assert date.count("작은칸담당") == 1 and "영업 작은칸담당</span>" in pane.split("fph-wg")[1]
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".fph-dr__ln { display: flex; flex-wrap: wrap; align-items: baseline;" in css
    assert ("min-width: 0; max-width: 100%; }" in css.split(".fph-dr__nm {")[1].split("}")[0] + "}")
    # 발주사·담당 글은 말줄임 없이 줄이 넘어간다 — 글자 150% 에서 담당 이름이 "…" 로 잘리던 것(스테이징 실화면)
    by = re.search(r"\.fph-dr__by \{[^}]*\}", css).group(0)
    piece = re.search(r"(?m)^\.fph-by \{[^}]*\}", css).group(0)
    assert "flex-wrap: wrap" in by and "nowrap" not in by and "ellipsis" not in by
    assert "overflow-wrap: anywhere" in piece and "word-break: keep-all" in piece and "nowrap" not in piece and "ellipsis" not in piece
    assert ".fph-qr__ln { display: flex; flex-wrap: wrap; align-items: baseline;" in css
    # 내 공정 줄은 `.fph-qr__who span`(한 줄 말줄임 · 회색)이 조각에도 걸린다 — 묶음과 조각 둘 다 풀어야 150% 에서 안 잘린다
    qby = re.search(r"\.fph-qr__who \.fph-qr__by \{[^}]*\}", css).group(0)
    qpiece = re.search(r"\.fph-qr__who \.fph-by \{[^}]*\}", css).group(0)
    assert "white-space: normal" in qby and "overflow: visible" in qby and "flex-wrap: wrap" in qby
    assert "white-space: normal" in qpiece and "overflow: visible" in qpiece
    # 시인성(사용자 11-11 "전부 회색이라 구분이 안 돼"): 이름은 굵고 진하게, 담당은 남색, 머리말만 회색 작게
    assert "font-weight: 700" in piece and "color: var(--fph-text);" in piece and "--fph-text3" not in piece + by + qby + qpiece
    assert "\n.fph-by.is-m { color: var(--fph-brand-dark); }" in css and ".fph-qr__who .fph-by.is-m { color: var(--fph-brand-dark); }" in css
    label = re.search(r"(?m)^\.fph-by i \{[^}]*\}", css).group(0)
    assert "color: var(--fph-text3)" in label and "calc(12px * var(--foms-fs, 1))" in label and "font-style: normal" in label


# ── 작은 화면 결함 3건(11-11): 곧 올 것 번호 · 전체 화면 시트 머리 줄(S3) · 옆 시트 머리와 닫기 단추(S4) ──

def _landscape_block(css: str) -> str:
    """가로 태블릿(레일 + 터치) 미디어 블록 하나 — 다음 빈 줄 앞까지."""
    head = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {"
    return css.split(head)[1].split(chr(10) + "}" + chr(10))[0]


def test_곧_올_것_긴_이름은_이름만_줄고_번호는_늘_보인다(client) -> None:
    _make_user(client, "tabs_prod_nx", "PRODUCTION")
    long_name = "가나다 인테리어 디자인 스튜디오 주식회사 본점"
    order = _add_order("PRODUCTION", long_name, 2)  # 재단 '곧 올 것' = 제작 대기
    html = client.get(HOME + "?tab=steps").get_data(as_text=True)
    nxt = html.split('data-foms-home-stepq="cut"')[1].split("fph-q__nextlist")[1].split("</div>")[0]
    assert f"<b><i>{long_name}</i> <small>#{order.id}</small></b>" in nxt
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    # 날짜 탭 큰 줄(.fph-dr__nm, M6)과 같은 방식: 칸은 flex, 이름(i)만 말줄임, 번호(small)는 안 준다
    assert ".fph-nx b { min-width: 0; display: flex; align-items: baseline; gap: 6px;" in css
    assert ".fph-nx b i { min-width: 0; overflow: hidden; text-overflow: ellipsis; font-style: normal; }" in css
    assert ".fph-nx b small { flex-shrink: 0;" in css
    nx_b = css.split(".fph-nx b {")[1].split("}")[0]
    assert "text-overflow" not in nx_b  # 번호까지 같이 잘리던 칸 전체 말줄임(옛 규칙)이 돌아오면 실패
    assert "home.css') }}?v=20261122y" in (ROOT / "templates/production/partials/home_styles.html").read_text(encoding="utf-8")


def test_전체_화면_시트_가로_태블릿은_머리_줄_한_줄이고_몸통이_남은_높이를_채운다() -> None:
    """S3: 몸통 높이를 '100dvh - 64px' 로 박아 두면 머리 줄 실제 높이(단추 56 + 8·8 + 선 1 = 73px)와 9px 어긋나고,
    긴 제목이 줄을 넘기면(150%) 머리 줄이 두 줄 129px 이 되어 페이지가 865px 로 화면(800)을 넘었다."""
    css = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    block = _landscape_block(css)
    assert ".foms-prod-page { height: calc(100dvh / var(--foms-ui-zoom, 1)); display: flex; flex-direction: column; }" in block
    assert ".foms-prod-page__bar { flex-wrap: nowrap; flex-shrink: 0; }" in block
    assert ".foms-prod-page__body { flex: 1 1 auto; height: auto; min-height: 0; }" in block
    assert "- 64px); min-height: 0; }" not in block
    # 제목은 줄 수 있는 유일한 칸(말줄임), 이름 · 번호 · 품목 · 단추는 그대로 마크업에 있다
    assert ".foms-prod-page__title { margin: 0; font-size: calc(20px * var(--foms-fs, 1)); font-weight: 800; line-height: 1.2; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }" in css
    page = (ROOT / "templates/production/sheet.html").read_text(encoding="utf-8")
    assert '<h1 class="foms-prod-page__title">{{ order.customer_name }} <small>#{{ order.id }}</small><span class="foms-prod-page__title-prod"> · {{ order.product_label }}</span></h1>' in page
    assert "sheet.css') }}?v=20261122y" in page


def test_옆_시트_머리_줄은_떠_있는_닫기_단추_자리를_비운다() -> None:
    """S4: 머리 줄 끝 '#번호 · 상차' 글이 우상단에 떠 있는 닫기(44px + 바깥 8px) 밑으로 20×8px 들어갔다."""
    css = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    assert ".foms-tablet-sheet--headless .foms-prod-sheet__titlebar { padding-right: 36px; }" in css
    frag = (ROOT / "templates/production/partials/tablet_sheet.html").read_text(encoding="utf-8")
    bar = frag.split('<div class="foms-prod-sheet__titlebar">')[1].split("{# ──")[0]
    assert '<div class="foms-prod-sheet__count">#{{ order.id }} · 상차 {{ order.load_md }}</div>' in bar
    body = (ROOT / "templates/production/partials/tablet_kanban_body.html").read_text(encoding="utf-8")
    assert "css/contexts/production/sheet.css') }}?v=20261122y" in body


def test_가로_터치_화면_시공일_띠는_늘_한_줄씩이고_칸을_채우거나_48px_로_굴린다() -> None:
    """11-21 사용자 ①(시안 안 3): 두 칸씩 배치를 없앴다. 11-14 의 두 칸씩 규칙(max-height 786px)은 media 키(배율 전 626)만 봐서
    현장 태블릿 1176×626 을 80% 로 줄여도 두 칸씩 — 띠가 왼쪽 칸 61% 에서 끝나 아래가 비었다. 이제 띠 상자가 칸 키를 박고 줄이 나눠 가진다."""
    from foms.services.production_home_days import PRODUCTION_HOME_STRIP_DAYS

    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    rows = PRODUCTION_HOME_STRIP_DAYS + 2  # 지난 7일 · 날들 · 그 뒤
    # 두 칸씩은 어디에도 없다(media · 컨테이너 쿼리 모두). 두 칸 칸에서만 쓰던 요일 글 바꿔치기도 뺐다
    assert "repeat(2, minmax(0, 1fr)); align-content: start;" not in css and "max-height: 785.98px" not in css
    assert "fph-sd__wd" not in css and "fph-sd__long" not in css and "nth-of-type(even)" not in css
    tpl = (ROOT / "templates/production/partials/home_date.html").read_text(encoding="utf-8")
    assert '<div class="fph-stripbox">\n  <aside class="fph-strip"' in tpl
    assert '<span class="fph-sd__d"><b>{{ d.label }}</b><small>{{ sub }}</small></span>' in tpl and "fph-sd__wd" not in tpl
    # 상자는 가로 터치 화면에서만(PC 마우스 · 세로 · 폰은 display: contents — 띠는 지금 그대로)
    assert ".fph-stripbox { display: contents; }" in css
    head = "@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse) {\n  .fph-stripbox {"
    assert css.count(head) == 1
    block = css.split(head)[1].split("\n}\n")[0]
    for line in ("display: block;", "position: sticky;", "top: var(--fph-bar-h, 73px);",
                 "height: calc(100dvh / var(--foms-ui-zoom, 1) - var(--fph-bar-h, 73px));", "container: fph-strip / size;",
                 ".fph-stripbox > .fph-strip { position: static; height: 100%; max-height: none; }", ".fph-sd { flex-grow: 1; }"):
        assert line in block, line
    # 기본 줄 키 48(장갑 D5) · 줄지 않음 — 다 안 들어가면 이 키 그대로 띠 안에서 굴린다(PC 띠 규칙도 그대로)
    assert re.search(r"\n\.fph-sd \{\n  width: 100%;\n  min-height: 48px;\n  flex-shrink: 0;", css)
    assert "max-height: calc(100dvh / var(--foms-ui-zoom, 1) - var(--fph-bar-h, 73px));\n  overflow-y: auto;" in css
    queries = re.findall(r"@container fph-strip \(min-height: calc\(([^\n]+)\)\) \{\n(.*?)\n\}\n", css, re.S)
    assert len(queries) == 1
    expr, body = queries[0]
    assert body.strip() == ".fph-sd { flex-shrink: 1; min-height: max(44px, 2.0125rem + 5px); }"  # 44px 아래로는 안 준다
    assert f"{rows} * max(44px, 2.0125rem + 5px)" in expr

    def _px(fs: float) -> float:  # 쿼리 식을 글자 배율 fs 에서 px 로 푼다(1rem = 16 × fs)
        py = re.sub(r"(\d+(?:\.\d+)?)rem", rf"(\1*{16 * fs})", expr)
        return eval(py.replace("px", ""), {"max": max})  # noqa: S307 — 저장소 CSS 의 고정 식

    assert _px(1) == 40 + rows * 44 + 49

    def _pane(h: float, z: float) -> float:  # 띠 칸 키 = 창 키 ÷ 화면 크기 − 제목 줄 73
        return h / z - 73

    assert _pane(626, 0.8) >= _px(1)  # 현장 태블릿 80%: 한 줄씩 칸을 채운다(줄 47.7px)
    assert abs((_pane(626, 0.8) - 40 - 49) / rows - 47.73) < 0.01
    assert _pane(626, 1) < _pane(626, 0.9) < _px(1)  # 100% · 90%: 줄 48 그대로 띠 안에서 굴린다
    assert _pane(626, 0.9) < 40 + rows * 48 + 49
    assert _pane(800, 1) >= _px(1)  # 1280×800: 칸을 채운다(줄 49.1px)
    assert "home.css') }}?v=20261122y" in (ROOT / "templates/production/partials/home_styles.html").read_text(encoding="utf-8")


def test_화면_크기와_글자를_키워_이름_칸이_좁아지면_카드를_두_줄로_100퍼센트는_그대로() -> None:
    """11-14 실측: 1176×626 화면 크기 130% + 글자 150% 에서 날짜 장 카드 455px 에 정해진 칸 470px 이 들어가 이름 칸이 0px,
    '발주 가나 인테리어' 가 한 글자씩 꺾였다(찾기 165px · 내 공정 274px 도 이름 글자의 5 · 8배). 칸을 담은 상자 너비를 컨테이너로 잰다."""
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    gate = "@media (min-width: 992px) {\n  .fph-panes { container: fph-pane / inline-size; }"
    assert css.count(gate) == 1  # 세로 · 폰(992px 아래)은 원래 두 줄 규칙만
    block = css.split(gate)[1].split("\n}\n")[0]
    for line in (".foms-prod-home__list { container: fph-list / inline-size; }", ".fph-q { container: fph-q / inline-size; }"):
        assert line in block
    queries = dict(re.findall(r"@container (fph-\w+) \(max-width: calc\(([^\n]+) - 0\.02px\)\) \{", block))
    # 받은함(바뀐 것)은 장 최소 너비로 칸 수를 스스로 정한다(auto-fit, test_production_home_changes_layout.py) — 컨테이너 쿼리 없음
    assert set(queries) == {"fph-pane", "fph-list", "fph-q"} and "fph-inbox" not in block

    def _px(name: str, fs: float) -> float:  # 쿼리 식을 글자 배율 fs 에서 px 로 푼다(1rem = 16 × fs)
        py = re.sub(r"(\d+(?:\.\d+)?)rem", rf"(\1*{16 * fs})", queries[name])
        return eval(py.replace("px", ""), {"max": max})  # noqa: S307 — 저장소 CSS 의 고정 식

    # 실측 카드를 담은 칸 너비(CSS px): 100% · 글자 100% 는 그대로(1176×626 이 가장 좁다), 130% + 글자 150% 는 두 줄
    for name, base_w, big_w in (("fph-pane", 760, 455), ("fph-list", 1072, 801), ("fph-q", 1072, 801)):
        assert _px(name, 1) < base_w and _px(name, 1.5) > big_w, name
    # 경계 = 이름 칸이 이름 글자의 12배(날짜 장 20px · 찾기 22px · 내 공정 22px, 글자 배율을 곱한다)
    assert abs(_px("fph-pane", 1) - (128 + 154 + 92 + 36 + 12 + 2 + 12 * 20)) < 0.01
    assert abs(_px("fph-list", 1.5) - (150 + 290 + 130 + 20 + 2 + 44 + 12 * 22 * 1.5)) < 0.01
    assert abs(_px("fph-q", 1.2) - (64 + 190 + 30 + 16 + 2 + 150 * 1.2 + 12 * 22 * 1.2)) < 0.01
    # 두 줄로 바꿀 때 칸 · 글자 · 단추 크기는 그대로 — 자리(grid)와 여백만 바꾸고 아무 칸도 숨기지 않는다
    assert not re.search(r"font-size|(?<![-\w])(min-)?(width|height):|display: none", block)
    for card in (".fph-dr {", ".foms-prod-home__job {", ".fph-qr {"):
        assert card + " grid-template-columns:" in block and "grid-template-rows: auto auto;" in block


def test_phone_nav_tabs_scroll_inside_instead_of_widening_page() -> None:
    """폰(992 아래): 탭 6개 줄(404px)이 폰 폭보다 넓어도 문서를 넓히지 않고 줄 안에서 옆으로 민다.

    2026-11-16 폰 실측: 탭 줄이 문서를 441 · 429px 로 넓혀 폰 브라우저가 화면을 통째로 줄였다 늘렸고,
    아래 메뉴 · 일감 줄이 첫 그림 뒤 83 · 139px 움직였다.
    """
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    phone = css[css.index("@media (max-width: 991.98px) {"):]
    rule = phone[phone.index(".foms-prod-home__nav {"):]
    rule = rule[:rule.index("}")]
    assert "min-width: 0" in rule and "overflow-x: auto" in rule
    tools = phone[phone.index(".foms-prod-home__tools {"):]
    assert "min-width: 0" in tools[:tools.index("}")]
