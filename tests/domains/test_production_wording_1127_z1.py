"""생산 화면 글 고침 셋(사장님 2026-11-27 질문 창 답 그대로) — 동작은 그대로, 사람이 읽는 글만.

1. 작업 시트 확인 창 띄어쓰기("띄어쓰기만 맞추기"): "제작을 취소하고 제작 대기로 되돌릴까요?" ·
   "완료를 취소하고 제작 중으로 되돌릴까요?"(``tablet-domain-sheets.js`` — 첫 화면 · 작업 시트 · 출고 CHAIN 이 싣는 공용 파일).
2. PC 도면 목록 창 줄("둘 다 맞추기"): "작업 시작 김재단 · 11/24 08:16" → "시작 김재단 · 11/24 08:16"(``pc_sheet._who``).
3. 도면 없는 주문 안내 글: "…공정 칸을 완료로 처리하거나 관리자에게 말해 주세요."(서버 한 곳 + 작업 시트 JS 한 곳 같은 글).
"""
from __future__ import annotations

import re
from pathlib import Path

from foms.services.production import pc_sheet
from foms.services.production.part_progress import NO_DRAWINGS_MESSAGE

ROOT = Path(__file__).resolve().parents[2]
SHEETS_JS = "static/js/foms/tablet-domain-sheets.js"
SHEET_PARTS_JS = "static/js/production/foms-production-sheet-parts.js"
PIN = "20261128e"  # foms-production-sheet-parts.js — 11-28 e: '도면 없음' 카드 주문 [제작 완료] 누름 글 = 서버 글 · 11-28 d: 바뀐 기록 머리 '도면 없음'
SHEETS_PIN = "20261128c"  # tablet-domain-sheets.js · shipment-entry.js — 11-28 c: 수정 제작 고르기 창


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_확인_창_띄어쓰기_두_군데만() -> None:
    js = _read(SHEETS_JS)
    assert 'title: "제작을 취소하고 제작 대기로 되돌릴까요?",' in js
    assert 'var text = "완료를 취소하고 제작 중으로 되돌릴까요?";' in js
    assert "제작대기로 되돌릴까요" not in js and "제작중으로 되돌릴까요" not in js
    # 그 밖의 글은 그대로 — 단추 · 사유 칸 이름
    assert 'actionLabel: "제작 시작 취소",' in js and 'detailLabel: "제작 취소 사유 (선택)",' in js
    assert 'ask(btn, { title: text, yes: "완료 취소", plain: text }' in js


def test_도메인_시트_JS_핀은_싣는_곳마다_새_값() -> None:
    for rel in ("templates/production/partials/home_body.html", "templates/production/sheet.html"):
        assert f"tablet-domain-sheets.js') }}}}?v={SHEETS_PIN}" in _read(rel), rel
    entry = _read("static/js/shipment/shipment-entry.js")
    assert f"'/static/js/foms/tablet-domain-sheets.js?v={SHEETS_PIN}'" in entry
    assert f"shipment-entry.js') }}}}?v={SHEETS_PIN}" in _read("templates/shipment/partials/dashboard_scripts.html")
    every = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "templates").rglob("*.html")) + entry
    assert set(re.findall(r"tablet-domain-sheets\.js(?:'\) \}\})?\?v=(\w+)", every)) == {SHEETS_PIN}


def test_PC_줄은_시작_이름_시각() -> None:
    assert pc_sheet._who("시작", "김재단", None) == "시작 김재단"
    crew = [{"name": "김재단", "at": "2026-11-23T23:16:00", "done": True, "done_name": "박반장", "done_at": "2026-11-24T06:02:00"}]
    lines = pc_sheet._people(crew)
    assert lines[0] == "시작 김재단 · 11/24 08:16", lines
    assert not any(line.startswith("작업 시작") for line in lines)
    assert '_who("작업 시작"' not in _read("foms/services/production/pc_sheet.py")


def test_도면_없는_주문_안내_글은_한_글() -> None:
    text = "도면이 없어요 — 공정 칸을 완료로 처리하거나 관리자에게 말해 주세요."
    assert NO_DRAWINGS_MESSAGE == text
    parts = _read(SHEET_PARTS_JS)
    assert f"return '{text}';" in parts and "작업 완료로 처리하거나" not in parts
    assert len(parts.splitlines()) <= 300
    assert f"foms-production-sheet-parts.js') }}}}?v={PIN}" in _read("templates/production/sheet.html")
    assert _read("templates/production/partials/home_scripts.html").count(f"foms-production-sheet-parts.js') }}}}?v={PIN}") == 2
