"""팀 이름 사본 금지 — 'CS' 키에 '…팀' 값을 가진 dict 는 team_labels.py 하나뿐."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from foms.services.orders.team_labels import TEAM_LABELS

ROOT = Path(__file__).resolve().parents[3]
CANON = ROOT / "foms" / "services" / "orders" / "team_labels.py"


def _team_copy_hits(source: str) -> list[int]:
    hits: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if (
                isinstance(key, ast.Constant) and key.value == "CS"
                and isinstance(value, ast.Constant) and isinstance(value.value, str)
                and value.value.endswith("팀")
            ):
                hits.append(node.lineno)
                break
    return hits


def test_no_team_label_copies_in_foms() -> None:
    found = [
        f"{path.relative_to(ROOT).as_posix()}:{line}"
        for path in sorted((ROOT / "foms").rglob("*.py"))
        if path != CANON
        for line in _team_copy_hits(path.read_text(encoding="utf-8"))
    ]
    assert found == [], found


def test_detector_catches_a_copy() -> None:
    assert _team_copy_hits('X = {"CS": "라홈팀", "SALES": "영업팀"}') == [1]


_OPTION_RE = re.compile(
    r'<option value="(CS|SALES|MEASURE|DRAWING|PRODUCTION|CONSTRUCTION|SHIPMENT)"[^>]*>\s*([^<]*팀)\s*</option>'
)


def _option_mismatches(html: str) -> list[tuple[str, str]]:
    return [(code, text.strip()) for code, text in _OPTION_RE.findall(html) if text.strip() != TEAM_LABELS[code]]


def test_template_team_options_match_canon() -> None:
    found = [
        f"{path.relative_to(ROOT).as_posix()}: {bad}"
        for path in sorted((ROOT / "templates").rglob("*.html"))
        for bad in _option_mismatches(path.read_text(encoding="utf-8"))
    ]
    assert found == [], found


def test_option_detector_catches_old_name() -> None:
    assert _option_mismatches('<option value="CS">라홈팀</option>') == [("CS", "라홈팀")]


def test_team_labels_table() -> None:
    assert TEAM_LABELS == {
        "CS": "CS팀", "SALES": "영업팀", "MEASURE": "실측팀", "DRAWING": "도면팀",
        "PRODUCTION": "생산팀", "CONSTRUCTION": "시공팀", "SHIPMENT": "출고팀",
    }


def test_js_team_labels_match_canon() -> None:
    src = (ROOT / "static" / "js" / "orders" / "erp-order-shared.js").read_text(encoding="utf-8")
    start = src.index("const ERP_TEAM_LABELS = {")
    block = src[start:src.index("}", start)]
    js = dict(re.findall(r"(\w+):\s*'([^']+)'", block))
    diff = {k: (v, TEAM_LABELS[k]) for k, v in js.items() if k in TEAM_LABELS and v != TEAM_LABELS[k]}
    assert diff == {}, diff
    assert set(TEAM_LABELS) <= set(js), sorted(set(TEAM_LABELS) - set(js))
