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
    d17 = days["2026-10-17"]
    assert {k: d17[k] for k in ("kind", "t_min", "t_max", "pop", "src", "base")} == {
        "kind": "drizzle", "t_min": 12, "t_max": 21, "pop": 70, "src": "mid", "base": "202610140600"}
    assert d17["slots"] == ["sun", "sun", "drizzle", "drizzle"]  # 시간 줄: 오전 글 0~11시 · 오후 글 12~23시
    # 중기는 비 양이 없다 → 강도는 비우고 오전/오후 강수확률만
    assert [(x["k"], x["lv"], x["pop"]) for x in d17["slot_detail"]] == [("sun", None, 10)] * 2 + [("drizzle", None, 70)] * 2
    assert days["2026-10-22"]["slots"] == ["flurry"] * 4  # 8일 뒤부터는 하루 글 하나
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


def test_calendar_cells_carry_weather():
    today = datetime.date(2026, 10, 14)
    weather = {"updated_at": "t", "days": {
        (today + datetime.timedelta(days=i)).isoformat(): {"kind": "sun", "t_min": 10 + i, "t_max": 20 + i} for i in range(-3, 11)}}
    from models import Order
    cal = ct._month_calendar(db_session.query(Order), today, today.replace(day=1), None, weather)
    cells = _cells(cal)
    assert cells["2026-10-11"]["wx"] == "sun"  # 지난 날 = 그날 마지막 예보
    assert (cells["2026-10-14"]["t_min_label"], cells["2026-10-14"]["t_max_label"]) == ("10°", "20°")
    assert cells["2026-10-31"]["wx"] == "" and cells["2026-10-31"]["t_max_label"] == ""  # 예보 밖 = 비움
    assert "날씨 맑음 10~20도" in cells["2026-10-14"]["aria"]
    assert cal["photo"]["month"] == 10 and "CC" in cal["photo"]["credit"]
    assert cal["wx_used"] == ["sun"] and cal["wx_legend"] == [["sun", "맑음"]]  # 범례 = 이 달에 나오는 날씨만



def test_today_keeps_lower_min_and_higher_max():
    """오후 발표에는 오늘 TMN·TMX 가 없다 — 앞서 받은 더 낮은 최저·더 높은 최고를 지킨다."""
    db_session.add(SystemSetting(setting_key=w.WEATHER_KEY, setting_value={"updated_at": "x", "days": {
        "2026-10-14": {"kind": "sun", "t_min": 9, "t_max": 20, "src": "short"}}}))
    db_session.commit()
    items = _hours("20261014", "TMP", [(15, "19"), (18, "15")]) + _hours("20261015", "TMP", [(h, "8" if h == 6 else "12") for h in range(24)])
    w.refresh_short(db_session, now=NOW, transport=_Transport({"getVilageFcst": _Resp(200, _ok(items))}), key="k")
    days = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]
    # 최저는 더 낮은 아침 값, 최고는 더 높은 앞선 값을 지킨다(저녁 발표엔 낮 최고가 없다 — 2026-10-15 '14°/13°' 사고)
    assert days["2026-10-14"]["t_min"] == 9 and days["2026-10-14"]["t_max"] == 20
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



# --------------------------------------------------------------------------- #
# 시간 줄 보기 — 6시간 칸(slots)
# --------------------------------------------------------------------------- #

def test_slots_split_day_into_four_six_hour_parts():
    """0~5·6~11·12~17·18~23시 칸마다 따로 판정한다. 밤 칸의 구름도 그 칸 시각으로 본다(낮 시간만 보지 않는다)."""
    items = (_hours("20261015", "TMP", [(h, "15") for h in range(24)])
             + _hours("20261015", "SKY", [(h, "4" if h < 6 else "1") for h in range(24)])
             + _hours("20261015", "PTY", [(h, "1" if 12 <= h < 18 else "0") for h in range(24)])
             + _hours("20261015", "PCP", [(h, "8.0mm" if h == 13 else ("1mm 미만" if 12 <= h < 18 else "강수없음")) for h in range(24)])
             + _hours("20261015", "SNO", [(h, "적설없음") for h in range(24)]))
    assert w.classify_slots(items) == ["cloud", "sun", "heavy", "sun"]


def test_slots_missing_hours_are_none_and_today_keeps_earlier_parts():
    """오늘 늦은 발표엔 지난 시간이 없다(None) — 먼저 받아 둔 그 칸 값을 지킨다."""
    morning = (_hours("20261014", "TMP", [(h, "15") for h in range(24)]) + _hours("20261014", "SKY", [(h, "4") for h in range(24)])
               + _hours("20261015", "TMP", [(h, "15") for h in range(24)]))
    w.refresh_short(db_session, now=NOW, transport=_Transport({"getVilageFcst": _Resp(200, _ok(morning))}), key="k")
    afternoon = (_hours("20261014", "TMP", [(h, "18") for h in range(15, 24)]) + _hours("20261014", "SKY", [(h, "1") for h in range(15, 24)])
                 + _hours("20261015", "TMP", [(h, "15") for h in range(24)]))
    assert w.classify_slots(afternoon[:18]) == [None, None, "sun", "sun"]
    later = NOW.replace(hour=15, minute=0)
    w.refresh_short(db_session, now=later, transport=_Transport({"getVilageFcst": _Resp(200, _ok(afternoon))}), key="k")
    days = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]
    assert days["2026-10-14"]["slots"] == ["cloud", "cloud", "sun", "sun"]


