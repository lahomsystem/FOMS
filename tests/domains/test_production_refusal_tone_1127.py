"""생산 화면 거절 · 응답 글 말투 '~해요'(사장님 2026-11-27 "'~해요'로 맞추기") — 뜻 · 코드 · 응답 숫자는 그대로, 글만.

- 생산 서버 파일(``foms/api/production`` · ``foms/services/production`` · ``foms/web/production``)의 글 상수에 합니다체
  ('…니다')가 남지 않는다. 남긴 글은 :data:`KEEP_FORMAL` 에 까닭과 함께.
- 낱말은 띄어 쓴다('제작 중' · '제작 대기' · '제작 완료'). 붙여 쓴 채 남긴 값(단계 이름 견주기 · 주문 기록에 저장되는 글)은
  :data:`KEEP_GLUED` 에 까닭과 함께.
- 대표 거절 셋은 실제 API 응답 글 원문으로.
"""
from __future__ import annotations

import ast
import re
import warnings
from pathlib import Path

from tests.domains.test_admin_override_production_reverts import _login, _make_order, _make_user, _mint_run

ROOT = Path(__file__).resolve().parents[2]
SCOPE = [ROOT / "foms" / "api" / "production", ROOT / "foms" / "services" / "production", ROOT / "foms" / "web" / "production"]

#: 합니다체로 남긴 글 — (파일 상대 경로, 글) → 까닭. 지금은 없다.
KEEP_FORMAL: dict[tuple[str, str], str] = {}

#: 붙여 쓴 채 남긴 값 — (파일 상대 경로, 글) → 까닭.
KEEP_GLUED: dict[tuple[str, str], str] = {
    ("foms/services/production/factory_home.py", "제작완료"): "단계 이름 값 견주기(stage_label) — 화면 글 아님",
    ("foms/services/production/factory_home.py", "제작중"): "단계 이름 값 견주기(stage_label) — 화면 글 아님",
    ("foms/api/production/orders.py", "제작 취소 (제작대기 복귀)"): "주문 단계 기록에 저장되는 글(타임라인) — 범위 밖",
    ("foms/api/production/orders.py", "완료 취소 (제작중 복귀)"): "주문 단계 기록에 저장되는 글(타임라인) — 범위 밖",
}


def _strings() -> list[tuple[str, int, str]]:
    """범위 파일의 글 상수(독스트링 뺌) — (상대 경로, 줄, 글)."""
    out = []
    for base in SCOPE:
        for path in sorted(base.rglob("*.py")):
            with warnings.catch_warnings():  # part_board.py 독스트링의 '\[' 경고(시험 밖 일)는 여기서 안 띄운다
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(path.read_text(encoding="utf-8"))
            docs = {id(n.body[0].value) for n in ast.walk(tree)
                    if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            rel = path.relative_to(ROOT).as_posix()
            out += [(rel, n.lineno, n.value) for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
    return out


def test_no_formal_ending_left_in_production_server_text():
    found = [(rel, line, text) for rel, line, text in _strings()
             if "니다" in text and (rel, text) not in KEEP_FORMAL]
    assert found == []


def test_production_words_are_spaced_in_server_text():
    found = [(rel, line, text) for rel, line, text in _strings()
             if re.search("제작(중|대기|완료)", text) and (rel, text) not in KEEP_GLUED]
    assert found == []
    kept = {(rel, text) for rel, _line, text in _strings()}
    assert set(KEEP_GLUED) <= kept  # 허용 목록에 없어진 글이 남지 않게


def test_three_refusals_read_in_haeyo_tone(client):
    _login(client, _make_user("tone_admin"))
    done = _make_order("CONSTRUCTION").id
    resp = client.post(f"/api/orders/{done}/production/cancel", json={})
    assert resp.status_code == 409
    assert resp.get_json() == {"success": False, "code": "INVALID_STAGE",
                               "message": "제작 중일 때만 제작 시작을 취소할 수 있어요."}

    running = _make_order("PRODUCTION").id
    _mint_run(running)
    resp = client.post(f"/api/orders/{running}/production/start", json={})
    assert resp.status_code == 409
    assert resp.get_json() == {"success": False, "code": "INVALID_STAGE", "message": "이미 제작 중인 주문이에요."}

    resp = client.post(f"/api/orders/{done}/production/complete", json={})
    assert resp.status_code == 409
    assert resp.get_json() == {"success": False, "code": "INVALID_STAGE",
                               "message": "제작 중일 때만 제작을 완료할 수 있어요."}

    resp = client.post("/api/orders/999999/production/uncomplete", json={})
    assert resp.status_code == 404
    assert resp.get_json() == {"success": False, "message": "주문을 찾을 수 없어요."}
