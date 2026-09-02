"""불가역 3종의 **결과가 화면에 닿는지** 회귀 테스트 (2026-08-24).

스펙 `docs/specs/2026-08-24-naver-workbench-async-result_SPEC.md`.

web 라우트는 큐에 넣고 바로 답한다(네이버 HTTP 는 WORKER 단일 출구). 그래서 버튼을 누른
직후의 화면은 아직 옛 상태다 — 사용자에게는 "눌러도 아무 일이 없다"로 보였다. 화면이
언제 뒤집혔는지 물어볼 자리(``fulfillment-state``)와 그 기준점(``rev``)을 여기서 잰다.

**판정을 두 벌로 만들지 않는 것**이 이 파일의 핵심 단언이다 — 새 경로가 ``can_confirm``
같은 화면 판정을 다시 구현하면 모달이 재진술하는 건수와 서버가 처리할 건수가 갈린다
(v3 리뷰 H1).
"""

from __future__ import annotations

import pathlib

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from models import ExternalOrderLink

from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _collected,
    _login,
    _uid,
    workbench_on,
)
from tests.services.integrations.test_naver_workbench_v3_followup import _order, _sibling

STATE_PATH = "/admin/naver-ingest/triage/fulfillment-state"
PROGRESS_PATH = "/admin/naver-ingest/triage/fulfillment-progress"

JS_PATH = pathlib.Path("static/js/admin/naver-workbench.js")
TEMPLATE_PATH = pathlib.Path("templates/admin/naver_workbench.html")
CSS_PATH = pathlib.Path("static/css/admin/naver-workbench.css")


def _mark(link_id: int, **fields) -> None:
    """워커가 남기는 처리 표식을 그대로 써 넣는다(JSONB 수정 패턴).

    **id 로 다시 읽는다** — 요청이 한 번 지나가면 스코프 세션이 정리돼 앞서 들고 있던
    ORM 객체는 detached 다(그 상태로 만지면 DetachedInstanceError).
    """
    link = db_session.get(ExternalOrderLink, int(link_id))
    state = dict(link.triage_state or {})
    state["fulfillment"] = dict(state.get("fulfillment") or {}, **fields)
    link.triage_state = state
    flag_modified(link, "triage_state")
    db_session.commit()


def _state(client, link_id: int):
    return client.get(f"{STATE_PATH}?link_id={link_id}").get_json()["data"]


# --------------------------------------------------------------------------- #
# 경로 자체 — 게이트·입력
# --------------------------------------------------------------------------- #

def test_state_route_is_hidden_when_gate_is_off(client):
    """게이트 OFF 화면에는 이 경로가 없다 — 롤백 경로를 우회하는 문을 열지 않는다."""
    _login(client)
    link = _collected(order_no=f"N-ST-OFF-{_uid()}", product="붙박이장", amount=100000)

    assert client.get(f"{STATE_PATH}?link_id={link.id}").status_code == 404


def test_state_route_needs_a_link_id(client, workbench_on):
    """무엇을 물어보는지 없으면 400 — 조용히 아무 집이나 답하지 않는다."""
    _login(client)

    assert client.get(STATE_PATH).status_code == 400


def test_state_route_404_for_unknown_link(client, workbench_on):
    """없는 링크는 404 다. 빈 성공으로 답하면 화면이 영원히 폴링한다."""
    _login(client)

    assert client.get(f"{STATE_PATH}?link_id=99999999").status_code == 404


# --------------------------------------------------------------------------- #
# 모집단 — 집 전체를 센다
# --------------------------------------------------------------------------- #

def test_state_counts_the_whole_household_not_one_link(client, workbench_on):
    """집 정의는 pane·모달과 **같다**(주문번호 + 묶음키).

    형제를 빼먹으면 부분 성공을 "끝났다"로 읽고 화면이 먼저 뒤집힌다.
    """
    _login(client)
    lead = _collected(order_no=f"N-ST-HH-{_uid()}", product="붙박이장", amount=300000)
    lead_id = lead.id
    _mark(_sibling(lead, product="서랍 옵션", amount=20000).id,
          place_confirmed_at="2026-08-24T01:00:00")

    data = _state(client, lead_id)

    assert data["total"] == 2, "형제까지 세야 한다"
    assert data["confirmed"] == 1
    assert data["dispatched"] == 0 and data["canceled"] == 0


