"""도크 그룹 금액 표시와 예약금(선금) 안내 (D2·D3 — 2026-08-27 원장).

**왜 이 파일이 따로 있나.** 담당자가 도크 머리말의 숫자를 그룹 전체 값으로 읽었다.
그 숫자는 본품 결제액 하나였고 그 본품에 귀속된 옵션값은 빠져 있었다 — 라벨이 없어서
무엇을 더한 값인지 물어볼 수도 없었다. 고친 자리는 셋이다.

1. 머리말 합계 = ``본품 + Σ 귀속 옵션`` (서버 ``mapping.map_group`` 의 정본 등식과 같다).
2. 그 숫자에 **라벨**을 붙인다 — ``본품+옵션`` / 본품 없는 묶음은 ``옵션 합``.
3. 행마다 금액을 붙여 사람이 **검산**할 수 있게 한다.

**계산이 JS 에 있는 이유**: 사람이 귀속 드롭다운을 바꾸면 화면이 ``render()`` 를 다시
부른다. 서버가 페이지 로드 시점에 계산해 실어 보낸 값은 그 순간 낡는다(``width_hints``
가 실제로 그 상태 — 선재 결함). 그래서 파이썬으로는 합계를 잡을 수 없고, 대가를 여기서
갚는다: 합계 규칙은 **함수를 Node 에 태워 실제로 실행**해 못박고, 나머지 표기 계약은
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

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_DOCK_JS = _REPO_ROOT / "static" / "js" / "orders" / "erp-naver-dock.js"
_DOCK_CSS = _REPO_ROOT / "static" / "css" / "orders" / "erp-naver-dock.css"

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
    합계 규칙만은 문자열이 아니라 **실제 실행**으로 못박아야 해서 함수 하나만 떼어낸다.

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


def _sum_rows(rows: list[dict]) -> dict:
    """도크의 ``sumRows`` 를 Node 로 실제 실행한 결과.

    Args:
        rows: 그룹에 속한 행들(도크 payload 의 행 모양).

    Returns:
        ``{"total": int, "known": int, "unknown": int}``.
    """
    script = (
        _extract_function(_source(), "sumRows")
        + "\nvar rows = " + json.dumps(rows, ensure_ascii=True) + ";"
        + "\nprocess.stdout.write(JSON.stringify(sumRows(rows)));\n"
    )
    node = shutil.which("node")
    assert node, "node 가 PATH 에 없다"
    with tempfile.TemporaryDirectory(prefix="naver-dock-sum-") as tmp:
        path = pathlib.Path(tmp) / "sum_rows_check.js"
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([node, str(path)], capture_output=True, text=True,
                              encoding="utf-8", timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------- #
# (1) 합계 등식 — Node 실행
# --------------------------------------------------------------------------- #

@_needs_node
def test_group_total_is_main_plus_attributed_options():
    """그룹 합계 = 본품 + 귀속 옵션 — 서버 ``map_group`` 의 ``items[].price`` 와 같은 등식."""
    result = _sum_rows([
        {"role": "main", "amount": 704200},
        {"role": "addon", "amount": 33000},
        {"role": "addon", "amount": 12000},
    ])

    assert result["total"] == 749200
    assert result["known"] == 3
    assert result["unknown"] == 0


@_needs_node
def test_zero_amount_row_is_counted_not_skipped():
    """0원 옵션은 **아는 값**이다 — 합계에 0 으로 들어가고 모름으로 세지 않는다."""
    result = _sum_rows([{"role": "main", "amount": 704200}, {"role": "addon", "amount": 0}])

    assert result == {"total": 704200, "known": 2, "unknown": 0}


@_needs_node
def test_missing_amount_is_unknown_never_added_as_zero():
    """``amount`` 가 없는 행은 0 으로 더하지 않고 **모름으로 센다**.

    0 으로 더하면 합계가 조용히 작아지고, 화면은 그것을 다 센 값처럼 말한다.
    ``null`` · 키 없음 · 숫자가 아닌 값 셋 다 같은 취급이어야 한다.
    """
    result = _sum_rows([
        {"role": "main", "amount": 704200},
        {"role": "addon", "amount": None},
        {"role": "addon"},
        {"role": "addon", "amount": "33000"},
    ])

    assert result["total"] == 704200, "모르는 값을 0(또는 문자열)으로 합계에 섞었다"
    assert result["known"] == 1
    assert result["unknown"] == 3


@_needs_node
def test_option_price_is_never_added_on_top_of_amount():
    """``optionPrice`` 는 합계에 안 쓴다 — ``amount`` 에 이미 들어 있어 두 번 센다.

    네이버 원본에서 옵션 행의 ``totalPaymentAmount`` 는 그 옵션 값을 이미 포함한다.
    ``optionPrice`` 를 함께 더하면 옵션 금액만큼 합계가 부풀고, 담당자는 그 부푼 값을
    출고가로 옮긴다.
    """
    result = _sum_rows([
        {"role": "main", "amount": 704200, "optionPrice": 90000},
        {"role": "addon", "amount": 0, "optionPrice": 50000},
    ])

    assert result["total"] == 704200
    # 소스에서도 못박는다 — 속성 접근 자체가 없어야 한다(주석 설명은 허용).
    source = _source()
    assert ".optionPrice" not in source and ".option_price" not in source


# --------------------------------------------------------------------------- #
# (2) 표기 계약 — 라벨·모름·환불
# --------------------------------------------------------------------------- #

def test_group_header_labels_what_it_summed():
    """머리말 숫자에 **라벨**이 붙는다 — 라벨 없는 숫자가 오해의 원인이었다.

    본품이 있는 그룹은 ``본품+옵션``, 본품이 없는 묶음(공통·귀속 미정)은 ``옵션 합``.
    그리고 합계는 **지금 그려질 행들**(``rows``)로 세야 귀속을 옮긴 직후에도 아래 행과
    맞는다 — 본품 행 하나만 보던 옛 코드가 어긋나던 자리다.
    """
    source = _squash(_source())

    assert "'본품+옵션 '" in source, "합계에 라벨이 없다"
    assert "'옵션 합 '" in source, "본품 없는 묶음의 라벨이 없다"
    assert "buildGroupAmount(sumRows(rows), mainRow)" in source, (
        "머리말이 화면에 그려질 행들로 합계를 세지 않는다")
    assert "formatAmount(mainRow.amount)" not in source, (
        "본품 결제액 하나를 그대로 머리말에 세우던 옛 코드가 남아 있다")


def test_group_header_says_partial_and_refunded_totals():
    """모르는 행이 섞이면 ``· 모름 N건``, 대체된 옛 집이면 ``환불됨 ·`` 를 붙인다."""
    source = _squash(_source())

    assert "' is-partial'" in source
    assert "'모름 '" in source and "'건'" in source
    assert "'환불됨 · '" in source
    assert "mainRow && mainRow.superseded" in source, "환불 판정을 서버 값으로 하지 않는다"
    # 행 쪽 판정줄은 그대로 둔다 — 머리말은 **별도 줄**이다(원장 회귀 위험 3).
    assert "row.superseded ? ' is-superseded' : ''" in source


def test_row_amount_chip_keeps_zero_and_adds_unknown():
    """행 금액 칩: 0원 표기는 그대로, 모름은 새로 — 둘을 같은 것으로 그리지 않는다.

    본품 행에도 붙는다. 검산할 수 없는 합계는 담당자가 다시 믿지 않는다.
    """
    source = _squash(_source())

    assert "el('span', 'naver-dock-zero', '0원')" in source, "0원 표기가 사라졌다"
    assert "'naver-dock-amt is-unknown', '금액 모름'" in source
    assert "0원이라는 뜻이 아닙니다" in source, "모름 칩이 0원과 다르다고 말하지 않는다"
    assert "title.appendChild(buildAmountChip(row));" in source, "본품 행에는 금액이 없다"


# --------------------------------------------------------------------------- #
# (3) 예약금(선금) 안내 — 하위호환·카드 조건·문구 자리
# --------------------------------------------------------------------------- #

def test_deposit_hint_is_optional_and_card_stands_only_when_values_differ():
    """``deposit_hint`` 키가 없어도 오늘과 똑같이 그린다. 카드는 ``differs`` 일 때만.

    도크 payload 는 서버가 따로 진화한다 — 키가 없는 응답에서 화면이 깨지면 배포 순서
    하나로 편집 화면이 죽는다. 그리고 값이 맞는 보통 주문에까지 카드를 세우면 그 자리가
    잡음이 되어, 정말 틀린 날에 아무도 안 읽는다.
    """
    source = _squash(_source())

    assert "depositHint: payload.deposit_hint || null" in source, "하위호환 기본값이 없다"
    assert "if (!hint || hint.state !== 'differs' || !hint.sentence) return null;" in source
    # 문장은 서버가 만든다 — 화면이 금액으로 문장을 조립하지 않는다(재결제 정본 규율).
    assert "el('div', 'naver-dock-deposit-say', hint.sentence)" in source
    # 복사값은 서버가 만든 쉼표 없는 정수 그대로 — 화면이 다시 포매팅하지 않는다.
    assert "copy.setAttribute('data-naver-dock-copy', hint.copy_value);" in source
    assert "formatAmount(hint" not in source, "복사값·문장을 화면이 다시 만들고 있다"


def test_deposit_line_is_appended_after_the_frozen_fact_lines():
    """예약금 한 줄은 facts **맨 뒤**에 붙는다 — 추가결제·재결제 줄 자리를 흔들지 않는다.

    담당자는 그 두 줄을 자리째로 외웠다(R1). 순서가 바뀌면 "무엇이 달라졌나"를 다시
    배워야 한다. ``differs`` 는 카드가 따로 서므로 여기서는 말하지 않는다 — 같은 말을
    두 번 하면 어느 쪽이 최신인지 사람이 의심한다.
    """
    source = _squash(_source())

    addon_at = source.index("facts.push(['추가결제', ")
    repay_at = source.index("facts.push(['재결제', ")
    deposit_at = source.index("facts.push(['예약금(선금)', ")
    assert addon_at < repay_at < deposit_at, "예약금 줄이 기존 두 줄 사이·앞으로 끼어들었다"

    assert "hint.state === 'differs' || !hint.sentence) return '';" in source
    assert "state.depositHint.state === 'match' ? '' : 'naver-dock-fact-warn'" in source, (
        "맞지 않는 상태를 평범한 줄로 말한다")


def test_deposit_card_sits_outside_the_scrolling_row_list():
    """카드는 정보 블록과 진행바 **사이**다 — 행을 훑는 동안에도 계속 보인다."""
    source = _squash(_source())

    info_at = source.index("var info = buildInfo();")
    card_at = source.index("var deposit = buildDepositCard();")
    pbar_at = source.index("var pbar = el('div', 'naver-dock-pbar');")
    assert info_at < card_at < pbar_at, "카드가 스크롤 영역 안이나 머리말 위로 갔다"


# --------------------------------------------------------------------------- #
# (4) 폼 불가침 회귀 가드
# --------------------------------------------------------------------------- #

def test_dock_js_never_touches_the_order_form():
    """도크는 폼 입력칸 id 를 **읽지도 쓰지도 않는다** (폼 불가침 계약).

    예약금 안내를 붙이면서 가장 쉬운 유혹이 "그냥 넣어주면 되지 않나"였다. 자동 기입
    금지는 명문 규약 4곳에 있고 재논의하지 않기로 결정된 사안이다 — 복사 버튼까지가 끝.

    판별자는 **하이픈**이다. 폼 입력칸 id 는 ``erp-deposit-amount`` 처럼 하이픈을 쓰고,
    도크 자신의 자산은 ``erpNaverDockPane``·``erpEditShell`` 처럼 낙타표기다. 그래서
    ``getElementById('erp`` 통째 금지는 오늘 소스와 모순이고, ``erp-`` 로 못박는다.

    문자열 금지만으로는 다음 사람이 ``document.querySelector`` 로 우회할 수 있다.
    그래서 **문서 전역 조회 대상 전부**를 목록으로 묶어 도크 자기 자산인지 확인한다
    (도크가 만든 노드 안에서 하는 조회는 이 규칙 밖 — 자기 DOM 이다).
    """
    source = _source()

    assert "erp-deposit" not in source, "예약금 입력칸 id 가 도크 소스에 들어왔다"
    assert re.search(r"getElementById\(\s*'erp-", source) is None
    assert re.search(r"querySelector(?:All)?\(\s*'#erp-", source) is None
    assert "[name=" not in source, "폼 필드를 name 으로 찾고 있다"
    assert "document.forms" not in source

    owned = {
        "naver-origin-data",      # 도크 전용 JSON 태그
        "erpEditShell",           # 셸 폭 판정(레이아웃) — 폼 필드가 아니다
        "erpNaverDockPane",
        "erpNaverDockFab",
        "erpNaverDockDrawer",
        ".erp-naver-dock-fab-badge",
        ".erp-naver-dock-mount",
    }
    looked_up = {
        match[1] for match in
        re.findall(r"document\.(getElementById|querySelectorAll|querySelector)\(\s*'([^']*)'",
                   source)
    }
    assert looked_up <= owned, f"도크가 자기 것이 아닌 DOM 을 찾는다: {looked_up - owned}"


def test_dock_css_added_the_new_rules_without_dropping_the_old_ones():
    """CSS 는 **추가만** — 기존 셀렉터를 지우거나 합치지 않았다."""
    css = _DOCK_CSS.read_text(encoding="utf-8")

    assert ".naver-dock-amt" in css and ".naver-dock-amt.is-unknown" in css
    assert ".naver-dock-grp-sub.is-partial" in css
    assert ".naver-dock-grp-sub.is-superseded" in css
    assert ".naver-dock-deposit" in css
    # 지키기로 한 자리(원장 회귀 위험 5).
    assert ".naver-dock-row.is-superseded" in css
    assert ".naver-dock-hh" in css
    assert ".naver-dock-row .naver-dock-zero" in css
