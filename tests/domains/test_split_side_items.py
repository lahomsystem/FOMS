"""T1a tablet split-view rail contract: permission-scoped side-tab items.

Locks the ``build_split_side_items`` builder behaviour (Spec
docs/plans/2026-07-10-tablet-shell-t0-implementation-spec.md, T1a):
- non-construction users → 9 ERP primary stages + calculator (10 items),
- CONSTRUCTION team → shipment/construction/completion/history only (4, no calc),
- href/label parity with the erp_navigation_contract SSOT,
- active highlighting for the current tab.
"""

from __future__ import annotations

from types import SimpleNamespace

from foms.services.common.erp_navigation_contract import ERP_PRIMARY_NAV_PATHS
from foms.services.foms_split_view import build_split_side_items

_EXPECTED_FULL_IDS = [
    "dashboard",
    "measurement",
    "drawing_workbench",
    "production",
    "shipment",
    "as",
    "construction",
    "completion",
    "history",
    "calculator",
]
_EXPECTED_LABELS = {
    "dashboard": "대시보드",
    "measurement": "실측",
    "drawing_workbench": "도면",
    "production": "생산",
    "shipment": "출고",
    "as": "AS",
    "construction": "시공",
    "completion": "완료",
    "history": "이력",
    "calculator": "계산기",
}


def _user(team: str | None = None, role: str = "STAFF") -> SimpleNamespace:
    return SimpleNamespace(team=team, role=role)


def test_full_menu_for_non_construction_user() -> None:
    items = build_split_side_items(_user(team="SALES"))
    assert [it["id"] for it in items] == _EXPECTED_FULL_IDS
    assert len(items) == 10


def test_none_user_defaults_to_full_menu() -> None:
    items = build_split_side_items(None)
    assert [it["id"] for it in items] == _EXPECTED_FULL_IDS


def test_construction_team_gets_four_stages_no_calculator() -> None:
    items = build_split_side_items(_user(team="CONSTRUCTION"))
    assert [it["id"] for it in items] == [
        "shipment",
        "construction",
        "completion",
        "history",
    ]
    assert all(it["id"] != "calculator" for it in items)


def test_hrefs_and_labels_match_ssot() -> None:
    items = build_split_side_items(_user(team="SALES"))
    by_id = {it["id"]: it for it in items}
    # First nine hrefs come from the erp_navigation_contract path SSOT, in order.
    stage_hrefs = [it["href"] for it in items if it["id"] != "calculator"]
    assert stage_hrefs == list(ERP_PRIMARY_NAV_PATHS)
    assert by_id["calculator"]["href"] == "/wdcalculator"
    for tab_id, label in _EXPECTED_LABELS.items():
        assert by_id[tab_id]["label"] == label
        assert by_id[tab_id]["icon"].startswith("fas fa-")


def test_active_tab_is_highlighted_uniquely() -> None:
    items = build_split_side_items(_user(team="SALES"), active_id="shipment")
    active = [it for it in items if it["active"]]
    assert len(active) == 1
    assert active[0]["id"] == "shipment"


def test_default_active_is_dashboard() -> None:
    items = build_split_side_items(_user(team="SALES"))
    active = [it for it in items if it["active"]]
    assert [it["id"] for it in active] == ["dashboard"]
