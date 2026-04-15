from types import SimpleNamespace

from models import Order

import foms.services.order_date_sync as order_date_sync


class _FakeOrderScheduleDate:
    def __init__(self, **kwargs):
        self.kind = kwargs["kind"]
        self.date = kwargs["date"]
        self.source = kwargs["source"]
        self.item_index = kwargs["item_index"]


def test_collect_order_schedule_date_specs_normalizes_and_deduplicates_dates():
    order = SimpleNamespace(
        measurement_date="2026-4-1,2026/04/02",
        scheduled_date="2026-5-1,2026/05/02",
        is_erp_beta=True,
        structured_data={
            "schedule": {
                "measurement": {"date": "2026-04-02,2026.04.03"},
                "as_visit": {"date": "2026.06.07"},
                "construction": {"date": "2026-05-02,2026.05.04"},
            },
            "items": [
                {"measurement_date": "2026/04/04", "construction_date": "2026/05/02"},
                {"construction_date": "2026-05-03"},
            ],
        },
    )

    specs = order_date_sync.collect_order_schedule_date_specs(order)

    assert specs == [
        {"kind": "measurement", "date": "2026-04-01", "source": "legacy_column", "item_index": None},
        {"kind": "measurement", "date": "2026-04-02", "source": "legacy_column", "item_index": None},
        {"kind": "measurement", "date": "2026-04-03", "source": "beta_schedule", "item_index": None},
        {"kind": "measurement", "date": "2026-04-04", "source": "beta_item", "item_index": 0},
        {"kind": "as_visit", "date": "2026-06-07", "source": "structured_schedule", "item_index": None},
        {"kind": "construction", "date": "2026-05-01", "source": "legacy_column", "item_index": None},
        {"kind": "construction", "date": "2026-05-02", "source": "legacy_column", "item_index": None},
        {"kind": "construction", "date": "2026-05-04", "source": "beta_schedule", "item_index": None},
        {"kind": "construction", "date": "2026-05-03", "source": "beta_item", "item_index": 1},
    ]


def test_sync_order_dates_uses_get_db_when_session_missing(monkeypatch):
    calls = []
    fake_db = object()
    order = SimpleNamespace(schedule_dates=[])

    monkeypatch.setattr(order_date_sync, "get_db", lambda: fake_db)
    monkeypatch.setattr(
        order_date_sync,
        "collect_order_schedule_date_specs",
        lambda _order: [
            {"kind": "measurement", "date": "2026-04-01", "source": "legacy_column", "item_index": None},
            {"kind": "construction", "date": "2026-05-01", "source": "beta_schedule", "item_index": 2},
        ],
    )
    monkeypatch.setattr(order_date_sync, "OrderScheduleDate", lambda **kwargs: calls.append(kwargs) or _FakeOrderScheduleDate(**kwargs))

    order_date_sync.sync_order_dates(order)

    assert calls == [
        {"kind": "measurement", "date": "2026-04-01", "source": "legacy_column", "item_index": None},
        {"kind": "construction", "date": "2026-05-01", "source": "beta_schedule", "item_index": 2},
    ]
    assert [(row.kind, row.date, row.source, row.item_index) for row in order.schedule_dates] == [
        ("measurement", "2026-04-01", "legacy_column", None),
        ("construction", "2026-05-01", "beta_schedule", 2),
    ]


def test_register_date_sync_listener_syncs_only_changed_orders(monkeypatch):
    captured = {}
    sync_calls = []

    def _fake_listens_for(target, event_name):
        captured["target"] = target
        captured["event_name"] = event_name

        def _decorator(fn):
            captured["listener"] = fn
            return fn

        return _decorator

    monkeypatch.setattr("sqlalchemy.event.listens_for", _fake_listens_for)
    monkeypatch.setattr(order_date_sync, "sync_order_dates", lambda order, session: sync_calls.append((order, session)))

    order_date_sync.register_date_sync_listener()

    order = Order()
    session = SimpleNamespace(new={order}, dirty={object()})
    captured["listener"](session, None, None)

    assert captured["event_name"] == "before_flush"
    assert sync_calls == [(order, session)]