def test_state_carries_no_screen_judgement(client, workbench_on):
    """폴링 경로는 **판정하지 않는다** — 무엇을 눌러도 되는지는 pane 이 혼자 정한다.

    여기서 `can_*` 를 만들면 판정이 두 벌이 되고, 그 갈라짐이 v3 리뷰 H1 이었다.
    """
    _login(client)
    lead = _collected(order_no=f"N-ST-JUDGE-{_uid()}", product="붙박이장", amount=100000)

    data = _state(client, lead.id)

    assert not [key for key in data if key.startswith("can_")], data
    # `returned` 는 판정이 아니라 **워커가 쓴 표식의 수**다(T8-S1 반품 접수) —
    # `confirmed`·`dispatched`·`canceled` 와 같은 층이다. 화면 판정(can_*)은 여전히 0개.
    assert set(data) == {"link_id", "total", "confirmed", "dispatched", "canceled",
                         "returned", "last_error", "last_error_at", "last_error_action",
                         "action_label", "rev"}


# --------------------------------------------------------------------------- #
# rev — 뒤집힘 신호
# --------------------------------------------------------------------------- #

def test_rev_is_stable_while_nothing_changes(client, workbench_on):
    """가만히 있으면 지문도 그대로여야 한다 — 아니면 폴링이 첫 회차에 거짓 완료한다."""
    _login(client)
    lead = _collected(order_no=f"N-ST-STABLE-{_uid()}", product="붙박이장", amount=100000)

    assert _state(client, lead.id)["rev"] == _state(client, lead.id)["rev"]


def test_rev_changes_when_the_worker_marks_success(client, workbench_on):
    """성공 표식이 찍히면 지문이 바뀐다 — 이게 화면을 다시 그리는 신호다."""
    _login(client)
    lead_id = _collected(order_no=f"N-ST-OK-{_uid()}", product="붙박이장", amount=100000).id
    before = _state(client, lead_id)["rev"]

    _mark(lead_id, place_confirmed_at="2026-08-24T02:00:00")

    assert _state(client, lead_id)["rev"] != before


def test_rev_changes_and_reason_surfaces_when_the_worker_fails(client, workbench_on):
    """실패도 **같은 신호**로 잡힌다. 사유가 응답에 실려야 새로고침 없이 화면에 뜬다."""
    _login(client)
    lead_id = _collected(order_no=f"N-ST-ERR-{_uid()}", product="붙박이장", amount=100000).id
    before = _state(client, lead_id)["rev"]

    _mark(lead_id, last_error="발주확인이 먼저입니다.", last_error_at="2026-08-24T03:00:00",
          last_error_action="dispatch")

    data = _state(client, lead_id)
    assert data["rev"] != before
    assert data["last_error"] == "발주확인이 먼저입니다."
    assert data["action_label"] == "발송처리", "사람이 읽는 이름은 실패 띠와 같은 표를 쓴다"


def test_rev_changes_when_a_sibling_moves(client, workbench_on):
    """형제 하나만 처리돼도 지문이 바뀐다 — 발송처리는 건별로 성공/실패한다."""
    _login(client)
    lead = _collected(order_no=f"N-ST-SIB-{_uid()}", product="붙박이장", amount=300000)
    lead_id = lead.id
    sibling_id = _sibling(lead, product="서랍 옵션", amount=20000).id
    before = _state(client, lead_id)["rev"]

    _mark(sibling_id, dispatched_at="2026-08-24T04:00:00")

    assert _state(client, lead_id)["rev"] != before


# --------------------------------------------------------------------------- #
# 기준점은 enqueue **직전**에 잡힌다 (설계 D4)
# --------------------------------------------------------------------------- #

