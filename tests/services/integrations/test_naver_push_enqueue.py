"""네이버 클레임·앱만료 알림의 **웹푸시 배달** 계약.

인앱 벨(`Notification` + `notification_user_states`)까지는 예전부터 나갔다. 빠져 있던
것은 그 다음 한 칸이다 — `enqueue_push_for_notification` 을 부르는 곳이 네이버 경로에
**0곳**이라, 화면을 안 보고 있으면 취소된 집으로 생산·시공이 그대로 나갔다.
(`push_sender._DEFAULT_P1_TYPES` 등재는 이미 돼 있었다. 등재는 발송의 필요조건이지
충분조건이 아니다 — 아무도 큐에 안 넣으면 등재는 아무 일도 하지 않는다.)

고정하는 계약:

* 5분 스윕(:func:`tasks.run_naver_order_sync_task`)과 수동 다시 읽기
  (:func:`tasks.run_naver_refresh_task`) **양쪽**에서 새 네이버 알림마다 push job 이 걸린다.
* enqueue 는 **커밋 이후**다. 알림을 만드는 `_notify` / `check_and_notify` 안에서 걸면
  아직 없는 id 로 job 이 나가 워커가 빈손으로 깬다.
* enqueue 가 터져도 클레임 동기화 자체는 살아남고, 실패는 **반드시 로그로** 남는다
  (묵시적 무시 금지).
* 같은 알림에 push job 이 두 번 들어가지 않는다.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session as SASession

from db import db_session
from foms.services.integrations.naver_commerce import app_expiry
from foms.services.integrations.naver_commerce.claim_watch import (
    NOTIFICATION_TYPE as CLAIM_TYPE,
)
from models import ExternalOrderLink, Notification, User

_REPO_ROOT = Path(__file__).resolve().parents[3]

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


# --------------------------------------------------------------------------- #
# 고정물
# --------------------------------------------------------------------------- #

def _admin() -> User:
    """알림 수신자(활성 ADMIN) 1명. 없으면 `_notify_targets` 가 대상 없음으로 끝난다."""
    user = User(username=f"push_admin_{_uid()}", password="pw-not-committed",
                name="관리자", role="ADMIN", team="CS", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _detail(external_id: str, *, order_no: str, claim: str = "") -> dict:
    product_order = {
        "productOrderId": external_id,
        "productOrderStatus": "CANCELED" if claim else "PAYED",
        "productName": "붙박이장",
        "totalPaymentAmount": 500000,
        "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                            "baseAddress": "서울 강남구 1", "detailedAddress": "101호"},
    }
    if claim:
        product_order["claimStatus"] = claim
    detail = {"order": {"orderId": order_no, "ordererName": "김주문"},
              "productOrder": product_order}
    if claim:
        detail["cancel"] = {"cancelReason": "SIMPLE_INTENT_CHANGED"}
    return detail


def _link(external_id: str, *, order_no: str) -> ExternalOrderLink:
    link = ExternalOrderLink(channel="NAVER", external_id=external_id,
                             external_order_no=order_no, sync_status="COLLECTED",
                             raw_snapshot=_detail(external_id, order_no=order_no))
    db_session.add(link)
    db_session.commit()
    return link


class _ClaimClient:
    """변경 목록에 취소를 실어 주는 가짜 커머스 클라이언트(상세 조회만 한다)."""

    def __init__(self, external_ids: list[str], *, order_no: str = "N-1",
                 claim: str = "CANCEL_DONE"):
        self._ids = list(external_ids)
        self._order_no = order_no
        self._claim = claim
        self.windows: list[tuple] = []

    def get_last_changed_statuses(self, start, end):
        self.windows.append((start, end))
        return [{"productOrderId": pid, "productOrderStatus": "CANCELED"}
                for pid in self._ids]

    def get_product_orders(self, ids):
        wanted = [str(i) for i in ids]
        return [_detail(pid, order_no=self._order_no, claim=self._claim)
                for pid in wanted]


def _use_fake_client(monkeypatch, fake) -> None:
    """WORKER 태스크가 만드는 네이버 클라이언트를 가짜로 바꾼다.

    태스크·`run_sweep` 둘 다 호출 시점에 모듈에서 이름을 찾으므로 여기 한 곳이면 된다.
    """
    from foms.services.integrations.naver_commerce import client as client_mod

    monkeypatch.setattr(client_mod, "NaverCommerceClient", lambda *a, **k: fake)


class _PushRecorder:
    """enqueue 호출과 **커밋 시점**을 한 타임라인에 적는다.

    ``events`` 는 ``("commit", 그 커밋으로 확정된 Notification id 집합)`` 과
    ``("enqueue", notification_id)`` 가 시간순으로 섞인 목록이다. 이 타임라인만이
    "커밋 후에 걸었는가" 를 코드로 판정할 수 있게 해 준다.

    커밋된 id 는 ``after_flush`` 에서 모은다 — ``after_commit`` 훅은 트랜잭션 밖이라
    SQL 을 낼 수 없다(거기서 조회하면 조용히 빈손이 돼 가짜 초록이 난다).
    """

    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.calls: list[tuple] = []
        self.explode = False


@pytest.fixture
def push_spy(monkeypatch):
    """push enqueue 스파이 + 커밋 타임라인 기록기."""
    from foms.services.notifications import push_sender

    rec = _PushRecorder()
    flushed: set[int] = set()
    committed: set[int] = set()

    def _fake_enqueue(notification_id, db=None):
        rec.calls.append((int(notification_id), db))
        rec.events.append(("enqueue", int(notification_id)))
        if rec.explode:
            raise RuntimeError("큐가 죽었다")
        return {"enqueued": True, "reason": None}

    monkeypatch.setattr(push_sender, "enqueue_push_for_notification", _fake_enqueue)

    def _after_flush(session, _flush_context):
        for obj in session.new:
            if isinstance(obj, Notification) and getattr(obj, "id", None) is not None:
                flushed.add(int(obj.id))

    def _after_commit(session):
        committed.update(flushed)
        flushed.clear()
        rec.events.append(("commit", frozenset(committed)))

    def _after_soft_rollback(session, _previous_transaction):
        flushed.clear()

    event.listen(SASession, "after_flush", _after_flush)
    event.listen(SASession, "after_commit", _after_commit)
    event.listen(SASession, "after_soft_rollback", _after_soft_rollback)
    try:
        yield rec
    finally:
        event.remove(SASession, "after_flush", _after_flush)
        event.remove(SASession, "after_commit", _after_commit)
        event.remove(SASession, "after_soft_rollback", _after_soft_rollback)


def _committed_before_enqueue(events: list[tuple], notification_id: int) -> bool:
    """해당 알림이 **커밋된 뒤에** enqueue 됐는지 판정한다.

    Args:
        events: :class:`_PushRecorder` 타임라인.
        notification_id: 검사할 알림 id.

    Returns:
        enqueue 시점 **이전**의 커밋에 그 id 가 이미 들어 있었으면 True.
    """
    for index, item in enumerate(events):
        if item[0] != "enqueue" or item[1] != int(notification_id):
            continue
        return any(prior[0] == "commit" and int(notification_id) in prior[1]
                   for prior in events[:index])
    return False


def _claim_notifications() -> list[Notification]:
    return (db_session.query(Notification)
            .filter(Notification.notification_type == CLAIM_TYPE)
            .order_by(Notification.id)
            .all())


# --------------------------------------------------------------------------- #
# 스윕(5분) 경로
# --------------------------------------------------------------------------- #

def test_sweep_task_enqueues_push_for_each_naver_claim_notification(app, monkeypatch,
                                                                   push_spy):
    """수집 후 취소가 잡히면 인앱 알림뿐 아니라 **웹푸시 job 까지** 나가야 한다."""
    from foms.services.jobs import tasks

    _admin()
    _link("PO-SWEEP-1", order_no="N-SWEEP")
    _use_fake_client(monkeypatch, _ClaimClient(["PO-SWEEP-1"], order_no="N-SWEEP"))

    payload = tasks.run_naver_order_sync_task()

    created = _claim_notifications()
    assert created, "클레임 알림 자체가 안 만들어지면 이 테스트는 아무것도 안 지킨다"
    assert sorted(nid for nid, _db in push_spy.calls) == sorted(
        int(n.id) for n in created), "새 클레임 알림마다 push job 이 걸려야 한다"
    assert payload["push"]["enqueued"] == len(created)


def test_sweep_task_passes_the_worker_session_to_the_enqueue_helper(app, monkeypatch,
                                                                   push_spy):
    """워커에는 요청 컨텍스트가 없다 — 세션을 안 넘기면 헬퍼의 `get_db()` 폴백이 터진다."""
    from foms.services.jobs import tasks

    _admin()
    _link("PO-SESS-1", order_no="N-SESS")
    _use_fake_client(monkeypatch, _ClaimClient(["PO-SESS-1"], order_no="N-SESS"))

    tasks.run_naver_order_sync_task()

    assert push_spy.calls, "enqueue 가 아예 안 불렸다"
    assert all(session is not None for _nid, session in push_spy.calls)


def test_sweep_task_enqueues_push_for_app_expiry_notification(app, monkeypatch, push_spy):
    """앱 인증 만료 경고도 같은 구멍에 빠져 있었다 — 만료되면 수집이 조용히 전면 중단된다."""
    from foms.services.integrations.naver_commerce.client import KST
    from foms.services.jobs import tasks
    from datetime import datetime

    _admin()
    app_expiry.set_expiry_date(db_session, datetime.now(KST).date() + timedelta(days=7))
    db_session.commit()
    _use_fake_client(monkeypatch, _ClaimClient([]))

    tasks.run_naver_order_sync_task()

    expiry = (db_session.query(Notification)
              .filter(Notification.notification_type == app_expiry.NOTIFICATION_TYPE)
              .one())
    assert int(expiry.id) in [nid for nid, _db in push_spy.calls]


# --------------------------------------------------------------------------- #
# 수동 다시 읽기 경로 + 커밋 순서
# --------------------------------------------------------------------------- #

def test_refresh_task_enqueues_push_after_the_notification_is_committed(app, monkeypatch,
                                                                       push_spy):
    """enqueue 는 **커밋 뒤**여야 한다 — 커밋 전 id 로 job 을 걸면 워커가 빈손으로 깬다."""
    from foms.services.jobs import tasks

    _admin()
    link_id = int(_link("PO-REFRESH-1", order_no="N-REFRESH").id)
    _use_fake_client(monkeypatch,
                     _ClaimClient(["PO-REFRESH-1"], order_no="N-REFRESH"))

    tasks.run_naver_refresh_task(link_id)

    assert push_spy.calls, "수동 다시 읽기에서도 push 가 나가야 한다"
    for nid, _db in push_spy.calls:
        assert _committed_before_enqueue(push_spy.events, nid), (
            f"알림 {nid} 이 커밋되기 전에 push job 이 걸렸다 — 워커가 빈손으로 깬다. "
            f"타임라인={push_spy.events}"
        )


def test_notification_authors_never_enqueue_push_themselves():
    """알림을 만드는 모듈은 enqueue 를 하지 않는다(그 자리는 커밋 전이다).

    소스 수준으로 못을 박는다 — 나중에 "여기서 한 번만" 이 들어오면 커밋 전 enqueue 가
    되살아난다. 거는 자리는 커밋을 소유한 `jobs/tasks.py` 뿐이다.
    """
    for rel in ("foms/services/integrations/naver_commerce/claim_watch.py",
                "foms/services/integrations/naver_commerce/app_expiry.py"):
        source = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "enqueue_push_for_notification(" not in source, (
            f"{rel} 은 커밋 전이다 — push enqueue 는 커밋한 호출자(tasks.py)가 한다"
        )


# --------------------------------------------------------------------------- #
# fail-open · 중복 금지
# --------------------------------------------------------------------------- #

def test_push_enqueue_failure_never_kills_the_claim_sync(app, monkeypatch, push_spy,
                                                         caplog):
    """부가 배달(push)이 본체(클레임 동기화)를 죽이면 안 된다. 대신 **로그는 남는다**."""
    from foms.services.jobs import tasks

    _admin()
    _link("PO-FAIL-1", order_no="N-FAIL")
    _use_fake_client(monkeypatch, _ClaimClient(["PO-FAIL-1"], order_no="N-FAIL"))
    push_spy.explode = True

    with caplog.at_level(logging.WARNING, logger="foms.services.jobs.tasks"):
        payload = tasks.run_naver_order_sync_task()

    created = _claim_notifications()
    assert len(created) == 1, "push 실패가 알림·동기화를 되돌리면 안 된다"
    link = (db_session.query(ExternalOrderLink)
            .filter(ExternalOrderLink.external_id == "PO-FAIL-1").one())
    assert link.raw_snapshot["productOrder"]["claimStatus"] == "CANCEL_DONE", (
        "스냅샷 갱신(동기화 본체)이 push 실패에 휩쓸려 사라졌다")
    assert payload["push"]["failed"] == 1

    failures = [r for r in caplog.records
                if r.levelno >= logging.WARNING
                and str(int(created[0].id)) in r.getMessage()]
    assert failures, ("push enqueue 실패를 조용히 삼켰다 — fail-open 은 로그가 조건이다. "
                      f"records={[r.getMessage() for r in caplog.records]}")


def test_same_notification_is_never_enqueued_twice(app, monkeypatch, push_spy):
    """같은 집·같은 상태를 두 경로가 다시 봐도 push job 은 알림당 정확히 1건이다."""
    from foms.services.jobs import tasks

    _admin()
    first = _link("PO-DUP-1", order_no="N-DUP")
    _link("PO-DUP-2", order_no="N-DUP")
    _use_fake_client(monkeypatch,
                     _ClaimClient(["PO-DUP-1", "PO-DUP-2"], order_no="N-DUP"))
    link_id = int(first.id)

    tasks.run_naver_order_sync_task()
    # 같은 집을 수동으로 다시 읽어도(스윕/수동 중복 경로) 새 알림도 새 job 도 없다.
    tasks.run_naver_refresh_task(link_id)

    created = _claim_notifications()
    assert len(created) == 1, "한 집의 세부옵션 2건이 알림 2건이 되면 안 된다"
    enqueued = [nid for nid, _db in push_spy.calls]
    assert enqueued == [int(created[0].id)], f"push job 이 중복됐다: {enqueued}"
