"""수집 작업대 render 예산(성능 원장 P2-2, 2026-10-02) — **읽는 양만** 줄었고 답은 그대로라는 계약.

스테이징 실측(claude_master, 정상 상태 4회): 처리 탭 render 642~885ms, 이력 탭 650~747ms
(전역 예산 500ms 초과). 그 안에서 세 가지가 같은 일을 되풀이했다.

1. 이력 탭은 처리 목록·칩·pane 을 그리지 않는데 처리 목록 전체(``_work_groups``)를 계산했다
   (wb_work_groups 511~603ms). 이력 탭에서 그 목록이 남기는 값은 탭 배지 `처리 N주문` 하나다.
2. 형제 색인(``wg_sibling`` 160~210ms)이 원천에서 **방금 읽은 행**을 ``raw_snapshot`` 째 다시
   읽었다 — 스테이징 원천 1,233행과 형제 1,233행이 같은 집합(원천 밖 형제 0행).
3. 배지 30초 캐시가 프로세스 메모리라 web 4개 프로세스가 각자 콜드 계산을 했다.

여기서 지키는 것: 같은 입력이면 **같은 집·같은 숫자**가 나온다는 사실, 그리고 줄인 읽기가
다시 늘지 않는다는 사실. 각 계약에는 같은 측정 장치가 옛 동작을 잡아낸다는 음성 대조군을 붙인다.
"""
from __future__ import annotations

import datetime
import re
import uuid
from typing import Any

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.common import dashboard_cache
from foms.services.integrations.naver_commerce import triage_count as tc
from models import ExternalOrderLink, User
from tests.services.integrations.test_naver_workbench_single_pass import _link, _seed_mixed

_REVIEWED_AT = datetime.datetime(2026, 10, 2, 0, 0, 0)

#: 형제 색인에서 판정에 쓰이는 칸 전부(``_SiblingIndex.__slots__`` 중 계산 결과).
INDEX_FIELDS = ("counts", "pending_counts", "blocking", "canceled",
                "confirmed_claim_blocked", "dispatched_all", "order_id_by_key")

TRIAGE_URL = "/admin/naver-ingest/triage"


@pytest.fixture
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


@pytest.fixture(autouse=True)
def _clean_badge_cache():
    tc.reset_triage_count_cache_for_tests()
    yield
    tc.reset_triage_count_cache_for_tests()


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"p22_{role.lower()}_{uuid.uuid4().hex[:8]}",
                password=generate_password_hash("pw"), role=role, team="CS",
                name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _tab_count(html: str) -> int:
    """머리줄 탭 배지 `처리 N주문` 의 N."""
    match = re.search(r'data-tab="work".*?처리<span class="wb-tab__n">(\d+)주문', html, re.S)
    assert match, "처리 탭 배지를 못 찾았다"
    return int(match.group(1))


def _id_of(external_id: str) -> int:
    row = (db_session.query(ExternalOrderLink)
           .filter(ExternalOrderLink.external_id == external_id).one())
    return int(row.id)


