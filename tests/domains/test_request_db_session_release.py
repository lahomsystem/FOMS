"""요청이 끝나면 DB 연결을 늘 돌려놓는다 — get_db() 를 안 부른 요청도 (DB-LEAK 11-08).

운영 ``[DB-LEAK]`` 기록 6일치 121건 중 116건이 로그인 없는 고객 공유 링크(``/s/<token>``)였다.
``close_db`` 는 ``g.db`` 가 있을 때(요청이 ``get_db()`` 를 불렀을 때)만 세션을 닫는데,
``foms/api/share.py`` 는 ``db_session`` 을 바로 쓴다. 그래서 마지막에 꺼낸 연결이 요청 뒤에도
세션에 남고, greenlet 이 끝난 뒤 GC 가 대신 치운다(그때 rollback 이 gevent 0.1초 Timeout 으로 깨진다).
"""
from db import db_session


def _holds_connection() -> bool:
    return db_session.registry.has() and db_session().in_transaction()


def test_anonymous_share_link_request_releases_db_session(client):
    db_session.remove()
    resp = client.get('/s/claude-test-no-such-share-token')
    assert resp.status_code in (404, 410)
    assert not _holds_connection(), '공유 링크 요청이 끝났는데 DB 연결이 트랜잭션째 남았다'


def test_request_without_db_use_does_not_open_session(client):
    db_session.remove()
    client.get('/healthz')
    assert not _holds_connection()


def test_transaction_open_before_request_is_left_alone(client):
    """요청 전부터 열린 트랜잭션(같은 스레드의 시험 데이터)은 그 요청 것이 아니다 — 건드리지 않는다."""
    from models import User

    db_session.remove()
    db_session.query(User).first()  # 트랜잭션을 연다
    client.get('/s/claude-test-no-such-share-token')
    assert _holds_connection()
    db_session.rollback()