def test_fulfillment_route_returns_the_rev_from_before_enqueue(client, workbench_on,
                                                               monkeypatch):
    """POST 응답의 ``rev`` 는 **큐에 넣기 전** 지문이어야 한다.

    뒤에서 잡으면 워커가 이미 끝냈을 때 화면이 뒤집힘을 영원히 못 보고 타임아웃 문구로
    접힌다. 여기서는 enqueue 가 곧바로 처리를 끝내는 최악의 타이밍을 흉내 낸다 —
    그래도 응답 지문은 **처리 전** 값이어야 폴링이 변화를 본다.
    """
    _login(client)
    lead_id = _collected(order_no=f"N-ST-PRE-{_uid()}", product="붙박이장", amount=100000).id

    def _instant_worker(link_id, action, actor_user_id=None):
        _mark(lead_id, place_confirmed_at="2026-08-24T05:00:00")
        return True

    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_fulfillment",
                        _instant_worker)

    response = client.post(f"/admin/naver-ingest/{lead_id}/fulfillment",
                           json={"action": "confirm"})

    assert response.status_code == 200
    returned = response.get_json()["data"]["rev"]
    assert returned, "폴링 기준점이 없으면 화면이 영원히 옛 상태를 본다"
    assert returned != _state(client, lead_id)["rev"], "처리 뒤 값을 돌려주면 안 된다"


def test_cancel_route_returns_a_rev(client, workbench_on, monkeypatch):
    """취소도 같은 신호를 쓴다(작업마다 다른 규칙을 만들지 않는다)."""
    _login(client)
    lead = _collected(order_no=f"N-ST-CAN-{_uid()}", product="붙박이장", amount=100000)
    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_cancel",
                        lambda *a, **k: True)

    response = client.post(f"/admin/naver-ingest/{lead.id}/cancel",
                           json={"reason": "PRODUCT_UNSATISFIED"})

    assert response.status_code == 200
    assert response.get_json()["data"]["rev"]


# --------------------------------------------------------------------------- #
# 화면 계약 — 폴링은 끝이 있고, 벌크는 폴링하지 않는다
# --------------------------------------------------------------------------- #

def test_polling_has_a_deadline_and_race_guards():
    """무한 폴링 금지. 마감과 경합 차단 2종이 소스에 있어야 한다."""
    source = JS_PATH.read_text(encoding="utf-8")

    assert "POLL_TIMEOUT_MS" in source and "POLL_INTERVAL_MS" in source
    assert "Date.now() >= deadline" in source, "마감 없이 도는 폴링을 만들지 않는다"
    assert "mine !== pollToken || paneAt !== paneToken" in source, (
        "늦게 온 폴링이 새 조작·새 선택을 덮으면 화면과 조작 대상이 갈린다")
    assert "while (true)" not in source and "while(true)" not in source


def test_bulk_and_retry_never_poll_per_household():
    """벌크·재시도는 **집마다** 폴링하지 않는다 — 조회가 집 수만큼 곱해진다.

    nav 뱃지 부하 실측(2026-08-24: 게이트 ON 콜드 113ms)이 이 화면의 조회 비용을 이미
    보여줬다. 벌크는 묶음키로 한 번에 걷는 진행 조회(집 수와 무관하게 회차당 2회)를 쓰고,
    재시도는 아예 폴링하지 않는다.
    """
    source = JS_PATH.read_text(encoding="utf-8")
    bulk = source.split("async function submitBulk")[1].split("    /**")[0]
    retry = source.split("async function submitRetry")[1].split("    /**")[0]

    assert "watchFulfillment" not in bulk, "벌크가 단건 폴링을 집마다 부르면 안 된다"
    assert "watchBulk(ids" in bulk, "벌크는 묶음 진행 조회를 쓴다"

    assert "watchFulfillment" not in retry and "watchBulk" not in retry
    assert "BULK_REFRESH_MS" in retry, "재시도는 한 번만 늦게 갱신한다"


def test_bulk_progress_is_batched_and_bounded():
    """벌크 진행 조회는 **한 번에** 묻고, 폴링에는 마감이 있다."""
    source = JS_PATH.read_text(encoding="utf-8")
    watch = source.split("function watchBulk")[1].split("function stopBulkWatch")[0]

    assert "readBulkProgress(ids)" in watch, "집 목록을 한 번에 넘긴다"
    assert "Date.now() >= deadline" in watch, "마감 없이 도는 폴링을 만들지 않는다"
    assert "mine !== bulkToken" in watch, "새 벌크가 앞 폴링을 끊어야 한다"

    reader = source.split("async function readBulkProgress")[1].split("    /**")[0]
    assert "ids.join(',')" in reader, "집마다 요청을 내지 않는다"


