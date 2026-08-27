"""총폭 힌트를 **지금 화면의 귀속**으로 다시 센다 (W1 — 2026-08-27 원장).

**왜 이 파일이 따로 있나.** 같은 세션에서 금액 합계는 화면이 세도록 바꿨다(``sumRows``)
— 사람이 옵션 귀속 드롭다운을 옮기면 즉시 갱신된다. 그런데 바로 옆 총폭은 서버가 페이지
로드 시점에 계산해 실어 보낸 ``width_hints`` 그대로였다. 한 화면의 두 숫자가 서로 다른
시점을 말했다(원장 "수용하는 위험" 첫 줄).

고친 방식은 금액과 **같은 분업**이다.

* 길이 해석은 서버가 계속 한다 — ``parse_length_mm``·``_LENGTH_ADDON_HINTS``·사양 축.
  서버는 행마다 조각(``width_unit_mm``·``width_label``·``width_axes``)을 실어 보낸다.
* 화면은 그 조각으로 **합·문자열 조립만** 다시 한다(``computeWidthHint``).
* 조각이 없는 옛 응답이면 ``width_hints`` 로 떨어져 **오늘과 똑같이** 그린다.

그래서 검증도 두 갈래다: 계산 규칙은 함수를 **Node 에 태워 실제로 실행**해 서버 정본
(``build_width_hint``)과 값이 같은지 대조하고, 화면 배선(어느 행 목록으로 세는가)은
소스 문자열로 못박는다.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.dock import (
    _row_width_facts,
    build_dock_payload,
    build_width_hint,
)
from tests.services.integrations.test_naver_dock import (
    _link,
    _naver_order,
    _snapshot,
    _staff,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_DOCK_JS = _REPO_ROOT / "static" / "js" / "orders" / "erp-naver-dock.js"

_needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")


def _source() -> str:
    """도크 JS 원문."""
    return _DOCK_JS.read_text(encoding="utf-8")


def _squash(text: str) -> str:
    """줄바꿈·들여쓰기를 공백 하나로 눌러 소스 문구를 한 줄로 비교한다."""
    return re.sub(r"\s+", " ", text)


def _extract_function(source: str, name: str) -> str:
    """도크 JS 에서 함수 하나를 통째로 뜯어낸다(중괄호 균형으로 끝을 찾는다).

    도크 JS 는 즉시실행 IIFE 라 통째로는 Node 에서 돌지 않는다(``document`` 를 만진다).

    Args:
        source: 도크 JS 원문.
        name: 뜯어낼 함수 이름.

    Returns:
        ``function name(...) { ... }`` 원문.
    """
    start = source.index("function " + name + "(")
    depth = 0
    for index in range(source.index("{", start), len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(name + " 함수의 끝을 못 찾았다")


#: 화면이 그룹을 가르는 술어 — ``buildPanel`` 원문을 그대로 베낀 것이다. 원문과 같음은
#: :func:`test_panel_groups_width_with_the_same_rows_as_the_amount` 가 못박는다.
_GROUP_HARNESS = """
function groupRows(rows, key) {
    return rows.filter(function (row) {
        if (row.role === 'main') return row.external_id === key;
        return effectiveMain(row) === key;
    });
}
function mainOf(rows, key) {
    return rows.filter(function (row) {
        return row.role === 'main' && row.external_id === key;
    })[0];
}
"""


def _screen_width_hints(rows: list[dict], keys: list[str],
                        server_hints: dict | None = None) -> dict:
    """도크 JS 의 총폭 계산을 Node 로 **실제 실행**한 결과.

    Args:
        rows: 도크 payload 의 행 목록(서버가 실어 보낸 모양 그대로).
        keys: 총폭을 물어볼 그룹 키 목록(본품 ``external_id``).
        server_hints: 로드 시점 ``width_hints``(폴백 경로 확인용).

    Returns:
        ``{그룹 키: 힌트 dict 또는 None}``.
    """
    source = _source()
    script = "\n".join([
        "var state = { widthHints: "
        + json.dumps(server_hints or {}, ensure_ascii=True) + " };",
        _extract_function(source, "effectiveMain"),
        _extract_function(source, "widthTerm"),
        _extract_function(source, "computeWidthHint"),
        _extract_function(source, "widthHintFor"),
        _GROUP_HARNESS,
        "var rows = " + json.dumps(rows, ensure_ascii=True) + ";",
        "var out = {};",
        json.dumps(keys, ensure_ascii=True)
        + ".forEach(function (key) {"
        " out[key] = widthHintFor(key, groupRows(rows, key), mainOf(rows, key)); });",
        "process.stdout.write(JSON.stringify(out));",
    ])
    node = shutil.which("node")
    assert node, "node 가 PATH 에 없다"
    with tempfile.TemporaryDirectory(prefix="naver-dock-width-") as tmp:
        path = pathlib.Path(tmp) / "width_hint_check.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([node, str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def _row(external_id: str, name: str, *, option: str = "", quantity: int = 1,
         role: str = "main", assigned: str | None = None,
         guess: str | None = None) -> dict:
    """서버가 실어 보내는 모양의 도크 행 하나(총폭 조각 포함).

    조각은 **서버 함수**(:func:`_row_width_facts`)가 찍는다 — 테스트가 손으로 지어내면
    화면만 통과하고 실제 payload 와 어긋난다.

    Args:
        external_id: 상품주문번호.
        name: 상품명.
        option: 옵션 원문.
        quantity: 수량.
        role: ``main`` / ``addon``.
        assigned: 사람이 고른 귀속 본품(없으면 None).
        guess: 서버 추정 귀속 본품(없으면 None).

    Returns:
        도크 행 dict.
    """
    row = {"external_id": external_id, "product_name": name, "option_text": option,
           "quantity": quantity, "role": role,
           "assigned_main": assigned, "guess_main": guess}
    row.update(_row_width_facts(row, is_main=role != "addon"))
    return row


# --------------------------------------------------------------------------- #
# (1) 사람이 귀속을 옮기면 총폭이 따라온다 — Node 실행
# --------------------------------------------------------------------------- #

@_needs_node
def test_width_follows_the_person_moving_the_attribution_dropdown():
    """옵션을 다른 본품으로 옮기면 **양쪽 총폭이 즉시** 바뀐다 (W1 결함 그 자체).

    본품 A(300mm × 12) · 본품 B(400mm × 2) · 길이추가(10mm × 12).
    처음엔 추가가 A 에 붙어 A = 3,720 · B = 800. 사람이 B 로 옮기면 A = 3,600 ·
    B = 920 이어야 한다 — 서버가 로드 시점에 보낸 값은 옮겨도 3,720 그대로다.
    """
    rows = [
        _row("A", "로라 무몰딩 여닫이 30cm", quantity=12),
        _row("B", "로라 무몰딩 여닫이 40cm", quantity=2),
        _row("X", "로라 무몰딩 여닫이(푸쉬) 1cm", option="길이추가(1cm)",
             quantity=12, role="addon", guess="A"),
    ]
    stale = {"A": {"total_mm": 3720, "formula": "300mm × 12 + 10mm × 12",
                   "parts": [], "mismatch": []}}

    before = _screen_width_hints(rows, ["A", "B"], server_hints=stale)
    assert before["A"]["total_mm"] == 3720
    assert before["A"]["formula"] == "300mm × 12 + 10mm × 12"
    assert before["B"]["total_mm"] == 800

    rows[2]["assigned_main"] = "B"
    after = _screen_width_hints(rows, ["A", "B"], server_hints=stale)

    assert after["A"]["total_mm"] == 3600, "옮겼는데 옛 본품의 총폭이 그대로다(낡은 값)"
    assert after["A"]["formula"] == "300mm × 12"
    assert after["B"]["total_mm"] == 920, "옮겨 받은 본품의 총폭이 안 늘었다"
    assert after["B"]["formula"] == "400mm × 2 + 10mm × 12"


@_needs_node
def test_screen_never_widens_the_total_with_a_non_length_option():
    """수납구성(TYPE A)·거울도어는 폭과 무관하다 — 서버가 조각을 안 주고 화면은 건너뛴다."""
    rows = [
        _row("A", "로라 무몰딩 여닫이 30cm", quantity=10),
        _row("X", "TYPE A (반옷장)", option="수납구성: TYPE A",
             quantity=2, role="addon", assigned="A"),
    ]
    assert rows[1]["width_unit_mm"] is None, "서버가 길이추가가 아닌 옵션에 조각을 줬다"

    hints = _screen_width_hints(rows, ["A"])

    assert hints["A"]["total_mm"] == 3000
    assert hints["A"]["formula"] == "300mm × 10"


@_needs_node
def test_screen_says_the_same_mismatch_sentence_as_the_server():
    """사양 불일치 경고는 **서버와 한 글자도 다르지 않아야** 한다.

    고객이 본품은 무몰딩, 1cm 추가는 몰딩으로 주문하는 사고가 실재한다. 화면이 문구를
    새로 지으면 담당자가 두 화면에서 다른 말을 읽는다.
    """
    main = _row("A", "로라 무몰딩 여닫이 30cm(푸쉬)", quantity=12)
    addon = _row("X", "로라 몰딩 여닫이 (푸쉬) 1cm", option="길이추가(1cm)",
                 quantity=12, role="addon", assigned="A")

    hints = _screen_width_hints([main, addon], ["A"])
    server = build_width_hint(main, [addon])

    assert hints["A"]["mismatch"] == server["mismatch"]
    assert any("몰딩" in line for line in hints["A"]["mismatch"])


@_needs_node
@pytest.mark.parametrize("case", ["실사례", "옵션이_상품명을_이긴다", "축_불일치", "길이없음"])
def test_screen_and_server_agree_on_the_load_time_grouping(case):
    """로드 직후(= 사람이 아무것도 안 옮긴 상태) 화면 값 == 서버 정본 값.

    분업의 전제는 "같은 조각으로 같은 답"이다. 한 자리라도 갈리면 새로고침 한 번에
    숫자가 바뀌어 담당자가 어느 쪽을 믿을지 모르게 된다.
    """
    fixtures = {
        "실사례": (
            _row("A", "로라 무몰딩 여닫이 30cm", quantity=12),
            _row("X", "로라 무몰딩 여닫이(푸쉬) 1cm", option="길이추가(1cm)",
                 quantity=12, role="addon", assigned="A"),
        ),
        "옵션이_상품명을_이긴다": (
            _row("A", "라홈 무몰딩 붙박이장 로라 시리즈 30cm 푸쉬타입 친환경 E0",
                 option="제품: 로라 몰딩 여닫이 30cm / 컬러: 화이트 / 손잡이: 푸쉬타입",
                 quantity=10),
            _row("X", "로라 몰딩 여닫이 (푸쉬) 1cm",
                 option="길이추가(1cm): 로라 몰딩 여닫이 (푸쉬) 1cm",
                 quantity=24, role="addon", assigned="A"),
        ),
        "축_불일치": (
            _row("A", "라홈 로라 붙박이장 30cm",
                 option="제품: 로라 무몰딩 여닫이 30cm / 손잡이: 푸쉬타입", quantity=10),
            _row("X", "보테가 슬라이딩 1cm", option="길이추가(1cm): 보테가 슬라이딩 1cm",
                 quantity=5, role="addon", assigned="A"),
        ),
        "길이없음": (
            _row("A", "붙박이장 세트", option="색상: 화이트", quantity=3),
            _row("X", "거울도어", option="구성: 거울도어", quantity=1,
                 role="addon", assigned="A"),
        ),
    }
    main, addon = fixtures[case]

    screen = _screen_width_hints([main, addon], ["A"])["A"]
    server = build_width_hint(main, [addon])

    if server is None:
        assert screen is None, "서버가 못 읽은 길이를 화면이 지어냈다"
        return
    assert screen["total_mm"] == server["total_mm"]
    assert screen["formula"] == server["formula"]
    assert screen["mismatch"] == server["mismatch"]
    assert screen["parts"] == server["parts"]


@_needs_node
def test_old_payload_without_row_parts_falls_back_to_the_server_hint():
    """조각이 없는 옛 응답이면 로드 시점 ``width_hints`` 를 **그대로** 그린다.

    도크 payload 는 서버가 따로 진화한다 — 배포 순서 하나로 총폭이 사라지면 안 된다.
    """
    rows = [
        {"external_id": "A", "role": "main", "quantity": 12},
        {"external_id": "X", "role": "addon", "quantity": 12,
         "assigned_main": "A", "guess_main": None},
    ]
    stale = {"A": {"total_mm": 3720, "formula": "300mm × 12 + 10mm × 12",
                   "parts": [], "mismatch": ["몰딩: 본품 무몰딩 · 추가 몰딩"]}}

    hints = _screen_width_hints(rows, ["A"], server_hints=stale)

    assert hints["A"] == stale["A"], "옛 응답에서 총폭이 사라지거나 달라졌다"


# --------------------------------------------------------------------------- #
# (2) 화면 배선 — 금액과 **같은 행 목록**으로 센다
# --------------------------------------------------------------------------- #

def test_panel_groups_width_with_the_same_rows_as_the_amount():
    """총폭과 금액이 **같은 모집단**(그룹 rows)을 센다 — 두 숫자가 갈리지 않는 근거.

    위 Node 검증은 ``computeWidthHint`` 안쪽만 본다. 어느 행 목록을 넘기는지는 여기서
    소스로 못박는다 — 이 줄이 무너지면 총폭이 다시 로드 시점 값으로 돌아간다.
    """
    source = _squash(_source())

    assert "buildGroupAmount(sumRows(rows), mainRow)" in source
    assert "widthHintFor(group.key, rows, mainRow)" in source, (
        "총폭을 화면 그룹으로 세지 않는다")
    assert "var hint = state.widthHints[group.key];" not in source, (
        "로드 시점 서버 값을 그대로 그리던 옛 코드가 남아 있다")
    # 그룹 술어 원문 — 위 Node 하네스가 베껴 쓰는 두 줄이다.
    assert "if (row.role === 'main') return row.external_id === group.key;" in source
    assert "return effectiveMain(row) === group.key;" in source


def test_width_fallback_and_payload_default_are_kept():
    """하위호환 두 자리(폴백 분기·payload 기본값)를 지운 채로 통과할 수 없다."""
    source = _squash(_source())

    assert "widthHints: payload.width_hints || {}" in source, "payload 기본값이 사라졌다"
    assert ("if (mainRow && 'width_unit_mm' in mainRow) "
            "return computeWidthHint(rows, mainRow);") in source, "새 조각 판별이 사라졌다"
    assert "state.widthHints[groupKey]" in source, "옛 응답 폴백이 사라졌다"


def test_screen_assembles_but_never_reparses_lengths():
    """길이 **해석**은 서버 몫 — 화면에 파서가 두 벌 생기면 두 답이 생긴다.

    화면이 하는 일은 곱·합과 문자열 조립뿐이다.
    """
    source = _source()

    assert "RegExp" not in source and re.search(r"\.match\(", source) is None, (
        "도크 JS 가 원문을 다시 파싱하고 있다")
    assert "parseFloat" not in source and "parseInt" not in source

    # 계산 함수는 **서버가 찍어 준 조각만** 읽는다 — 상품명·옵션 원문에 손대는 순간
    # 길이 파서가 두 벌이 되고, 서버가 규칙을 고쳐도 화면만 옛 답을 낸다.
    fn = _extract_function(source, "computeWidthHint")
    assert "product_name" not in fn and "option_text" not in fn, (
        "총폭 계산이 원문을 다시 읽고 있다")
    for field in ("width_unit_mm", "width_label", "width_axes"):
        assert field in fn, f"{field} 조각을 안 쓴다"
    # 조립만 한다 — 조각은 서버가 준 값 그대로 쓴다.
    assert "unitMm.toLocaleString('ko-KR') + 'mm × ' + quantity" in source


# --------------------------------------------------------------------------- #
# (3) payload — 행마다 조각이 실린다
# --------------------------------------------------------------------------- #

def test_payload_rows_carry_the_width_parts(app):
    """도크 payload 의 **행마다** 총폭 조각이 실린다 — 화면이 다시 셀 재료다."""
    order = _naver_order(_staff())
    _link(order, _snapshot(product_name="로라 무몰딩 여닫이 30cm",
                           amount=800000, quantity=12))
    _link(order, _snapshot(product_name="로라 무몰딩 여닫이(푸쉬) 1cm",
                           option="길이추가(1cm)", product_class="추가구성상품",
                           amount=33200, quantity=12))
    _link(order, _snapshot(product_name="TYPE A (반옷장)", option="수납구성: TYPE A",
                           product_class="추가구성상품", amount=0, quantity=2))

    rows = build_dock_payload(db_session, order)["rows"]

    assert [row["width_unit_mm"] for row in rows] == [300, 10, None], (
        "길이추가가 아닌 옵션에 폭 조각이 붙었거나, 본품 길이가 빠졌다")
    assert rows[0]["width_label"] == "로라 무몰딩 여닫이 30cm"
    assert rows[0]["width_axes"] == {"몰딩": "무몰딩", "문 방식": "여닫이"}
    assert rows[2]["width_label"] == "TYPE A (반옷장)", "라벨은 조각이 없어도 싣는다"
