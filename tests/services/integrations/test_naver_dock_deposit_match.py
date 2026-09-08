"""도크 예약금 대조 — 넣었는지 화면이 센다 (2026-09-09, Node 실행).

**왜 생겼나.** 돈은 사람이 넣는다(2026-09-08 확정 결정, 뒤집지 않는다). 문제는 **안 넣었을
때 아무도 몰랐다**는 것이다. 재결제 실사례: 새 결제가 1,088,450원인데 예약금 칸에 옛 값
1,093,100원이 남으면 잔금(``출고가 − 예약금``)이 4,650원 틀린다. 그 오차는 조용하고,
정산 탭에서 드러날 때는 이미 몇 주 뒤다.

그래서 **넣지는 않되 대조는 한다**. 넣은 사람은 ✓ 를 보고 끝내고, 안 넣은 사람은 경고를
계속 본다 — 토스트는 사라지지만 이 줄은 고칠 때까지 남는다.

무엇이 깨지면 무슨 일이 나나:

* 쉼표를 안 걷으면 ``1,088,450`` 이 언제나 `differs` 다 — 넣어도 경고가 안 사라진다.
  경고가 늘 떠 있으면 사람이 안 읽는다.
* 빈 칸을 `unknown` 으로 세면 **아직 안 넣은 사람에게 아무 말도 안 한다** — 이 기능이
  막으려던 바로 그 경우다.
* 숫자가 아닌 글자를 `differs` 로 세면 담당자가 적어 둔 메모를 틀렸다고 말한다.
  모르면 말하지 않는다.
"""

from __future__ import annotations

import pathlib

from tests.services.integrations.test_naver_dock_autofill_wire import _run
from tests.services.integrations.test_naver_dock_width_live import _needs_node

DOCK_JS = pathlib.Path("static/js/orders/erp-naver-dock.js").read_text(encoding="utf-8")


@_needs_node
def test_deposit_match_reads_the_number_through_commas_and_won():
    """쉼표·``원``·공백을 걷고 숫자만 견준다 — 칸은 언제나 쉼표를 달고 산다."""
    got = _run(("dockDepositMatch",), """[
        dockDepositMatch('1,088,450', 1088450),
        dockDepositMatch('1088450', 1088450),
        dockDepositMatch(' 1,088,450원 ', 1088450),
        dockDepositMatch('1,093,100', 1088450)
    ]""")

    assert got == ["match", "match", "match", "differs"]


@_needs_node
def test_blank_deposit_counts_as_different_not_unknown():
    """빈 칸은 `differs` 다 — '아직 안 넣었다'가 이 기능이 잡으려던 경우다."""
    got = _run(("dockDepositMatch",),
               "[dockDepositMatch('', 1088450), dockDepositMatch('   ', 1088450)]")

    assert got == ["differs", "differs"]


@_needs_node
def test_unreadable_text_is_unknown_so_the_screen_stays_quiet():
    """숫자를 못 읽으면 `unknown` — 사람이 적어 둔 글자를 틀렸다고 말하지 않는다."""
    got = _run(("dockDepositMatch",), """[
        dockDepositMatch('상담', 1088450),
        dockDepositMatch('1,088,450원 중 절반', 1088450),
        dockDepositMatch('1,088,450', 0),
        dockDepositMatch('1,088,450', null)
    ]""")

    assert got == ["unknown", "unknown", "unknown", "unknown"]


def test_the_dock_reads_the_deposit_field_by_contract_not_by_form_id():
    """칸은 ``data-erp`` 로 찾는다 — 폼 id 무참조 계약이 여기서도 그대로다.

    도크가 ``#erp-deposit-amount`` 를 읽기 시작하면 폼 불가침 계약의 남은 절반이 깨진다.
    """
    assert 'data-erp="deposit_amount"' in DOCK_JS
    assert "erp-deposit-amount" not in DOCK_JS, "도크가 폼 id 를 읽는다"

    tab = pathlib.Path("templates/orders/partials/erp_order_tab.html").read_text(encoding="utf-8")
    assert 'data-erp="deposit_amount"' in tab, "예약금 칸에 계약 속성이 없다"


def test_the_match_line_follows_the_person_typing():
    """사람이 예약금을 고치면 대조 줄이 따라간다 — 넣고 나서 ✓ 를 봐야 끝난 줄 안다."""
    assert "syncDepositMatch" in DOCK_JS
    # `['input','change'].forEach` 는 값을 넣는 자리에도 있다 — 문서 리스너 쪽을 집는다.
    at = DOCK_JS.index("document.addEventListener(name, function (event) {")
    window = DOCK_JS[at - 400:at + 400]
    assert 'data-erp="deposit_amount"' in window, "예약금 입력을 듣지 않는다"
    assert "syncDepositMatch()" in window


def test_the_deposit_chip_still_carries_no_autofill_target():
    """음성 대조군 — 대조를 붙였다고 **돈이 자동으로 들어가지는 않는다**.

    2026-09-08 확정 결정이다. 대조 줄은 읽기만 한다.
    """
    at = DOCK_JS.index("function buildDepositCard")
    body = DOCK_JS[at:at + 1600]

    # 주석은 "달지 않는다" 고 적혀 있다 — 실제로 다는 자리(`setAttribute`)만 본다.
    assert "setAttribute('data-naver-dock-target'" not in body, (
        "예약금 칩에 자동 입력 칸 이름이 붙었다")
    assert "naver-dock-deposit-state" in body, "대조 줄이 카드에 없다"