def test_single_actions_wait_for_the_worker():
    """단건 3종은 모두 결과를 기다렸다가 그린다 — 즉시 reload 로 되돌아가지 않게."""
    source = JS_PATH.read_text(encoding="utf-8")

    for name, label in (("submitConfirm", "발주확인"), ("submitDispatch", "발송처리"),
                        ("submitCancel", "취소")):
        body = source.split(f"async function {name}")[1].split("async function")[0]
        assert f"watchFulfillment(id, result.data && result.data.rev, '{label}')" in body
        assert "window.location.reload()" not in body, (
            f"{name} 이 즉시 새로고침하면 워커 전 화면을 다시 그린다")


def test_soft_refresh_replaces_the_whole_workbench_root():
    """pane 만 갈면 왼쪽 목록 배지·칩 숫자가 낡아 한 화면이 두 말을 한다."""
    source = JS_PATH.read_text(encoding="utf-8")
    body = source.split("async function softRefresh")[1].split("    /* ──")[0]

    assert "querySelector('.naver-workbench')" in body
    assert "current.replaceWith(next)" in body
    assert "applyFontScale(readFontScale())" in body, "글자 배율은 교체로 잃는다"
    assert "syncBulk()" in body


def test_soft_refresh_keeps_the_find_word_and_the_scroll_place(): # noqa: E501
    """교체로 잃는 것 둘을 더 되돌린다 — 찾기 낱말과 훑던 자리 (2026-08-26).

    서버는 사용자가 무엇을 쳤는지 모르므로 전체 렌더가 찾기 칸을 늘 빈 채로 준다. 그리고
    집 하나가 큐에서 빠지면 문서가 짧아져 브라우저가 스크롤을 위로 당긴다. 둘을 안 되돌리면
    큐를 위에서부터 훑는 손이 한 집을 처리할 때마다 맨 위에서 다시 찾아야 한다 —
    **통째 이동을 없앤 값어치가 바로 이 둘이다.**
    """
    source = JS_PATH.read_text(encoding="utf-8")
    body = source.split("async function softRefresh")[1].split("    /* ──")[0]

    assert "captureFind()" in body, "교체 직전에 찾기 상태를 떠야 한다"
    assert "restoreFind(" in body, "새 칸에 다시 심어야 한다"
    assert "window.scrollTo(" in body, "줄어든 문서가 스크롤을 위로 당긴다"

    restore = source.split("function restoreFind")[1].split("    function ")[0]
    assert "applyFind(" in restore, (
        "값만 옮기고 다시 좁히지 않으면 칸에는 낱말이 남았는데 전체 목록이 보인다")


def test_history_find_is_left_to_the_server(client, workbench_on):
    """이력 탭 찾기는 **화면이 좁히지 않는다** (2026-09-02).

    원래는 두 탭이 같은 화면 필터를 썼다. 이력 표는 서버가 50집씩 잘라 주므로 그 필터가
    닿는 데는 지금 쪽뿐이었고, 800주문·16쪽짜리 운영 화면에서 고객명을 쳤을 때
    "0주문 / 이 페이지 50주문" 이 나왔다(사용자 실화면 보고).

    화면 필터를 남긴 채 서버 검색을 얹으면 더 나쁘다 — 서버가 준 결과 위에 한 겹이 더
    얹혀, note 가 말하는 숫자와 보이는 줄이 갈린다. 그래서 ``onInput`` 이 이력 탭을
    **먼저 걸러낸다**. 처리 탭 필터는 그대로다(목록이 한 번에 다 와 있다).
    """
    _login(client)
    source = JS_PATH.read_text(encoding="utf-8")
    body = source.split("function applyFind")[1].split("    function ")[0]

    assert "#wb-queue a.wb-row" in body, "처리 탭 모집단을 잃으면 안 된다"
    assert "wb-find-note" in body, "좁힌 결과를 말할 자리에 써야 한다"

    machinery = source.split("function onInput")[1].split("function applyFind")[0]
    assert "isHistoryTab()" in machinery, "이력 탭에서 화면 필터가 먼저 빠져나가야 한다"
    assert "이 페이지" not in source, (
        "'이 페이지' 범위 고지는 서버가 전체를 찾는 지금 거짓말이다")

    # 서버가 좁힌 결과를 서버가 말한다 — 화면이 비워 두면 무엇을 찾았는지 알 길이 없다.
    body_html = client.get("/admin/naver-ingest/triage?tab=all&q=zzz없음").get_data(as_text=True)
    assert "찾은 주문 없음" in body_html, "0건 고지가 서버 렌더에 없다"

    # 이력에서도 `지금 수집` → watchRun → softRefresh 로 화면 루트가 통째로 갈린다.
    # 처리 탭 복원 경로는 그대로 살아 있어야 한다.
    restore = source.split("function restoreFind")[1].split("    function ")[0]
    assert "applyFind(" in restore, "복원이 다시 좁히지 않으면 칸에 낱말만 남는다"


