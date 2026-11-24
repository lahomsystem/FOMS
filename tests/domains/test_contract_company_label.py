"""계약 회사 표시 이름(설계서 2026-11-23 §8-7 · 결정 C7) — ``flags.factory2`` 는 실제 2공장과 다른 것(견적 공급자 · 계좌를 가르는
계약 회사)이라 화면 글에서 '2공장'을 뺀다. 칸 이름 · 값 · 뜻 · 권한 · 견적 동작은 그대로다.

되돌리면 실패: 옛 칸반 거르개 · 칩 · 도면팀 바뀜 알림 · 감사 이름 · 실측 태블릿 폼에 '2공장'이 남음 · 거르개 값(1 · 2)이 바뀜(옛 판정 깨짐).
대조군: '라홈시스템'만 쓰는 곳(주문 화면 체크 · 접수 마법사 · 주문 대시보드 딱지)은 지금 글 그대로.
"""
from __future__ import annotations

import re
from pathlib import Path

from foms.services.audit_message_display import PATH_LABELS
from foms.services.notifications.drawing_order_change import _STRUCT_FIELD_LABELS, compute_drawing_relevant_changes

ROOT = Path(__file__).resolve().parents[2]
NEW = "라홈시스템 계약"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_old_kanban_filter_and_chip_say_contract_company_and_keep_values():
    src = _read("templates/production/partials/tablet_kanban_body.html")
    select = src.split("<select data-tablet-prod-factory", 1)[1].split("</select>", 1)[0]
    assert re.findall(r'<option value="(\d?)"[^>]*>([^<]+)</option>', select) == [
        ("", "전체"), ("1", "다른 계약"), ("2", NEW)]  # 값 · 판정(tablet-domain-sheets.js)은 그대로
    assert 'aria-label="계약 회사"' in select
    chip = src.split('class="foms-kanban-card__factory"', 1)[1].split("</span>", 1)[0]
    assert f'title="{NEW} 주문"' in chip and chip.rstrip().endswith(NEW)
    assert "2공장" not in src


def test_drawing_change_alert_audit_and_tablet_form_labels():
    old = {"flags": {"factory2": False}}
    new = {"flags": {"factory2": True}}
    labels = [c["label"] for c in compute_drawing_relevant_changes(old, new) if c["path"] == "flags.factory2"]
    assert labels == [NEW] and _STRUCT_FIELD_LABELS["factory2"] == NEW
    assert PATH_LABELS["flags.factory2"] == NEW
    js = _read("static/js/foms/tablet-measure-form.js")
    assert js.count(f'"{NEW}"') == 2 and "라홈시스템(2공장)" not in js
    assert "tablet-measure-form.js') }}?v=20261124f" in _read("templates/partials/shared/layout_scripts.html")


def test_lahom_only_places_stay_as_now():
    assert '<span class="form-check-label">라홈시스템</span>' in _read("templates/orders/partials/erp_order_tab.html")
    assert '<span class="foms-wizard__flag-txt">라홈시스템</span>' in _read("templates/orders/wizard/step3_schedule.html")
    assert "<i class=\"fas fa-industry\"></i> 라홈시스템</span>" in _read("templates/orders/partials/dashboard_grid.html")
