"""조작 결과 폴링은 **이번 조작의 실패**만 말한다 (2026-09-04 사용자 2차 신고).

`last_error` 는 명시적으로 지울 때까지 남는 값이다. 그래서 폴링이 "실패가 있다"만 보고
말하면, 옛 실패가 남아 있는 집에서는 **이번 조작이 성공해도** 화면이 실패를 다시 말한다.
운영에서 취소 승인이 성공한 직후 "네이버 취소 실패: 주문상태 확인 필요"가 그대로 떴다.

이 함정은 2026-08-26(CEO 리뷰 B3)에 한 번 발견돼 `다시 읽기` **한 갈래만** 고쳐졌고,
나머지는 `baseErrorAt === undefined` 폴백으로 옛 동작이 남아 있었다. 이번 사고는 그 유예의
청구서다 — 여기서 여섯 갈래 전부를 못박는다.

* 라우트는 **누르기 직전의 실패 시각**(`err_at`)을 응답에 싣는다.
* 화면은 그 값과 비교해 **시각이 달라졌을 때만** 실패로 말한다.
* 폴백(`=== undefined`)은 없다 — 폴백이 있으면 새 호출자가 조용히 옛 동작으로 떨어진다.
"""

from __future__ import annotations

import pathlib

JS = pathlib.Path("static/js/admin/naver-workbench.js").read_text(encoding="utf-8")
ROUTES = pathlib.Path("foms/web/admin/naver_ingest.py").read_text(encoding="utf-8")
WORKBENCH = pathlib.Path("templates/admin/naver_workbench.html").read_text(encoding="utf-8")

#: 결과를 지켜보는 여섯 갈래(+다시 읽기) — 전부 같은 규칙을 쓴다.
WATCH_CALLERS = ("submitConfirm", "submitDispatch", "submitCancel", "submitReturn",
                 "submitReturnReject", "submitClaimApprove", "submitRefresh")

#: pane 밖(띠·정리 계획 카드)에서 쏘는 세 갈래 — :func:`watchOriginAct` 를 쓴다.
#: pane 갈래와 **같은 결함이 그대로 남아 있었다**(CEO FIX 2026-09-07): 축이 다른 옛
#: 실패(발송처리 등)가 `last_error` 에 남아 있으면 — `_clear_settled_failures` 는
#: **같은 축만** 지운다 — 환불이 **성공했는데** 버튼이 "취소 승인 실패"라고 말했다.
ORIGIN_WATCH_CALLERS = ("submitOriginCancel", "submitOriginReturn",
                        "submitPlanClaimApprove")


def test_every_watch_caller_passes_the_base_error_time():
    """여섯 갈래 전부 `err_at` 을 넘긴다 — 한 갈래만 고치면 나머지가 거짓말한다."""
    for name in WATCH_CALLERS:
        # 이름 접두사가 겹치는 함수가 있다(`submitRefresh` vs `submitRefreshAll`) —
        # 여는 괄호까지 붙여 잘라야 엉뚱한 함수 몸통을 재게 되지 않는다.
        needle = f"async function {name}("
        assert needle in JS, f"{name} 이 사라졌다(이름이 바뀌었나)"
        body = JS.split(needle)[1].split("async function")[0]
        assert "watchFulfillment(" in body, name
        assert "result.data && result.data.err_at" in body, f"{name} 이 err_at 를 안 넘긴다"


def test_every_origin_watch_caller_passes_the_base_error_time():
    """띠·정리 계획 카드의 세 갈래도 `err_at` 을 넘긴다 — pane 갈래와 같은 규칙이다.

    한 갈래만 고치면 나머지가 거짓말한다는 것은 2026-09-04 에 이미 청구서를 받은 교훈인데,
    `watchOriginAct` 쪽은 그때 함께 고쳐지지 않았다.
    """
    for name in ORIGIN_WATCH_CALLERS:
        needle = f"async function {name}("
        assert needle in JS, f"{name} 이 사라졌다(이름이 바뀌었나)"
        body = JS.split(needle)[1].split("async function")[0]
        assert "watchOriginAct(" in body, name
        assert "errAt: result.data && result.data.err_at" in body,             f"{name} 이 err_at 기준선을 안 넘긴다 — 옛 실패를 이번 실패로 말한다"


