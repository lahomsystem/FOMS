"""재결제 후속 프로세스 — 정리 뒤 남은 일과 예약금 대조 (2026-09-09).

**왜 생겼나.** 담당자 보고: "네이버 반품 요청 승인 → 이후 재결제에 대한 후속 프로세스
없음, 반품 완료 및 재결제에 대한 안내 없음". 화면을 읽어 보니 끊긴 자리가 셋이었다.

1. **정리 실행 성공 화면에 옛 결제를 환불하라는 말이 없었다.** 그 지시는 실행 **전**
   계획 카드 i 칸에만 있었다. 성공 화면(``.wb-plan__done``)은 예약금과 주문 링크만
   말한다 — 담당자가 그 화면을 읽고 닫으면 환불이 통째로 남는다. 재결제는 돈이 두 번
   움직이는 건인데(옛 결제 환불 + 새 결제 수령) 화면이 그 둘을 한자리에서 세지 않았다.
2. **두 문구가 서로 반대 순서를 말했다.** 계획 카드는 "정리한 뒤 옛 주문을 반품하세요",
   승인 결과는 "확정이 돌아오면 **정리 실행이 열립니다**". 카드 지시대로 정리를 먼저 한
   담당자에게 뒤엣말은 뜻이 없다 — 이미 열렸고 이미 눌렀다.
3. **예약금을 안 넣어도 아무도 몰랐다.** 돈을 시스템이 넣지 않는 것은 확정된 결정이다.
   문제는 안 넣었을 때 조용하다는 것이다 — 실사례로 예약금이 옛 값 1,093,100원으로
   남으면 잔금(``출고가 − 예약금``)이 4,650원 틀린다.

이 파일은 1·2 를 못박는다(3 은 화면 함수라
:mod:`tests.services.integrations.test_naver_dock_deposit_match` 가 Node 로 돌린다).
판정 축(``run_gate``·``discard_policy``·``can_discard``)은 한 글자도 보지 않는다 —
전부 **표시 축**이다.
"""

from __future__ import annotations

import pathlib
import re

