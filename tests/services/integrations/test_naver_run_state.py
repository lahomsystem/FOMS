""""지금 수집" 이 끝났는지 화면이 물어볼 자리 — 계약 테스트 (2026-08-26).

"지금 수집" 은 rq enqueue 로 끝나고 실제 수집은 WORKER 가 몇 초~몇 분 뒤에 한다. 그래서
버튼을 누른 직후의 화면은 아직 옛 상태다. 지금까지 화면은 "잠시 뒤 새로고침하면 결과가
이력에 나타납니다" 라고 말하고 끝났다 — 사용자가 F5 를 누르기 전까지 영원히 아무 변화가
없었다는 뜻이다.

여기서 고정하는 것은 둘이다:

1. **기준점**(``rev``) — 워터마크 상태의 지문. run-now 와 run-state 가 **같은 지문**을
   봐야 화면이 "바뀌었다"를 판정할 수 있다. 두 벌로 갈라지면 폴링은 영원히 끝나지 않는다.
2. **워커 0대면 넣지 않는다** — 아무도 꺼내지 않는 큐에 job 을 앉혀 놓고 "넣었습니다"라고
   말하는 것은 눌러도 아무 일이 없는 것과 같고, 사유조차 없어 더 나쁘다.

REDIS 미설정 503 계약(``test_naver_admin_surface.py``)은 그대로 살아 있어야 한다 —
워커 판정은 **큐에 닿는데도 워커가 없는 경우**만 추가로 막는 것이지 기존 경로를 대체하지
않는다(:func:`test_queue_disabled_still_falls_back_to_the_existing_503` 가 그것을 못박는다).
"""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce import watermark as wm
from foms.services.integrations.naver_commerce.client import KST
from models import User

RUN_PATH = "/admin/naver-ingest/run"
STATE_PATH = "/admin/naver-ingest/run-state"

_seq = itertools.count(1)


def _uid() -> int:
    """테스트 안에서만 쓰는 증가 번호(사용자명 충돌 방지)."""
    return next(_seq)


