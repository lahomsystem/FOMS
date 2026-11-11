"""생산팀 첫 화면 리뷰·실측 고침 시험 — :mod:`tests.domains.test_production_home_tabs` 에서 옮겼다(파일 500줄 래칫).

공용 도우미(``_make_user`` · ``_add_order`` · ``_pane`` · ``ROOT`` · ``HOME``)는 원래 파일에서 가져온다.
"""

from __future__ import annotations

import datetime
import re

from foms.api.production.orders import _PRODUCTION_STEP_DEFS
from foms.services.datetime_kst import get_today_kst
from foms.services import production_home_read_model
from foms.services.production_home_days import production_home_days
from foms.services.production_home_read_model import (
    production_home_counts,
    production_home_stage,
    production_home_step_queues,
)
from tests.domains.test_production_home_tabs import HOME, ROOT, _add_order, _make_user, _pane


# ── 리뷰 고침 묶음(원장 §16 R1·R2·R3·R5·R10, 2026-11-10) ──

def _reload_href(html: str) -> str:
    return re.search(r'data-foms-home-reload href="([^"]*)"', html).group(1)


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
    assert "만들 것 5 · 도면·컨펌 기다림 1" in pane and ">도면·컨펌 기다림 1 <small>" in pane
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
    assert 'aria-pressed="true"' in auto.split(f'data-foms-home-daybtn="{(get_today_kst() + datetime.timedelta(days=3)).isoformat()}"')[1].split("</button>")[0]
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
    btn = html.split('data-foms-home-daybtn="past"')[1].split("</button>")[0]
    assert btn.endswith(">지난 시공일 0건<small>2건 더</small>")  # 안 읽은 수는 둘째 줄 작은 글(M5)
    # 시공일 없음 장은 안 읽은 수가 없으니 '없어요' 그대로, 단추는 한 줄(small 없음)
    assert "이 날은 시공이 없어요." in _pane(html, "none")
    none_btn = html.split('data-foms-home-daybtn="none"')[1].split("</button>")[0]
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


def test_제목_줄_보드_단추와_레일_생산이_첫_화면(client, monkeypatch) -> None:
    """D19(11-10): 제목 줄 탭 끝(찾기 뒤)에 옛 보드로 가는 [보드], 태블릿 레일 '생산' 은 첫 화면으로 가고 강조된다."""
    user = _make_user(client, "tabs_prod_board", "PRODUCTION")
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    html = client.get(HOME).get_data(as_text=True)
    nav = html[html.index('class="foms-prod-home__nav"'):]
    nav = nav[: nav.index("</nav>")]
    board = re.search(r"<a [^>]*data-foms-home-board[^>]*>", nav)
    assert board and 'href="/erp/production/dashboard"' in board.group(0)
    assert "foms-prod-home__navtab--out" in board.group(0)
    assert nav.index(">찾기</a>") < nav.index("data-foms-home-board")
    assert "home.css?v=20261111d" in html
    # [보드] 는 온전한 페이지 이동(첫 화면은 조각 화면이 아니다)
    assert 'data-foms-erp-no-shell="1"' in board.group(0)
    # 제목 줄 오른쪽 묶음: 받음 표시 · 글자 손잡이 · [다시 받기] 가 한 묶음이라 줄이 넘쳐도 같이 내려간다(② 빈 줄 없이)
    tools = html[html.index('class="foms-prod-home__tools"'):]
    tools = tools[: tools.index("</header>")]
    assert "data-foms-home-sync" in tools and "data-foms-fs-ctl" in tools and "data-foms-home-reload" in tools
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".foms-prod-home__tools { margin-left: auto; display: flex;" in css
    # 띠: 하루짜리 빈 줄만 '· 없음', 묶음 줄(지난 7일 · 그 뒤)은 날짜 글이 길어 안 붙인다
    strip = html[html.index('class="fph-strip"'):]
    strip = strip[: strip.index("</aside>")]
    recent = re.search(r'data-foms-home-daybtn="recent".*?</button>', strip, re.S).group(0)
    assert "없음" not in recent
    rail = html[html.index('class="foms-tablet-rail"'):]
    rail = rail[: rail.index("</nav>")]
    prod = re.search(r'<a\s+class="foms-tablet-rail__item[^"]*"\s+href="([^"]+)"\s+title="생산"[^>]*>', rail)
    assert prod and prod.group(1) == HOME and "is-active" in prod.group(0)
    assert 'data-foms-rail-match="/erp/production"' in prod.group(0)
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".foms-prod-home__navtab--out i { font-size: calc(13px * var(--foms-fs, 1)); }" in css


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


