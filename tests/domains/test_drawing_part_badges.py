"""도면 마법사 학습 이름표 화면 계약 테스트(사용성 평가 2026-10-25 큼-7·큼-8·보통-1·보통-2·작음).

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.1
- 그림 이름 딱지·미분류 칩·분류 진행 칩(part-badges.js)은 순수 함수를 node 로 돌려 글과 고르기를 본다.
- 주방 짝 규칙 판단(part-pair.js pairChanged·releaseNote)은 저장 필드 없이 계산한다.
- wizard.js 연결(숫자키 여러 장·Enter 맞음·첫 수정 안내·딱지 다시 그리기)과 도움말·CSS 는 문자열 계약으로 본다.
(test_drawing_part_ai_contract.py 가 파이썬 500줄 래칫에 걸려 이 파일로 나눴다.)
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

from foms.api.drawing import wizard as wizard_api

ROOT = Path(__file__).resolve().parents[2]
BADGES_JS = ROOT / "static/js/drawing/part-badges.js"
STATUS_JS = ROOT / "static/js/drawing/part-status.js"
SPOT_JS = ROOT / "static/js/drawing/part-badge-spot.js"
PAIR_JS = ROOT / "static/js/drawing/part-pair.js"
WIZARD_JS = ROOT / "static/js/drawing/wizard.js"
TEMPLATE = ROOT / "templates/drawing/wizard.html"
CSS = ROOT / "static/css/contexts/drawing/wizard.css"


def _node():
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


def test_part_badges_node_check_and_size():
    for path in (BADGES_JS, STATUS_JS, SPOT_JS, PAIR_JS, WIZARD_JS):
        proc = subprocess.run([_node(), "--check", str(path)], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
    for path in (BADGES_JS, STATUS_JS, SPOT_JS):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 300   # 새 JS 300줄 래칫


def test_template_loads_part_badges_after_pair():
    html = TEMPLATE.read_text(encoding="utf-8")
    for name in ("part-badge-spot.js", "part-status.js", "part-badges.js"):
        tag = re.search(r'<script src="[^"]*' + re.escape(name) + r'[^"]*"[^>]*>', html)
        assert tag and "?v=" in tag.group(0) and " defer" in tag.group(0), name
        assert html.index("js/drawing/part-pair.js") < tag.start() < html.index("js/drawing/wizard.js"), name
    # 딱지(part-badges.js)는 자리 고르기·앱바 칩을 init 때 쓴다 — 둘이 먼저 돈다(defer 는 적힌 순서)
    assert html.index("js/drawing/part-badge-spot.js") < html.index("js/drawing/part-badges.js")
    assert html.index("js/drawing/part-status.js") < html.index("js/drawing/part-badges.js")


BADGE_RUNNER = r"""
global.window = {};
require(process.argv[1]);
require(process.argv[4]);
require(process.argv[2]);
const P = window.FomsPartPair, B = window.FomsPartBadges, St = window.FomsPartStatus, job = JSON.parse(process.argv[3]);
const each = (fn) => Object.fromEntries(Object.entries(job.parts).map(([k, p]) => [k, fn(p)]));
const out = {
  badge: each(p => B.badgeInfo(p, 0.5, false)),
  badgeWait: B.badgeInfo(null, 0.5, true),
  hint: each(p => B.partHint(p, 0.5)),
  changed: each(p => P.pairChanged(p, 0.5)),
  release: Object.fromEntries(Object.entries(job.release).map(([k, items]) =>
    [k, P.releaseNote(items, P.pairLabels(items, 0.5), 0.5)])),
  progress: job.progress.map(a => St.progressText(a[0], a[1], a[2])),
  parts: [St.progressParts(3, 8, false, false), St.progressParts(8, 8, false, true), St.progressParts(8, 8, false, false)],
  unsure: [0, 2].map(St.unsureText),
  ro: job.ro.map(B.withRo),
  plan: B.multiLabelPlan(job.plan, '정면·도어'),
  planNone: B.multiLabelPlan([{ id: 't', type: 'text' }], '사진'),
  next: job.next.map(c => St.nextUnsorted(c.items, c.current)),
  shift: job.shift.map(a => St.scrollShift(a[0], a[1], a[2], a[3])),
};
process.stdout.write(JSON.stringify(out));
"""


def _badges(job):
    proc = subprocess.run([_node(), "-e", BADGE_RUNNER, str(PAIR_JS), str(BADGES_JS), json.dumps(job), str(STATUS_JS)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _it(i, ai, conf, label, hatch):
    return {"id": i, "ai": ai, "conf": conf, "label": label, "hatch": hatch}


def test_part_badges_label_texts_hints_and_pair_judgement():
    """딱지 글(AI 짐작·사람 확인·미분류·짝 규칙) · 종류 칸 옆 글과 풍선 말 · 짝 규칙 판단(저장 필드 없이 계산)."""
    job = {
        "parts": {
            "ai": {"label": "정면·내부", "src": "ai", "ai": "정면·내부", "conf": 0.72, "head": "h1"},
            "pair": {"label": "정면·내부", "src": "ai", "ai": "정면·도어", "conf": 0.37, "head": "h1"},
            "pairLow": {"label": "입체·도어", "src": "ai", "ai": "입체·도어", "conf": 0.4},
            "user": {"label": "정면·도어", "src": "user", "ai": "정면·내부", "conf": 0.8, "head": "h1"},
            "aiUnsure": {"label": "미분류", "src": "ai", "ai": "사진", "conf": 0.31},
            "userUnsure": {"label": "미분류", "src": "user"},
            "photo": {"label": "사진", "src": "ai", "ai": "사진", "conf": 0.93},
            "none": None,
        },
        "release": {
            # 짝(a 내부·b 도어)이 있던 시트에 같은 보기 세 번째 그림이 오면 짝이 풀려 a 가 모델 짐작으로 돌아간다
            "third": [_it("a", "정면·도어", 0.9, "정면·내부", 0.42), _it("b", "정면·도어", 0.8, "정면·도어", 0.10),
                      _it("c", "정면·내부", 0.7, "정면·내부", 0.30)],
            "fourIso": [_it("a", "입체·도어", 0.9, "입체·내부", 0.5), _it("b", "입체·도어", 0.9, "입체·도어", 0.1),
                        _it("c", "입체·내부", 0.8, "입체·내부", 0.3), _it("d", "입체·도어", 0.6, "입체·도어", 0.2)],
            # 짝 하나를 사람이 가져가 AI 그림이 하나만 남은 경우
            "alone": [_it("a", "정면·도어", 0.9, "정면·내부", 0.42)],
            "pairing": [_it("a", "정면·도어", 0.9, "정면·도어", 0.42), _it("b", "정면·도어", 0.8, "정면·도어", 0.10)],
            "stable": [_it("a", "정면·도어", 0.9, "정면·내부", 0.42), _it("b", "정면·도어", 0.8, "정면·도어", 0.10)],
        },
        "progress": [[3, 8, False], [0, 8, True], [8, 8, False], [0, 0, False]],
        "ro": ["정면·도어", "평면·상판", "그림 아님", "미분류", "서랍 단면"],
        "plan": [], "next": [], "shift": [],
    }
    res = _badges(job)
    b = res["badge"]
    # text = pre + label — 좁은 자리(그림 폭보다 길거나 가릴 때)에서는 앞 글을 빼고 종류 이름만(재평가 QA3)
    assert b["ai"] == {"kind": "ai", "text": "AI 72% · 정면·내부", "pre": "AI 72% · ", "label": "정면·내부"}
    assert b["pair"]["text"] == "AI 짝 규칙 · 정면·내부" and b["pairLow"]["text"] == "AI 짝 규칙 · 입체·도어"
    assert b["pair"]["pre"] == "AI 짝 규칙 · " and b["pair"]["pair"] is True
    # 사람 확인은 짧게 '✓ 종류'(마지막 실화면 확인 V1 — 초록 '확인 · ' 딱지가 넓어 치수를 덮었다)
    assert b["user"] == {"kind": "user", "text": "✓ 정면·도어", "pre": "✓ ", "label": "정면·도어"}
    assert b["photo"]["text"] == "AI 93% · 사진" and b["photo"]["label"] == "사진"
    for k in ("aiUnsure", "userUnsure", "none"):
        assert b[k] == {"kind": "unsure", "text": "? 미분류", "pre": "", "label": "? 미분류"}, k
    assert res["badgeWait"]["kind"] == "wait"                         # 알아보는 중 — 딱지 없음, 미분류로 세지 않음

    h = res["hint"]
    assert h["ai"] == {"kind": "ai", "note": "AI 72%", "ok": True,
                       "title": "AI 짐작(확신 72%) — 틀리면 숫자키 1~9, 맞으면 Enter"}
    assert h["pair"]["note"] == "AI 짝 규칙" and h["pair"]["ok"] is True
    assert h["pair"]["title"] == ("AI 짐작 정면·도어(확신 37%) — 틀리면 숫자키 1~9, 맞으면 Enter"
                                  " · 주방 짝 규칙: 빗금 많은 쪽 = 내부")
    assert h["user"]["note"] == "확인" and h["user"]["ok"] is False
    assert h["aiUnsure"]["ok"] is False and h["aiUnsure"]["title"].startswith("AI가 잘 모르는 그림(확신 31%)")
    assert h["none"]["note"] == "" and h["none"]["ok"] is False

    assert res["changed"] == {"ai": False, "pair": True, "pairLow": True, "user": False, "aiUnsure": False,
                              "userUnsure": False, "photo": False, "none": False}
    rel = res["release"]
    assert rel["third"] == "주방 앞모습이 세 장이 되어 짝 규칙을 풀었어요 — 종류를 확인해 주세요"
    assert rel["fourIso"] == "주방 입체 그림이 4장이 되어 짝 규칙을 풀었어요 — 종류를 확인해 주세요"
    assert rel["alone"] == "주방 짝이 맞지 않아 짝 규칙을 풀었어요 — 종류를 확인해 주세요"
    assert rel["pairing"] == "" and rel["stable"] == ""              # 짝을 새로 맺거나 그대로면 조용히

    # 모델 단계에도 장수(재평가 QA1) · 좁은 앱바용 짧은 글(QA2) · 끝난 뒤 잠깐 'N/N'(QA3 — 0.8초는 보이게)
    assert res["progress"] == ["그림 종류 알아보는 중 3/8", "모델 받는 중 0/8", "", ""]
    assert res["parts"][0] == {"text": "그림 종류 알아보는 중", "short": "분류 중", "count": "3/8",
                               "title": "그림 종류 알아보는 중 3/8"}
    assert res["parts"][1]["count"] == "8/8" and res["parts"][2] is None
    assert res["unsure"] == ["", "미분류 2장 ›"]
    assert res["ro"] == ["정면·도어로", "평면·상판으로", "그림 아님으로", "미분류로", "서랍 단면으로"]


def test_part_badges_multi_select_digits_next_unsorted_and_scroll():
    """여러 장 숫자키(그림만·이미 같은 사람 이름표는 건너뜀) · '미분류 N장 ›' 다음 그림 고르기 · 화면에 보이게 옮길 거리."""
    rows = [{"id": "r2a", "x": 40, "y": 420, "unsure": True}, {"id": "r1b", "x": 600, "y": 110, "unsure": True},
            {"id": "r1a", "x": 40, "y": 90, "unsure": False}, {"id": "r1c", "x": 900, "y": 100, "unsure": True}]
    job = {
        "parts": {}, "release": {}, "progress": [], "ro": [],
        "plan": [{"id": "u", "type": "image", "part": {"label": "정면·도어", "src": "user"}},
                 {"id": "a", "type": "image", "part": {"label": "정면·내부", "src": "ai", "ai": "정면·내부", "conf": 0.8}},
                 {"id": "t", "type": "text"}, {"id": "n", "type": "image"}, None],
        "next": [{"items": rows, "current": None}, {"items": rows, "current": "r1b"}, {"items": rows, "current": "r1c"},
                 {"items": rows, "current": "r2a"}, {"items": rows, "current": "r1a"},
                 {"items": [{"id": "x", "x": 0, "y": 0, "unsure": True}], "current": "x"},
                 {"items": [{"id": "y", "x": 0, "y": 0, "unsure": False}], "current": None}],
        "shift": [[100, 200, 0, 500], [-50, 50, 0, 500], [450, 600, 0, 500], [-100, 800, 0, 500], [600, 1400, 0, 500]],
    }
    res = _badges(job)
    assert res["plan"] == {"count": 3, "change": ["a", "n"], "text": "고른 그림 3장을 정면·도어로 정했어요"}
    assert res["planNone"] == {"count": 0, "change": [], "text": ""}     # 그림이 없으면 원래대로(반응 없음)
    # 읽는 순서: 위 줄(r1a·r1b·r1c, 왼→오른) → 아래 줄(r2a), 끝이면 처음으로, 미분류만 고른다
    assert res["next"] == ["r1b", "r1c", "r2a", "r1b", "r1b", "x", None]
    assert res["shift"] == [0, -50, 100, -100, 600]


def _fn_body(src, name):
    start = src.index("function " + name + "(")
    return src[start:src.index("\n  }\n", start)]


def test_wizard_wires_badges_learning_keys_and_keeps_part_shape():
    js = WIZARD_JS.read_text(encoding="utf-8")
    assert "window.FomsPartBadges.init({" in _fn_body(js, "initPartBadges")
    assert "initPartBadges()" in _fn_body(js, "initPartSelect")
    assert "window.FomsPartBadges.refresh()" in _fn_body(js, "rebuildAnno")   # 시트 바꿈·되돌리기·배치 뒤 딱지 다시 맞춤
    for name in ("setPartLabel", "setPartLabelMany", "confirmPartLabel", "applyKitchenPairs"):
        body = _fn_body(js, name)
        assert "refreshPartBadges()" in body, name                    # 이름이 바뀌는 모든 길에서 딱지·칩을 다시 그림
        assert "sanitizePart(partWith(" in body, name                 # 저장 모양은 서버 검사와 같은 닫힌 모양 그대로
    confirm = _fn_body(js, "confirmPartLabel")
    assert "recordUndo()" in confirm and "markDirty()" in confirm and "{ src: 'user' }" in confirm
    assert "확인했어요 — 다음 학습에 씁니다" in confirm
    many = _fn_body(js, "setPartLabelMany")
    assert many.count("recordUndo()") == 1                            # 여러 장도 되돌리기 한 번
    tip = _fn_body(js, "showPartLearnTip")
    assert "try {" in tip and "localStorage" in tip and "고친 종류는 다음 AI 학습에 쓰여요" in tip
    kitchen = _fn_body(js, "applyKitchenPairs")
    assert "pair.releaseNote(items, next, th)" in kitchen and "toast(note)" in kitchen
    hint = _fn_body(js, "syncImageToolbar")
    assert "mtPartNote" in hint and "mtPartOk" in hint and "partHint(part)" in hint
    # 키 처리: 글자 편집 중 조기 반환 → 숫자키(여러 장 포함) → Enter(맞음) → 도구 단축키 순서
    i_edit = js.index("if (editing) { return; }")
    i_many = js.index("setPartLabelMany(selectedIds.slice(), digitLabel)")
    i_enter = js.index("confirmPartLabel(okObj.id)")
    i_tools = js.index("/* 도구 단축키(수정자 없음)")
    assert i_edit < i_many < i_enter < i_tools
    enter = js[js.rindex("e.key === 'Enter'", 0, i_enter):i_enter]
    assert "!e.isComposing" in enter and "e.keyCode !== 229" in enter and "selectedIds.length === 1" in enter
    assert "!e.repeat" in enter                                       # 꾹 누름 반복으로 토스트가 쌓이지 않게
    assert "/^(BUTTON|A|SUMMARY)$/.test(ae.tagName)" in enter         # 단추에 초점이 있으면 단추 Enter 그대로


def test_wizard_digit_guard_selection_hide_and_model_cache_wiring():
    """재평가 QA3: Ctrl+A 뒤 이름을 치자 그림 14장이 잇달아 바뀌고 '사람 확인'으로 굳었다 · 모델을 받아 둔 뒤에도 '모델 받는 중'."""
    js = WIZARD_JS.read_text(encoding="utf-8")
    # 숫자키: 글자를 치다 섞인 숫자 · Ctrl+A 전체 선택 그대로의 여러 장은 받지 않는다(바꾸기보다 먼저 본다)
    i_digit = js.index("var digitLabel = PART_LABELS[")
    i_guard = js.index("if (partDigitBlocked(e)) { return; }")
    assert i_digit < i_guard < js.index("setPartLabel(partObj.id, digitLabel)") < js.index("setPartLabelMany(selectedIds.slice(), digitLabel)")
    assert "markPartSelectAll();" in _fn_body(js, "selectAllOnSheet")   # Ctrl+A 전체 선택을 기억(그대로면 숫자키 안 받음)
    guard = _fn_body(js, "partDigitBlocked")
    assert "partTyping()" in guard and "partAllSig !== partSelectionSig()" in guard and "selectedIds.length < 2" in guard
    assert "Date.now() - partTypedAt < PART_TYPING_MS" in js
    i_enter = js.index("confirmPartLabel(okObj.id)")
    assert "!partTyping()" in js[js.rindex("e.key === 'Enter'", 0, i_enter):i_enter]   # 글자를 치다 누른 Enter 도 '맞음' 아님
    assert "전체 선택(Ctrl+A)으로는 종류를 한꺼번에 바꾸지 않아요" in guard and "partAllWarned" in guard   # 한 번만 알림
    typing = _fn_body(js, "notePartTyping")
    assert "e.ctrlKey || e.metaKey || e.altKey" in typing and "k === 'Process' || e.keyCode === 229" in typing
    assert "!/^(Digit|Numpad)[0-9]$/.test(e.code || '')" in typing   # 숫자는 글자 치기로 세지 않는다
    sel = _fn_body(js, "initPartSelect")
    assert "document.addEventListener('keydown', notePartTyping, true)" in sel
    assert "document.addEventListener('pointerdown', function () { partTypedAt = 0; partAllSig = ''; }, true)" in sel
    assert "' (되돌리기 Ctrl+Z)'" in _fn_body(js, "setPartLabelMany")
    # 하나만 고른 그림의 딱지는 숨긴다 — 고르기·풀기 때 다시 그림, 딱지 자리용 줌·양식 칸
    assert "refreshPartBadges();" in _fn_body(js, "applySelection") and "refreshPartBadges();" in _fn_body(js, "deselect")
    init = _fn_body(js, "initPartBadges")
    assert "zoom: function () { return zoom; }" in init and "selectedIds.length === 1 ? selected : null" in init
    assert "zones: partBadgeZones" in init
    zones = _fn_body(js, "partBadgeZones")
    assert ".dws-header" in zones and "PART_FRAME.pageBox" in zones and "partTableTop(currentSheet())" in zones
    # 모델을 이 브라우저에 받아 둔 뒤면 '모델 받는 중'이 아니라 '알아보는 중'
    prog = _fn_body(js, "partProgress")
    check = _fn_body(js, "partCheckModel")
    assert "ai.cached().then(function (hit) { partModelCached = !!hit; partProgress(0, 0); }" in check
    assert "partCheckModel();" in prog
    assert "loading: !partModelReady && (partModelCached === null ? null : !partModelCached)" in prog   # 준비됨 false · 모름 null
    # 같이 올린 묶음은 장수를 처음에 한 번에(V3) — 못 올린 그림은 미리 센 장수에서 뺀다
    assert "partProgress(images.length, 0, true)" in _fn_body(js, "addImagesFromFiles")
    assert "if (!id) { partProgress(-1, 0, true); }" in _fn_body(js, "finishPartBatch")
    assert "partBusy.held" in prog


def test_help_lists_part_number_keys_first_in_label_order():
    body = TEMPLATE.read_text(encoding="utf-8").split('id="dws-help"', 1)[1]
    group = body.split("그림 종류 숫자키", 1)[1].split("</section>", 1)[0]
    pairs = re.findall(r"<dt><kbd>(\d)</kbd></dt><dd>([^<]+)</dd>", group)
    assert pairs == [(str((i + 1) % 10), label) for i, label in enumerate(wizard_api._PART_LABELS)]
    assert "<kbd>Enter</kbd>" in group and "맞음" in group
    assert body.index("그림 종류 숫자키") < body.index('dws-help-group-title">도구<')   # 앞쪽(기본 다음)
    assert "고른 그림의 종류 정하기" not in body                      # 예전 '1~9 · 0' 한 줄은 이 묶음으로 옮김
    assert "Ctrl+A 전체 선택은 빼요" in group                        # 재평가 QA3 — 전체 선택으로는 한꺼번에 안 바꾼다
    assert "<dt>그림 위 딱지</dt>" in group and "딱지 단추로 모두 숨기기" in group and "앱바" not in group   # 개발 말 없이
    assert "초록 ✓ = 확인함" in group and "그림을 하나 고르면 그 위 딱지가 흐려져요" in group   # 딱지 모양 뜻 · 태블릿 흐림(V1)
    assert "<dt><kbd>Ctrl</kbd>+<kbd>S</kbd></dt><dd>저장(지금 시트를 전달 대기함에)</dd>" in body   # 리드 메모


def test_part_badges_css_screen_only_and_click_through():
    css = CSS.read_text(encoding="utf-8")
    src = BADGES_JS.read_text(encoding="utf-8")
    assert "'dws-pbadges dws-ui'" in src                               # 내보내기·저장 그림에서 숨는 층
    assert ".dws-exporting .dws-ui { display: none !important; }" in css
    layer = css.split(".dws-pbadges {", 1)[1].split("}", 1)[0]
    assert "pointer-events: none" in layer
    badge = css.split(".dws-pbadge {", 1)[1].split("}", 1)[0]
    # 100% 이상은 화면에서 12px, 아래에서는 줌을 따라 80% 까지(part-badge-spot.js badgeScale 과 같은 식 — V1 맞춤 74%)
    assert "font-size: 12px" in badge and "calc(clamp(0.8, var(--dws-zoom, 1), 1) / var(--dws-zoom, 1))" in badge
    assert "MIN_SCALE = 0.8" in SPOT_JS.read_text(encoding="utf-8")
    user = css.split(".dws-pbadge-user {", 1)[1].split("}", 1)[0]
    assert "rgba(20, 108, 49, 0.88)" in user and "#ffffff" in user   # 조금 비치는 초록(흰 바탕 위 글자 대비 5.0)
    assert "translate(" not in badge                                   # 자리는 part-badge-spot.js 가 고른다(안쪽 6px 고정 아님)
    for sel in (".dws-pbadge-ai", ".dws-pbadge-user", ".dws-pbadge-unsure", ".dws-pbadge-hint",
                ".dws-part-status-busy", ".dws-part-status-unsure", ".dws-part-status-eye"):
        assert sel + " {" in css or sel + "[" in css, sel
    assert ".dws-pbadge-short .dws-pbadge-pre { display: none; }" in css   # 좁으면 종류 이름만
    assert ".dws-pbadge-dim { opacity: 0.25; }" in css                     # 마우스를 올린 그림 위 딱지는 흐리게
    assert ".dws-pbadge-sel { visibility: hidden; }" in css               # 자리는 그대로 두고 안 보이게(잴 수 있게)
    assert ".dws-pbadges.dws-pbadges-off { display: none; }" in css
    assert '.dws-part-status-eye[aria-pressed="true"] .dws-part-eye-slash { display: inline; }' in css


FAKE_DOM = r"""
const reg = {}, store = {}, raf = [], timers = [];
let now = 1000, NARROW = false;
global.setTimeout = (f, ms) => { timers.push({ f, at: now + (ms || 0) }); return timers.length; };
global.clearTimeout = (id) => { if (timers[id - 1]) { timers[id - 1].f = null; } };
Date.now = () => now;
function el(tag) {
  return { tagName: tag.toUpperCase(), className: '', hidden: false, title: '', children: [], attrs: {}, style: {}, ls: {}, _t: '',
    get textContent() { return this.children.length ? this.children.map(c => c.textContent).join('') : this._t; },
    set textContent(v) { this._t = String(v); this.children = []; },
    get scrollWidth() { return this.textContent.length * 12; }, get clientWidth() { return NARROW ? 60 : 1000; },
    get offsetWidth() {   // 딱지: 글자당 7px + 안쪽 여백·테두리 15px
      if (this.className === 'dws-pbadge-pre') { return this.textContent.length * 7; }
      return /^dws-pbadge /.test(this.className) ? this.textContent.length * 7 + 15 : 0;
    },
    get offsetHeight() { return /^dws-pbadge /.test(this.className) ? 21 : 0; },
    appendChild(c) { c.parentNode = this; this.children.push(c); return c; },
    removeChild(c) { this.children.splice(this.children.indexOf(c), 1); c.parentNode = null; return c; },
    insertBefore(c, ref) { c.parentNode = this; const i = this.children.indexOf(ref); this.children.splice(i < 0 ? this.children.length : i, 0, c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k]; },
    addEventListener(t, f) { (this.ls[t] = this.ls[t] || []).push(f); }, click() { (this.ls.click || []).forEach(f => f()); },
    set id(v) { this.attrs.id = v; reg[v] = this; }, get id() { return this.attrs.id; } };
}
global.window = { requestAnimationFrame: (f) => raf.push(f),
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } } };
global.document = { createElement: el, createElementNS: (ns, tag) => el(tag), getElementById: (id) => reg[id] || null };
const flush = () => { while (raf.length) { raf.shift()(); } };
const tick = (ms) => { now += ms; timers.filter(t => t.f && t.at <= now).forEach(t => { const f = t.f; t.f = null; f(); }); flush(); };
for (const f of process.argv.slice(1)) { require(f); }
const bar = el('div'), save = bar.appendChild(el('span'));
save.id = 'dws-save-status';
const B = window.FomsPartBadges;
"""

CHIP_RUNNER = FAKE_DOM + r"""
B.init({ host: el('div'), getSheet: () => ({ objects: [] }), nodeFor: () => null, anchor: save });
const out = [];
const snap = () => { const box = reg['dws-part-status'], chip = box.children[0];
  return { box: box.hidden, hidden: chip.hidden, title: chip.title, parts: chip.children.map(c => [c.className, c.textContent, c.hidden]) }; };