WORKBENCH_JS = pathlib.Path("static/js/admin/naver-workbench.js").read_text(encoding="utf-8")
INGEST_PY = pathlib.Path("foms/web/admin/naver_ingest.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 1. 정리 성공 화면이 남은 일을 센다
# --------------------------------------------------------------------------- #

def test_reconcile_response_carries_the_living_old_payments():
    """``/reconcile`` 응답이 **살아 있는 옛 결제**를 함께 낸다.

    이 값이 없으면 성공 화면은 환불할 것이 있는지조차 모른다. 후보가 이미 세어 둔 값을
    그대로 실어 보낸다 — 여기서 다시 세면 실행 전 카드와 실행 후 화면의 숫자가 갈린다.
    """
    assert '"origin_alive"' in INGEST_PY, "정리 응답에 살아 있는 옛 결제가 없다"
    assert 'candidate.get("naver_alive_rows")' in INGEST_PY, (
        "옛 결제를 후보 값에서 가져오지 않고 다시 세고 있다")


def test_discard_fork_carries_no_leftover_old_payment():
    """취소 처리(휴지통) 갈래는 옛 결제 목록을 내지 않는다.

    그 갈래는 ERP 주문 자체가 휴지통으로 간다 — 남은 일 목록을 띄우면 사라진 주문에
    대해 뭔가 하라고 말하는 셈이다. 예약금 안내가 승계일 때만 붙는 것과 같은 규칙이다.
    """
    at = INGEST_PY.index('"origin_alive"')
    window = INGEST_PY[at:at + 260]
    assert 'result["fork"] == "SUCCEED"' in window, "취소 처리 갈래에도 남은 일이 실린다"


def test_success_screen_lists_the_refund_and_the_deposit_together():
    """성공 화면이 **환불**과 **예약금**을 한 목록으로 센다.

    둘 중 하나만 말하면 나머지 하나가 조용히 남는다. 이 프로젝트가 이미 겪은 실패다.
    """
    at = WORKBENCH_JS.index("function showPlanResult")
    body = WORKBENCH_JS[at:at + 3000]

    assert "var todos = []" in body, "남은 일을 세는 자리가 없다"
    assert "Array.isArray(data.origin_alive) && data.origin_alive.length" in body, (
        "옛 결제가 있을 때만 환불을 남은 일에 올리는 갈래가 없다")
    assert "originAliveText" in body, "옛 결제를 사람이 읽는 줄로 만들지 않는다"
    assert "'남은 일 '" in body, "몇 개 남았는지 말하지 않는다"
    assert "예약금을 " in body, "예약금이 남은 일에 없다"
    # 목록은 순서가 있는 일이다 — 환불이 먼저고 예약금이 뒤다(돈이 나가야 금액이 굳는다).
    assert body.index("data.origin_alive") < body.index("예약금을 ")


def test_old_payment_line_shows_the_order_number_count_and_money():
    """옛 결제 한 줄은 **주문번호·건수·금액** 셋을 다 말한다.

    금액이 빠지면 담당자가 얼마를 환불하는지 모른 채 승인 버튼으로 간다. 불가역 경로다.
    """
    at = WORKBENCH_JS.index("function originAliveText")
    body = WORKBENCH_JS[at:at + 700]

    assert "external_order_no" in body
    assert "product_order_count" in body
    assert "amount_total" in body
    assert "toLocaleString('ko-KR')" in body, "금액에 쉼표가 없다 — 자릿수를 잘못 읽는다"


# --------------------------------------------------------------------------- #
# 2. 승인 문구가 순서를 전제하지 않는다
# --------------------------------------------------------------------------- #

def test_approve_result_does_not_promise_that_reconcile_will_open():
    """승인 결과가 `정리 실행이 열립니다` 라고 말하지 않는다.

    계획 카드는 **정리를 먼저** 하라고 말한다. 그 지시를 따른 담당자에게 이 문장은
    뜻이 없다 — 정리는 이미 끝났다. 화면이 자기 자신과 모순되면 담당자는 둘 중 어느
    쪽이 맞는지 확인하러 판매자센터를 연다.
    """
    at = WORKBENCH_JS.index("function submitPlanClaimApprove")
    body = WORKBENCH_JS[at:at + 2400]
    # 주석은 옛 문장을 근거로 인용한다 — 화면에 나가는 것은 `doneText:` 줄뿐이다.
    done_line = [line for line in body.splitlines() if "doneText:" in line]

    assert len(done_line) == 1, "승인 결과 문장이 한 자리가 아니다"
    assert "정리 실행이 열립니다" not in done_line[0], "승인 문구가 순서를 거꾸로 전제한다"
    assert "네이버가 확정하면" in done_line[0], "확정을 기다린다는 사실이 사라졌다"


def test_approve_result_says_which_action_it_sent():
    """`취소 승인` 인지 `반품 승인` 인지 결과 문장이 스스로 말한다.

    같은 집에 취소·반품 버튼이 나란히 설 수 있다(``data-kind`` 로 가른다). 결과 문장이
    낱말을 안 들면 담당자가 어느 버튼의 결과인지 모른다.
    """
    at = WORKBENCH_JS.index("function submitPlanClaimApprove")
    body = WORKBENCH_JS[at:at + 1800]

    assert re.search(r"doneText:\s*label \+ ' 보냄", body), (
        "결과 문장이 취소/반품 낱말을 들지 않는다")


# --------------------------------------------------------------------------- #
# 3. 자산 핀 — 화면 JS·CSS 가 함께 움직였다
# --------------------------------------------------------------------------- #

def test_workbench_asset_pin_moved_for_the_followup_change():
    """서비스워커가 옛 JS 를 주지 않도록 CSS·JS 핀이 **함께** 올라갔다."""
    markup = pathlib.Path("templates/admin/naver_workbench.html").read_text(encoding="utf-8")

    assert markup.count("?v=20260909a") == 2, "CSS·JS 핀을 함께 올린다"
