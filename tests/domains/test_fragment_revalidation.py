"""HB-S2a 계약 — 프래그먼트 버전 키 + 그림자 관측.

스펙: ``docs/specs/2026-09-01-shell-heartbeat-cheap-revalidation_SPEC.md`` §8.

여기서 고정하는 것:

1. **키가 축마다 갈린다** — 요청 인자·사용자·mine·오늘 날짜·테이블 카운터 중 하나가
   바뀌면 키가 바뀐다. 안 바뀌면 렌더 전 304 가 낡은 본문을 내보낸다.
2. **모르는 인자가 오면 키를 포기한다**(``None``) — 새 필터가 키에 반영 안 된 채
   조용히 같은 키를 내는 것이 이 설계의 최악 실패다.
3. **Redis 가 없으면 키를 포기한다** — fail-safe(느릴 뿐 정확).
4. **Flask-Compress 접미사 대조 규칙** — ``"abc:br"`` 과 ``"abc"`` 는 같은 검증자다.
5. **그림자 모드는 응답을 안 바꾼다** — 기본 off, 켜도 본문·상태코드 불변.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from foms.services.common import fragment_revalidation as fr


class _Req:
    """최소 Flask Request 대역(``args`` 만 쓴다)."""

    def __init__(self, args: dict[str, str]) -> None:
        self._args = dict(args)

    @property
    def args(self):
        return self

    def keys(self):
        return self._args.keys()

    def getlist(self, name: str) -> list[str]:
        value = self._args.get(name)
        return [] if value is None else [value]


class _User:
    def __init__(self, uid: int, role: str = "ADMIN", team: str | None = None) -> None:
        self.id = uid
        self.role = role
        self.team = team


_ARGS = ("q", "stage", "page")
_TABLES = ("orders", "order_attachments")


@pytest.fixture
def stable_cohort():
    """코호트 재료를 고정한다(플래그 변동이 키 축 테스트를 흔들지 않게)."""
    with patch.object(fr, "_cohort_material", return_value={"_shell_variant": "legacy"}):
        yield


_DEFAULT_VERSIONS = {"orders": 1, "order_attachments": 1}


def _key(req_args, user=None, versions=_DEFAULT_VERSIONS, mine=False):
    """테이블 카운터를 고정한 채 키를 만든다 (``versions=None`` = Redis 없음)."""
    from foms.services.common import table_version_counter as tvc

    with patch.object(tvc, "get_table_versions", return_value=versions):
        return fr.build_fragment_version_key(
            route_id="erp_history_dashboard",
            req=_Req(req_args),
            user=user if user is not None else _User(1),
            tables=_TABLES,
            allowed_args=_ARGS,
            mine_only=mine,
        )


# --------------------------------------------------------------------------- #
# 1. 압축 접미사 대조 규칙
# --------------------------------------------------------------------------- #

def test_strip_compress_suffix():
    """Flask-Compress 가 붙이는 :br/:gzip/:deflate/:zstd 만 벗긴다."""
    assert fr.strip_content_encoding_suffix('"abc:br"') == "abc"
    assert fr.strip_content_encoding_suffix('"abc:gzip"') == "abc"
    assert fr.strip_content_encoding_suffix('W/"abc:deflate"') == "abc"
    assert fr.strip_content_encoding_suffix('"abc:zstd"') == "abc"
    assert fr.strip_content_encoding_suffix('"abc"') == "abc"
    assert fr.strip_content_encoding_suffix("abc") == "abc"


def test_strip_leaves_unknown_suffix_alone():
    """모르는 접미사는 안 벗긴다 — 키 안에 콜론이 들어가도 안전해야 한다."""
    assert fr.strip_content_encoding_suffix('"abc:notacodec"') == "abc:notacodec"


def test_compressed_and_plain_validators_compare_equal():
    """클라가 접미사 붙은 값을 에코해도 같은 검증자로 읽힌다(S2b 대조의 근거)."""
    plain = fr.strip_content_encoding_suffix('"deadbeefdeadbeef"')
    compressed = fr.strip_content_encoding_suffix('"deadbeefdeadbeef:br"')
    assert plain == compressed


# --------------------------------------------------------------------------- #
# 2. 키가 축마다 갈린다
# --------------------------------------------------------------------------- #

def test_key_is_stable_for_identical_input(stable_cohort):
    """같은 입력 → 같은 키(안 그러면 304 가 한 번도 안 걸린다)."""
    assert _key({"q": "kim"}) == _key({"q": "kim"})
    assert _key({"q": "kim"}) is not None


def test_key_changes_per_axis(stable_cohort):
    """요청 인자·사용자·역할·팀·mine·테이블 카운터가 각각 키를 가른다."""
    base = _key({"q": "kim", "page": "1"})
    assert base != _key({"q": "lee", "page": "1"}), "검색어"
    assert base != _key({"q": "kim", "page": "2"}), "페이지"
    assert base != _key({"q": "kim", "page": "1"}, user=_User(2)), "사용자"
    assert base != _key({"q": "kim", "page": "1"}, user=_User(1, role="STAFF")), "역할"
    assert base != _key({"q": "kim", "page": "1"}, user=_User(1, team="CONSTRUCTION")), "팀"
    assert base != _key({"q": "kim", "page": "1"}, mine=True), "mine"
    assert base != _key(
        {"q": "kim", "page": "1"}, versions={"orders": 2, "order_attachments": 1}
    ), "orders 카운터"
    assert base != _key(
        {"q": "kim", "page": "1"}, versions={"orders": 1, "order_attachments": 2}
    ), "order_attachments 카운터"


def test_key_changes_when_day_rolls_over(stable_cohort):
    """자정을 넘기면 키가 바뀐다(스펙 §5-3)."""
    import datetime

    from foms.services import datetime_kst

    with patch.object(datetime_kst, "get_today_kst", return_value=datetime.date(2026, 9, 1)):
        day1 = _key({"q": "kim"})
    with patch.object(datetime_kst, "get_today_kst", return_value=datetime.date(2026, 9, 2)):
        day2 = _key({"q": "kim"})
    assert day1 != day2


def test_key_changes_with_cohort():
    """코호트 변형(v2/v3)이 키를 가른다."""
    with patch.object(fr, "_cohort_material", return_value={"_shell_variant": "v2"}):
        v2 = _key({"q": "kim"})
    with patch.object(fr, "_cohort_material", return_value={"_shell_variant": "v3"}):
        v3 = _key({"q": "kim"})
    assert v2 != v3


def test_key_changes_with_session(stable_cohort):
    """세션(CSRF 토큰)이 다르면 키가 다르다.

    2026-09-01 스테이징 그림자 관측이 잡은 축이다. 프래그먼트 본문에 세션마다 다른
    ``csrf_token`` 이 박히므로, 키에 세션이 없으면 재로그인 후 렌더 전 304 가
    **옛 세션의 토큰이 박힌 폼**을 되살려 저장이 403 으로 실패한다.
    """
    with patch.object(fr, "_session_material", return_value="sessAAAAAAAA"):
        a = _key({"q": "kim"})
    with patch.object(fr, "_session_material", return_value="sessBBBBBBBB"):
        b = _key({"q": "kim"})
    assert a != b


def test_session_material_uses_digest_not_the_token(app):
    """세션 재료는 토큰 자체가 아니라 digest 다(키 재료에 비밀값을 두지 않는다)."""
    from flask import session

    with app.test_request_context("/erp/history/"):
        session["csrf_token"] = "raw-secret-token-value"
        material = fr._session_material()
    assert material != "raw-secret-token-value"
    assert "raw-secret" not in material
    assert len(material) == 12


def test_key_changes_with_release(stable_cohort):
    """릴리스가 다르면 키가 다르다.

    본문에 자산 ``?v=`` 핀이 26개 박혀 있어, 핀을 올리는 배포는 카운터·사용자·날짜를
    전혀 건드리지 않고 마크업만 바꾼다. 릴리스 축이 없으면 그 순간 렌더 전 304 가
    옛 마크업을 계속 돌려준다.
    """
    with patch.object(fr, "RELEASE_ID", "releaseAAAA"):
        a = _key({"q": "kim"})
    with patch.object(fr, "RELEASE_ID", "releaseBBBB"):
        b = _key({"q": "kim"})
    assert a != b


def test_release_id_is_stable_within_a_process():
    """릴리스 식별자는 프로세스 안에서 안정적이다(요청마다 흔들리면 304 가 안 걸린다)."""
    assert fr.RELEASE_ID
    assert fr.RELEASE_ID == fr.RELEASE_ID
    assert fr._compute_release_id() == fr._compute_release_id()


def test_release_id_prefers_explicit_env(monkeypatch):
    """운영이 심어준 식별자가 최우선이다(워커 간에 같은 값이 나와야 304 가 걸린다)."""
    monkeypatch.setenv("FOMS_RELEASE_ID", "deadbeefcafe0001")
    assert fr._compute_release_id() == "deadbeefcafe0001"


def test_view_param_is_allowed_but_not_key_material(stable_cohort):
    """``view`` 는 언제나 허용하되 키 재료에서는 뺀다(tier 헤더가 담당)."""
    assert _key({"q": "kim", "view": "fragment"}) == _key({"q": "kim"})


# --------------------------------------------------------------------------- #
# 3. 키를 포기해야 하는 경우 (fail-safe)
# --------------------------------------------------------------------------- #

def test_unknown_arg_abandons_the_key(stable_cohort):
    """등재 안 된 인자가 하나라도 오면 None.

    새 필터가 추가됐는데 allowed_args 에 없으면, 그 필터를 바꿔도 키가 같아
    낡은 본문이 재사용된다. 그럴 바엔 단축을 포기한다.
    """
    assert _key({"q": "kim", "brand_new_filter": "x"}) is None


def test_no_redis_abandons_the_key():
    """테이블 카운터를 못 읽으면(Redis 없음) None — 지금 동작 그대로 간다."""
    assert _key({"q": "kim"}, versions=None) is None


# --------------------------------------------------------------------------- #
# 4. 그림자 관측
# --------------------------------------------------------------------------- #

class _FakePipeline:
    """GET+SETEX 를 한 왕복으로 묶는 실제 구현과 같은 모양."""

    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._ops: list = []

    def get(self, k):
        self._ops.append(("get", k))

    def setex(self, k, ttl, v):
        self._ops.append(("setex", k, v))

    def incr(self, k):
        self._ops.append(("incr", k))

    def lpush(self, k, v):
        self._ops.append(("lpush", k, v))

    def ltrim(self, k, a, b):
        self._ops.append(("ltrim", k))

    def execute(self):
        out = []
        for op in self._ops:
            kind = op[0]
            if kind == "get":
                out.append(self._redis.store.get(op[1]))
            elif kind == "setex":
                self._redis.store[op[1]] = op[2]
                out.append(True)
            elif kind == "incr":
                out.append(self._redis.incr(op[1]))
            elif kind == "lpush":
                self._redis.lists.setdefault(op[1], []).insert(0, op[2])
                out.append(len(self._redis.lists[op[1]]))
            else:
                out.append(True)
        return out


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.counters: dict[str, int] = {}
        self.lists: dict[str, list] = {}

    def pipeline(self):
        return _FakePipeline(self)

    def incr(self, k):
        self.counters[k] = self.counters.get(k, 0) + 1
        return self.counters[k]


def test_shadow_flag_is_off_by_default():
    """기본 off — 관측 비용은 스테이징에서만 낸다(스펙 §8.4)."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FOMS_FRAGMENT_SHADOW_REVALIDATION_ENABLED", None)
        assert fr.is_shadow_revalidation_enabled() is False