for (const a of [[3, 8, false], [12, 18, false], [0, 8, true]]) { B.progress(a[0], a[1], { loading: a[2] }); flush(); out.push(snap()); }
tick(300); B.progress(8, 8, {}); flush(); out.push(snap());          // 0.3초 만에 끝남 → 'N/N' 으로 남은 0.5초 더
tick(499); out.push(snap()); tick(1); out.push(snap());              // 0.8초가 차면 숨김(다시 그림)
B.progress(1, 2, {}); flush(); tick(900); B.progress(2, 2, {}); flush(); out.push(snap());   // 오래 보였으면 바로 숨김
NARROW = true; B.progress(3, 8, {}); flush(); out.push(snap());     // 좁은 앱바 — 짧은 글
process.stdout.write(JSON.stringify(out));
"""


def test_busy_chip_counts_short_text_and_min_show():
    """진행 칩(재평가 QA1·QA2·QA3): 장수는 따로 늘 보이고, 모델 단계도 장수, 너무 빨리 끝나도 0.8초는 'N/N',
    좁은 앱바에서 글이 잘리면 짧은 글('분류 중')."""
    proc = subprocess.run([_node(), "-e", CHIP_RUNNER, str(STATUS_JS), str(BADGES_JS)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    text, count = "dws-part-status-busy-text", "dws-part-status-busy-count"
    assert res[0] == {"box": False, "hidden": False, "title": "그림 종류 알아보는 중 3/8",
                      "parts": [[text, "그림 종류 알아보는 중", False], [count, " 3/8", False]]}
    assert res[1]["parts"][1] == [count, " 12/18", False]
    assert res[2]["parts"] == [[text, "모델 받는 중", False], [count, " 0/8", False]]
    assert res[2]["title"] == "모델 받는 중 0/8 — 처음 한 번만 받아요"
    assert res[3]["hidden"] is False and res[3]["parts"][1] == [count, " 8/8", False]   # 잠깐 더 보인다
    assert res[4]["hidden"] is False and res[5]["hidden"] is True and res[5]["box"] is True
    assert res[6]["hidden"] is True
    assert res[7]["parts"] == [[text, "분류 중", False], [count, " 3/8", False]]
    assert res[7]["title"] == "그림 종류 알아보는 중 3/8"                 # 풍선 말은 전체 글
    css = CSS.read_text(encoding="utf-8")
    label = css.split(".dws-part-status-busy-text {", 1)[1].split("}", 1)[0]
    assert "min-width: 0" in label and "text-overflow: ellipsis" in label   # 줄어드는 쪽은 글 칸
    assert "flex: 0 0 auto" in css.split(".dws-part-status-busy-count {", 1)[1].split("}", 1)[0]   # 장수는 안 줄어든다
    chip = css.split(".dws-appbar-right .dws-part-status-busy {", 1)[1].split("}", 1)[0]
    assert "max-width: var(--dws-busy-max" in chip and "display: inline-flex" in chip


LAYER_RUNNER = FAKE_DOM + r"""
const hs = {}, rects = { a: [600, 300, 400, 300], b: [100, 700, 300, 200], c: [1100, 700, 60, 100], d: [100, 904, 300, 100],
  t: [580, 250, 80, 30] };
