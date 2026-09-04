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
    assert WORKBENCH.count("?v=20260904a") == 2, "CSS·JS 핀을 함께 올린다"
