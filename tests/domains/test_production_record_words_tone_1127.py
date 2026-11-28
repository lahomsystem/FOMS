"""작업 시트 '바뀐 기록' 낱말 · 공정 칸 알림 · 생산 화면 JS 글 말투(사장님 2026-11-27 질문 창 답 그대로).

일 1 — "단추 말과 맞추기": 기록 '작업 시작' → '시작', '작업 완료' → '완료', '작업 취소' → '완료 취소'. 줄 머리에 공정 이름이 이미 있다
("재단 도면 1/3: 김재단 시작 11/27 10:00 → 박엣지 같이 작업 10:05"), 그래서 낱말만 바꾼다(파트 이름을 새로 붙이지 않는다). 카드 동기화
줄도 같은 낱말("도면 모두 완료 — 완료 처리" · "도면 미완료 — 완료 취소 처리"). 도면 0장 주문 공정 칸 알림은 누른 공정 이름을 붙여
"재단 완료했어요" / "재단 완료 취소했어요" — 도면 카드 알림(foms-production-parts.js ``p.run + '했어요'``, run = "재단 완료" ·
"재단 완료 취소")과 글자까지 같은 꼴.

일 2 — "'~해요'로 맞추기": 생산 화면 JS(static/js/production/** · 공용 tablet-domain-sheets.js)에 박힌 화면 글에 '…습니다' ·
'…십시오' · '…하세요'로 끝나는 글이 없다. 남긴 것은 아래 허용 목록(까닭과 함께) — 생산 화면에서 안 뜨는 글이다.

되돌리면 실패: KIND 에 '작업 시작' · '작업 완료' · '작업 취소'가 돌아옴 · 알림이 '작업 완료했어요' 로 돌아옴 · 생산 JS 에 '습니다' 글이
새로 생김 · 허용 목록 글이 생산 함수로 옮겨 감. 이름은 지어낸 값(김재단 · 박엣지 · 박반장).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROD_JS = ROOT / "static/js/production"
SHEETS_JS = ROOT / "static/js/foms/tablet-domain-sheets.js"
SHEET_PARTS = PROD_JS / "foms-production-sheet-parts.js"
SHEET_PAGE = PROD_JS / "foms-production-sheet-page.js"
PIN = "20261127z"
PARTS_PIN = "20261128d"  # 11-28 d: 바뀐 기록 머리 '도면 없음'(test_production_order_card_arrival) · 11-28 c: 담당 고르기 · 조립 없음 낱말 · 11-28 b: 바뀐 기록 겹친 완료 빼기 · 11-28 a: 도면 없는 주문 안내 글 '완료로 처리'(test_production_wording_1127_z1)

# 남긴 '…습니다' 글 — (파일, 글, 그 글이 있는 함수, 까닭)
ALLOWED = [
    ("static/js/foms/tablet-domain-sheets.js", "권한이 없습니다.", "function shipmentSave(",
     "출고 태블릿 서랍 [저장](shipment-save) 403 기본 글 — 생산 화면에서는 안 뜬다(사장님 답은 생산 화면 글)"),
]
STIFF = re.compile(r"(습니다|십시오|하세요)[.!?]?\s*$")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strings(src: str) -> list[tuple[int, str]]:
    """JS 문자열 글(따옴표 둘 · 백틱) — 주석 안 글은 뺀다. (줄 번호, 글)."""
    out: list[tuple[int, str]] = []
    i, n, line = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += src.count("\n", i, j)
            i = j
        elif c in "'\"`":
            j, buf, start = i + 1, [], line
            while j < n and src[j] != c:
                if src[j] == "\\" and j + 1 < n:
                    buf.append(src[j:j + 2])
                    j += 2
                    continue
                if src[j] == "\n":
                    line += 1
                buf.append(src[j])
                j += 1
            out.append((start, "".join(buf)))
            i = j + 1
        else:
            i += 1
    return out


def _kind() -> dict[str, str]:
    m = re.search(r"var KIND = \{(.*?)\};", _read(SHEET_PARTS), re.S)
    assert m, "KIND 없음"
    return dict(re.findall(r"(\w+): '([^']*)'", m.group(1)))


# --------------------------------------------------------------------------- #
# 일 1 — 바뀐 기록 낱말 · 알림
# --------------------------------------------------------------------------- #
def test_바뀐_기록_낱말은_단추_말과_같다() -> None:
    kind = _kind()
    assert kind["take"] == "시작" and kind["step_on"] == "완료" and kind["step_off"] == "완료 취소"
    # 그대로인 낱말(대조군) — 이미 단추 말
    assert kind["join"] == "같이 작업" and kind["done"] == "완료" and kind["undo"] == "완료 취소"
    assert kind["release"] == "시작 취소" and kind["remove"] == "시작 취소" and kind["check"] == "완료" and kind["basic"] == "기본"
    assert not [v for v in kind.values() if v.startswith("작업 ")]
    src = _read(SHEET_PARTS)
    assert "'도면 모두 완료' + t" in src and "'도면 모두 완료 — '" not in src and "'도면 미완료 — ' + KIND.step_off + ' 처리'" in src
    assert "작업 완료 처리'" not in src and "작업 취소 처리'" not in src


def test_공정_칸_알림은_누른_공정_이름을_붙인다() -> None:
    page = _read(SHEET_PAGE)
    assert "savedText((stepLabel(btn) + (done ? ' 완료했어요' : ' 완료 취소했어요')).trim())" in page
    assert "'작업 완료했어요'" not in page and "'작업을 취소했어요'" not in page
    # 도면 카드 알림과 같은 꼴 — run = LABEL + ' 완료' · LABEL + ' 완료 취소', 알림 = run + '했어요'
    parts = _read(PROD_JS / "foms-production-parts.js")
    modal = _read(PROD_JS / "foms-production-parts-modal.js")
    assert "p.run + '했어요'" in parts
    assert "run: LABEL + ' 완료'" in modal and "run: LABEL + ' 완료 취소'" in modal
    label = "재단"
    for done, want in ((True, "재단 완료했어요"), (False, "재단 완료 취소했어요")):
        assert (label + (" 완료했어요" if done else " 완료 취소했어요")).strip() == want
        assert (label + (" 완료" if done else " 완료 취소")) + "했어요" == want  # 카드 알림 글과 한 글자도 같다


NODE_LOG = r"""
const fs = require('fs');
function el(tag) { return { tag, kids: [], textContent: '', setAttribute() {}, appendChild(c) { this.kids.push(c); } }; }
global.window = {};
global.document = { addEventListener() {}, createElement: el, createTextNode: (t) => ({ text: t }), querySelector: () => null };
eval(fs.readFileSync(process.argv[2], 'utf8'));
const items = JSON.parse(process.argv[3]);
const list = el('ul');
window.FomsSheetParts.renderLog(list, items, ['k1', 'k2', 'k3']);
const out = list.kids.map((li) => li.kids.map((k) => (k.text != null ? k.text : k.textContent)).join(''));
process.stdout.write(JSON.stringify(out));
"""


def test_바뀐_기록_줄_원문(tmp_path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node 없음")
    at = "2026-11-27T01:%02d:00+00:00"
    items = [
        {"part": "cut", "drawing_key": "k1", "kind": "take", "by_name": "김재단", "at": at % 0},
        {"part": "cut", "drawing_key": "k1", "kind": "join", "by_name": "박엣지", "at": at % 5},
        {"part": "cut", "drawing_key": "k1", "kind": "done", "by_name": "김재단", "at": at % 10},
        {"part": "cut", "drawing_key": "k1", "kind": "undo", "by_name": "김재단", "at": at % 11},
        {"part": "cut", "drawing_key": "k1", "kind": "remove", "by_name": "박반장", "target_name": "박엣지", "at": at % 12},
        {"part": "cut", "drawing_key": "k1", "kind": "take", "by_name": "박반장", "holder_name": "김재단", "at": at % 13},
        {"part": "edge", "drawing_key": "", "kind": "step_on", "by_name": "박반장", "at": at % 20},
        {"part": "edge", "drawing_key": "", "kind": "step_off", "by_name": "박반장", "at": at % 21},
        {"part": "cut", "drawing_key": "", "kind": "step_on", "via": "part_marks", "at": at % 30},
        {"part": "cut", "drawing_key": "", "kind": "step_off", "via": "part_marks", "at": at % 31},
    ]
    script = tmp_path / "log.js"
    script.write_text(NODE_LOG, encoding="utf-8")
    proc = subprocess.run([node, str(script), str(SHEET_PARTS), json.dumps(items, ensure_ascii=False)],
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stderr
    lines = json.loads(proc.stdout)
    assert lines == [  # 같은 공정은 '칸'(도면 없는 기록) 줄이 도면 줄보다 앞(renderLog 정렬 그대로)
        "재단 칸: 도면 모두 완료 11/27 10:30 → 도면 미완료 — 완료 취소 처리 10:31",  # 11-28 겹친 '완료' 뺌
        "재단 도면 1/3: 김재단 시작 11/27 10:00 → 박엣지 같이 작업 10:05 → 김재단 완료 10:10 → 김재단 완료 취소 10:11"
        " → 박엣지 시작 취소 (박반장) 10:12 → 박반장 (김재단 대신) 시작 10:13",
        "엣지 칸: 박반장 완료 11/27 10:20 → 박반장 완료 취소 10:21",
    ]
    assert not [x for x in lines if "작업 시작" in x or "작업 완료" in x or "작업 취소" in x]


def test_고친_파일_핀은_싣는_곳마다_같다() -> None:
    sheet = _read(ROOT / "templates/production/sheet.html")
    scripts = _read(ROOT / "templates/production/partials/home_scripts.html")
    body = _read(ROOT / "templates/production/partials/home_body.html")
    assert f"foms-production-sheet-parts.js') }}}}?v={PARTS_PIN}" in sheet and f"foms-production-sheet-page.js') }}}}?v={PIN}" in sheet
    assert scripts.count(f"foms-production-sheet-parts.js') }}}}?v={PARTS_PIN}") == 2
    assert f"foms-production-sheet-page.js') }}}}?v={PIN}" in body
    every = "".join(_read(p) for p in (ROOT / "templates").rglob("*.html"))
    for name, pin in (("foms-production-sheet-parts.js", PARTS_PIN), ("foms-production-sheet-page.js", PIN)):
        pins = set(re.findall(re.escape(name) + r"'\) \}\}\?v=(\w+)", every))
        assert pins == {pin}, (name, pins)


# --------------------------------------------------------------------------- #
# 일 2 — 생산 화면 JS 글 말투
# --------------------------------------------------------------------------- #
def _stiff_hits() -> list[tuple[str, int, str]]:
    files = sorted(PROD_JS.rglob("*.js")) + [SHEETS_JS]
    hits = []
    for path in files:
        for line, text in _strings(_read(path)):
            if STIFF.search(text):
                hits.append((path.relative_to(ROOT).as_posix(), line, text))
    return hits


def test_생산_JS_화면_글에_습니다_꼴이_없다() -> None:
    hits = _stiff_hits()
    allowed = {(rel, text) for rel, text, _fn, _why in ALLOWED}
    assert [(rel, line, text) for rel, line, text in hits if (rel, text) not in allowed] == []
    # 허용 목록은 지금도 있고(낡은 목록 아님), 생산 화면이 안 부르는 함수 안에 있다
    for rel, text, fn, _why in ALLOWED:
        src = _read(ROOT / rel)
        start = src.index(fn)
        end = src.index("\n  }\n", start)
        assert src.count('"' + text + '"') == 1 and start < src.index('"' + text + '"') < end, (rel, text)
    assert 'action === "shipment-save"' in _read(SHEETS_JS)
    for tpl in (ROOT / "templates/production").rglob("*.html"):
        assert "shipment-save" not in _read(tpl), tpl  # 생산 화면에는 출고 서랍 [저장] 단추가 없다


def test_글_찾기가_주석은_빼고_글은_잡는다() -> None:
    # 음성 대조군 — 주석 속 '습니다'는 안 잡고, 문자열 속 '습니다'는 잡는다
    src = "// 권한이 없습니다.\n/* 다시 시도하세요. */\nvar a = '저장했습니다.';\nvar b = \"눌러 주세요.\";\nvar c = 'http://x';\n"
    found = [t for _l, t in _strings(src) if STIFF.search(t)]
    assert found == ["저장했습니다."]
    assert [t for _l, t in _strings(src)] == ["저장했습니다.", "눌러 주세요.", "http://x"]
