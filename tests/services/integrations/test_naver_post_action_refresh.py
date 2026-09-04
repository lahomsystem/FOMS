"""조작이 끝나도 화면은 **다시 읽기까지** 기다린다 (2026-09-04 사용자 제보).

사용자 제보: "반품 접수를 하면 바로 반품 승인으로 바뀌는 게 아니라 페이지 새로고침을
해야 버튼이 바뀐다."

원인은 서버가 아니라 화면이다. 워커 잡은 두 번에 나눠 일한다:

1. `fulfillment.request_return` 이 우리 표식(`triage_state['return']`)만 쓰고 커밋한다 —
   이때 `_fulfillment_state` 지문(`rev`)이 **1차로** 바뀐다.
2. `jobs.tasks._enqueue_refresh_after` 가 **별도 잡**으로 자동 다시 읽기를 큐에 넣는다.
   그 잡이 `raw_snapshot` 을 갈아 끼우면 지문이 **2차로** 바뀐다.

승인 버튼의 술어 `fulfillment.is_return_approvable` 은 우리 표식이 아니라 **스냅샷의
클레임 상태**를 본다. 그래서 화면이 1차 변경만 보고 손을 떼면 승인 버튼이 없는 화면에서
멈춘다 — 사람이 새로고침해야 나타났다.

이 파일이 못박는 계약:

* 상태 API 가 `sync_at`(집 안 가장 최근 다시 읽기 시각)을 **밖으로** 낸다.
  지문 안에만 있으면 화면이 "어느 축이 바뀌었나"를 구분하지 못한다.
* 조작 라우트 전부가 **누르기 직전의** `sync_at` 을 응답에 싣는다(`err_at` 과 같은 규율).
* 화면은 조작 표식(`rev`)을 본 뒤 `sync_at` 이 갱신될 때까지 한 박자 더 본다.
* 그 두 번째 기다림에는 **자기 창**이 있다 — 워커가 1대라 재읽기 잡이 다른 잡 뒤에 선다.
"""

from __future__ import annotations

import pathlib

JS = pathlib.Path("static/js/admin/naver-workbench.js").read_text(encoding="utf-8")
ROUTES = pathlib.Path("foms/web/admin/naver_ingest.py").read_text(encoding="utf-8")
TASKS = pathlib.Path("foms/services/jobs/tasks.py").read_text(encoding="utf-8")
WORKBENCH = pathlib.Path("templates/admin/naver_workbench.html").read_text(encoding="utf-8")

#: 결과를 지켜보는 일곱 갈래 — 전부 같은 규칙을 쓴다.
WATCH_CALLERS = ("submitConfirm", "submitDispatch", "submitCancel", "submitReturn",
                 "submitReturnReject", "submitClaimApprove", "submitRefresh")


def test_state_api_exposes_the_sync_time():
    """`sync_at` 이 지문 밖으로 나온다 — 화면이 재읽기 완료를 따로 판정해야 한다."""
    assert '"sync_at": sync_at,' in ROUTES, "상태 API 가 sync_at 을 안 낸다"
    # 집 안 **최댓값**이어야 한다. 형제 하나만 읽혀도 갱신으로 치면 이르게 손을 뗀다.
    assert "if at_sync > sync_at:" in ROUTES


def test_every_watch_caller_passes_the_base_sync_time():
    """일곱 갈래 전부 `sync_at` 을 넘긴다 — 한 갈래만 고치면 나머지가 옛 동작으로 남는다."""
    for name in WATCH_CALLERS:
        needle = f"async function {name}("
        assert needle in JS, f"{name} 이 사라졌다(이름이 바뀌었나)"
        body = JS.split(needle)[1].split("async function")[0]
        assert "watchFulfillment(" in body, name
        assert "result.data && result.data.sync_at" in body, f"{name} 이 sync_at 을 안 넘긴다"


def test_routes_ship_the_base_sync_time():
    """조작 라우트는 누르기 직전의 `sync_at` 을 싣는다(`err_at` 과 같은 두 축)."""
    # 조작 5곳은 변수로, 다시 읽기 1곳은 직접 읽어 싣는다.
    assert ROUTES.count('"sync_at": base_sync_at') == 5
    assert '"sync_at": base_state.get("sync_at", "")' in ROUTES
    assert ROUTES.count('base_sync_at = base_state.get("sync_at", "")') == 5


def test_the_watcher_waits_for_the_follow_up_refresh():
    """1차 변경에서 끝내지 않는다 — `sync_at` 이 갱신될 때까지 한 박자 더 본다."""
    assert "function watchFulfillment(linkId, baseRev, label, baseErrorAt, baseSyncAt)" in JS
    assert "var POST_REFRESH_TIMEOUT_MS" in JS
    assert "deadline = Date.now() + POST_REFRESH_TIMEOUT_MS;" in JS
    # 두 단계를 가르는 표식이 있어야 한다(1차를 본 뒤에만 2차를 기다린다).
    assert "sawAction = true;" in JS
    assert "} else if (sawAction && synced(state)) {" in JS


def test_the_watcher_stops_when_the_action_itself_is_the_refresh():
    """`다시 읽기` 처럼 조작 자체가 스냅샷을 갈아 끼우면 두 번 기다리지 않는다."""
    body = JS.split("function watchFulfillment(")[1].split("\n    /**")[0]
    assert "if (synced(state)) {" in body, "재읽기 갈래를 가르는 조건이 없다"


def test_a_failed_action_does_not_wait_for_a_refresh_that_never_comes():
    """실패한 조작에는 이어질 상태 변화가 없다 — 거기서 접는다(빈 기다림 금지)."""
    body = JS.split("function watchFulfillment(")[1].split("\n    /**")[0]
    failed = body.split("if (freshError) {")[1].split("}")[0]
    assert "stopWatch();" in failed, "실패인데 두 번째 기다림으로 넘어간다"


def test_the_timeout_message_does_not_deny_a_finished_action():
    """조작은 성공했는데 스냅샷만 늦은 경우, '결과가 안 왔다'고 말하지 않는다."""
    assert "최신 상태 반영이 늦어지고 있습니다" in JS
    body = JS.split("function watchFulfillment(")[1].split("\n    /**")[0]
    assert "if (sawAction) {" in body


def test_the_follow_up_refresh_covers_every_action():
    """자동 다시 읽기 대상이 일곱 갈래 전부다 — 화면 기다림과 서버 예약이 같아야 한다."""
    block = TASKS.split("REFRESH_AFTER_ACTIONS = ")[1].split(")")[0]
    for action in ("confirm", "dispatch", "cancel", "return", "return-reject",
                   "cancel-approve", "return-approve"):
        assert f'"{action}"' in block, f"{action} 이 자동 다시 읽기 대상에서 빠졌다"


def test_the_asset_pin_moved():
    """JS 를 고쳤으면 핀을 올린다 — 서비스워커 캐시가 옛 파일을 준다."""
    assert WORKBENCH.count("?v=20260904d") == 2, "CSS·JS 핀을 함께 올린다"
