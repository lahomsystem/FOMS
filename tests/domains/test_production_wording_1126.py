"""생산 탭 글 맞춤(사장님 2026-11-26 답 여덟) — 글자 그대로 고정.

- 판 머리 칸 이름: 파트 계정 '내 작업', 반장 · 보기만 '작업 중'(모두의 장을 세는 화면).
- 저장이 안 됐을 때: '오류:' 머리 · 숫자 없음, 서버 글 그대로, 글 없는 409 는 한 문장. 다시 받으라는 말 = "[다시 받기]를 눌러 주세요."
- 누른 뒤 알림 = 누른 단추 말 그대로, 0장이면 안 띄움.
- [제작 시작 취소](창 [닫기]) · 영업 담당 '영업' · 도면팀 '도면 담당 없음' · 주문은 '건/주문' · 도면 칸 창 [닫기] · [불량 알리기].
"""
from __future__ import annotations

import ast
import re
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
    assert "'같이 작업': '같이 작업 시작했어요', '기본으로': '기본으로 했어요', '담당 바꾸기': '담당 바꿨어요'" in parts
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
    assert "data-pp-act=\"undo\">{{ (pb.part_label ~ ' 완료 취소') if c.state == 'done' else '기본 취소' }}</button>" in parts  # 기본 = [기본 취소](11-26 가)
    crew = _read(JS / "foms-production-parts-crew.js")
    assert "st === 'basic' ? '기본 취소' : LABEL + ' 완료 취소'" in crew and crew.count("run: LABEL + ' 완료 취소'") == 2
    modal = _read(JS / "foms-production-parts-modal.js")
    assert "title: LABEL + ' 완료를 취소할까요?'" in modal and "run: LABEL + ' 완료 취소', tone: 'need'" in modal
    assert "title: '기본을 취소할까요?', line: '기본 → 안 봄', run: '기본 취소'" in modal  # 11-26 가


def test_hold_reason_reads_the_same_on_every_screen():
    """사장님 2026-11-26 — 보류 사유는 "보류 · 자재 기다림" 한 꼴(도면 칸 · 남은 공정 판 · 작업 시트 · PC 줄). 해제 확인 창은 그대로."""
    panel = _read(TPL / "partials" / "home_step_panel.html")
    assert "보류{% if p.hold_reason %} · {{ p.hold_reason }}{% endif %}</b></div>" in panel and "보류 사유" not in panel
    assert "보류 · <strong>{{ order.hold_reason }}</strong>" in _read(TPL / "sheet.html")
    pc = _read(TPL / "partials" / "home_pc_macros.html")
    assert pc.count("보류{% if r.pc_hold_reason %} · {{ r.pc_hold_reason }}{% endif %}") == 2 and "보류 중" not in pc
    css = _read(ROOT / "static/css/contexts/production/home.css")
    assert ".fph-sp__hold b svg { flex: none; }" in css and "word-break: keep-all; overflow-wrap: anywhere; }" in css  # 긴 사유 두 줄


def test_sheet_done_cell_says_where_it_was_done():
    assert "<small>작업 시트에서 완료</small>" in _read(TPL / "partials" / "home_parts.html")
    assert "el('small', '', '작업 시트에서 완료')" in _read(JS / "foms-production-parts-claim.js")
    assert '"note": "작업 시트에서 완료" if state == "hand"' in _read(ROOT / "foms/services/production/pc_sheet.py")


def test_title_name_style_lives_in_the_always_loaded_stylesheet():
    """제목의 이름(파트 계정 · 반장)은 어느 탭이든 — parts.css 는 도면 판에서만 실리므로 꾸밈은 home.css."""
    assert ".foms-prod-home__me {" in _read(ROOT / "static/css/contexts/production/home.css")
    assert ".foms-prod-home__me" not in _read(ROOT / "static/css/contexts/production/parts.css")
    home = _read(ROOT / "foms/web/production/home.py")
    assert "'part_title': _home_title(mode, user, board, name) if surface else None," in home
    assert "return ('반장', name) if mode == VIEW_SUB else None" in home