const node = (id) => ({ getClientRect: () => ({ x: rects[id][0], y: rects[id][1], width: rects[id][2], height: rects[id][3] }),
  rotation: () => 0, image: () => null,
  on(ev, fn) { ev.split(' ').forEach(e => { const k = id + ':' + e.split('.')[0]; (hs[k] = hs[k] || []).push(fn); }); } });
const nodes = Object.fromEntries(Object.keys(rects).map(id => [id, node(id)]));
const fire = (id, e) => (hs[id + ':' + e] || []).forEach(f => f());
const img = (id, part) => ({ id, type: 'image', part });
const sheet = { objects: [img('a', { label: '정면·내부', src: 'ai', ai: '정면·내부', conf: 0.72 }),
  img('b', { label: '정면·도어', src: 'user' }), img('c', { label: '사진', src: 'ai', ai: '사진', conf: 0.9 }),
  img('d', { label: '평면·상판', src: 'ai', ai: '평면·상판', conf: 0.8 }), { id: 't', type: 'text' }] };
let solo = 'a';
const host = el('div');
B.init({ host, getSheet: () => sheet, nodeFor: (id) => nodes[id] || null, anchor: save, threshold: () => 0.5,
  zoom: () => 1, soloId: () => solo, zones: () => [{ x: 48, y: 43, w: 650, h: 52 }] });