class _FakeRedis:
    """``get``·``setex`` 만 쓰는 공유 캐시 대역 — 프로세스 경계를 흉내 낸다."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    def get(self, key: str) -> Any:
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value
        self.ttl[key] = ttl


class _BrokenRedis:
    """연결이 끊긴 공유 캐시."""

    def get(self, key: str) -> Any:
        raise ConnectionError("redis down")

    def setex(self, key: str, ttl: int, value: str) -> None:
        raise ConnectionError("redis down")


# --------------------------------------------------------------------------- #
# ② 형제 색인은 원천에서 이미 읽은 행을 다시 읽지 않는다
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("display", [False, True])
def test_reused_sibling_index_equals_full_read(app, display):
    """원천 행을 재사용한 색인 == 형제를 통째로 다시 읽은 색인(두 표시 모드 모두)."""
    from foms.web.admin.naver_ingest import (
        _build_sibling_index,
        _source_order_nos,
        _work_source_links,
    )

    _seed_mixed(db_session)
    source, _ = _work_source_links(db_session, display=display)
    order_nos = _source_order_nos(source)

    full = _build_sibling_index(db_session, order_nos, display=display)
    reused = _build_sibling_index(db_session, order_nos, display=display, loaded=source)

    # 빈 색인끼리 같다는 거짓 통과를 막는다. `confirmed_claim_blocked` 는 원천 **밖** 형제
    # (발주확인 끝난 반품 형제)를 읽어야만 채워진다 — 재사용 경로가 그 행까지 읽었다는 증거.
    assert full.counts and full.confirmed_claim_blocked
    for name in INDEX_FIELDS:
        assert getattr(reused, name) == getattr(full, name), name


@pytest.mark.parametrize("display", [False, True])
def test_padded_order_no_is_not_reused(app, display):
    """SQL ``IN`` 은 공백을 털지 않는다 — 털린 번호로 재사용을 고르면 옛 조회가 안 읽던 행이 섞인다."""
    from foms.web.admin.naver_ingest import (
        _build_sibling_index,
        _source_order_nos,
        _work_source_links,
    )

    # 원천 안: 공백 붙은 번호 1 + 정확한 번호 1. 원천 밖: 정확한 번호의 발주확인 끝난 반품 형제.
    _link(db_session, external_id="20261002000001", order_no=" M-W ", name="공백집",
          tel="010-4000-0001", addr="서울 W로 1")
    _link(db_session, external_id="20261002000002", order_no="M-W", name="공백집",
          tel="010-4000-0001", addr="서울 W로 1")
    _link(db_session, external_id="20261002000003", order_no="M-W", name="공백집",
          tel="010-4000-0001", addr="서울 W로 1", status="LINKED", place="OK",
          claim="RETURN_REQUEST", reviewed_at=_REVIEWED_AT)
    source, _ = _work_source_links(db_session, display=display)
    order_nos = _source_order_nos(source)
    assert order_nos == {"M-W"}

    full = _build_sibling_index(db_session, order_nos, display=display)
    reused = _build_sibling_index(db_session, order_nos, display=display, loaded=source)

    assert sum(full.counts.values()) == 2, "옛 조회는 공백 붙은 행을 형제로 안 읽는다"
    for name in INDEX_FIELDS:
        assert getattr(reused, name) == getattr(full, name), name


def _spy_fetch(monkeypatch) -> list[list[int]]:
    """``_fetch_links`` 가 돌려준 행 id 를 호출마다 모은다."""
    import foms.web.admin.naver_ingest as ingest

    calls: list[list[int]] = []
    real = ingest._fetch_links

    def _spy(db, *criteria, **kwargs):
        rows = real(db, *criteria, **kwargs)
        calls.append([int(row.id) for row in rows])
        return rows

    monkeypatch.setattr(ingest, "_fetch_links", _spy)
    return calls


@pytest.mark.parametrize("display", [False, True])
def test_sibling_read_returns_only_rows_outside_the_source(app, monkeypatch, display):
    """처리 목록 1회 = 링크 조회 2회(원천 + 원천 밖 형제)이고, 두 번째는 **원천 밖 행만** 읽는다."""
    from foms.web.admin.naver_ingest import _work_groups

    _seed_mixed(db_session)
    calls = _spy_fetch(monkeypatch)

    _work_groups(db_session, display=display)

    assert len(calls) == 2, calls
    source_ids, sibling_ids = set(calls[0]), calls[1]
    assert not set(sibling_ids) & source_ids, "원천에서 이미 읽은 행을 다시 읽었다"
    # 시드에서 원천 밖 형제는 하나뿐이다(같은 주문번호의 발주확인 끝난 반품 형제).
    assert sibling_ids == [_id_of("20260824100010")]


def test_full_sibling_read_rereads_source_rows_negative_control(app, monkeypatch):
    """음성 대조군 — 재사용을 끄면(옛 경로) 같은 측정이 원천 행 재읽기를 잡아낸다."""
    from foms.web.admin.naver_ingest import _sibling_rows, _source_order_nos, _work_source_links

    _seed_mixed(db_session)
    source, _ = _work_source_links(db_session, display=False)
    calls = _spy_fetch(monkeypatch)

    _sibling_rows(db_session, _source_order_nos(source), display=False)

    assert len(calls) == 1
    assert set(calls[0]) & {int(row.id) for row in source}, \
        "옛 경로도 원천 행을 안 읽는다면 위 계약의 측정이 아무것도 못 가른다"


# --------------------------------------------------------------------------- #
# ① 이력 탭은 처리 목록을 계산하지 않는다
# --------------------------------------------------------------------------- #

def _spy_work_groups(monkeypatch) -> list[bool]:
    """``_work_groups`` 호출마다 ``display`` 값을 모은다."""
    import foms.web.admin.naver_ingest as ingest

    seen: list[bool] = []
    real = ingest._work_groups

    def _spy(db, **kwargs):
        seen.append(bool(kwargs.get("display", True)))
        return real(db, **kwargs)

    monkeypatch.setattr(ingest, "_work_groups", _spy)
    return seen


def test_history_tab_does_not_build_the_work_list(client, workbench_on, monkeypatch):
    """이력 탭은 표시용 처리 목록을 안 만든다. 캐시가 비었으면 배지 정의(얇은 경로)로 1회만 센다."""
    _seed_mixed(db_session)
    _login(client)
    seen = _spy_work_groups(monkeypatch)

    resp = client.get(TRIAGE_URL + "?tab=all")

    assert resp.status_code == 200
    assert True not in seen, f"이력 탭이 처리 목록(표시 모드)을 통째로 계산했다: {seen}"
    assert seen == [False], seen


def test_work_tab_still_builds_the_work_list_negative_control(client, workbench_on, monkeypatch):
    """음성 대조군 — 처리 탭은 여전히 표시 모드로 목록을 만든다(측정이 둘을 가른다)."""
    _seed_mixed(db_session)
    _login(client)
    seen = _spy_work_groups(monkeypatch)

    resp = client.get(TRIAGE_URL)

    assert resp.status_code == 200
    assert seen == [True], seen


def test_history_tab_count_equals_work_tab_count(client, workbench_on):
    """이력 탭의 `처리 N주문` == 처리 탭의 `처리 N주문` (같은 데이터, 콜드 캐시 각각)."""
    _seed_mixed(db_session)
    _login(client)

    history = _tab_count(client.get(TRIAGE_URL + "?tab=all").get_data(as_text=True))
    tc.reset_triage_count_cache_for_tests()
    work = _tab_count(client.get(TRIAGE_URL).get_data(as_text=True))

    assert work > 0
    assert history == work


def test_history_tab_reuses_the_badge_cache(client, workbench_on, monkeypatch):
    """배지 캐시가 살아 있으면 이력 탭은 목록을 아예 안 센다 — 그 값을 그대로 쓴다."""
    _seed_mixed(db_session)
    _login(client)
    tc.remember_triage_pending_count(41, workbench=True)
    seen = _spy_work_groups(monkeypatch)

    html = client.get(TRIAGE_URL + "?tab=all").get_data(as_text=True)

    assert seen == []
    assert _tab_count(html) == 41


def test_work_tab_writes_through_only_for_default_sort(client, workbench_on, monkeypatch):
    """처리 탭이 센 수는 기본 정렬일 때만 배지 캐시에 넣는다(다른 정렬은 캡이 자르는 집이 다르다)."""
    import foms.web.admin.naver_ingest as ingest

    _seed_mixed(db_session)
    _login(client)
    seen: list[tuple[int, bool]] = []
    monkeypatch.setattr(ingest, "remember_triage_pending_count",
                        lambda value, *, workbench: seen.append((int(value), workbench)))

    client.get(TRIAGE_URL + "?s=due")
    assert seen == [], "임박순 정렬의 수를 배지 캐시에 넣었다(음성 대조군)"

    html = client.get(TRIAGE_URL).get_data(as_text=True)
    assert seen == [(_tab_count(html), True)]


def test_pending_count_after_work_tab_is_a_cache_hit(client, workbench_on, monkeypatch):
    """처리 탭을 연 직후의 배지 요청은 목록을 다시 세지 않는다 — 그리고 같은 수를 말한다."""
    _seed_mixed(db_session)
    _login(client)
    html = client.get(TRIAGE_URL).get_data(as_text=True)
    seen = _spy_work_groups(monkeypatch)

    resp = client.get(TRIAGE_URL + "/pending-count")

    assert resp.get_json()["data"]["count"] == _tab_count(html)
    assert seen == []


# --------------------------------------------------------------------------- #
# ③ 배지 캐시는 프로세스 사이에 공유된다(Redis), 없으면 예전처럼 프로세스 칸
# --------------------------------------------------------------------------- #

def _counting_compute(monkeypatch, value: int) -> list[int]:
    calls: list[int] = []

    def _compute(db, *, workbench=False):
        calls.append(1)
        return value

    monkeypatch.setattr(tc, "compute_triage_pending_count", _compute)
    return calls


def _forget_process_cache() -> None:
    """다른 프로세스 흉내 — 프로세스 칸만 비운다."""
    tc.reset_triage_count_cache_for_tests()


def test_second_process_reads_the_shared_value(monkeypatch):
    """한 프로세스가 센 값을 다른 프로세스가 다시 세지 않고 읽는다."""
    fake = _FakeRedis()
    monkeypatch.setattr(tc, "get_dashboard_redis", lambda: fake)
    calls = _counting_compute(monkeypatch, 9)

    assert tc.get_triage_pending_count(object(), workbench=True) == 9
    key = tc.SHARED_KEY_PREFIX + tc._cache_key(True)
    assert fake.store[key] == "9"
    assert fake.ttl[key] == tc.TRIAGE_COUNT_CACHE_TTL_SEC, "신선도 약속(30초)이 바뀌었다"

    _forget_process_cache()
    assert tc.get_triage_pending_count(object(), workbench=True) == 9
    assert calls == [1]


def test_without_redis_each_process_computes_negative_control(monkeypatch):
    """음성 대조군 — Redis 가 없으면 예전처럼 프로세스마다 센다(같은 측정이 둘을 가른다)."""
    monkeypatch.setattr(tc, "get_dashboard_redis", lambda: None)
    calls = _counting_compute(monkeypatch, 9)

    assert tc.get_triage_pending_count(object(), workbench=True) == 9
    assert tc.get_triage_pending_count(object(), workbench=True) == 9
    assert calls == [1], "Redis 가 없어도 프로세스 캐시는 그대로 돌아야 한다"
    _forget_process_cache()
    assert tc.get_triage_pending_count(object(), workbench=True) == 9
    assert calls == [1, 1]


def test_broken_redis_falls_back_to_process_cache(monkeypatch):
    """공유 캐시가 끊겨도 배지는 나오고, 프로세스 칸이 계산 횟수를 지킨다."""
    monkeypatch.setattr(tc, "get_dashboard_redis", lambda: _BrokenRedis())
    calls = _counting_compute(monkeypatch, 5)

    assert tc.get_triage_pending_count(object(), workbench=True) == 5
    assert tc.get_triage_pending_count(object(), workbench=True) == 5
    assert calls == [1]


def test_populations_keep_separate_shared_slots(monkeypatch):
    """게이트 on/off 모집단은 공유 칸도 따로다 — 같은 칸이면 서로의 수를 읽는다."""
    fake = _FakeRedis()
    monkeypatch.setattr(tc, "get_dashboard_redis", lambda: fake)

    def _compute(db, *, workbench=False):
        return 1 if workbench else 2

    monkeypatch.setattr(tc, "compute_triage_pending_count", _compute)

    assert tc.get_triage_pending_count(object(), workbench=True) == 1
    assert tc.get_triage_pending_count(object(), workbench=False) == 2
    _forget_process_cache()
    assert tc.get_triage_pending_count(object(), workbench=True) == 1
    assert tc.get_triage_pending_count(object(), workbench=False) == 2


def test_remember_fills_the_shared_cache(monkeypatch):
    """처리 탭이 넣은 값은 다른 프로세스의 배지가 계산 없이 읽는다."""
    fake = _FakeRedis()
    monkeypatch.setattr(tc, "get_dashboard_redis", lambda: fake)
    calls = _counting_compute(monkeypatch, 99)

    tc.remember_triage_pending_count(12, workbench=True)
    _forget_process_cache()

    assert tc.get_triage_pending_count(object(), workbench=True) == 12
    assert calls == []


def test_shared_key_is_outside_the_dashboard_prefix():
    """대시보드 슬라이스 접두사 밖이어야 한다 — 그 접두사는 주문 저장마다 통째로 비워진다."""
    assert not tc.SHARED_KEY_PREFIX.startswith(dashboard_cache.CACHE_KEY_PREFIX)
