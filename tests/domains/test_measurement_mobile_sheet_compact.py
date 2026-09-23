"""실측 모바일 바텀시트 압축안(2026-09-23 목업 "이대로 만들기") — 화면 계약.

목업: 세션 스크래치 sheet-compact/compare.html(가운데 폰), 규칙 원문 after-append.css.
test_measurement_mobile_unified.py 가 500줄 기준(test_file_size_ratchet)에 닿아 따로 둔다.

고정하는 회귀축:
- decorate() 가 줄·뱃지·단추 줄에 data-meas-sheet-* 표식을 단다(노드 이동 없이, 몇 번 불려도 같게)
- CSS 는 :has() 없이 그 표식만 고르고, 모든 규칙이 .foms-meas-sheet 안(공유 카드·다른 화면 불변)
- 덧붙이기만(기존 규칙 해시는 test_glance_css_is_append_only 가 지킨다)
"""

from __future__ import annotations

import re

from tests.domains.test_measurement_mobile_unified import GLANCE_CSS, PARTS_JS, _missing, _read

COMPACT_MARKER = "/* ── 압축 시트(2026-09-23"


def _compact_css() -> str:
    return COMPACT_MARKER + _read(GLANCE_CSS).replace("\r\n", "\n").split(COMPACT_MARKER, 1)[1]


def _css_rules(css: str) -> list[tuple[str, str]]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)]


def test_compact_sheet_decorate_tags_rows_idempotently():
    """:has() 없이 CSS 가 고르게 decorate() 가 표식을 단다 — 매번 불려도(이전·다음) 결과가 같아야 한다."""
    js = _read(PARTS_JS)
    tag = js.split("function tagRows(card)", 1)[1].split("function decorate(", 1)[0]
    required = [
        "'data-meas-sheet-row'",
        "dd[data-queue-card-field=\"address\"] > a[data-queue-card-map-link]",
        "kind = 'addr'",
        "dd[data-queue-card-field=\"phone\"] > a[data-queue-card-call-link]",
        "kind = 'phone'",
        "dd.foms-tabular",
        "kind = 'date'",
        "dd[data-queue-card-field=\"manager\"]",
        "kind = 'mgr'",
        "'data-meas-sheet-badge'",
        "classList.contains('foms-stage-badge--measure') ? 'stage' : null",
        "'data-meas-sheet-foot'",
        ".foms-measure-done') ? 'handed' : null",
    ]
    assert _missing(tag, required) == []
    # 표식만 단다(노드 이동·생성 없음) — 머리 중복 회귀와 같은 부류를 막는다.
    assert "insertBefore" not in tag and "appendChild" not in tag and "createElement" not in tag
    mark = js.split("function mark(el, name, value)", 1)[1].split("function tagRows", 1)[0]
    assert "el.getAttribute(name) !== value" in mark and "removeAttribute(name)" in mark
    decorate = js.split("function decorate(card, sheet)", 1)[1].split("\n    }\n", 1)[0]
    assert decorate.index("placeHanded(card);") < decorate.index("tagRows(card);"), "넘김 표시를 옮긴 뒤 foot 표식"
    assert "title.nextSibling !== vc" in decorate


def test_compact_sheet_css_scoped_and_no_has():
    added = _compact_css()
    code = re.sub(r"/\*.*?\*/", "", added, flags=re.S)
    assert ":has(" not in code, "iOS 15.4 미만 — :has() 대신 data-meas-sheet-* 표식"
    assert "!important" not in code
    rules = _css_rules(added)
    assert rules
    for sel, _ in rules:
        for part in sel.split(","):
            assert part.strip().startswith(".foms-meas-sheet"), f"시트 밖 규칙: {part.strip()}"
    required = [
        # C1 위쪽 고정 + 내용 높이(dvh 앞에 vh 폴백)
        "justify-content: flex-start;",
        "padding: max(12vh,",
        "padding: max(12dvh,",
        ".foms-meas-sheet .foms-meas-sheet__panel {\n  height: auto;\n  max-height: 100%;",
        ".foms-meas-sheet .foms-meas-sheet__body {\n  flex: 0 1 auto;",
        # C2 숨김
        '[data-meas-sheet-badge="stage"]',
        '[data-meas-sheet-row="date"]',
        '[data-meas-sheet-row="mgr"] {\n  display: none;',
        ".foms-tl-trigger::after",
        "inset: -2px;",
        # C3 한 줄 + 줄 전체 링크 + 아이콘
        '[data-meas-sheet-row="addr"] > dd > a::before',
        '[data-meas-sheet-row="phone"]::after {\n  content: "\\f095";',
        '[data-meas-sheet-row="addr"]::after {\n  content: "\\f3c5";',
        # C4
        ".foms-meas-sheet .foms-meas-sheet__vcheck {\n  min-height: 48px;",
        # C5 단추 한 줄, 실측 완료는 뒤·넓게, 넘긴 주문은 줄바꿈
        "flex-wrap: nowrap;",
        ".queue-card__action > .foms-btn.erp-queue-card__quest-approve {\n  order: 1;",
        '.queue-card__action[data-meas-sheet-foot="handed"] {\n  flex-wrap: wrap;',
        '[data-meas-sheet-foot="handed"] > .foms-measure-done {\n  order: 2;',
    ]
    assert _missing(added, required) == []
    # 담당 줄·날짜 줄 숨김을 줄 모양(flex) 규칙이 되살리지 않는다 — flex 규칙은 addr·phone 만 고른다.
    for sel, body in rules:
        if "display: flex" in body and "queue-card__meta" in sel:
            assert '"date"' not in sel and '"mgr"' not in sel


def test_compact_sheet_keeps_shared_card_untouched():
    """공유 카드 파셜은 그대로 — 퀘스트 승인 단추·지도·전화 링크를 새로 만들지 않는다."""
    card = _read("templates/partials/shared/erp_mobile_queue_card_v2.html")
    assert "data-meas-sheet" not in card
    assert 'erp-queue-card__quest-approve"' in card and 'data-confirm="{{ quest.approve_confirm }}"' in card
    js = _read(PARTS_JS)
    assert "href" not in js.split("function tagRows(card)", 1)[1].split("function decorate(", 1)[0]
