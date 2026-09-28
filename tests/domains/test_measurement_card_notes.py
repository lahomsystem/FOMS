"""실측 모바일 카드 현장 메모 — 화면 계약(2026-09-28 목업 ① "종류별 색 알약").

- 주소·연락처 특이사항: 그 줄 바로 밑(매크로 옵트인 address_note / phone_note).
- 실측 특이사항·비고·고객 요청(네이버 배송메모): "현장 메모" 한 상자, 종류별 알약.
- 목록 줄: "가기 전 확인 N" 알약(빈 칸 제외 개수). 메모가 없으면 아무것도 안 그린다.
- 다른 도메인 카드(옵트인 없음)는 렌더가 바뀌지 않는다.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from flask import render_template, render_template_string

from foms.services.measurement.site_memo import build_site_memo
from foms.services.measurement.visit_check import build_measurement_glance_groups

ROOT = Path(__file__).resolve().parents[2]
FULL = {"address": "지하 B2 방문차량 등록", "phone": "오후 2시 이후", "measure": "붙박이장 철거 뒤\n<b>줄자</b>",
        "notes": "몰딩 샘플", "request": "방문 전 문자"}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _row(i: int, memo: dict) -> dict:
    return {"id": i, "customer_name": f"고객{i}", "manager_name": "최진호", "measurement_visit_done": False,
            "structured_data": {}, "alerts": {}, "attachment_preview_items": [], "attachments_count": 0,
            "address": "경기도 안양시 평촌대로 1", "phone": "010-0000-1234",
            "site_memo": memo, "site_memo_count": sum(1 for v in memo.values() if v)}


def _render(app, rows) -> str:
    with app.test_request_context("/erp/measurement"):
        return render_template(
            "measurement/partials/mobile_list.html", mobile_queue_rows=rows,
            mobile_glance_groups=build_measurement_glance_groups(rows), measurement_visit_date="2026-04-08",
            can_mark_measurement_visit=True, selected_date="2026-04-08", today_date="2026-04-08",
            current_user=SimpleNamespace(name="최진호"), erp_mine_only=False,
        )


def _card(html: str, oid: int) -> str:
    return html.split(f'id="meas-card-{oid}"', 1)[1].split("</article>", 1)[0]


def test_build_site_memo_reads_five_sources_and_tolerates_string_notes():
    order = SimpleNamespace(notes="  비고  ", structured_data={
        "notes": {"address_note": "주차", "phone_note": "", "measurement_note": "줄자"},
        "naver": {"shipping_memo": "문자 주세요"}})
    got = build_site_memo(order)
    assert got["site_memo"] == {"address": "주차", "phone": "", "measure": "줄자", "notes": "비고",
                                "request": "문자 주세요"}
    assert got["site_memo_count"] == 4
    # 마법사 주문: structured_data.notes 가 문자열 — 특이사항 dict 로 읽지 않고, 비고는 Order.notes 로.
    wiz = build_site_memo(SimpleNamespace(notes="현장 비고", structured_data={"notes": "현장 비고"}))
    assert wiz["site_memo"]["notes"] == "현장 비고" and wiz["site_memo_count"] == 1
    assert build_site_memo(SimpleNamespace(notes=None, structured_data=None))["site_memo_count"] == 0


def test_card_places_row_notes_and_memo_box(app):
    card = _card(_render(app, [_row(1, FULL)]), 1)
    # 주소·연락처 메모는 그 줄 dl 안, 값 바로 뒤.
    assert card.index('data-queue-card-field="address"') < card.index('data-queue-card-field="address-note"') \
        < card.index('data-queue-card-field="phone"') < card.index('data-queue-card-field="phone-note"')
    assert card.count("data-queue-card-has-note") == 2
    # 현장 메모 상자: meta 다음, 단추 줄 앞, 세 종류 알약 순서 고정, 개수 3.
    assert card.index("</dl>") < card.index("data-meas-memo") < card.index("queue-card__action")
    assert card.index("--measure") < card.index("--notes") < card.index("--request")
    assert 'foms-meas-memo__count">3<' in card
    assert "붙박이장 철거 뒤\n&lt;b&gt;줄자&lt;/b&gt;" in card, "줄바꿈 그대로·HTML 은 이스케이프"


def test_list_row_pill_counts_memos(app):
    html = _render(app, [_row(1, FULL), _row(2, dict.fromkeys(FULL, ""))])
    assert 'data-meas-glance-memo="5">가기 전 확인 5<' in html
    assert html.count("data-meas-glance-memo") == 1


def test_empty_memo_renders_nothing(app):
    card = _card(_render(app, [_row(2, dict.fromkeys(FULL, ""))]), 2)
    for marker in ("data-meas-memo", "row-note", "data-queue-card-has-note"):
        assert marker not in card


def test_macro_without_opt_in_is_unchanged(app):
    """옵트인이 없는 도메인(시공·생산·출고…)은 메모 표식이 하나도 안 나온다."""
    src = ("{% from 'partials/shared/erp_mobile_queue_card_v2.html' import render_queue_card_v2 %}"
           "{{ render_queue_card_v2(o) }}")
    order = {"id": 7, "customer_name": "고객", "address": "주소 1", "phone": "010-1", "alerts": {},
             "structured_data": {}}
    with app.test_request_context("/"):
        html = render_template_string(src, o=order)
    assert "has-note" not in html and "row-note" not in html


def test_assets_wired():
    css = _read("static/css/contexts/measurement/measurement-mobile-glance.css")
    text_rule = css.split(".foms-meas-memo__text {", 1)[1].split("}", 1)[0]
    assert "white-space: pre-line;" in text_rule
    note_rule = css.split(".foms-queue-card-v2__row-note {", 1)[1].split("}", 1)[0]
    assert "z-index: 1;" in note_rule, "메모를 눌러도 줄 전체 지도·전화 링크가 열리면 안 된다"
    value_rule = css.split("[data-queue-card-has-note] > dd:not(.foms-queue-card-v2__row-note) {", 1)[1].split("}", 1)[0]
    assert "flex: 1 1 0;" in value_rule, "메모 줄에서도 주소 값이 이름표와 같은 줄에 남아야 한다(스테이징 #4172)"
    parts = _read("static/js/measurement/mobile-glance-sheet-parts.js")
    place = parts.split("function placePhotos(card) {", 1)[1].split("card.querySelectorAll", 1)[0]
    assert "card.querySelector('[data-meas-memo]') || card.querySelector('.queue-card__meta')" in place
    assert "_row.update(build_site_memo(_o))" in _read("foms/web/measurement/dashboard.py")
