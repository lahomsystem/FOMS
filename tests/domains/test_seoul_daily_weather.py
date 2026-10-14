"""모바일 홈 달력 — 서울 날짜별 날씨(기상청 API허브) 수집·판정·저장 계약 테스트.

근거: docs/specs/2026-10-14-mobile-calendar-weather-band_SPEC.md §3
진짜 기상청은 부르지 않는다 — 응답 모양만 흉내 낸 가짜 전송을 쓴다.
"""

import datetime

import pytest

from db import db_session
from foms.services.orders import dashboard_control_tower as ct
from foms.services.integrations.kma import seoul_daily_weather as w
from models import SystemSetting

KST = datetime.timezone(datetime.timedelta(hours=9))
NOW = datetime.datetime(2026, 10, 14, 9, 30, tzinfo=KST)


@pytest.fixture(autouse=True)
def _clean(app):
    db_session.query(SystemSetting).filter(SystemSetting.setting_key == w.WEATHER_KEY).delete()
    db_session.commit()
    yield
    db_session.rollback()
    db_session.query(SystemSetting).filter(SystemSetting.setting_key == w.WEATHER_KEY).delete()
    db_session.commit()


class _Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data


def _ok(items):
    return {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                         "body": {"items": {"item": items}}}}


class _Transport:
    """경로별로 정해 둔 응답을 돌려주고, 받은 요청을 기록한다."""

    def __init__(self, by_path):
        self.by_path = by_path
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        for key, resp in self.by_path.items():
            if url.endswith(key):
                return resp
        raise AssertionError(f"unexpected url {url}")


def _hours(date, cat, values):
    return [{"fcstDate": date, "fcstTime": f"{h:02d}00", "category": cat, "fcstValue": v} for h, v in values]


# --------------------------------------------------------------------------- #
# 판정
# --------------------------------------------------------------------------- #

def test_pcp_text_to_mm():
    assert w.parse_pcp_mm("강수없음") == 0
    assert w.parse_pcp_mm("1mm 미만") == 0.5
    assert w.parse_pcp_mm("2.5mm") == 2.5
    assert w.parse_pcp_mm("30.0~50.0mm") == 30
    assert w.parse_pcp_mm("50.0mm 이상") == 50


def test_short_snow_wins_over_rain():
    items = _hours("20261014", "PTY", [(9, "1"), (10, "3")])
    assert w.classify_short(items)["kind"] == "flurry"  # 신적설 없음 = 부슬눈
    assert w.classify_short(_hours("20261014", "PTY", [(9, "2")]))["kind"] == "flurry"  # 비/눈(진눈깨비) = 부슬눈


@pytest.mark.parametrize("sno, kind", [
    ([(9, "1cm 미만"), (10, "1cm 미만")], "flurry"),
    ([(9, "1.0cm")], "snow"),                                  # 한 시간 1cm = 함박눈
    ([(h, "0.6cm") for h in range(9, 14)], "snow"),            # 하루 3cm = 함박눈
    ([(h, "0.5cm") for h in range(9, 14)], "flurry"),          # 하루 2.5cm
    ([(9, "5.0cm 이상")], "snow"),
])
def test_short_snow_strength(sno, kind):
    items = _hours("20261014", "PTY", [(9, "3")]) + _hours("20261014", "SNO", sno)
    assert w.classify_short(items)["kind"] == kind


def test_sleet_with_snowfall_stays_flurry():
    """진눈깨비(PTY 2)는 쌓여도 함박눈 그림으로 그리지 않는다 — 함박눈은 눈(PTY 3)일 때만."""
    items = _hours("20261014", "PTY", [(9, "2")]) + _hours("20261014", "SNO", [(9, "2.0cm")])
    assert w.classify_short(items)["kind"] == "flurry"


@pytest.mark.parametrize("pcp, kind", [
    ([(9, "6.9mm"), (10, "6.9mm")], "drizzle"),                        # 합 13.8, 한 시간 7 미만
    ([(9, "7.0mm")], "heavy"),                                          # 한 시간 7mm
    ([(h, "2.0mm") for h in range(9, 19)], "heavy"),                    # 합 20mm
    ([(h, "1.9mm") for h in range(9, 19)], "drizzle"),                  # 합 19mm
])
def test_short_rain_strength(pcp, kind):
    items = _hours("20261014", "PTY", [(9, "1")]) + _hours("20261014", "PCP", pcp)
    assert w.classify_short(items)["kind"] == kind


