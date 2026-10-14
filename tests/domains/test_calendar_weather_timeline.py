"""모바일 홈 달력 '시간 줄' 날씨 보기 — 그림 만들기·사람마다 고르기(쿠키) 계약 (2026-10-14).

근거: docs/specs/2026-10-14-mobile-calendar-weather-band_SPEC.md §시간 줄 보기.
"""

import datetime
import re

from db import db_session
from foms.services.orders import calendar_weather_timeline as tl
from foms.services.orders import dashboard_control_tower as ct

TODAY = datetime.date(2026, 10, 14)


def _cell(wx, slots=None, iso="2026-10-14", past=False):
    return {"wx": wx, "wx_slots": slots, "iso": iso, "is_past": past}


def test_week_slots_fill_missing_parts_with_day_weather():
    cells = [_cell("sun", ["sun", None, "cloud", "heavy"]), _cell("drizzle"), _cell(""), _cell("cloud", ["x", "sun", "sun", "sun"])]
    assert tl.week_slots(cells) == ["sun", "sun", "cloud", "heavy", *["drizzle"] * 4, *["none"] * 4, "cloud", "sun", "sun", "sun"]


def test_runs_follow_weather_not_day_edges():
    sl = ["sun", "sun", "cloud", "cloud", "cloud", "drizzle", "sun", "sun"]
    assert tl.runs(sl, lambda k: k == "sun") == [(0, 2), (6, 8)]
    assert tl.runs(sl, lambda k: k not in ("sun", "none")) == [(2, 6)]  # 구름은 날짜 경계를 넘어 한 무리


def test_sky_blends_over_half_a_day_at_weather_changes():
    """바탕은 같은 날씨 안에서 한 색, 바뀌는 자리는 6시간 칸 2개에 걸쳐 섞는다(칼로 자른 듯 끊기지 않게)."""
    stops = tl._sky_stops(["sun"] * 4 + ["cloud"] * 4)
    assert stops == [(0.0, "sun"), (0.375, "sun"), (0.625, "cloud"), (1.0, "cloud")]


def test_week_svg_draws_one_sun_per_run_and_unique_ids():
    cells = [_cell("sun", ["sun"] * 4), _cell("sun", ["sun", "sun", "heavy", "heavy"]), _cell("snow", ["snow"] * 4)]
    svg = str(tl.week_band_svg(cells, uid="tlA", now_index=0.5))
    assert svg.startswith('<svg class="tl-svg" viewBox="0 0 300 190"')
    assert svg.count('href="#tlRays"') == 1                         # 맑음 1.5일 = 해 하나
    assert 'class="tl-flash"' in svg and 'href="#tlStreak"' in svg  # 장대비 + 번개
    assert 'href="#tlFlake"' in svg and 'class="tl-now"' in svg      # 함박눈 결정 + 지금 선
    assert 'x1="50.0"' in svg                                        # 지금 선 = 첫날 정오
    ids = re.findall(r'id="([^"]+)"', svg)
    assert ids and all(i.startswith("tlA") for i in ids) and len(ids) == len(set(ids))
    assert "style=" not in svg                                       # 인라인 스타일 금지(색은 CSS 변수 클래스)


def test_week_svg_still_and_empty_week():
    svg = str(tl.week_band_svg([_cell("", past=True)] * 2, uid="tlB", still=True))
    assert 'class="tl-svg is-still"' in svg and "tl-s-none" in svg
    assert "mask=" not in svg and "tl-now" not in svg               # 날씨 없음 = 회백색 바탕만


def test_style_cookie_defaults_to_cell():
    assert tl.wx_style({}) == "cell"
    assert tl.wx_style({"foms_wx_style": "timeline"}) == "timeline"
    assert tl.wx_style({"foms_wx_style": "<script>"}) == "cell"


def _render(app, cookie=None):
    from flask import render_template
    from models import Order
    headers = {"Cookie": f"foms_wx_style={cookie}"} if cookie else {}
    weather = {"days": {"2026-10-14": {"kind": "sun", "slots": ["sun", "sun", "cloud", "drizzle"]},
                        "2026-10-15": {"kind": "drizzle"}, "2026-10-05": {"kind": "snow"}}}
    cal = ct._month_calendar(db_session.query(Order), TODAY, TODAY.replace(day=1), None, weather)
    with app.test_request_context("/erp/dashboard", headers=headers):
        return render_template("orders/partials/dashboard_mobile_tower_calendar.html", cal=cal, calendar_colors_editable=False)


def test_calendar_default_is_cell_view(app):
    html = _render(app)
    assert "foms-wx-seg" in html and "tl-svg" not in html and 'id="tlRays"' not in html
    assert 'data-foms-wx-style="cell" aria-pressed="true"' in html
    assert 'data-foms-wx-style="timeline" aria-pressed="false"' in html


def test_calendar_timeline_view_from_cookie(app):
    html = _render(app, "timeline")
    assert "foms-wx-seg" not in html and "fwxStill" not in html     # 칸 그림 대신 주마다 SVG 한 장
    assert html.count('class="tl-svg') == 5 and html.count('id="tlRays"') == 1
    assert 'class="tl-svg is-still"' in html                         # 10/4~10 주 = 전부 지난 날 → 멈춤
    assert 'data-foms-wx-style="timeline" aria-pressed="true"' in html
    ids = re.findall(r'id="([^"]+)"', html)
    assert len(ids) == len(set(ids))                                 # 주마다 접두어가 달라 겹치지 않는다
