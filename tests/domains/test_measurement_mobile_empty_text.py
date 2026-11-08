"""휴대폰 실측 화면 빈 목록 문구(2026-11-08 점검 ui-phone 3).

아래 탭 "실측" 배지는 날짜와 상관없는 실측 단계(MEASURE) 주문 수이고(dashboard_counts.NAV_STATUS_BUCKETS),
목록은 고른 날짜의 실측만 보인다 — 배지 1 · 목록 0 은 정상이다. 다른 날 실측은 위 "오늘 예정 실측 없음 ·
다음 예정" 줄이 알려 준다. 빈 상자는 없는 "칩 필터" 이야기를 하지 않고, 검색했을 때만 되돌리는 길을 적는다.
"""

from __future__ import annotations

from flask import render_template

PANEL = [
    {"date": "2026-11-08", "count": 0, "weekday": 6},
    {"date": "2026-11-20", "count": 1, "weekday": 4},
]


def _render_empty(app, *, search_q: str) -> str:
    with app.test_request_context("/erp/measurement"):
        return render_template(
            "measurement/partials/mobile_list.html", mobile_queue_rows=[], measurement_panel_dates=PANEL,
            selected_date="2026-11-08", today_date="2026-11-08", search_q=search_q,
        )


def _empty_box(html: str) -> str:
    start = html.index('class="foms-mobile-empty"')
    return html[start: html.index("</div>", start)]


def test_검색_없이_비면_칩_이야기_없이_날짜만_말한다(app) -> None:
    html = _render_empty(app, search_q="")
    box = _empty_box(html)
    assert "칩" not in box
    assert "고른 날짜에 잡힌 실측 일정이 없습니다." in box
    assert "검색어" not in box, "검색하지 않았는데 검색어를 지우라고 하지 않는다"
    # 다른 날 실측은 기존 상태 줄이 알려 준다(빈 상자와 말이 어긋나지 않음).
    assert "다음 예정 · 2026-11-20 · 1건" in html


def test_검색해서_비면_날짜_또는_검색어를_바꾸라고_한다(app) -> None:
    box = _empty_box(_render_empty(app, search_q="홍길동"))
    assert "칩" not in box
    assert "조건에 맞는 실측 일정이 없습니다." in box
    assert "위 날짜를 바꾸거나 검색어를 지워 보세요." in box
