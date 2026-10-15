"""모바일 홈 달력 '시간 줄' 날씨 띠 v2 — 유일한 보기 (2026-10-15).

근거: docs/specs/2026-10-14-mobile-calendar-weather-band_SPEC.md §시간 줄.
"""

import datetime
import re

from db import db_session
from foms.services.orders import calendar_weather_timeline as tl
from foms.services.orders import dashboard_control_tower as ct

TODAY = datetime.date(2026, 10, 14)


def _cell(wx, detail=None, iso="2026-10-14", past=False, slots=None):
    return {"wx": wx, "wx_detail": detail, "wx_slots": slots, "iso": iso, "is_past": past}


def _d(k, lv=None, pop=None, wind=None):
    return {"k": k, "lv": lv, "pop": pop, "wind": wind}


def test_week_slots_fill_missing_parts_with_day_weather():
    cells = [_cell("sun", [_d("sun"), None, _d("partly"), _d("rain", 2, 80, 5)]), _cell("drizzle"), _cell(""),
             _cell("cloud", slots=["x", "sun", "sun", "sun"])]
    sl = tl.week_slots(cells)
    assert [s["k"] for s in sl] == ["sun", "sun", "partly", "rain", *["drizzle"] * 4, *["none"] * 4, "cloud", "sun", "sun", "sun"]
    assert sl[3]["lv"] == 2 and sl[3]["pop"] == 80 and sl[3]["wind"] == 5
    assert sl[4]["lv"] == tl.DEFAULT_LV["drizzle"]  # 강도 모르는 비(옛 자료·중기) = 종류 기본값


def test_runs_follow_weather_not_day_edges():
    sl = ["sun", "sun", "cloud", "cloud", "cloud", "drizzle", "sun", "sun"]
    assert tl.runs(sl, lambda k: k == "sun") == [(0, 2), (6, 8)]
    assert tl.runs(sl, lambda k: k not in ("sun", "none")) == [(2, 6)]  # 구름은 날짜 경계를 넘어 한 무리


def test_sky_blends_over_eighteen_hours_and_sunny_day_is_sunny_all_day():
    """바탕은 같은 날씨 안에서 한 색, 바뀌는 자리는 18시간에 걸쳐 섞는다. 맑은 날 밤 칸에도 남색을 섞지 않는다(2026-10-15)."""
    assert tl._sky_stops(["sun"] * 4 + ["cloud"] * 4) == [(0.0, "sun"), (0.3125, "sun"), (0.6875, "cloud"), (1.0, "cloud")]
    svg = str(tl.week_band_svg([_cell("sun", [_d("sun")] * 4)], uid="tlS"))
    assert re.findall(r'class="tl-s-([\w-]+)"', svg) == ["sun", "sun"] and svg.count('href="#tlRays"') == 1


def test_rain_intensity_drives_speed_tilt_opacity_splash_and_lightning():
    week = [_cell("drizzle", [_d("drizzle", 0, 40)] * 4), _cell("rain", [_d("rain", 2, 90, 10)] * 4),
            _cell("heavy", [_d("heavy", 3, 100)] * 4)]
    svg = str(tl.week_band_svg(week, uid="tlR"))
    assert 'class="tl-r0 tl-w0' in svg and 'class="tl-r2 tl-w2' in svg and 'class="tl-r3 tl-w0' in svg
    assert 'opacity="0.64"' in svg              # 강수확률 40% → 옅게
    assert svg.count('href="#tlSplash"') == 16  # 보통 비부터 땅에 튄다(칸마다 2개 × 8칸)
    assert svg.count('class="tl-flash"') == 2   # 강한 비만 번개
    lv0 = re.search(r'class="tl-r0 tl-w0 tl-p0"[^>]*>(.*?)</g>', svg).group(1).count("<use")
    lv3 = re.search(r'class="tl-r3 tl-w0 tl-p0"[^>]*>(.*?)</g>', svg).group(1).count("<use")
    assert lv3 > lv0                             # 강할수록 촘촘