def test_short_cloud_needs_half_of_daytime():
    half = [(h, "4" if h < 14 else "1") for h in range(9, 19)]       # 10시간 중 5시간 흐림
    less = [(h, "3" if h < 13 else "1") for h in range(9, 19)]       # 4시간
    night = [(h, "4") for h in (0, 3, 21)] + [(h, "1") for h in range(9, 19)]
    assert w.classify_short(_hours("20261014", "SKY", half))["kind"] == "cloud"
    assert w.classify_short(_hours("20261014", "SKY", less))["kind"] == "sun"
    assert w.classify_short(_hours("20261014", "SKY", night))["kind"] == "sun"  # 밤 구름은 세지 않는다


def test_short_temperature_and_pop():
    items = (_hours("20261014", "TMP", [(9, "-4"), (15, "-1")]) + _hours("20261014", "POP", [(9, "20"), (15, "60")]))
    out = w.classify_short(items)
    assert (out["t_min"], out["t_max"], out["pop"]) == (-4, -1, 60)  # TMN·TMX 없으면 시간별 기온으로
    with_daily = w.classify_short(items + _hours("20261014", "TMX", [(15, "-0.4")]) + _hours("20261014", "TMN", [(6, "-7.0")]))
    assert (with_daily["t_min"], with_daily["t_max"]) == (-7, 0)


@pytest.mark.parametrize("texts, kind", [
    (("흐리고 비", "맑음"), "drizzle"),   # 중기는 비의 양이 없다 → 부슬비
    (("비/눈",), "flurry"),   # 중기는 눈의 양이 없다 → 부슬눈
    (("흐리고 눈",), "flurry"),
    (("구름많음", "흐림"), "cloud"),
    (("맑음", "맑음"), "sun"),
    (("흐리고 소나기",), "drizzle"),
])
def test_mid_text(texts, kind):
    assert w.classify_mid_text(*texts) == kind


def test_base_times():
    assert w.short_base_time(datetime.datetime(2026, 10, 14, 1, 5)) == ("20261013", "2300")
    assert w.short_base_time(datetime.datetime(2026, 10, 14, 5, 9)) == ("20261014", "0200")
    assert w.short_base_time(datetime.datetime(2026, 10, 14, 5, 10)) == ("20261014", "0500")
    assert w.mid_tm_fc(datetime.datetime(2026, 10, 14, 6, 20)) == "202610131800"
    assert w.mid_tm_fc(datetime.datetime(2026, 10, 14, 6, 40)) == "202610140600"


# --------------------------------------------------------------------------- #
# 수집 + 저장
# --------------------------------------------------------------------------- #

def _short_items():
    return (_hours("20261014", "PTY", [(9, "1")]) + _hours("20261014", "PCP", [(9, "8.0mm")])
            + _hours("20261014", "TMX", [(15, "23.0")])
            + _hours("20261015", "SKY", [(h, "1") for h in range(9, 19)]) + _hours("20261015", "TMX", [(15, "25.0")])
            + _hours("20261015", "TMP", [(h, "18") for h in range(24)]))


def test_no_key_skips_without_calling():
    tr = _Transport({})
    assert w.refresh_short(db_session, now=NOW, transport=tr, key="") == {"skipped": "no_key"}
    assert tr.calls == []


def test_refresh_short_stores_days_and_never_logs_key():
    tr = _Transport({"getVilageFcst": _Resp(200, _ok(_short_items()))})
    out = w.refresh_short(db_session, now=NOW, transport=tr, key="KEY-SECRET")
    assert out == {"stored": 2, "base": "202610140800"}
    url, params, timeout = tr.calls[0]
    assert params["nx"] == 60 and params["ny"] == 127 and params["base_time"] == "0800" and timeout == 5
    assert params["authKey"] == "KEY-SECRET" and "KEY-SECRET" not in url
    days = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]
    assert days["2026-10-14"]["kind"] == "heavy" and days["2026-10-14"]["t_max"] == 23
    assert days["2026-10-15"]["kind"] == "sun" and days["2026-10-15"]["src"] == "short"