def test_request_modal_close_and_server_refusals_use_current_button_names():
    """[도면 수정 요청] 창 왼쪽 단추 = [닫기] · 서버 거절 글 셋은 옛 [되돌리기] 대신 [OO 완료 취소]."""
    overlays = _read(TPL / "partials" / "home_parts_overlays.html")
    assert "data-pp-rq-close>닫기</button>" in overlays
    assert "data-pp-rq-close>취소</button>" not in overlays
    for name, path in (("JOIN_DONE_MESSAGE", "part_mark_rules.py"), ("RELEASE_AFTER_DONE_MESSAGE", "part_mark_rules.py"),
                       ("STEP_SET_BY_CARDS_MESSAGE", "part_mark_gates.py")):
        line = next(x for x in _read(ROOT / "foms/services/production" / path).splitlines() if x.startswith(name + " ="))
        assert "[되돌리기]" not in line, name
        assert "[{label} 완료 취소]" in line, name


def test_basic_and_step_undo_buttons_are_paired_names():
    """사장님 2026-11-26 가 "둘 다 맞추기" — 기본 무르기 = [기본 취소], '남은 공정' 띠 = [<공정> 완료 취소]."""
    assert "'되돌리기'" not in _read(JS / "foms-production-parts.js")  # 알림은 규칙(…취소 → 했어요)으로 "기본 취소했어요"
    steps = _read(JS / "foms-production-home-steps.js")
    assert "btn.textContent = u.busy ? '취소하는 중…' : u.label + ' 완료 취소';" in steps
    assert "u.error = '취소하지 못했어요. ' + failText(result);" in steps
    assert "G.api.setStatus('취소했어요. ' + u.name + ' — 다시 ' + u.label + ' 줄로 가요')" in steps
    assert "msg.textContent = u.error || (u.name + ' ' + u.label + ' 완료');" in steps  # 띠 글은 그대로


def test_confirm_and_pc_state_words_say_working_but_audit_keeps_need():
    """사장님 2026-11-26 나 "화면 글만 '작업 중'으로" — 확인 창 · 빈 이름 자리 · PC 상태 칸. 감사 글은 "작업 필요" 그대로."""
    modal = _read(JS / "foms-production-parts-modal.js")
    assert "'→ 작업 중 · ' + NAME" in modal and "line: '작업 중 → ' + LABEL" in modal and "' 완료 → 작업 중 · ' + NAME" in modal
    crew = _read(JS / "foms-production-parts-crew.js")
    assert "line: '작업 중 → ' + LABEL" in crew and "half(cr) + ' → 작업 중 · ' + NAME" in crew
    assert "(o.mine ? '다른 사람 작업 중' : '작업 중')" in crew
    assert "('다른 사람 작업 중' if pb.mine else '작업 중')" in _read(TPL / "partials" / "home_parts.html")
    for text in (modal, crew):
        assert "'작업 필요" not in text and "작업 필요 · '" not in text and "→ 작업 필요 · '" not in text  # 따옴표 안 글(주석은 그대로)
    assert '.replace("작업 필요", "작업 중")' in _read(ROOT / "foms/services/production/pc_sheet.py")
    assert 'else "작업 필요"' in _read(ROOT / "foms/services/production/part_mark_notes.py")  # 감사 낱말은 그대로


def test_unseen_text_and_bulk_button_count_the_same_cards():
    """사장님 2026-11-26 다 "두 숫자를 같게" — '안 본 도면 N장'도 막힌(보류 · 도면 고치는 중) 장을 빼고 센다(서버 · JS 둘 다)."""
    board = _read(ROOT / "foms/services/production/part_board.py")
    assert '"unseen": bulk_count(cards),' in board
    assert 'return sum(1 for c in cards if c["state"] == "none" and not c.get("order_block"))' in board
    assert "unseen: bulkable(card) ? 1 : 0, look: bulkable(card) ? 1 : 0" in _read(JS / "foms-production-parts.js")
    req = _read(JS / "foms-production-drawing-request.js")
    assert "var look = Math.max(0, Number(text.getAttribute('data-pp-unseen-text') || 0) - 1);" in req
    assert "text.textContent = look ? '안 본 도면 ' : '안 본 도면 없어요';" in req