def _login(client, *, role: str = "ADMIN") -> User:
    """지정 역할로 로그인한 세션을 만든다(로그인 폼을 타지 않는 지름길)."""
    user = User(username=f"rs_{role.lower()}_{_uid()}", password=generate_password_hash("pw"),
                role=role, team="CS", name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _with_workers(monkeypatch, *, worker_count: int = 1, state: str = "reachable",
                  worker_count_known: bool = True, enqueue_ok: bool = True) -> list:
    """큐 런타임 상태를 고정하고, enqueue 호출을 기록하는 리스트를 돌려준다.

    실제 REDIS 에 의존하면 이 파일의 단언이 환경(REDIS_URL 유무)에 따라 흔들린다.
    ``worker_count_known=False`` 는 **ping 은 통했는데 워커 수를 못 센** 상태다.
    """
    calls: list = []

    def _fake_enqueue(dry_run=False):
        calls.append(dry_run)
        return enqueue_ok

    monkeypatch.setattr("foms.web.admin.naver_ingest.get_rq_runtime_status",
                        lambda: {"state": state, "worker_count": worker_count,
                                 "worker_count_known": worker_count_known})
    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_order_sync", _fake_enqueue)
    return calls


# --------------------------------------------------------------------------- #
# 기준점(rev) — 두 라우트가 같은 지문을 본다
# --------------------------------------------------------------------------- #

def test_run_now_hands_back_a_watermark_rev(app, client, monkeypatch):
    """"지금 수집" 응답에 기준점이 실려야 화면이 무엇과 비교할지 안다."""
    _login(client)
    calls = _with_workers(monkeypatch, worker_count=2)

    payload = client.post(RUN_PATH, json={}).get_json()

    assert payload["success"] is True
    assert calls == [False]
    assert payload["data"]["queued"] is True
    assert payload["data"]["worker_count"] == 2
    assert isinstance(payload["data"]["rev"], str) and payload["data"]["rev"]


def test_run_state_reports_the_same_rev_as_run_now(app, client, monkeypatch):
    """두 라우트가 **같은 지문**을 봐야 화면이 변화를 감지한다.

    지문이 갈리면 첫 폴링부터 "바뀌었다"로 읽히거나(가짜 완료) 영원히 안 바뀐다.
    """
    _login(client)
    _with_workers(monkeypatch)

    base_rev = client.post(RUN_PATH, json={}).get_json()["data"]["rev"]
    state = client.get(STATE_PATH).get_json()

    assert state["success"] is True
    assert state["error"] is None
    assert state["data"]["rev"] == base_rev


def test_rev_changes_once_a_sweep_advances_the_watermark(app, client, monkeypatch):
    """수집이 실제로 돌면 지문이 바뀐다 — 그것이 화면의 종료 신호다."""
    _login(client)
    _with_workers(monkeypatch)

    base_rev = client.post(RUN_PATH, json={}).get_json()["data"]["rev"]

    wm.advance(db_session, success_to=datetime.now(KST),
               summary={"collected": 3, "skipped": 1, "pending_review": 2})
    db_session.commit()

    after = client.get(STATE_PATH).get_json()["data"]
    assert after["rev"] != base_rev
    assert after["last_summary"] == "수집 3 · 건너뜀 1 · 보류 2"
    assert after["last_run_at"]
    assert after["last_error"] == ""


def test_rev_changes_when_a_sweep_fails(app, client, monkeypatch):
    """실패도 결말이다 — 실패하면 지문이 안 바뀌어 화면이 영원히 도는 일이 없어야 한다."""
    _login(client)
    _with_workers(monkeypatch)

    base_rev = client.post(RUN_PATH, json={}).get_json()["data"]["rev"]

    wm.record_failure(db_session, error="HTTP 500 판매자센터 응답 없음")
    db_session.commit()

    after = client.get(STATE_PATH).get_json()["data"]
    assert after["rev"] != base_rev
    assert "HTTP 500" in after["last_error"]


def test_rev_is_stable_while_nothing_happens(app, client, monkeypatch):
    """아무 일도 없으면 지문은 그대로 — 폴링이 매번 "끝났다"로 읽으면 쓸모가 없다."""
    _login(client)
    _with_workers(monkeypatch)

    wm.advance(db_session, success_to=datetime.now(KST) - timedelta(minutes=5),
               summary={"collected": 0, "skipped": 0, "pending_review": 0})
    db_session.commit()

    first = client.get(STATE_PATH).get_json()["data"]["rev"]
    second = client.get(STATE_PATH).get_json()["data"]["rev"]
    assert first == second


# --------------------------------------------------------------------------- #
# 워커가 없으면 넣지 않는다
# --------------------------------------------------------------------------- #

def test_run_now_refuses_when_no_worker_is_alive(app, client, monkeypatch):
    """큐에 닿아도 워커가 0대면 **넣지 않고** 503 + 사람 말로 된 사유를 준다."""
    _login(client)
    calls = _with_workers(monkeypatch, worker_count=0)

    response = client.post(RUN_PATH, json={})
    payload = response.get_json()

    assert response.status_code == 503
    assert payload["success"] is False
    assert calls == []  # 아무도 꺼내지 않는 큐에 job 을 앉히지 않았다
    assert "워커" in payload["error"]


def test_unknown_worker_count_is_not_reported_as_no_worker(app, client, monkeypatch):
    """**"못 셌다"를 "0대"라고 말하지 않는다** (2026-08-26 CEO 지적).

    ping 은 통했는데 그 직후 ``Worker.count`` 가 실패하는 짧은 창이 실재한다. 예전에는
    그 실패가 조용히 0 이 되어, 워커가 멀쩡히 도는데도 화면이 "한 대도 살아 있지
    않습니다. WORKER 서비스를 확인하세요"라고 말했다 — 사람을 엉뚱한 곳으로 보낸다.
    못 셌으면 막지 않고 그대로 넣는다.
    """
    _login(client)
    calls = _with_workers(monkeypatch, worker_count=0, worker_count_known=False)

    response = client.post(RUN_PATH, json={})
    payload = response.get_json()

    assert response.status_code == 200, payload
    assert payload["success"] is True
    assert calls == [False], "못 셌다는 이유로 넣지 않았다"
    assert payload["data"]["worker_count_known"] is False, "모른다는 사실을 숨겼다"


def test_dead_queue_behind_an_unknown_count_still_says_queue_failure(app, client, monkeypatch):
    """못 센 뒤 큐가 실제로 죽어 있으면 **"큐 장애"** 라는 맞는 사유가 나간다.

    못 셌을 때 막지 않는 것이 안전한 이유가 이것이다 — 진짜 고장이면 enqueue 가
    바로 실패하고, 그 자리에서 정확한 사유가 나온다.
    """
    _login(client)
    calls = _with_workers(monkeypatch, worker_count=0, worker_count_known=False,
                          enqueue_ok=False)

    response = client.post(RUN_PATH, json={})
    payload = response.get_json()

    assert response.status_code == 503
    assert calls == [False]
    assert "워커" not in payload["error"], "큐 장애를 워커 탓으로 말했다"
    assert "큐" in payload["error"]


def test_queue_disabled_still_falls_back_to_the_existing_503(app, client, monkeypatch):
    """REDIS 미설정(``disabled``)은 예전 그대로 enqueue 실패로 503 이다.

    워커 판정이 기존 경로를 **대체하지 않는다**는 못. 대체하면
    ``test_naver_admin_surface.py`` 의 "큐가 없으면 성공한 척하지 않는다" 계약이
    다른 이유로 통과하게 되어 실제 회귀를 못 잡는다.
    """
    _login(client)
    calls: list = []

    def _fake_enqueue(dry_run=False):
        calls.append(dry_run)
        return False

    monkeypatch.setattr("foms.web.admin.naver_ingest.get_rq_runtime_status",
                        lambda: {"state": "disabled", "worker_count": 0})
    monkeypatch.setattr("foms.web.admin.naver_ingest.enqueue_naver_order_sync", _fake_enqueue)

    response = client.post(RUN_PATH, json={})

    assert response.status_code == 503
    assert response.get_json()["success"] is False
    assert calls == [False]  # 큐에 넣어 보고 실패한 것이다(가로채지 않았다)


# --------------------------------------------------------------------------- #
# 권한 — 실행 이력은 수집 규모를 드러낸다
# --------------------------------------------------------------------------- #

def test_run_state_requires_login(app, client):
    """비로그인은 못 본다."""
    assert client.get(STATE_PATH).status_code in (301, 302, 401, 403)


def test_run_state_denies_non_admin_roles(app, client):
    """"지금 수집" 과 같은 ADMIN 권한 — 권한 없는 역할은 못 본다."""
    _login(client, role="STAFF")
    assert client.get(STATE_PATH).status_code in (301, 302, 401, 403)


def test_run_state_is_read_only_for_post(app, client, monkeypatch):
    """읽기 전용 GET 이다 — POST 로는 존재하지 않는다(쓰기 문을 열지 않았다)."""
    _login(client)
    assert client.post(STATE_PATH, json={}).status_code == 405