def test_not_applied_403_is_quiet_none():
    denied = _Resp(403, {"result": {"status": 403, "message": "활용신청이 필요한 API 입니다."}})
    tr = _Transport({"getVilageFcst": denied})
    assert w.refresh_short(db_session, now=NOW, transport=tr, key="k") == {"skipped": "no_data"}
    assert db_session.query(SystemSetting).filter(SystemSetting.setting_key == w.WEATHER_KEY).first() is None


def test_mid_fills_later_days_but_keeps_short_values():
    w.refresh_short(db_session, now=NOW, transport=_Transport({"getVilageFcst": _Resp(200, _ok(_short_items()))}), key="k")
    land = {"wf3Am": "맑음", "wf3Pm": "흐리고 비", "rnSt3Am": 10, "rnSt3Pm": 70, "wf8": "눈", "rnSt8": 60}
    ta = {"taMin3": 12, "taMax3": 21, "taMin8": -6, "taMax8": 2}
    tr = _Transport({"getMidLandFcst": _Resp(200, _ok([land])), "getMidTa": _Resp(200, _ok([ta]))})
    # tmFc 10/14 06시 → 3일 뒤 = 10/17, 8일 뒤 = 10/22. 단기 날짜(10/14·15)는 건드리지 않는다.
    out = w.refresh_mid(db_session, now=NOW, transport=tr, key="k")
    assert out == {"stored": 2, "base": "202610140600"}
    days = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]
    assert days["2026-10-17"] == {"kind": "drizzle", "t_min": 12, "t_max": 21, "pop": 70, "src": "mid", "base": "202610140600"}
    assert days["2026-10-22"]["kind"] == "flurry" and (days["2026-10-22"]["t_min"], days["2026-10-22"]["t_max"]) == (-6, 2)
    assert days["2026-10-14"]["src"] == "short"


def test_past_days_keep_last_forecast_and_old_days_are_pruned():
    old = (NOW.date() - datetime.timedelta(days=w.RETAIN_PAST_DAYS + 1)).isoformat()
    db_session.add(SystemSetting(setting_key=w.WEATHER_KEY, setting_value={"updated_at": "x", "days": {
        "2026-10-13": {"kind": "snow", "t_max": 1, "src": "short"},
        old: {"kind": "sun", "t_max": 1, "src": "short"},
    }}))
    db_session.commit()
    items = _hours("20261013", "SKY", [(h, "1") for h in range(9, 19)]) + _short_items()
    w.refresh_short(db_session, now=NOW, transport=_Transport({"getVilageFcst": _Resp(200, _ok(items))}), key="k")
    days = w.load_days(db_session, datetime.date(2026, 7, 1), datetime.date(2026, 10, 31))["days"]
    assert days["2026-10-13"]["kind"] == "snow"  # 어제는 그날 마지막 예보 그대로
    assert old not in days


def test_load_days_tolerates_broken_values():
    db_session.add(SystemSetting(setting_key=w.WEATHER_KEY, setting_value={"days": {
        "2026-10-14": {"kind": "tornado"}, "2026-10-15": "sun", "2026-10-16": {"kind": "cloud"}}}))
    db_session.commit()
    out = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))
    assert list(out["days"]) == ["2026-10-16"]
    assert w.weather_version(db_session) == ""


# --------------------------------------------------------------------------- #
# 달력 페이로드
# --------------------------------------------------------------------------- #

def _cells(cal):
    return {c["iso"]: c for week in cal["weeks"] for c in week if c["in_month"]}


