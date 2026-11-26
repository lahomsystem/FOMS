"""생산 탭 글 맞춤(사장님 2026-11-26 답 여덟) — 글자 그대로 고정.

- 판 머리 칸 이름: 파트 계정 '내 작업', 반장 · 보기만 '작업 중'(모두의 장을 세는 화면).
- 저장이 안 됐을 때: '오류:' 머리 · 숫자 없음, 서버 글 그대로, 글 없는 409 는 한 문장. 다시 받으라는 말 = "[다시 받기]를 눌러 주세요."
- 누른 뒤 알림 = 누른 단추 말 그대로, 0장이면 안 띄움.
- [제작 시작 취소](창 [닫기]) · 영업 담당 '영업' · 도면팀 '도면 담당 없음' · 주문은 '건/주문' · 도면 칸 창 [닫기] · [불량 알리기].
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "static" / "js" / "production"
TPL = ROOT / "templates" / "production"
STALE = "다른 사람이 먼저 바꿨어요. [다시 받기]를 눌러 주세요."


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_board_head_tab_name_follows_the_viewer():
    parts = _read(TPL / "partials" / "home_parts.html")
    assert "{{ '내 작업' if pb.mine else '작업 중' }} <small data-pp-count=\"need\">" in parts
    viewer = _read(JS / "foms-production-parts-viewer.js")
    assert "' 도면이 없어요.'" in viewer and "'작업 필요 도면이 없어요.'" not in viewer  # 빈 글도 칸 이름을 따른다


def test_failed_save_text_has_no_error_head_or_status_number():
    for name in ("foms-production-home-steps.js", "foms-production-home.js", "foms-production-sheet-page.js", "foms-production-steps.js"):
        src = _read(JS / name)
        assert "'오류: '" not in src and "'HTTP '" not in src, name
        assert "res.status === 409 ? '" + STALE + "' : ''" in src, name
    for name in ("foms-production-home-steps.js", "foms-production-home.js", "foms-production-sheet-page.js"):
        assert "result.message || '처리하지 못했어요'" in _read(JS / name), name


def test_reload_instruction_is_one_sentence_on_board_refusals():
    from foms.services.orders.drawing_fix_requests import INVALID_STAGE, MESSAGES  # noqa: PLC0415
    from foms.services.production import factory_scope, part_mark_rules, part_mark_write  # noqa: PLC0415

    tail = "[다시 받기]를 눌러 주세요."
    texts = [part_mark_rules.STALE_MESSAGE, part_mark_rules.NEW_STALE_MESSAGE, part_mark_write.NOT_CURRENT_MESSAGE,
             part_mark_write.NOT_IN_PRODUCTION_MESSAGE, factory_scope.other_factory_message(2), MESSAGES[INVALID_STAGE]]
    for text in texts:
        assert text.endswith(tail) and "위 [다시 받기]" not in text and "다시 받아 주세요" not in text, text


def test_toast_says_what_was_pressed_and_stays_quiet_for_zero():
    parts = _read(JS / "foms-production-parts.js")
    assert "/(완료|시작|취소)$/.test(p.run || '')) ? p.run + '했어요' : (SAID[p.run] || '저장했어요')" in parts
    assert "'같이 작업': '같이 작업 시작했어요', '기본으로': '기본으로 했어요', '되돌리기': '되돌렸어요', '담당 바꾸기': '담당 바꿨어요'" in parts
    assert "var text = changed ? changed + '장 기본으로 했어요' : '';" in parts


def test_production_cancel_button_and_dialog_words():
    for path in (TPL / "sheet.html", TPL / "partials" / "tablet_sheet.html"):
        html = _read(path)
        assert 'data-tablet-sheet-action="production-cancel" data-order-id="{{ order.id }}">제작 시작 취소</button>' in html, path.name
    sheets = _read(ROOT / "static" / "js" / "foms" / "tablet-domain-sheets.js")
    assert 'actionLabel: "제작 시작 취소",' in sheets and 'cancelLabel: "닫기",' in sheets
    assert 'if (btn) btn.textContent = text || "취소";' in sheets  # 다른 사유 창은 열 때마다 [취소]로 되돌린다
    assert sheets.count("setReasonCloseText(") == 3  # 정의 1 + 부르는 곳 2(되돌리기 창 · 보류 창)


def test_owner_words_for_people_orders_dialogs_and_defect():
    from foms.services.production.drawing_arrival import BLOCKER_LABELS  # noqa: PLC0415
    from foms.services.production.pc_sheet import START_NOTE  # noqa: PLC0415

    assert BLOCKER_LABELS["no_owner"] == "도면 담당 없음"
    assert "'label': '영업', 'name': manager" in _read(ROOT / "foms" / "services" / "production_home_read_model.py")
    assert START_NOTE == "이 주문 첫 도면이라 제작 시작도 같이 돼요."
    parts = _read(TPL / "partials" / "home_parts.html")
    assert "도면 나온 {{ pp.drawn_orders }}건" in parts and "파트 일이 끝난 주문" in parts and "집</small>" not in parts
    for name in ("home_steps.html", "home_pc_steps.html"):
        assert "도면 마감 지난 주문 <b>" in _read(TPL / "partials" / name), name
    modal = _read(JS / "foms-production-parts-modal.js")
    assert "p.closeText || '닫기';" in modal and "'이 주문 첫 도면이라 제작 시작도 같이 돼요.'" in modal
    assert "data-pp-modal-close>닫기</button>" in _read(TPL / "partials" / "home_parts_overlays.html")
    assert "</svg>불량 알리기</button>" in _read(TPL / "partials" / "home_step_panel.html")
    assert "</i> 불량 알리기" in _read(TPL / "partials" / "production_steps_sheet.html")  # 폰 공정 시트 단추


def test_top_tab_is_named_for_what_it_counts():
    body = _read(TPL / "partials" / "home_body.html")
    assert ">남은 공정 <" in body and ">내 공정 <" not in body  # 반장 혼자 할 일이 아니라 공장 전체의 남은 공정


def test_change_tag_names_what_changed():
    from foms.services.production.change_tag import change_tag  # noqa: PLC0415

    assert change_tag([{"kind": "construction_date"}]) == "시공일 바뀜"
    assert change_tag([{"kind": "drawing"}]) == "도면 바뀜" and change_tag([{"kind": "factory"}]) == "공장 바뀜"
    assert change_tag([{"kind": "construction_date"}, {"kind": "drawing"}]) == "시공일 외 1건 바뀜"
    assert change_tag([{"kind": "drawing"}, {"kind": "drawing"}, {"kind": "factory"}]) == "도면 외 2건 바뀜"
    assert change_tag([{"kind": "something_new"}]) == "바뀜" and change_tag([]) == "" and change_tag(None) == ""
    parts = _read(TPL / "partials" / "home_parts.html")
    tag = "<em class=\"pp-chg\">{{ c.chg_text or '바뀜' }}</em>"
    # 표는 시공일 줄에(이름 줄에 두면 긴 표가 손님 이름을 한 글자로 밀어냈다 — 실화면 2026-11-26). 전체 도면 칸 · 작업 필요 칸
    assert parts.count('<div class="pp-duerow">{{ fph_due(c) }}{% if c.has_changes %}' + tag + '{% endif %}</div>') == 2 and parts.count(tag) == 2


def test_lead_picker_title_is_one_line_and_short_notices():
    modal = _read(JS / "foms-production-parts-modal.js")
    assert "return names + ' ' + (at ? at + '부터 ' : '') + '작업 중';" in modal
    assert "title: heldTitle(card, holder), line: '', run: ''" in modal
    crew = _read(JS / "foms-production-parts-crew.js")
    assert "title: cr.d || !M.heldTitle ? cr.who + ' 작업 중' : M.heldTitle(card, cr.who), line: ''" in crew
    assert "alert.hidden = !line;" in _read(JS / "foms-production-parts.js")  # 빈 띠를 안 남긴다
    assert "{{ pp.hidden }}장이 더 있어요. [찾기]에서 손님 이름으로 찾아 주세요." in _read(TPL / "partials" / "home_parts.html")
    assert "'detail': '만들던 것은 멈춰 주세요'" in _read(ROOT / "foms" / "services" / "production_home_read_model.py")


def test_sheet_drawing_caption_uses_item_name_not_file_name(monkeypatch):
    from foms.services import production_sheet_view as view  # noqa: PLC0415

    files = [{"key": "a", "filename": "가람_도면1.png", "view_url": "/v/a", "item_uids": ["idx:0"]},
             {"key": "b", "filename": "가람_도면2.png", "view_url": "/v/b"}]
    monkeypatch.setattr(view, "resolve_final_drawing_files", lambda sd: files)
    out = view._prod_sheet_drawing_files({"items": [{"product_name": "거실장"}]})
    assert [(f["label"], f["title"]) for f in out] == [("가람_도면1.png", "거실장"), ("가람_도면2.png", "")]  # 못 이으면 제목 없음
    sheet = _read(TPL / "sheet.html")
    assert "도면 1 / {{ _imgs | length }}{% if _imgs[0].title %} · {{ _imgs[0].title }}{% endif %}</p>" in sheet
    assert 'data-foms-sheet-dwg-title="{{ f.title }}"' in sheet
    page = _read(JS / "foms-production-sheet-page.js")
    assert "(title ? ' · ' + title : '')" in page and "(label ? ' · ' + label : '')" not in page


def test_empty_day_shows_only_none_word():
    strip = _read(TPL / "partials" / "home_date.html")
    assert "{% if d.total or d.show_day %}<b>{{ d.make }}</b><small> / {{ d.total }}</small>{% endif %}</span>" in strip
    assert "(' · 없음' if not d.total and not d.show_day else '')" in strip  # '없음'이 보이는 날 = 숫자를 뺀 날(같은 조건)


def test_undo_button_is_named_after_its_done_button():
    parts = _read(TPL / "partials" / "home_parts.html")
    assert parts.count('data-pp-act="undo">{{ pb.part_label }} 완료 취소</button>') == 2  # 내 몫만 완료 줄(파트 계정 · 반장)
    assert "data-pp-act=\"undo\">{{ (pb.part_label ~ ' 완료 취소') if c.state == 'done' else '되돌리기' }}</button>" in parts  # 기본은 그대로
    crew = _read(JS / "foms-production-parts-crew.js")
    assert "st === 'basic' ? '되돌리기' : LABEL + ' 완료 취소'" in crew and crew.count("run: LABEL + ' 완료 취소'") == 2
    modal = _read(JS / "foms-production-parts-modal.js")
    assert "title: LABEL + ' 완료를 취소할까요?'" in modal and "run: LABEL + ' 완료 취소', tone: 'need'" in modal
    assert "title: '안 봄으로 되돌릴까요?', line: '기본 → 안 봄', run: '되돌리기'" in modal  # 기본 되돌리기는 안 여쭌 것 — 그대로
