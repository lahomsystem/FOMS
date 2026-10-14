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
    assert w.classify_short(items)["kind"] == "snow"
    assert w.classify_short(_hours("20261014", "PTY", [(9, "2")]))["kind"] == "snow"  # 비/눈 = 눈 그림


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
    assert out["t_max"] == -1 and out["pop"] == 60
    assert w.classify_short(items + _hours("20261014", "TMX", [(15, "-0.4")]))["t_max"] == 0


@pytest.mark.parametrize("texts, kind", [
    (("흐리고 비", "맑음"), "drizzle"),   # 중기는 비의 양이 없다 → 부슬비
    (("비/눈",), "snow"),
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
            + _hours("20261015", "SKY", [(h, "1") for h in range(9, 19)]) + _hours("20261015", "TMX", [(15, "25.0")]))


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
    ta = {"taMax3": 21, "taMax8": 2}
    tr = _Transport({"getMidLandFcst": _Resp(200, _ok([land])), "getMidTa": _Resp(200, _ok([ta]))})
    # tmFc 10/14 06시 → 3일 뒤 = 10/17, 8일 뒤 = 10/22. 단기 날짜(10/14·15)는 건드리지 않는다.
    out = w.refresh_mid(db_session, now=NOW, transport=tr, key="k")
    assert out == {"stored": 2, "base": "202610140600"}
    days = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]
    assert days["2026-10-17"] == {"kind": "drizzle", "t_max": 21, "pop": 70, "src": "mid", "base": "202610140600"}
    assert days["2026-10-22"]["kind"] == "snow" and days["2026-10-22"]["t_max"] == 2
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


def test_calendar_cells_carry_weather_and_only_seven_days_move():
    today = datetime.date(2026, 10, 14)
    weather = {"updated_at": "t", "days": {
        (today + datetime.timedelta(days=i)).isoformat(): {"kind": "sun", "t_max": 20 + i} for i in range(-3, 11)}}
    from models import Order
    cal = ct._month_calendar(db_session.query(Order), today, today.replace(day=1), None, weather)
    cells = _cells(cal)
    live = sorted(iso for iso, c in cells.items() if c["wx_live"])
    assert live == [(today + datetime.timedelta(days=i)).isoformat() for i in range(7)]
    assert cells["2026-10-11"]["wx"] == "sun" and not cells["2026-10-11"]["wx_live"]  # 지난 날 = 멈춘 그림
    assert cells["2026-10-14"]["t_max_label"] == "20°"
    assert cells["2026-10-31"]["wx"] == "" and cells["2026-10-31"]["t_max_label"] == ""  # 예보 밖 = 비움
    assert "날씨 맑음 20도" in cells["2026-10-14"]["aria"]
    assert cal["photo"]["month"] == 10 and "CC" in cal["photo"]["credit"]


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
