"""GEO-SWEEP-01 — 좌표 스윕(``scripts/maintenance/run_geocode_sweep.py``) 계약 테스트.

배경: 주문 생성·주소 수정의 지오코딩 예약이 SIDEFX outbox 로 옮겨졌는데 그 워커가 운영에
배포된 적이 없어, 신규 주문은 좌표 없이 남고 ``pending`` 으로 고착된 계열까지 생겼다.
스윕은 RQ 경로로 그 구멍을 메우는 안전망이다.

여기서 잠그는 계약:

1. 대상 선별 술어 — 미시도(NULL)·오래된 ``pending``(시각 NULL 포함)은 집고,
   최근 ``pending``·좌표 있음·주소 없음·삭제 주문은 집지 않는다. ``failed`` 는 옵션.
2. **라운드 간 중복 방지** — enqueue 전에 ``pending`` + ``geocoded_at`` 시도 표식을
   커밋하므로, 워커가 아직 소진하지 못한 주문이 다음 라운드에 다시 큐로 들어가지 않는다.
3. 큐를 쓸 수 없으면(``REDIS_URL`` 부재) 조용히 성공하지 않고 exit 1.

실제 카카오 API·Redis 는 호출하지 않는다(enqueue 는 monkeypatch).
"""
from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from db import db_session
from foms.services.jobs import queue as queue_module
from models import Order

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "run_geocode_sweep.py"
)