flush();
const layer = host.children[0], eye = reg['dws-part-status'].children[2];
const badge = (id) => layer.children[['a', 'b', 'c', 'd'].indexOf(id)];
const state = () => Object.fromEntries(['a', 'b', 'c', 'd'].map(id => { const b = badge(id);
  return [id, { at: [b.style.left, b.style.top], cls: b.className.split(' ').slice(2), text: b.textContent }]; }));
const out = { first: state(), eye: [eye.hidden, eye.attrs['aria-pressed'], eye.title],
  icon: [eye.children[0].tagName, eye.children[0].children.map(c => c.tagName), eye.children[0].children[2].attrs.class] };
fire('b', 'mouseenter'); out.hoverB = state(); fire('b', 'mouseleave'); out.leaveB = state();
solo = null; window.FomsPartBadges.refresh(); flush(); out.noSolo = state().a.cls;
solo = 'b'; window.FomsPartBadges.refresh(); flush(); out.soloB = state();   // 손가락·펜슬: 마우스 올리기 대신 눌러 고른 그림
solo = null; window.FomsPartBadges.refresh(); flush();
rects.b = [100, 600, 300, 200]; fire('b', 'yChange'); flush(); out.movedB = state().b.at;
eye.click(); flush(); out.off = [layer.className, store['foms.drawingWizard.partBadgesOff'], eye.attrs['aria-pressed']];
eye.click(); flush(); out.on = [layer.className, store['foms.drawingWizard.partBadgesOff']];
process.stdout.write(JSON.stringify(out));
"""


def test_badges_sit_outside_above_dodge_text_shorten_hide_selected_and_dim_on_hover():
    """딱지 자리(재평가 QA1·QA3) — 그림 틀 위 바깥 · 글자 객체([SR]) 피하기 · 좁은 그림은 짧은 글 · 하나만 고른 그림은 숨김 ·
    마우스를 올린 그림 위에 걸친 딱지는 흐림 · 앱바 딱지 단추로 모두 숨김(이 브라우저에 기억)."""
    proc = subprocess.run([_node(), "-e", LAYER_RUNNER, str(SPOT_JS), str(STATUS_JS), str(BADGES_JS)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    first = res["first"]
    assert first["a"] == {"at": ["881px", "277px"], "cls": ["dws-pbadge-sel"], "text": "AI 72% · 정면·내부"}   # 위 왼쪽 글자 → 위 오른쪽
    assert first["b"] == {"at": ["106px", "677px"], "cls": [], "text": "✓ 정면·도어"}
    assert first["c"]["at"] == ["1106px", "677px"] and first["c"]["cls"] == ["dws-pbadge-short"]   # 그림 폭 60 < 글 92
    # b 바로 밑(틈 4px) d — 틀에 걸쳐(딱지 60% 가 제 그림 안) 윗그림 b 는 4px 만 덮는다(V1: 틈보다 큰 딱지가 윗그림 '60' 을 덮음)
    assert first["d"]["at"] == ["106px", "896px"] and first["d"]["cls"] == ["dws-pbadge-short"]
    assert res["eye"] == [False, "false", "그림 종류 딱지 숨기기 — 딱지가 치수를 가릴 때"]
    assert res["icon"] == ["SVG", ["PATH", "CIRCLE", "LINE"], "dws-part-eye-slash"]   # 딱지 모양(innerHTML 없이)
    assert res["hoverB"]["d"]["cls"] == ["dws-pbadge-short", "dws-pbadge-dim"]   # b 위에 걸친 d 딱지만 흐려진다
    assert res["hoverB"]["b"]["cls"] == [] and res["leaveB"]["d"]["cls"] == ["dws-pbadge-short"]
    assert res["noSolo"] == []                                         # 고르기를 풀면 다시 보인다
    # 하나만 고른 그림 위에 걸친 딱지도 흐려진다(태블릿엔 마우스 올리기가 없다) — 고른 그림의 제 딱지는 숨김
    assert res["soloB"]["d"]["cls"] == ["dws-pbadge-short", "dws-pbadge-dim"]
    assert res["soloB"]["b"]["cls"] == ["dws-pbadge-sel"] and res["soloB"]["a"]["cls"] == []
    assert res["movedB"] == ["106px", "577px"]                         # 끌면 다음 그림 틀에 자리만 다시
    assert res["off"] == ["dws-pbadges dws-ui dws-pbadges-off", "1", "true"]
    assert res["on"] == ["dws-pbadges dws-ui", "0"]


ZOOM_RUNNER = FAKE_DOM + r"""
let Z = 1;
const node = { getClientRect: () => ({ x: 600, y: 300, width: 400, height: 300 }), rotation: () => 0, image: () => null, on() {} };
const sheet = { objects: [{ id: 'a', type: 'image', part: { label: '정면·내부', src: 'ai', ai: '정면·내부', conf: 0.72 } }] };
const host = el('div');
B.init({ host, getSheet: () => sheet, nodeFor: (id) => (id === 'a' ? node : null), anchor: save, threshold: () => 0.5, zoom: () => Z });
flush();
const out = [];
for (const z of [2, 1, 0.74, 0.5]) { Z = z; window.FomsPartBadges.refresh(); flush(); const b = host.children[0].children[0]; out.push([b.style.left, b.style.top]); }
process.stdout.write(JSON.stringify(out));
"""


def test_badge_stage_size_follows_zoom_down_to_80_percent():
    """V1 맞춤 74%: 딱지가 화면에서 늘 12px 라 그림보다 커 보여 치수를 덮었다 — 100% 아래에서는 80% 까지 같이 준다.
    자리 계산(스테이지 좌표)도 CSS 와 같은 배율(badgeScale)로 잰 크기를 쓴다: 그림 (600,300) 위 바깥 = y - 높이 - 틈/3."""
    proc = subprocess.run([_node(), "-e", ZOOM_RUNNER, str(SPOT_JS), str(STATUS_JS), str(BADGES_JS)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    # 높이 21 · 틈 6(화면 px) × 배율 k = badgeScale(z) / z: 2배 0.5 · 1배 1 · 74% 1.081 · 50% 1.6
    assert json.loads(proc.stdout) == [["603px", "289px"], ["606px", "277px"], ["606px", "275px"], ["610px", "263px"]]
    src = BADGES_JS.read_text(encoding="utf-8")
    assert "S.badgeScale(z) : 1) / z" in src and "fw: el._fw * k" in src


REFIT_RUNNER = FAKE_DOM + r"""
const ros = [];
window.ResizeObserver = function (cb) { this.observe = (t) => ros.push({ cb, t }); };
B.init({ host: el('div'), getSheet: () => ({ objects: [] }), nodeFor: () => null, anchor: save });
const chip = reg['dws-part-status'].children[0], text = chip.children[0], cnt = chip.children[1];
const snap = () => [text.textContent, text.hidden, cnt.textContent, chip.title];
const resize = () => { ros.forEach(r => r.cb([])); flush(); };
const out = { observed: ros.map(r => r.t === chip) };
B.progress(0, 4, { loading: false }); flush(); out.wide = snap();
NARROW = true; resize(); out.narrow = snap();          // 칩이 보이는 동안 좁아짐 — 다음 진행 칸을 기다리지 않고 짧은 글로
NARROW = false; resize(); out.wideAgain = snap();      // 다시 넓어지면 넓은 글로
B.progress(0, 0, {}); tick(900); B.progress(0, 5, { loading: null }); flush(); out.unknown = snap();   // 모델이 있는지 아직 모름
B.progress(1, 5, { loading: true }); flush(); out.known = snap();
process.stdout.write(JSON.stringify(out));
"""


def test_busy_chip_refits_on_resize_and_shows_count_only_until_model_state_known():
    """V1: 넓은 글을 보이던 중 창이 1920→1366 으로 줄자 '그림 종… 0/4' 로 잘린 채 남았다 · 첫 올림에서
    '그림 종류 알아보는 중 0/2' 가 0.1초 뒤 '모델 받는 중 0/5' 로 바뀌며 깜빡였다."""
    proc = subprocess.run([_node(), "-e", REFIT_RUNNER, str(STATUS_JS), str(BADGES_JS)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout)
    assert res["observed"][0] is True                                   # 칩 폭을 지켜본다(+ 앱바가 있으면 앱바)
    assert res["wide"] == ["그림 종류 알아보는 중", False, " 0/4", "그림 종류 알아보는 중 0/4"]
    assert res["narrow"] == ["분류 중", False, " 0/4", "그림 종류 알아보는 중 0/4"]
    assert res["wideAgain"][0] == "그림 종류 알아보는 중"
    assert res["unknown"] == ["", True, "0/5", "그림 종류 0/5"]           # 글 없이 장수만 — 바뀔 글을 미리 보이지 않는다
    assert res["known"] == ["모델 받는 중", False, " 1/5", "모델 받는 중 1/5 — 처음 한 번만 받아요"]
    js = WIZARD_JS.read_text(encoding="utf-8")
    prog = _fn_body(js, "partProgress")
    assert "partModelCached === null ? null" in prog                     # 답이 오기 전에는 loading: null
    assert "partCheckModel()" in _fn_body(js, "initPartBadges")         # 페이지를 열 때 미리 물어 둔다
