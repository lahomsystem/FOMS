"""긴급 실측 알림 → 실측 탭 그 카드로, 그리고 목록·카드의 "당일" 표시(2026-09-29 목업 A안).

- 폰 알림·앱 확인창·알림 벨 세 입구가 모두 ``/erp/measurement?date=<알림 KST 날짜>&focus_order=<id>``
  로 간다(예전: 주문 수정 화면 ``/erp/orders/<id>``).
- "당일" 판정은 보는 날짜(KST)에 만들어진 ``MEASURE_SAME_DAY_ADDED`` 알림이다.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from types import SimpleNamespace

from db import db_session
from foms.services.measurement.same_day_mark import load_same_day_marks
from foms.services.notifications.measure_same_day_payload import measure_same_day_link
from models import Notification

ROOT = Path(__file__).resolve().parents[2]
MOBILE_LIST = ROOT / "templates/measurement/partials/mobile_list.html"


def test_link_uses_kst_date_of_alert():
    # UTC 9/28 15:30 = KST 9/29 00:30 — 날짜는 KST 로 박힌다.
    added = _dt.datetime(2026, 9, 28, 15, 30)
    assert measure_same_day_link(77, added) == "/erp/measurement?date=2026-09-29&focus_order=77"
    assert measure_same_day_link(77, None) == "/erp/measurement?focus_order=77"


def test_push_deep_link_goes_to_measurement_card():
    from foms.services.notifications.push_sender import _build_payload

    notif = SimpleNamespace(
        id=5,
        is_urgent=False,
        notification_type="MEASURE_SAME_DAY_ADDED",
        order_id=42,
        created_at=_dt.datetime(2026, 9, 29, 0, 59),
    )
    payload = _build_payload(notif)
    assert payload["data"]["deep_link"] == "/erp/measurement?date=2026-09-29&focus_order=42"
    # 고객 이름을 넘기지 않으면(주문 조회 전) 일반 문구.
    assert payload["body"] == "오늘 실측이 긴급 추가됐어요"


def test_bell_list_deep_link_matches_push():
    from foms.api.notifications import _resolve_notification_deep_link

    notif = SimpleNamespace(
        notification_type="MEASURE_SAME_DAY_ADDED",
        order_id=42,
        created_at=_dt.datetime(2026, 9, 29, 0, 59),
    )
    out = _resolve_notification_deep_link(notif, {})
    assert out["deep_link_url"] == "/erp/measurement?date=2026-09-29&focus_order=42"


def _notif(order_id: int, created_at: _dt.datetime, by: str, ntype: str = "MEASURE_SAME_DAY_ADDED"):
    n = Notification(
        order_id=order_id,
        notification_type=ntype,
        target_type="TEAM",
        target_team="SALES",
        title="t",
        created_by_name=by,
        created_at=created_at,
    )
    db_session.add(n)
    return n


def test_load_marks_only_that_kst_day(app):
    # KST 9/29 = UTC 9/28 15:00 ~ 9/29 15:00
    _notif(901, _dt.datetime(2026, 9, 29, 0, 59), "이소영")        # KST 09:59 → 표시
    _notif(901, _dt.datetime(2026, 9, 29, 3, 0), "나중")           # 같은 주문 두 번째 → 가장 이른 것만
    _notif(902, _dt.datetime(2026, 9, 28, 14, 59), "전날")          # KST 9/28 23:59 → 제외
    _notif(903, _dt.datetime(2026, 9, 29, 1, 0), "x", "ERP_ORDER_CHANGED")  # 다른 유형 → 제외
    _notif(904, _dt.datetime(2026, 9, 29, 2, 0), "목록 밖")         # 목록에 없는 주문 → 제외
    db_session.commit()

    marks = load_same_day_marks(db_session, [901, 902, 903], "2026-09-29")
    assert marks == {901: {"at": "09:59", "by": "이소영"}}
    assert load_same_day_marks(db_session, [901], "bad-date") == {}
    assert load_same_day_marks(db_session, [], "2026-09-29") == {}


def test_template_renders_badge_row_class_and_why_box():
    text = MOBILE_LIST.read_text(encoding="utf-8")
    assert "{% if o.same_day_mark %} is-same-day{% endif %}" in text
    assert 'class="foms-meas-sameday" data-meas-same-day' in text
    assert 'class="foms-meas-sameday-why" data-meas-same-day-why' in text