def test_날짜_장_미리_보기는_6줄까지_뒤_장들을_잇고_모자라면_밀린_것_자기_자신은_안_단다(client) -> None:
    """M4(11-11 · §18 11-11): 뒤 장들(그 뒤 포함) 만들 것을 6줄까지 잇고, 모자라면 남은 자리만큼 지난 7일(밀린 것).
    지난 7일 장은 자기를 안 달고, 아래 두 장(지난 시공일 · 시공일 없음)에는 없다."""
    today = datetime.date(2026, 11, 11)

    def _row(rid: int, date: str | None) -> dict:
        return {"id": rid, "construction_date": date, "home_view": "prod", "home_stage": "제작 대기", "home_steps": []}

    def _pv(days: dict, key: str) -> list:
        return [(p["title"], p["hint"], p["show_day"], [r["id"] for r in p["rows"]])
                for p in next(b for b in days["panes"] if b["key"] == key)["previews"]]

    recent7 = [_row(100 + i, "2026-11-08") for i in range(7)]
    on13 = [_row(20 + i, "2026-11-13") for i in range(7)]
    rows = recent7 + on13 + [_row(10, "2026-11-12"), _row(11, "2026-11-12"), _row(30, "2026-11-21"),
                             _row(40, "2026-12-01"), _row(50, "2026-10-01"), _row(60, None)]
    days = production_home_days(rows, today)
    # (가) 뒤 장 하나로 6줄이 차면 그 장 제목, 밀린 것 없음
    assert _pv(days, "2026-11-12") == [("11/13 (금) 만들 것 7", "미리 보기", False, [20, 21, 22, 23, 24, 25])]
    # (나) 여러 장을 이으면 "다음에 만들 것 <뒤 장들 합계>", 줄마다 시공일, 6줄 이하
    assert _pv(days, "2026-11-11") == [("다음에 만들 것 11", "미리 보기", True, [10, 11, 20, 21, 22, 23])]
    # (다) 뒤가 1줄(그 뒤 묶음) 뿐이면 밀린 것 5줄을 더해 합 6. 그 뒤 장은 뒤가 없어 밀린 것 6줄
    assert _pv(days, "2026-11-21") == [("11/22 뒤 만들 것 1", "미리 보기", True, [40]),
                                       ("지난 7일 만들 것 7", "밀린 것", True, [100, 101, 102, 103, 104])]
    assert _pv(days, "later") == [("지난 7일 만들 것 7", "밀린 것", True, [100, 101, 102, 103, 104, 105])]
    # (라) 지난 7일 장에는 밀린 것 없음 (마) 아래 두 장에는 미리 보기 없음
    assert [p[1] for p in _pv(days, "recent")] == ["미리 보기"]
    assert _pv(days, "past") == [] and _pv(days, "none") == []
    alone = production_home_days(recent7[:1], today)
    assert _pv(alone, "recent") == [] and _pv(alone, "2026-11-11") == [("지난 7일 만들 것 1", "밀린 것", True, [100])]
    # 화면: 밀린 것 제목과 줄의 시공일 글
    _make_user(client, "tabs_prod_m4", "PRODUCTION")
    _add_order("PRODUCTION", "밀린주문", -3)
    pane = _pane(client.get(HOME + f"?day={get_today_kst().isoformat()}").get_data(as_text=True), get_today_kst().isoformat())
    old = production_home_read_model.production_home_day(get_today_kst() - datetime.timedelta(days=3), get_today_kst())["label"]
    assert "지난 7일 만들 것 1 <small>밀린 것</small>" in pane and "밀린주문" in pane and f"<small>{old}</small>" in pane