def test_history_card_dropped_the_three_lines_of_prose():
    """사용자가 지운 안내문 3줄이 템플릿 소스에 남아 있지 않다 (2026-08-27).

    응답 단언으로는 다 못 잡는다: "큐에 넣기만 합니다" 는 ``ingest_status`` 가 있을 때만
    나오는 블록 안이라, 그 블록이 빠진 화면에서는 무엇을 지우든 green 이다. 세 줄을 한
    자리에서 세려면 소스를 읽는 수밖에 없다.

    나머지 둘의 **화면 쪽** 가드는
    ``test_naver_workbench.py::test_history_prose_the_user_deleted_stays_deleted`` 다.
    """
    markup = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "큐에 넣기만 합니다" not in markup, "지운 수집 버튼 밑 설명이 돌아왔다"
    assert "숫자는 모두 주문 단위" not in markup, "지운 카운트 문구가 돌아왔다"
    assert "읽기 전용 — 처리는" not in markup, "지운 읽기 전용 고지가 돌아왔다"


def test_review_done_does_not_reload_the_whole_page():
    """확인 완료는 화면 루트만 갈아 끼운다 — 통째 이동은 폴백에만 남는다 (2026-08-26).

    옛 코드는 ``location.href`` 로 페이지를 다시 받아 스크롤·찾기 낱말·글자 배율을 전부
    잃었다. "페이지를 다시 받지 않는다"는 v3 규율 밖에 남아 있던 마지막 자리였다.
    """
    source = JS_PATH.read_text(encoding="utf-8")
    body = source.split("async function submitReviewDone")[1].split("    /**")[0]

    assert "await softRefresh()" in body, "부분 갱신으로 끝내야 한다"
    assert "replacePaneState(null, next)" in body, (
        "주소에서 선택만 지운다. pushState 면 뒤로가기가 방금 뺀 집으로 돌아간다")
    assert "if (!refreshed)" in body, (
        "부분 갱신이 안 되는 응답(로그인 리다이렉트)에서 뺀 집이 남은 것처럼 보이면 안 된다")


def test_run_now_waits_with_its_own_token_and_a_deadline():
    """지금 수집은 결과를 기다리되, 단건·벌크 폴링을 끊지 않는다 (2026-08-26).

    옛 코드는 큐에 넣고 "잠시 뒤 새로고침하세요"로 끝냈다 — 사용자가 F5 를 누르기 전까지
    화면은 영원히 그대로였다. 기다리게 하되 **토큰을 나눠 쓰면 안 된다**: 하나를 공유하면
    수집을 누른 순간 돌고 있던 집 조작 폴링이 끊기고, 끊긴 쪽은 결과를 영영 못 본다.
    """
    source = JS_PATH.read_text(encoding="utf-8")
    submit = source.split("async function submitRunNow")[1].split("    /**")[0]
    watch = source.split("function watchRun")[1].split("function stopRunWatch")[0]

    assert "watchRun(rev)" in submit, "응답 지문을 기준으로 결과를 기다린다"
    assert "pollToken" not in watch and "bulkToken" not in watch, (
        "단건·벌크 토큰을 나눠 쓰면 서로를 끊는다")
    assert "mine !== runToken" in watch, "새 수집이 앞 폴링을 끊어야 한다"
    assert "Date.now() >= deadline" in watch, "마감 없이 도는 폴링을 만들지 않는다"
    assert "RUN_POLL_TIMEOUT_MS" in source and "RUN_POLL_INTERVAL_MS" in source

    # 정지기가 **실제로 정지하는지**까지 본다. 토큰 비교만 못박으면 `stopRunWatch()` 본문이
    # 비어도 전부 green 이다(2026-08-26 변이 실측으로 확인한 구멍) — 그러면 앞 폴링이
    # 계속 돌면서 새 수집의 문구를 옛 결과로 덮는다.
    stop = source.split("function stopRunWatch")[1].split("    /**")[0]
    assert "runToken += 1" in stop, "토큰을 올리지 않으면 돌던 회차가 살아남는다"
    assert "window.clearTimeout(runTimer)" in stop, "예약된 다음 회차를 취소해야 한다"