def test_shadow_observation_new_then_match():
    """첫 관측은 new, 같은 본문 재관측은 match."""
    from foms.services.common import dashboard_cache as dc

    fake = _FakeRedis()
    with patch.object(dc, "get_dashboard_redis", return_value=fake):
        assert fr.record_shadow_observation("k1", b"<html>a</html>", route_id="r") == fr.SHADOW_STATE_NEW
        assert fr.record_shadow_observation("k1", b"<html>a</html>", route_id="r") == fr.SHADOW_STATE_MATCH
    assert fr.SHADOW_MISMATCH_COUNTER_KEY not in fake.counters, "정상 관측은 mismatch 를 올리지 않는다"
    # 적중률을 사후에 재려면 상태별 수가 필요하다(mismatch 만 세면 "이득이 있나"를 못 잰다).
    assert fake.counters[f"{fr.SHADOW_STATE_COUNTER_PREFIX}:new"] == 1
    assert fake.counters[f"{fr.SHADOW_STATE_COUNTER_PREFIX}:match"] == 1


def test_shadow_observation_detects_mismatch():
    """같은 키에 다른 본문 → MISMATCH + 카운터 증가.

    이것이 "키에 빠진 축이 있다"는 증거다. S2b(렌더 전 304)는 이 값이 0 이라는
    스테이징 관측 후에만 켠다.
    """
    from foms.services.common import dashboard_cache as dc

    fake = _FakeRedis()
    with patch.object(dc, "get_dashboard_redis", return_value=fake):
        fr.record_shadow_observation("k1", b"<html>a</html>", route_id="r")
        state = fr.record_shadow_observation("k1", b"<html>DIFFERENT</html>", route_id="r")
    assert state == fr.SHADOW_STATE_MISMATCH
    assert fake.counters.get(fr.SHADOW_MISMATCH_COUNTER_KEY) == 1
    # 카운터만으로는 밤사이 난 mismatch 의 원인을 못 쫓는다(배포가 교체되면 로그가
    # 사라진다). 상세를 남기고, 특히 릴리스가 그 사이 바뀌었는지를 기록한다.
    import json as _json

    entries = fake.lists.get(fr.SHADOW_MISMATCH_LOG_KEY) or []
    assert len(entries) == 1
    rec = _json.loads(entries[0])
    assert rec["route"] == "r" and rec["key"] == "k1"
    assert rec["prev"] and rec["now"] and rec["prev"] != rec["now"]
    assert rec["same_release"] is True, "같은 프로세스 안이면 릴리스는 그대로여야 한다"


