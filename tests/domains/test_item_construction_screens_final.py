"""제품마다 시공 끝 — 최종 화면 검수 고침(F-S1 ~ F-S8) 계약.

설계서 docs/specs/2026-11-21-item-construction-done_SPEC.md 6절. 가짜 DOM 동작(읽는 중 끔 · 그날 · 나눠 시공 줄만 읽기)은
tests/support/item_construction_dom_node_checks.js 가 잰다(tests/domains/test_item_construction_screens.py 가 부른다).
"""
from __future__ import annotations

import datetime
from pathlib import Path

from foms.services.orders import item_construction_view as icv

ROOT = Path(__file__).resolve().parents[2]
TODAY = datetime.date(2026, 11, 21)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_visit_day_is_min_of_chosen_and_today_within_13_days() -> None:
    assert icv.visit_day("2026-11-25", TODAY) == "2026-11-21"  # 앞날 줄 → 오늘
    assert icv.visit_day("2026-11-19", TODAY) == "2026-11-19"
    assert icv.visit_day("2026-11-08", TODAY) == "2026-11-08"  # 오늘-13일까지
    assert icv.visit_day("2026-11-07", TODAY) == "2026-11-21"  # 더 지난 날 → 오늘
    assert icv.visit_day(None, TODAY) == icv.visit_day("x", TODAY) == "2026-11-21"


def test_annotate_split_rows_uses_clamped_day(monkeypatch) -> None:
    from tests.domains.test_item_construction_screens import _split_sd

    monkeypatch.delenv("FOMS_ITEM_CONSTRUCTION_DONE_ENABLED", raising=False)
    today = icv.get_today_kst()
    later = (today + datetime.timedelta(days=4)).isoformat()
    rows = [{"stage": "생산중", "structured_data": _split_sd()}]
    icv.annotate_split_rows(rows, visit_date=later)
    assert rows[0]["item_done_visit_date"] == today.isoformat()


def test_complete_windows_busy_and_stale_reload() -> None:
    gate = _read("static/js/construction/foms-complete-gate.js")
    dash = _read("static/js/construction/dashboard.js")
    for js in (gate, dash):
        assert "hasAttribute('data-busy')" in js and "setAttribute('data-busy', '1')" in js  # F-S5
        assert "FomsVisitItems.isStale(" in js  # F-S3
    assert "mountVisitItems(sheet, orderId);" in gate.split("isStale(", 1)[1][:200]
    assert "mountCompleteVisitItems(" in dash.split("isStale(", 1)[1][:200]


def test_undo_reason_reopens_with_text_when_too_long() -> None:
    js = _read("static/js/orders/erp-item-construction-done.js")
    assert "REASON_MAX = 200;" in js and "askReason(name, onReason, reason);" in js  # F-S7
    assert "box.value = prefill" in js


def test_construction_only_moves_the_removed_day() -> None:
    js = _read("static/js/orders/erp-construction-only.js")
    assert "if (diff.removed.length === 1) fromSel.value = diff.removed[0];" in js  # F-S4
    assert "addEventListener('change', syncFromPick)" in js


def test_pins_and_partner_layout_follow_erp_pro() -> None:
    head = _read("templates/partials/shared/layout_head.html")
    pin = head.split("erp-pro.css') }}?v=", 1)[1].split('"', 1)[0]
    assert f"erp-pro.css') }}}}?v={pin}" in _read("templates/partner/layout.html")  # F-S6
    tpl = _read("templates/orders/partials/edit_order_body.html")
    assert "{% if erp_construction_dates|default([]) %}" in tpl  # F-S8