def test_calendar_cells_carry_slots_only_when_well_formed():
    today = datetime.date(2026, 10, 14)
    weather = {"days": {"2026-10-14": {"kind": "sun", "slots": ["sun", "cloud", "cloud", "drizzle"]},
                        "2026-10-15": {"kind": "sun", "slots": ["sun"]},     # 깨진 값
                        "2026-10-16": {"kind": "cloud"}}}                    # 옛 저장 값(칸 없음)
    from models import Order
    cells = _cells(ct._month_calendar(db_session.query(Order), today, today.replace(day=1), None, weather))
    assert cells["2026-10-14"]["wx_slots"] == ["sun", "cloud", "cloud", "drizzle"]
    assert cells["2026-10-15"]["wx_slots"] is None and cells["2026-10-16"]["wx_slots"] is None
    assert cells["2026-10-20"]["wx_slots"] is None


# --------------------------------------------------------------------------- #
# 시간 줄 v2 — 칸마다 강도·강수확률·바람 (기상청 강수강도)
# --------------------------------------------------------------------------- #

def _slot_rows(date, pty, pcp, sno="적설없음", sky="4", pop="60", wsd="2.0", hours=range(24)):
    rows = []
    for h in hours:
        rows += _hours(date, "TMP", [(h, "10")]) + _hours(date, "PTY", [(h, pty)]) + _hours(date, "PCP", [(h, pcp)])
        rows += _hours(date, "SNO", [(h, sno)]) + _hours(date, "SKY", [(h, sky)]) + _hours(date, "POP", [(h, pop)])
        rows += _hours(date, "WSD", [(h, wsd)])
    return rows


@pytest.mark.parametrize("pcp, kind, lv", [
    ("1mm 미만", "drizzle", 0), ("2.0mm", "drizzle", 1), ("8.0mm", "rain", 2), ("30.0~50.0mm", "heavy", 3),
])
def test_slot_detail_rain_levels_follow_kma_intensity(pcp, kind, lv):
    """비 강도 = 기상청 강수강도(이슬비 <1 · 약한 비 1~3 · 보통 비 3~15 · 강한 비 ≥15 mm/h)."""
    det = w.classify_slot_detail(_slot_rows("20261015", "1", pcp))
    assert all(d["k"] == kind and d["lv"] == lv and d["pop"] == 60 and d["wind"] == 2.0 for d in det)


@pytest.mark.parametrize("sno, kind, lv", [("1cm 미만", "flurry", 0), ("2.0cm", "snow", 1), ("5.0cm 이상", "snow", 2)])
def test_slot_detail_snow_levels(sno, kind, lv):
    det = w.classify_slot_detail(_slot_rows("20261215", "3", "강수없음", sno=sno))
    assert {(d["k"], d["lv"]) for d in det} == {(kind, lv)}


@pytest.mark.parametrize("sky, kind", [("1", "sun"), ("3", "partly"), ("4", "cloud")])
def test_slot_detail_sky_three_steps(sky, kind):
    det = w.classify_slot_detail(_slot_rows("20261015", "0", "강수없음", sky=sky))
    assert {d["k"] for d in det} == {kind}


def test_three_hourly_day_is_a_full_day_and_rate_is_per_hour():
    """3~4일 뒤 예보는 3시간 간격(하루 8칸) — 하루치로 받고, 3시간 강수량은 시간당으로 나눠 본다(2026-10-15 18일 사고)."""
    rows = _slot_rows("20261018", "1", "6.0mm", hours=range(0, 24, 3))
    assert w._covers_day(rows)
    assert {(d["k"], d["lv"]) for d in w.classify_slot_detail(rows)} == {("drizzle", 1)}  # 6mm/3h = 2mm/h = 약한 비
    w.refresh_short(db_session, now=NOW, transport=_Transport({"getVilageFcst": _Resp(200, _ok(rows))}), key="k")
    d18 = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]["2026-10-18"]
    assert d18["src"] == "short" and d18["full"] is True
    # 중기예보가 와도 하루치 단기 값을 덮지 않는다
    tr = _Transport({"getMidLandFcst": _Resp(200, _ok([{"wf4Am": "맑음", "wf4Pm": "맑음"}])), "getMidTa": _Resp(200, _ok([{}]))})
    w.refresh_mid(db_session, now=NOW, transport=tr, key="k")
    assert w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]["2026-10-18"]["src"] == "short"


def test_day_kind_is_worst_slot_and_today_keeps_earlier_slots():
    """하루 대표 날씨 = 6시간 칸 중 가장 궂은 것. 오늘 늦은 발표는 지난 칸을 앞서 받은 값으로 채운 뒤 다시 정한다."""
    morning = _slot_rows("20261014", "1", "8.0mm", hours=range(6, 12)) + _slot_rows("20261014", "0", "강수없음", sky="1", hours=range(12, 24))
    w.refresh_short(db_session, now=NOW, transport=_Transport({"getVilageFcst": _Resp(200, _ok(morning))}), key="k")
    day = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]["2026-10-14"]
    assert day["kind"] == "rain" and [d and d["k"] for d in day["slot_detail"]] == [None, "rain", "sun", "sun"]
    evening = _slot_rows("20261014", "0", "강수없음", sky="1", hours=range(18, 24))
    w.refresh_short(db_session, now=NOW.replace(hour=17), transport=_Transport({"getVilageFcst": _Resp(200, _ok(evening))}), key="k")
    day = w.load_days(db_session, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))["days"]["2026-10-14"]
    assert day["kind"] == "rain"  # 저녁 몇 시간이 맑다고 하루가 '맑음'이 되지 않는다
    assert [d and d["k"] for d in day["slot_detail"]] == [None, "rain", "sun", "sun"]


def test_mid_text_partly_vs_cloud():
    assert w.classify_mid_text("구름많음") == "partly" and w.classify_mid_text("흐림") == "cloud"
    assert w.classify_mid_text("구름많고 비") == "drizzle" and w.classify_mid_text("흐리고 눈") == "flurry"