def test_bulk_note_exists_and_asset_pin_moved():
    """진행 문구 자리가 있어야 하고, JS/CSS 를 고쳤으면 ``?v`` 핀이 움직여야 한다.

    SW 가 staticCacheFirst 라 핀을 안 올리면 옛 파일이 계속 나온다.
    """
    markup = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert 'id="wb-bulk-note"' in markup
    assert 'id="wb-retry-note"' in markup
    assert markup.count("?v=20260902g") == 2, "CSS·JS 핀을 함께 올린다"


# --------------------------------------------------------------------------- #
# 벌크 진행 — 집 수와 무관하게 조회 2회 (승격 게이트 1의 부하 교훈)
# --------------------------------------------------------------------------- #

def _progress(client, link_ids):
    ids = ",".join(str(i) for i in link_ids)
    return client.get(f"{PROGRESS_PATH}?link_ids={ids}").get_json()["data"]


def test_progress_route_is_hidden_when_gate_is_off(client):
    """게이트 OFF 화면에는 이 경로가 없다."""
    _login(client)
    link = _collected(order_no=f"N-PG-OFF-{_uid()}", product="붙박이장", amount=100000,
                      place_status="NOT_YET")

    assert client.get(f"{PROGRESS_PATH}?link_ids={link.id}").status_code == 404


def test_progress_route_needs_link_ids(client, workbench_on):
    """무엇을 묻는지 없으면 400 — 숫자가 아닌 값도 무시하고 400 이다."""
    _login(client)

    assert client.get(PROGRESS_PATH).status_code == 400
    assert client.get(f"{PROGRESS_PATH}?link_ids=abc,%20").status_code == 400


def test_progress_counts_the_whole_household(client, workbench_on):
    """대표 하나만 넘겨도 **집 전체**를 센다 — 벌크는 집 단위로 나간다."""
    _login(client)
    lead = _collected(order_no=f"N-PG-HH-{_uid()}", product="붙박이장", amount=300000,
                      place_status="NOT_YET")
    lead_id = lead.id
    _sibling(lead, product="서랍 옵션", amount=20000, place_status="NOT_YET")

    data = _progress(client, [lead_id])

    assert data["links"] == 2, "형제까지 세야 '119건 중 47건' 이 거짓이 안 된다"
    assert data["place_pending"] == 2


def test_progress_uses_the_server_pending_predicate(client, workbench_on):
    """남은 건수 술어는 서버 SSOT(`is_place_pending`) 하나다.

    판매자센터에서 손으로 확인한 건은 우리 표식이 없고 컬럼만 ``OK`` 인데, 그걸 남은
    것으로 세면 진행률이 영원히 100%에 못 닿는다.
    """
    _login(client)
    lead = _collected(order_no=f"N-PG-PRED-{_uid()}", product="붙박이장", amount=300000,
                      place_status="NOT_YET")
    lead_id = lead.id
    _sibling(lead, product="서랍 옵션", amount=20000, place_status="OK")

    data = _progress(client, [lead_id])

    assert data["links"] == 2
    assert data["place_pending"] == 1, "컬럼이 OK 인 형제는 이미 끝난 것이다"


