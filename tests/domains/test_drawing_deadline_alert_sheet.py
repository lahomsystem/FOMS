"""작업 시트 '알림 보냄' 줄(설계서 2026-11-22 §5-7 · §8 표) — 보낸 것만 · 날마다 묶음 · 켬 + 안 내려온 주문만 기록 줄 읽기 +1."""
from __future__ import annotations

from db import db_session
from foms.services.notifications import drawing_deadline_alert as alert
from models import SystemSetting
from tests.support.drawing_deadline_seed import statements

# --------------------------------------------------------------------------- #
# 작업 시트 '알림 보냄'(§5-7)
# --------------------------------------------------------------------------- #
def test_알림_보냄_줄은_보낸_것만_날마다_묶어(app):
    sent = {
        "7:2026-11-23:pm": {"at": "2026-11-23T18:01+09:00", "to": ["이가짜"], "skipped": 0},
        "7:2026-11-23:am": {"at": "2026-11-23T08:02+09:00", "to": ["이가짜"], "skipped": 0},
        "7:2026-11-24:late": {"at": "2026-11-24T08:01+09:00", "to": ["이가짜"], "skipped": 0},
        "7:2026-11-25:late": {"at": "2026-11-25T08:01+09:00", "to": [], "skipped": 2},  # 아무도 안 받음
        "77:2026-11-23:am": {"at": "2026-11-23T08:03+09:00", "to": ["이가짜"], "skipped": 0},
    }
    assert alert.format_alert_line(sent, 7) == "알림 보냄 11/23 (월) 아침 8:02 · 저녁 6:01 · 11/24 (화) 아침 8:01"
    assert alert.format_alert_line(sent, 8) == "" and alert.format_alert_line({}, 7) == ""


def _sheet(client, oid):
    return client.get(f"/erp/production/sheet/{oid}").get_data(as_text=True)


def _sheet_queries(client, oid):
    client.get(f"/erp/production/sheet/{oid}")
    with statements() as seen:
        assert client.get(f"/erp/production/sheet/{oid}").status_code == 200
    return len(seen)


def test_작업_시트_알림_보냄_줄과_쿼리_수(client, monkeypatch):
    """켬 + 안 내려온 주문만 기록 줄 PK 읽기 +1(§8 표). 끔이면 줄도 쿼리도 없다. 내려온 주문은 늘 그대로."""
    from tests.domains.test_production_home_tabs import _make_user
    from tests.domains.test_production_v7_screens import _sheet_order

    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")
    monkeypatch.delenv(alert.ENABLED_ENV, raising=False)
    _make_user(client, "dda_sheet", "PRODUCTION")
    wait = _sheet_order("가기다림", "DRAWING", 3, drawing_assignees=[{"id": 1, "name": "장가짜"}]).id
    made = _sheet_order("나생산", "PRODUCTION", 3).id
    db_session.add(SystemSetting(setting_key=alert.STATE_KEY, version=1, setting_value={"sent": {
        f"{wait}:2026-11-23:am": {"at": "2026-11-23T08:02+09:00", "to": ["장가짜"], "skipped": 0},
        f"{wait}:2026-11-23:pm": {"at": "2026-11-23T18:01+09:00", "to": ["장가짜"], "skipped": 0},
    }}))
    db_session.commit()
    off = {"wait": _sheet_queries(client, wait), "made": _sheet_queries(client, made)}
    assert "알림 보냄" not in _sheet(client, wait) and off["wait"] == off["made"]
    monkeypatch.setenv(alert.ENABLED_ENV, "1")
    on = {"wait": _sheet_queries(client, wait), "made": _sheet_queries(client, made)}
    assert "<small>알림 보냄 11/23 (월) 아침 8:02 · 저녁 6:01</small>" in _sheet(client, wait)
    assert on == {"wait": off["wait"] + 1, "made": off["made"]}, (off, on)