def _load_sweep_module() -> Any:
    """``scripts/`` 는 패키지가 아니라서 파일 경로로 직접 로드한다."""
    spec = importlib.util.spec_from_file_location("run_geocode_sweep_ut", _SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sweep = _load_sweep_module()

# 나이 판정을 결정적으로 만들기 위한 고정 기준 시각(naive UTC 규약).
NOW = datetime.datetime(2026, 8, 31, 3, 0, 0)


def _make_order(**overrides: Any) -> Order:
    """좌표 없는 활성 주문 1건을 만든다(기본값 = 스윕 대상).

    Args:
        **overrides: 덮어쓸 Order 컬럼.

    Returns:
        커밋된 :class:`~models.Order`.
    """
    payload: dict[str, Any] = {
        "received_date": "2026-08-31",
        "customer_name": "좌표 스윕 대상",
        "phone": "010-0000-0000",
        "address": "서울시 강남구 테헤란로 1",
        "product": "장",
        "status": "RECEIVED",
        "lat": None,
        "lng": None,
        "geocode_status": None,
        "geocoded_at": None,
    }
    payload.update(overrides)
    order = Order(**payload)
    db_session.add(order)
    db_session.commit()
    return order


def _run_sweep(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> tuple[list[int], dict[str, int]]:
    """스윕 1라운드를 돌리고 (enqueue 된 order_id 목록, 집계)를 돌려준다.

    Args:
        monkeypatch: pytest fixture.
        **kwargs: :func:`sweep_once` 로 넘길 키워드 인자.

    Returns:
        ``(queued_ids, result)``.
    """
    queued: list[int] = []

    def _fake_enqueue(order_id: int) -> bool:
        queued.append(int(order_id))
        return True

    monkeypatch.setattr(queue_module, "enqueue_geocode_order_address", _fake_enqueue)
    kwargs.setdefault("now", NOW)
    result = sweep.sweep_once(db_session, **kwargs)
    return queued, result


# ---------------------------------------------------------------------------
# 1. 대상 선별 술어
# ---------------------------------------------------------------------------


def test_untried_order_is_swept(app, monkeypatch: pytest.MonkeyPatch) -> None:
    """``geocode_status IS NULL`` (한 번도 시도 안 함) 은 대상이다."""
    order = _make_order()

    queued, result = _run_sweep(monkeypatch)

    assert queued == [order.id]
    assert result == {"scanned": 1, "queued": 1, "skipped": 0, "failed": 0}


def test_pending_with_null_attempt_time_is_swept(app, monkeypatch: pytest.MonkeyPatch) -> None:
    """``pending`` + 시도 시각 NULL = 고착 건이므로 반드시 집는다.

    ``reset_order_geocode_on_address_change`` 는 ``pending`` 만 찍고 ``geocoded_at`` 은
    건드리지 않는다. 여기서 NULL 을 제외해 버리면 그 계열이 영영 안 풀린다.
    """
    order = _make_order(geocode_status="pending", geocoded_at=None)

    queued, _ = _run_sweep(monkeypatch)

    assert queued == [order.id]


def test_pending_with_stale_attempt_time_is_swept(app, monkeypatch: pytest.MonkeyPatch) -> None:
    """``pending`` 이라도 마지막 시도가 임계값보다 오래됐으면 다시 집는다."""
    stale = NOW - datetime.timedelta(seconds=sweep.PENDING_RETRY_SECONDS + 60)
    order = _make_order(geocode_status="pending", geocoded_at=stale)

    queued, _ = _run_sweep(monkeypatch)

    assert queued == [order.id]


def test_pending_with_recent_attempt_time_is_skipped(app, monkeypatch: pytest.MonkeyPatch) -> None:
    """방금 예약한 ``pending`` 은 집지 않는다(큐 중복 방지의 핵심 음성 대조군)."""
    recent = NOW - datetime.timedelta(seconds=sweep.PENDING_RETRY_SECONDS - 60)
    _make_order(geocode_status="pending", geocoded_at=recent)

    queued, result = _run_sweep(monkeypatch)

    assert queued == []
    assert result["scanned"] == 0


def test_failed_is_excluded_by_default_and_included_with_flag(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``failed`` 는 기본 제외(카카오 쿼터 보호), ``include_failed`` 로만 포함."""
    order = _make_order(geocode_status="failed", geocoded_at=NOW - datetime.timedelta(days=1))

    queued_default, _ = _run_sweep(monkeypatch)
    assert queued_default == []

    queued_opt_in, _ = _run_sweep(monkeypatch, include_failed=True)
    assert queued_opt_in == [order.id]


def test_order_with_coordinates_is_excluded(app, monkeypatch: pytest.MonkeyPatch) -> None:
    """이미 좌표가 있는 주문은 대상이 아니다."""
    _make_order(lat=37.5, lng=127.0, geocode_status="success", geocoded_at=NOW)

    queued, result = _run_sweep(monkeypatch)

    assert queued == []
    assert result["scanned"] == 0


@pytest.mark.parametrize("address", ["", "-"])
def test_blank_or_dash_address_is_excluded(
    app, monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    """주소가 비었거나 ``'-'`` 면 변환할 것이 없으므로 대상이 아니다."""
    _make_order(address=address)

    queued, result = _run_sweep(monkeypatch)

    assert queued == []
    assert result["scanned"] == 0


def test_deleted_order_is_excluded(app, monkeypatch: pytest.MonkeyPatch) -> None:
    """soft-delete 된 주문은 ``active_filter`` 로 빠진다."""
    _make_order(status="DELETED")

    queued, result = _run_sweep(monkeypatch)

    assert queued == []
    assert result["scanned"] == 0


def test_erp_order_with_dash_site_address_is_skipped(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ERP 주문의 정본 주소(structured_data.site)가 ``'-'`` 면 큐에 넣지 않는다.

    DB 술어는 ``Order.address`` 컬럼만 보므로, 실제 변환에 쓰이는 주소로 한 번 더 거른다.
    """
    _make_order(
        is_erp_order=True,
        structured_data={"site": {"address_full": "-", "address_main": "-", "address_detail": ""}},
    )

    queued, result = _run_sweep(monkeypatch)

    assert queued == []
    assert result == {"scanned": 1, "queued": 0, "skipped": 1, "failed": 0}


# ---------------------------------------------------------------------------
# 2. 라운드 간 중복 방지 (시도 표식)
# ---------------------------------------------------------------------------


def test_sweep_stamps_attempt_and_next_round_does_not_requeue(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1라운드가 ``pending`` + ``geocoded_at`` 을 찍어 2라운드 중복 enqueue 를 막는다.

    지오코딩은 건당 약 2.9초·워커 동시성 1이라, 60초 간격 스윕이 표식 없이 돌면 아직
    ``lat IS NULL`` 인 같은 주문을 매 라운드 다시 큐에 넣어 큐가 중복 잡으로 부푼다.
    """
    order = _make_order()

    first_queued, _ = _run_sweep(monkeypatch)
    assert first_queued == [order.id]

    db_session.expire_all()
    marked = db_session.get(Order, order.id)
    assert marked.geocode_status == "pending"
    assert marked.geocoded_at == NOW
    # 좌표는 워커가 채운다 — 스윕은 표식만 찍는다.
    assert marked.lat is None and marked.lng is None

    second_queued, second = _run_sweep(monkeypatch)
    assert second_queued == []
    assert second["scanned"] == 0

    # 임계값을 넘기면 다시 집는다(워커가 정말 처리하지 못한 경우의 구제).
    later = NOW + datetime.timedelta(seconds=sweep.PENDING_RETRY_SECONDS + 1)
    third_queued, _ = _run_sweep(monkeypatch, now=later)
    assert third_queued == [order.id]


def test_batch_caps_round_and_enqueues_each_order_once(
    app, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``batch`` 상한이 라운드 크기를 자르고, 같은 주문을 두 번 넣지 않는다."""
    orders = [_make_order(customer_name=f"대상 {i}") for i in range(4)]
    assert len({o.id for o in orders}) == 4

    queued, result = _run_sweep(monkeypatch, batch=2)

    assert len(queued) == 2
    assert len(set(queued)) == 2
    assert result["scanned"] == 2
    assert result["queued"] == 2


# ---------------------------------------------------------------------------
# 2b. failed 백오프 재시도 / address_error 영구 제외 (GEO-FAILKIND-01)
# ---------------------------------------------------------------------------


def test_stale_failed_is_swept_but_fresh_failed_is_not(
    app, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """사유 불명 ``failed`` 는 하루 뒤 다시 집는다(영구 제외였던 것이 이번 사고의 절반).

    음성 대조군으로 방금 실패한 건을 같이 둔다 — 백오프를 무시하고 전부 집는 구현이면
    이 대조군이 함께 큐에 들어가 실패한다.
    """
    stale = _make_order(customer_name="오래된 실패", geocode_status="failed",
                        geocoded_at=NOW - datetime.timedelta(days=2))
    _make_order(customer_name="방금 실패", geocode_status="failed",
                geocoded_at=NOW - datetime.timedelta(minutes=5))
    legacy = _make_order(customer_name="시각 없는 실패", geocode_status="failed",
                         geocoded_at=None)

    queued, _result = _run_sweep(monkeypatch)

    assert set(queued) == {stale.id, legacy.id}


def test_address_error_is_never_swept(app, monkeypatch: pytest.MonkeyPatch) -> None:
    """``address_error`` 는 나이와 무관하게, ``--include-failed`` 로도 집지 않는다."""
    _make_order(customer_name="주소 오류", geocode_status="address_error",
                geocoded_at=NOW - datetime.timedelta(days=30))
    untried = _make_order(customer_name="미시도 대조군")

    queued, _result = _run_sweep(monkeypatch, include_failed=True)

    assert queued == [untried.id]


# ---------------------------------------------------------------------------
# 3. 술어 SSOT 공유 (백필 CLI 회귀 방지)
# ---------------------------------------------------------------------------


def test_backfill_cli_shares_predicate_but_keeps_pending_out(app) -> None:
    """백필 CLI 는 같은 술어 모듈을 쓰되 ``pending`` 재시도는 하지 않는다.

    ``pending`` 재시도는 스윕 담당이다. 공용화하면서 백필 대상이 조용히 넓어지면 안 된다.
    """
    from tools.ops.backfill_geocode_missing import _candidate_query

    untried = _make_order(customer_name="미시도")
    _make_order(customer_name="고착 pending", geocode_status="pending", geocoded_at=None)

    ids = {order.id for order in _candidate_query(db_session, False).all()}

    assert ids == {untried.id}


# ---------------------------------------------------------------------------
# 4. 큐 사용 불가 시 무음 실패 금지
# ---------------------------------------------------------------------------


def test_main_returns_1_when_redis_url_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``REDIS_URL`` 이 없으면 조용히 성공하지 않고 에러 로그 + exit 1."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(queue_module, "_rq_queue", None)

    exit_code = sweep.main(["--once"])

    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "FATAL" in stderr
    assert "REDIS_URL" in stderr
