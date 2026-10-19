"""KST 경계 회귀: 날짜 기본값은 KST 오늘, aware 시각은 UTC 로 바꾼 뒤 비교한다."""
from __future__ import annotations

import datetime

from foms.services import settlement_channel
from foms.services.integrations.naver_commerce import claim_watch
from foms.web.admin import naver_ingest


def test_refreshed_since_converts_kst_offset_to_utc():
    since = datetime.datetime(2026, 10, 18, 16, 0, 0)  # naive UTC = KST 10-19 01:00
    # KST 00:30 = UTC 15:30 → since 보다 이전. 그냥 떼면 00:30 으로 오판되던 자리.
    assert claim_watch._refreshed_since("2026-10-19T00:30:00+09:00", since) is False
    assert claim_watch._refreshed_since("2026-10-19T01:30:00+09:00", since) is True
    assert claim_watch._refreshed_since("2026-10-18T16:30:00", since) is True


def test_is_recent_refresh_converts_kst_offset_to_utc():
    cutoff = datetime.datetime(2026, 10, 18, 16, 0, 0)
    assert claim_watch._is_recent_refresh("2026-10-19T00:59:00+09:00", cutoff) is False
    assert claim_watch._is_recent_refresh("2026-10-19T01:00:00+09:00", cutoff) is True


def test_hours_since_converts_kst_offset(monkeypatch):
    now = datetime.datetime(2026, 10, 18, 16, 0, 0)
    monkeypatch.setattr(settlement_channel, "now_utc_naive", lambda: now)
    assert settlement_channel._hours_since("2026-10-19T00:00:00+09:00") == 1.0
    assert settlement_channel._hours_since("2026-10-18T15:00:00") == 1.0


def test_expiry_days_left_uses_kst_today(monkeypatch):
    from foms.services.integrations.naver_commerce import app_expiry

    monkeypatch.setattr(app_expiry, "read_expiry_date", lambda db: datetime.date(2026, 10, 29))
    monkeypatch.setattr(naver_ingest, "get_today_kst", lambda: datetime.date(2026, 10, 19))
    assert naver_ingest._expiry_view(None)["days_left"] == 10


def test_packing_js_formats_in_seoul_timezone():
    import pathlib
    src = pathlib.Path("static/js/shipment/foms-packing.js").read_text(encoding="utf-8")
    assert src.count("timeZone: 'Asia/Seoul'") == 4