def test_calendar_cells_carry_weather_and_future_days_move():
    today = datetime.date(2026, 10, 14)
    weather = {"updated_at": "t", "days": {
        (today + datetime.timedelta(days=i)).isoformat(): {"kind": "sun", "t_min": 10 + i, "t_max": 20 + i} for i in range(-3, 11)}}
    from models import Order
    cal = ct._month_calendar(db_session.query(Order), today, today.replace(day=1), None, weather)
    cells = _cells(cal)
    live = sorted(iso for iso, c in cells.items() if c["wx_live"])
    # 오늘부터 예보 끝(10일 뒤)까지 전부 움직인다 — 이 달 안(14~24일)만 셀에 있다. 지난 날은 멈춤.
    assert live == [(today + datetime.timedelta(days=i)).isoformat() for i in range(11)]
    assert cells["2026-10-11"]["wx"] == "sun" and not cells["2026-10-11"]["wx_live"]  # 지난 날 = 멈춘 그림
    assert (cells["2026-10-14"]["t_min_label"], cells["2026-10-14"]["t_max_label"]) == ("10°", "20°")
    assert cells["2026-10-31"]["wx"] == "" and cells["2026-10-31"]["t_max_label"] == ""  # 예보 밖 = 비움
    assert "날씨 맑음 10~20도" in cells["2026-10-14"]["aria"]
    assert cal["photo"]["month"] == 10 and "CC" in cal["photo"]["credit"]
    assert cal["wx_used"] == ["sun"] and cal["wx_still"] == ["sun"]  # 11~13일(지난 날) = 멈춘 맑음


def test_calendar_defs_only_ship_kinds_in_use(app):
    """그 달에 없는 날씨의 그림 정의는 보내지 않는다 — 대시보드 전송 바이트 예산(perf-gate)."""
    from flask import render_template
    from models import Order
    ctx = app.test_request_context("/erp/dashboard")
    ctx.push()
    today = datetime.date(2026, 10, 14)
    weather = {"days": {"2026-10-14": {"kind": "heavy"}, "2026-10-10": {"kind": "sun"}}}  # 10일 = 지난 날(멈춤)
    cal = ct._month_calendar(db_session.query(Order), today, today.replace(day=1), None, weather)
    assert cal["wx_used"] == ["heavy", "sun"] and cal["wx_still"] == ["sun"]
    html = render_template("orders/partials/dashboard_mobile_tower_calendar.html", cal=cal, calendar_colors_editable=False)
    assert 'id="fwxStill-sun"' in html and 'id="fwxStill-heavy"' not in html  # 장대비는 움직이는 칸에만
    assert 'id="fwxHvDrop"' in html and 'id="fwxSnFront"' not in html and 'id="fwxFlake"' not in html
    empty = ct._month_calendar(db_session.query(Order), today, today.replace(day=1), None, {"days": {}})
    assert 'foms-wx-defs' not in render_template(
        "orders/partials/dashboard_mobile_tower_calendar.html", cal=empty, calendar_colors_editable=False)
    ctx.pop()


def test_band_neighbours_blend_within_the_week_only():
    today = datetime.date(2026, 10, 14)
    weather = {"days": {"2026-10-03": {"kind": "heavy"}, "2026-10-04": {"kind": "snow"}, "2026-10-05": {"kind": "sun"}}}
    from models import Order
    cells = _cells(ct._month_calendar(db_session.query(Order), today, today.replace(day=1), None, weather))
    sat, sun = cells["2026-10-03"], cells["2026-10-04"]           # 10/3 토요일 = 주 끝, 10/4 일요일 = 다음 주 시작
    assert sat["wx_next"] == "heavy" and sat["band_end"]           # 띠 끝은 제 색
    assert sun["wx_prev"] == "snow" and sun["band_start"] and sun["wx_next"] == "sun"
    assert cells["2026-10-01"]["band_start"]                       # 10/1 목요일 = 첫 주 띠 시작
    assert cells["2026-10-02"]["wx_prev"] == "none"                # 날씨 없는 이웃


def test_today_min_keeps_the_lower_morning_value():
    """오후 발표에는 오늘 TMN 이 없다 — 아침에 받은 더 낮은 최저기온을 지킨다."""
    db_session.add(SystemSetting(setting_key=w.WEATHER_KEY, setting_value={"updated_at": "x", "days": {
        "2026-10-14": {"kind": "sun", "t_min": 9, "t_max": 20, "src": "short"}}}))
    db_session.commit()
    items = _hours("20261014", "TMP", [(15, "19"), (18, "15")]) + _hours("20261015", "TMP", [(h, "8" if h == 6 else "12") for h in range(24)])
    w.refresh_short(db_session, now=NOW, transport=_Transport({"getVilageFcst": _Resp(200, _ok(items))}), key="k")
    days = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]
    assert days["2026-10-14"]["t_min"] == 9 and days["2026-10-14"]["t_max"] == 19
    assert days["2026-10-15"]["t_min"] == 8