def test_shadow_observation_harmless_without_redis():
    """Redis 가 없으면 조용히 new — 관측 실패가 응답을 건드리지 않는다."""
    from foms.services.common import dashboard_cache as dc

    with patch.object(dc, "get_dashboard_redis", return_value=None):
        assert fr.record_shadow_observation("k1", b"x", route_id="r") == fr.SHADOW_STATE_NEW


def test_shadow_observation_never_raises_on_redis_failure():
    """Redis 가 터져도 예외가 새지 않는다."""
    from foms.services.common import dashboard_cache as dc

    class _Boom:
        def pipeline(self):
            raise RuntimeError("redis down")

        def incr(self, k):
            raise RuntimeError("redis down")

    with patch.object(dc, "get_dashboard_redis", return_value=_Boom()):
        assert fr.record_shadow_observation("k1", b"x", route_id="r") == fr.SHADOW_STATE_NEW


# --------------------------------------------------------------------------- #
# 5. 라우트 배선 — 동작 변경 0
# --------------------------------------------------------------------------- #

def _login_admin(client):
    from werkzeug.security import generate_password_hash

    from db import db_session
    from models import User

    user = User(
        username="fragver_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="FragVer Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _fragment(client):
    return client.get(
        "/erp/history/?view=fragment&q=zzz-no-match",
        headers={"X-FOMS-ERP-SHELL": "1"},
    )


def test_shadow_mode_off_adds_no_header(client, monkeypatch):
    """플래그가 꺼져 있으면 진단 헤더조차 안 붙는다."""
    monkeypatch.delenv("FOMS_FRAGMENT_SHADOW_REVALIDATION_ENABLED", raising=False)
    _login_admin(client)
    resp = _fragment(client)
    assert resp.status_code == 200
    assert fr.SHADOW_HEADER not in resp.headers


def test_shadow_mode_on_does_not_change_the_response(client, monkeypatch):
    """켜도 상태코드·본문이 그대로다(동작 변경 0이 S2a 의 계약)."""
    monkeypatch.delenv("FOMS_FRAGMENT_SHADOW_REVALIDATION_ENABLED", raising=False)
    _login_admin(client)
    off = _fragment(client)

    monkeypatch.setenv("FOMS_FRAGMENT_SHADOW_REVALIDATION_ENABLED", "1")
    on = _fragment(client)

    assert on.status_code == off.status_code == 200
    assert on.data == off.data, "그림자 모드가 본문을 바꾸면 안 된다"


def test_route_observes_new_then_match_when_redis_is_available(client, monkeypatch):
    """실제 라우트에서 키가 만들어지고 같은 본문이 match 로 관측된다.

    Redis 없는 기본 테스트 환경에서는 키 생성이 포기되므로(fail-safe) 그림자 경로가
    통째로 안 돈다 — 배선이 정말 살아 있는지는 카운터/Redis 를 붙여야만 보인다.
    """
    from foms.services.common import dashboard_cache as dc
    from foms.services.common import table_version_counter as tvc

    monkeypatch.setenv("FOMS_FRAGMENT_SHADOW_REVALIDATION_ENABLED", "1")
    _login_admin(client)
    fake = _FakeRedis()
    versions = {"orders": 7, "order_attachments": 3, "order_schedule_dates": 1, "users": 2}

    with patch.object(tvc, "get_table_versions", return_value=versions), \
            patch.object(dc, "get_dashboard_redis", return_value=fake):
        first = _fragment(client)
        second = _fragment(client)

    assert first.headers.get(fr.SHADOW_HEADER) == fr.SHADOW_STATE_NEW
    assert second.headers.get(fr.SHADOW_HEADER) == fr.SHADOW_STATE_MATCH
    assert fake.counters.get(fr.SHADOW_MISMATCH_COUNTER_KEY) is None


def test_route_reports_mismatch_when_body_changes_without_a_counter_bump(client, monkeypatch):
    """카운터를 고정한 채 본문이 바뀌면 MISMATCH 로 표면화된다.

    이것이 그림자 모드의 존재 이유다 — 키에 없는 축(여기서는 새 주문)이 본문을 바꾸면
    렌더 전 304 에서는 **낡은 본문**이 나갔을 상황이다.
    """
    from db import db_session
    from models import Order

    from foms.services.common import dashboard_cache as dc
    from foms.services.common import table_version_counter as tvc

    monkeypatch.setenv("FOMS_FRAGMENT_SHADOW_REVALIDATION_ENABLED", "1")
    _login_admin(client)
    fake = _FakeRedis()
    versions = {"orders": 7, "order_attachments": 3, "order_schedule_dates": 1, "users": 2}

    with patch.object(tvc, "get_table_versions", return_value=versions), \
            patch.object(dc, "get_dashboard_redis", return_value=fake):
        first = client.get(
            "/erp/history/?view=fragment&q=FRAGVER-MISMATCH",
            headers={"X-FOMS-ERP-SHELL": "1"},
        )
        db_session.add(Order(
            received_date="2026-09-01",
            customer_name="FRAGVER-MISMATCH",
            phone="010-0000-0000",
            address="Seoul",
            product="Wardrobe",
            status="RECEIVED",
            is_erp_order=True,
            structured_data={"workflow": {"stage": "RECEIVED"}},
        ))
        db_session.commit()
        second = client.get(
            "/erp/history/?view=fragment&q=FRAGVER-MISMATCH",
            headers={"X-FOMS-ERP-SHELL": "1"},
        )

    assert first.headers.get(fr.SHADOW_HEADER) == fr.SHADOW_STATE_NEW
    assert second.headers.get(fr.SHADOW_HEADER) == fr.SHADOW_STATE_MISMATCH
    assert fake.counters.get(fr.SHADOW_MISMATCH_COUNTER_KEY) == 1