def test_날짜_장_큰_줄_긴_이름은_말줄임으로_줄고_주문_번호는_밖에_남는다(client) -> None:
    """M6(11-11): 글자 150% 에서 긴 이름이 말줄임 없이 잘리고 #번호까지 밀려 사라졌다 — flex 칸엔 text-overflow 가 안 먹는다."""
    _make_user(client, "tabs_prod_m6", "PRODUCTION")
    order = _add_order("PRODUCTION", "아주긴상호이름가구인테리어주식회사본점", 0)
    pane = _pane(client.get(HOME).get_data(as_text=True), get_today_kst().isoformat())
    assert (f'<span class="fph-dr__nm"><b>아주긴상호이름가구인테리어주식회사본점</b> <small>#{order.id}</small></span>'
            in pane)
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".fph-dr__nm b { min-width: 0; overflow: hidden; text-overflow: ellipsis; font-weight: inherit; }" in css
    assert ".fph-dr__nm small { flex-shrink: 0;" in css


def test_만들_것_줄에_발주사와_영업_담당을_이름_줄_오른쪽에_보인다(client) -> None:
    """사용자 11-11 "태블릿 생산 탭 메인 > 발주사, 영업 담당 표기": 날짜 큰 줄 · 내 공정 줄만. 빈 쪽은 빼고 둘 다 없으면 안 그린다."""
    _make_user(client, "tabs_prod_by", "PRODUCTION")
    both = _add_order("PRODUCTION", "둘다있음", 0, with_run=True, orderer="한샘대리점", manager="김영업")
    only_o = _add_order("PRODUCTION", "발주만", 0, with_run=True, orderer="리바트")
    only_m = _add_order("PRODUCTION", "담당만", 0, with_run=True, manager="이담당")
    none = _add_order("PRODUCTION", "둘다없음", 0, with_run=True, manager="-")
    _add_order("DRAWING", "도면주문", 0, orderer="작은칸발주", manager="작은칸담당")
    want = {both.id: "발주 한샘대리점 · 담당 김영업", only_o.id: "발주 리바트", only_m.id: "담당 이담당"}
    date = client.get(HOME).get_data(as_text=True)
    pane = _pane(date, get_today_kst().isoformat())
    steps = client.get(HOME + "?tab=steps").get_data(as_text=True)
    cut = steps.split('data-foms-home-stepq="cut"')[1].split('data-foms-home-stepq="edge"')[0].split("fph-q__nextlist")[0]
    for oid, text in want.items():
        assert f'<small>#{oid}</small></span><span class="fph-dr__by">{text}</span></span>' in pane
        assert f'<small>#{oid}</small></b><span class="fph-qr__by">{text}</span></div>' in cut
    assert f'<small>#{none.id}</small></span></span>' in pane and f'<small>#{none.id}</small></b></div>' in cut
    assert pane.count('class="fph-dr__by"') == 3 and cut.count('class="fph-qr__by"') == 3
    assert "작은칸발주" not in date and "작은칸담당" not in date and "도면주문" in pane.split("fph-wg")[1]
    css = (ROOT / "static/css/contexts/production/home.css").read_text(encoding="utf-8")
    assert ".fph-dr__ln { display: flex; flex-wrap: wrap; align-items: baseline;" in css
    assert ("min-width: 0; max-width: 100%; }" in css.split(".fph-dr__nm {")[1].split("}")[0] + "}")
    assert (".fph-dr__by { font-size: calc(14px * var(--foms-fs, 1)); color: var(--fph-text3); white-space: nowrap;"
            " overflow: hidden; text-overflow: ellipsis;") in css
    assert ".fph-qr__ln { display: flex; flex-wrap: wrap; align-items: baseline;" in css
    assert ".fph-qr__who .fph-qr__by { max-width: 100%; color: var(--fph-text3); }" in css