def test_origin_watch_compares_against_the_base_error_time():
    """`watchOriginAct` 는 실패 **시각**을 견준다 — "실패가 있다"만 보고 말하지 않는다."""
    assert "state.last_error_at !== baseErrAt" in JS
    # 실패 표시(글자·빨간 표식)가 둘 다 그 판정을 쓴다 — 한쪽만 고치면 글자는 성공인데
    # 버튼만 빨갛게 남는다.
    assert "btn.classList.toggle('wb-origin-act--err', !!freshError)" in JS


def test_the_plan_approve_done_text_does_not_promise_an_open_gate():
    """승인 완료 문장이 `정리 실행` 이 **이미 열렸다**고 단정하지 않는다.

    폴링이 보는 것은 승인 표식이 뒤집힌 순간이고, 잠금을 여는 것은 그 뒤의 스냅샷
    재조회(`_enqueue_refresh_after` → 집계 `all_done` → `run_gate`)다. 그 사이를
    "열립니다"로 단정하면 새로고침한 사람이 여전히 잠긴 버튼을 본다.
    """
    # 2026-09-07: 완료 뒤 화면이 스스로 다시 그리게 되면서 문장이 바뀌었다.
    # 2026-09-09: **정리 실행을 아예 입에 담지 않는다**. 계획 카드는 "정리한 뒤 옛 주문을
    # 반품하세요" 라고 말하는데, 그 지시를 따른 담당자에게 "정리 실행이 열립니다" 는 뜻이
    # 없는 말이다(이미 열렸고 이미 눌렀다). 두 문구가 서로 반대 순서를 전제하면 담당자는
    # 어느 쪽이 맞는지 확인하러 판매자센터를 연다. **단정 금지 규칙은 그대로다.**
    assert "네이버가 확정하면 화면 상태가 바뀝니다" in JS
    assert "정리 실행이 열립니다" not in _plan_approve_done_line(), (
        "승인 완료 문장이 다시 순서를 전제한다")
    assert "완료 — 새로고침하면 정리 실행이 열립니다" not in JS
    assert "정리 실행이 열렸습니다" not in JS


def _plan_approve_done_line() -> str:
    """승인 완료 문장 한 줄 — 주석이 옛 문장을 인용하므로 `doneText:` 줄만 집는다."""
    at = JS.index("function submitPlanClaimApprove")
    body = JS[at:at + 2400]
    lines = [line for line in body.splitlines() if "doneText:" in line]
    assert len(lines) == 1, "승인 결과 문장이 한 자리가 아니다"
    return lines[0]


def test_the_undefined_fallback_is_gone():
    """폴백이 남아 있으면 새 호출자가 조용히 옛 동작으로 떨어진다."""
    assert "baseErrorAt === undefined" not in JS
    assert "state.last_error_at !== (baseErrorAt || '')" in JS


def test_routes_ship_the_base_error_time():
    """rev 를 싣는 조작 라우트는 err_at 도 함께 싣는다(둘은 같은 판정의 두 축이다)."""
    # 다시 읽기 1곳(옛 구현) + 조작 5곳(2026-09-04 신설).
    assert ROUTES.count('"err_at": base_err_at') == 5
    assert '"err_at": base_state["last_error_at"]' in ROUTES


def test_the_cancel_failure_note_points_at_the_approve_button():
    """실패 안내가 승인 기능 이전 문장에 머물지 않는다 — 같은 화면의 버튼을 가리킨다."""
    assert "네이버 취소 승인" in WORKBENCH
    assert "고객이 먼저 취소를 요청한 주문" in WORKBENCH


def test_the_asset_pin_moved():
    """JS 를 고쳤으면 핀을 올린다 — 서비스워커 캐시가 옛 파일을 준다."""
    assert WORKBENCH.count("?v=20260910a") == 2, "CSS·JS 핀을 함께 올린다"