def test_snow_is_bold_and_strong_snow_blows():
    svg = str(tl.week_band_svg([_cell("snow", [_d("flurry", 0), _d("snow", 1), _d("snow", 2, None, 10), _d("snow", 2)])], uid="tlN"))
    assert 'stroke="#3d63a8"' in svg and 'href="#tlFlakeB"' in svg and 'fill="url(#tlSnowVeil)"' in svg
    assert 'class="up-blow' in svg and 'class="up-sn' in svg


def test_partly_day_has_small_sun_and_no_moon_or_stars():
    svg = str(tl.week_band_svg([_cell("partly", [_d("partly")] * 4)], uid="tlP"))
    assert 'scale(0.62)' in svg and "tlStar" not in svg and "Moon" not in svg


def test_week_svg_unique_ids_and_no_inline_style():
    week = [_cell("sun", [_d("sun")] * 4), _cell("heavy", [_d("heavy", 3)] * 4), _cell("snow", [_d("snow", 1)] * 4)]
    svg = str(tl.week_band_svg(week, uid="tlA", now_index=0.5))
    assert svg.startswith('<svg class="tl-svg" viewBox="0 0 300 190"')
    assert 'x1="50.0"' in svg and 'y1="42" y2="96"' in svg  # 지금 선 = 첫날 정오, 위쪽 절반만
    ids = re.findall(r'id="([^"]+)"', svg)
    assert ids and all(i.startswith("tlA") for i in ids) and len(ids) == len(set(ids))
    assert "style=" not in svg


def test_past_part_dimmed_and_whole_past_week_still():
    cells = [_cell("sun", iso="2026-10-13", past=True), _cell("heavy"), _cell("cloud", iso="2026-10-15")]
    svg = str(tl.week_band_svg(cells, uid="tlC", now_index=1.5, past_days=1))
    assert '<rect class="tl-past is-part" width="104"' in svg and 'stop-opacity="0"' in svg
    whole = str(tl.week_band_svg(cells[:1], uid="tlD", still=True, past_days=1))
    assert 'class="tl-svg is-still"' in whole and '<rect class="tl-past" width="100"' in whole


def _render(app, weather):
    from flask import render_template
    from models import Order
    cal = ct._month_calendar(db_session.query(Order), TODAY, TODAY.replace(day=1), None, weather)
    with app.test_request_context("/erp/dashboard"):
        return cal, render_template("orders/partials/dashboard_mobile_tower_calendar.html", cal=cal, calendar_colors_editable=False)


def test_calendar_renders_timeline_only_with_month_legend(app, monkeypatch):
    """칸 보기·[칸 | 시간 줄] 버튼은 없다. 범례는 이 달 띠에 나오는 날씨만. 7일 밖 주는 멈춘다."""
    monkeypatch.setattr(tl, "now_kst", lambda: datetime.datetime(2026, 10, 14, 9, 0))
    weather = {"days": {"2026-10-14": {"kind": "rain", "slot_detail": [_d("sun"), _d("partly"), _d("rain", 2, 70), _d("rain", 1)]},
                        "2026-10-15": {"kind": "drizzle"}, "2026-10-05": {"kind": "snow"}, "2026-10-30": {"kind": "sun"}}}
    cal, html = _render(app, weather)
    assert "foms-wx-seg" not in html and "data-foms-wx-style" not in html and "fwx" not in html
    assert html.count('class="tl-svg') == 5 and html.count('id="tlRays"') == 1
    assert [k for k, _ in cal["wx_legend"]] == ["sun", "partly", "drizzle", "rain", "snow"]
    assert re.findall(r'wx-k-(\w+)">', html) == ["sun", "partly", "drizzle", "rain", "snow"]
    still = re.findall(r'<svg class="tl-svg( is-still)?"', html)
    assert still == [" is-still", " is-still", "", " is-still", " is-still"]  # 오늘(14일)부터 7일 안 = 셋째 주만 움직인다
    ids = re.findall(r'id="([^"]+)"', html)
    assert len(ids) == len(set(ids))


def test_month_without_weather_ships_no_defs(app):
    _, html = _render(app, {"days": {}})
    assert "foms-wx-defs" not in html and 'tl-s-none' in html
