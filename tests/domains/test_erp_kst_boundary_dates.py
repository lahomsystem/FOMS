"""KST 0~9시 경계 날짜 회귀 — UTC 날짜로 하루 당겨지던 버그 방지."""
import datetime

from foms.services.orders import erp_policy_tasks as tasks

KST = datetime.timezone(datetime.timedelta(hours=9))


def _sla(stage_updated_at):
    return tasks._resolve_due_date(
        {"type": "blueprint_sla", "offset_hours": 48},
        {"workflow": {"stage_updated_at": stage_updated_at}},
        None,
    )


def test_blueprint_sla_naive_utc_at_kst_0030_uses_kst_date():
    # 2026-10-19 00:30 KST == 2026-10-18 15:30 UTC (naive 저장)
    assert _sla("2026-10-18T15:30:00") == "2026-10-21"


def test_blueprint_sla_aware_kst_and_naive_utc_agree():
    assert _sla("2026-10-19T00:30:00+09:00") == "2026-10-21"
    assert _sla("2026-10-19T00:30:00+09:00") == _sla("2026-10-18T15:30:00")


def test_blueprint_sla_invalid_timestamp_returns_none():
    assert _sla("not-a-date") is None


def test_today_due_uses_kst_date_for_naive_utc_now():
    now_utc_naive = datetime.datetime(2026, 10, 18, 15, 30)  # = 10-19 00:30 KST
    assert tasks._resolve_due_date({"type": "today"}, {}, now_utc_naive) == "2026-10-19"


def test_today_due_defaults_to_kst_today(monkeypatch):
    monkeypatch.setattr(tasks, "get_today_kst", lambda: datetime.date(2026, 10, 19))
    assert tasks._resolve_due_date({"type": "today"}, {}, None) == "2026-10-19"


def test_sales_delivery_card_assigned_at_shows_kst_date(client):
    env = client.application.jinja_env
    tmpl = env.get_template("measurement/partials/sales_delivery_cards.html")
    html = tmpl.module.render_sales_delivery_cards([
        {"order_id": 1, "customer_name": "x", "state": "assigned",
         "assigned_by": "a", "assigned_at": "2026-10-18T15:30:00"},
    ])
    assert "2026-10-19" in str(html)
    assert "2026-10-18" not in str(html)
