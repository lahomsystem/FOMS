"""마법사 공장 줄 접기(사장님 2026-11-25 "단추를 눌렀을 때만 보이기") — 설계서 2026-11-23 §8-5 마법사 시트 도구 줄.

평소에는 탭 줄 아래 공장 줄을 숨기고 탭 줄 오른쪽(이미 있는 자리)에 [공장 지정] 단추 하나만 둔다. 누르면 펼치고 다시 누르면 접는다.
2공장 시트가 있는 주문은 처음부터 펼친다. 펼침은 화면 상태라 저장 자료 · 자동 저장 · 지문에 넣지 않는다. 고를 수 없는 사람은
지금처럼 줄도 단추도 없다. 이름은 모두 지어낸 값이다.

되돌리면 실패: 2공장 없는 주문에서 줄이 펼쳐진 채 뜸(그리는 자리 45px 잃음) · 2공장 있는 주문이 접힌 채 뜸 · 단추가 새 줄에 섬 ·
단추 한 번에 안 펼쳐지고 안 접힘 · 펼침을 저장 자료(마법사 상태) · 브라우저 저장소에 넣음 · 고를 수 없는 사람에게 단추 · CSS 가
[hidden] 을 못 이김 · 핀을 안 올림.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JS_PATH = ROOT / "static/js/drawing/wizard-factory.js"
JS = JS_PATH.read_text(encoding="utf-8")
CSS = (ROOT / "static/css/contexts/drawing/sheet-factory.css").read_text(encoding="utf-8")
RUNNER = ROOT / "tests/domains/wizard_factory_fold_runner.js"
NODE = shutil.which("node")


def _run(**case) -> dict:
    done = subprocess.run([NODE, str(RUNNER), str(JS_PATH)], input=json.dumps(case), capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


needs_node = pytest.mark.skipif(NODE is None, reason="node 가 없다")


@needs_node
def test_order_without_second_factory_starts_folded_and_one_click_opens_then_closes():
    out = _run(by_sheet={}, clicks=2)
    assert out["fold"] == {"text": "공장 지정", "type": "button", "controls": "dsf-toolrow", "className": "dsf-fold"}
    assert out["side_first"] and out["side_count"] == 2  # 탭 줄 오른쪽 이미 있는 자리 맨 앞(새 줄 아님)
    assert out["row"]["next_to_tabrow"] and "dsf-toolrow" in out["row"]["className"]
    assert out["steps"] == [{"expanded": "false", "hidden": True},   # 처음 = 접힘 → 그리는 자리 ④ 전과 같음
                            {"expanded": "true", "hidden": False},   # 한 번 = 펼침
                            {"expanded": "false", "hidden": True}]   # 다시 = 접힘
    assert out["core_calls"] == []  # 저장 · 자동 저장 · 되돌리기 · 브라우저 저장소 아무것도 안 부른다


@needs_node
def test_order_with_second_factory_sheet_starts_open_and_can_fold():
    out = _run(by_sheet={"sheet-b": 2}, clicks=1)
    assert out["steps"] == [{"expanded": "true", "hidden": False}, {"expanded": "false", "hidden": True}]
    assert out["core_calls"] == []


@needs_node
def test_people_who_cannot_set_get_no_row_and_no_button():
    out = _run(by_sheet={"sheet-b": 2}, can_set=False)
    assert out["fold"] is None and out["row"] is None and out["side_count"] == 1  # 지금처럼 탭 표시만


@needs_node
def test_without_a_place_for_the_button_row_stays_open_as_before():
    out = _run(by_sheet={}, side=False)
    assert out["fold"] is None and out["steps"] == [{"expanded": None, "hidden": False}]


def test_fold_state_is_screen_only_and_never_saved():
    assert not re.search(r"localStorage|sessionStorage|markDirty|core\.save|recordUndo|\.state\(\)\.\w+\s*=", JS)
    assert "var unfolded = Object.keys(bySheet).some(" in JS  # 처음 펼침 = 서버가 그린 2공장 시트 표(화면 열 때 값)


def test_css_hides_row_and_keeps_button_size():
    rules = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    assert ".dsf-toolrow[hidden] { display: none; }" in rules  # display:flex 가 [hidden] 을 이기지 않게
    fold = re.search(r"\.dsf-fold \{([^}]*)\}", rules).group(1)
    assert "font-size: calc(13px * var(--foms-fs, 1));" in fold and "min-height: 30px;" in fold  # 탭 줄 44px 안
    assert re.search(r"@media \(pointer: coarse\) \{[^@]*\.dsf-fold \{ min-height: 40px; \}", rules)
    assert '.dsf-fold[aria-expanded="true"]' in rules


def test_pins_moved_with_the_files():
    wizard = (ROOT / "templates/drawing/wizard.html").read_text(encoding="utf-8")
    bench = (ROOT / "templates/drawing/partials/workbench_detail_body.html").read_text(encoding="utf-8")
    assert "js/drawing/wizard-factory.js') }}?v=20261125a" in wizard
    pin = "css/contexts/drawing/sheet-factory.css') }}?v=20261125a"
    assert pin in wizard and pin in bench  # 같은 CSS 를 두 화면이 같은 주소로
    assert len(JS.splitlines()) < 300  # 새 JS 300줄 래칫