def test_progress_rev_and_pending_move_when_the_worker_confirms(client, workbench_on):
    """워커가 표식을 찍으면 남은 수가 줄고 지문이 바뀐다 — 이게 진행률의 신호다."""
    _login(client)
    lead_id = _collected(order_no=f"N-PG-MOVE-{_uid()}", product="붙박이장", amount=100000,
                         place_status="NOT_YET").id
    before = _progress(client, [lead_id])

    _mark(lead_id, place_confirmed_at="2026-08-24T06:00:00")

    after = _progress(client, [lead_id])
    assert before["place_pending"] == 1 and after["place_pending"] == 0
    assert after["rev"] != before["rev"]


def test_progress_surfaces_failures(client, workbench_on):
    """실패도 진행 조회로 보인다 — 벌크는 상세 pane 이 없어 여기 말고 볼 곳이 없다."""
    _login(client)
    lead_id = _collected(order_no=f"N-PG-ERR-{_uid()}", product="붙박이장", amount=100000,
                         place_status="NOT_YET").id

    _mark(lead_id, last_error="네이버가 거절했습니다.", last_error_at="2026-08-24T07:00:00",
          last_error_action="confirm")

    data = _progress(client, [lead_id])
    assert data["failed_links"] == 1
    assert data["last_error"] == "네이버가 거절했습니다."


def test_progress_carries_no_screen_judgement(client, workbench_on):
    """진행 조회도 화면 판정을 만들지 않는다(판정 SSOT 는 pane 하나)."""
    _login(client)
    lead_id = _collected(order_no=f"N-PG-JUDGE-{_uid()}", product="붙박이장", amount=100000,
                         place_status="NOT_YET").id

    data = _progress(client, [lead_id])

    assert set(data) == {"links", "place_pending", "failed_links", "last_error", "rev"}


def test_progress_caps_the_number_of_households(client, workbench_on, monkeypatch):
    """상한을 넘겨 보내도 상한까지만 본다 — 조용히 커진 요청이 조회를 키우지 않게."""
    from foms.web.admin import naver_ingest

    _login(client)
    first = _collected(order_no=f"N-PG-CAP1-{_uid()}", product="붙박이장", amount=100000,
                       place_status="NOT_YET")
    second = _collected(order_no=f"N-PG-CAP2-{_uid()}", product="장롱", amount=200000,
                        place_status="NOT_YET")
    ids = [first.id, second.id]
    monkeypatch.setattr(naver_ingest, "PROGRESS_LINK_ID_LIMIT", 1)

    data = _progress(client, ids)

    assert data["links"] == 1, "상한 밖 집은 보지 않는다"


# --------------------------------------------------------------------------- #
# 터치 기기 잠금 사유 (승격 게이트 3) — hover 없이도 읽혀야 한다
# --------------------------------------------------------------------------- #

def test_locked_checkbox_passes_the_tap_to_the_row():
    """잠긴 체크박스는 탭을 행에게 넘긴다.

    `disabled` 폼 컨트롤은 click 이벤트를 **아예 내지 않는다** — 마우스가 없는 기기에서는
    title 에 적힌 "왜 못 고르는지"를 읽을 길이 없었다. 포인터를 통과시키면 같은 탭이
    `a.wb-row` 에 닿아 상세가 열리고, 사유는 거기 상시 문구·배지로 이미 있다.
    """
    css = CSS_PATH.read_text(encoding="utf-8")

    assert ".wb-pick:disabled { pointer-events: none; }" in css
    assert ".wb-pick { pointer-events: none" not in css, "활성 체크박스까지 막으면 안 된다"


def test_create_lock_reason_is_visible_text_not_only_a_tooltip(client, workbench_on):
    """'주문 만들기' 가 잠긴 사유가 **화면 글자**로 있어야 한다(배지·문구와 같은 부류)."""
    _login(client)
    lead = _collected(order_no=f"N-TAP-CREATE-{_uid()}", product="붙박이장", amount=100000,
                      place_status="NOT_YET")
    order = _order("탭검증")
    lead_id = lead.id
    link = db_session.get(ExternalOrderLink, lead_id)
    link.order_id = order.id
    db_session.commit()

    body = client.get(f"/admin/naver-ingest/triage?link_id={lead_id}").get_data(as_text=True)
    pane = body.split('id="wb-pane"')[1]

    assert f"주문 #{order.id}</b> 가 있습니다" in pane, "사유가 title 밖에도 있어야 한다"