def test_partial_last_short_day_is_left_to_mid():
    """오후 발표의 끝 날짜(자정 몇 시간뿐)는 단기로 판정하지 않고, 중기예보가 채운다."""
    items = _short_items() + _hours("20261018", "TMP", [(0, "18"), (1, "18")]) + _hours("20261018", "SKY", [(0, "1")])
    w.refresh_short(db_session, now=NOW, transport=_Transport({"getVilageFcst": _Resp(200, _ok(items))}), key="k")
    days = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]
    assert "2026-10-18" not in days
    land = {"wf4Am": "흐리고 비", "wf4Pm": "흐리고 비", "rnSt4Am": 60, "rnSt4Pm": 60}
    tr = _Transport({"getMidLandFcst": _Resp(200, _ok([land])), "getMidTa": _Resp(200, _ok([{"taMin4": 17, "taMax4": 22}]))})
    w.refresh_mid(db_session, now=NOW, transport=tr, key="k")
    d18 = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]["2026-10-18"]
    assert (d18["kind"], d18["t_min"], d18["t_max"], d18["src"]) == ("drizzle", 17, 22, "mid")


def test_mid_overrides_legacy_short_value_without_hours():
    db_session.add(SystemSetting(setting_key=w.WEATHER_KEY, setting_value={"updated_at": "x", "days": {
        "2026-10-18": {"kind": "sun", "t_min": 18, "t_max": 18, "src": "short"}}}))
    db_session.commit()
    tr = _Transport({"getMidLandFcst": _Resp(200, _ok([{"wf4Am": "흐리고 비"}])), "getMidTa": _Resp(200, _ok([{}]))})
    w.refresh_mid(db_session, now=NOW, transport=tr, key="k")
    assert w.load_days(db_session, datetime.date(2026, 10, 18), datetime.date(2026, 10, 18))["days"]["2026-10-18"]["kind"] == "drizzle"


def test_partial_day_drops_legacy_short_value():
    db_session.add(SystemSetting(setting_key=w.WEATHER_KEY, setting_value={"updated_at": "x", "days": {
        "2026-10-17": {"kind": "cloud", "t_min": 14, "t_max": 14, "src": "short"}}}))
    db_session.commit()
    items = _short_items() + _hours("20261017", "TMP", [(h, "14") for h in range(8)])
    w.refresh_short(db_session, now=NOW, transport=_Transport({"getVilageFcst": _Resp(200, _ok(items))}), key="k")
    assert "2026-10-17" not in w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]


def test_join_flags_only_between_same_weather():
    """같은 날씨가 이어지는 쪽만 그림이 번진다 — 다른 날씨 옆은 제 칸 안에서 끝난다."""
    today = datetime.date(2026, 10, 14)
    weather = {"days": {"2026-10-12": {"kind": "sun"}, "2026-10-13": {"kind": "sun"}, "2026-10-14": {"kind": "cloud"},
                        "2026-10-17": {"kind": "sun"}, "2026-10-18": {"kind": "sun"}}}
    from models import Order
    cells = _cells(ct._month_calendar(db_session.query(Order), today, today.replace(day=1), None, weather))
    assert (cells["2026-10-12"]["wx_join_l"], cells["2026-10-12"]["wx_join_r"]) == (False, True)
    assert (cells["2026-10-13"]["wx_join_l"], cells["2026-10-13"]["wx_join_r"]) == (True, False)
    assert not cells["2026-10-14"]["wx_join_l"] and not cells["2026-10-14"]["wx_join_r"]
    assert not cells["2026-10-17"]["wx_join_r"] and not cells["2026-10-18"]["wx_join_l"]  # 토→일은 다른 주(띠가 끊긴다)
    assert not cells["2026-10-15"]["wx_join_l"]  # 날씨 없는 날