def test_other_part_words_are_mijeong_and_working():
    """사장님 2026-11-26 가 — 도면 칸 아래 다른 파트 줄: 손 안 댄 것은 파트 구분 없이 "미정", 시작한 것은 "작업 중"(완료 · 기본 그대로)."""
    board = _read(ROOT / "foms/services/production/part_board.py")
    assert '_CUT_WORDS = {"done": "완료", "basic": "기본", "need": "작업 중", "none": "미정"}' in board
    assert '_OTHER_WORDS = {"done": "완료", "need": "작업 중", "none": "미정"}' in board


def test_new_sheet_says_edit_make_not_remake():
    """사장님 2026-11-26 나 — 새 작업 시트(sheet.html)의 배지 · 사유 줄은 "수정 제작"."""
    sheet = _read(TPL / "sheet.html")
    assert ">수정 제작{% if order.rework_count %} {{ order.rework_count }}회{% endif %}</span>" in sheet
    assert ">수정 제작{% if order.rework_count %} {{ order.rework_count }}회{% endif %} 사유 <strong>" in sheet
    assert "재제작{% if" not in sheet


def test_big_button_default_dialog_texts_match_production_buttons():
    """사장님 2026-11-26 다 — 큰 단추 인터넷 기본 창 글: 실패 알림은 서버 글만, 묻는 글은 해요체. 출고 저장 글은 그대로."""
    js = _read(ROOT / "static/js/foms/tablet-domain-sheets.js")
    assert '"오류: " + (data.message || "처리 실패")' not in js and js.count('"처리하지 못했어요"') == 4
    assert 'window.alert(data.message || "처리하지 못했어요");' in js
    assert '"제작을 시작할까요?"' in js and '"제작을 완료할까요?" + productionSplitNote(orderId)' in js
    assert 'var msg = "보류 중인 주문이에요";' in js
    assert js.count("사유 입력 창을 불러오지 못했어요. 새로고침한 뒤 다시 시도해 주세요.") == 2
    assert "시작하시겠습니까" not in js and "완료하시겠습니까" not in js and "불러오지 못했습니다" not in js
    assert 'window.alert("오류: " + (data.message || "저장 실패"));' in js  # 출고 저장 글은 그대로
    entry = _read(ROOT / "static/js/shipment/shipment-entry.js")
    assert "tablet-domain-sheets.js?v=20261126b" in entry


def _py_strings(path: Path) -> str:
    """파이썬 파일의 글자열 상수만(독스트링 · 주석 빼고) — 코드 설명 속 '도면 고치는 중'은 개념 이름이라 남겨도 된다."""
    tree = ast.parse(_read(path))
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
            and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    return "\n".join(n.value for n in ast.walk(tree)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs)


def test_production_screen_says_drawing_fix_in_progress_like_the_sheet_badge():
    """사장님 2026-11-26 "도면 수정 중"으로 — 생산 화면 도면 칸 · 공정 줄 · 제작 시작 막힘 · 바뀐 것 글이 작업 시트 배지와 같은 말."""
    svc = ROOT / "foms" / "services"
    card = _py_strings(svc / "production" / "part_card_state.py")
    fix = _py_strings(svc / "orders" / "drawing_fix.py")
    gate = _py_strings(svc / "orders" / "confirm_drawing_gate.py")
    alerts = _py_strings(svc / "production_change_alerts.py")
    assert "도면 수정 중" in card.splitlines()
    assert " 수정 중" in fix.splitlines() and " 수정 중이라 빼요." in fix.splitlines() and " 수정 중이라 뺐어요." in fix.splitlines()
    assert "도면 수정 중이라 아직 제작을 시작할 수 없어요. 영업 담당(" in gate
    assert "도면 수정 중" in alerts.splitlines()
    steps = re.sub(r"\{#.*?#\}", "", _read(TPL / "partials" / "home_steps.html"), flags=re.S)  # Jinja 주석 뺌
    for src in (card, fix, gate, alerts, steps):
        assert "고치는 중" not in src
