"""NAVER-INGEST-01 T5: 폴링 배선 · 워터마크 · web 경계 계약 테스트.

가장 중요한 계약은 **네이버 HTTP 가 WORKER 에서만 나간다**는 것이다. 커머스API센터 호출 IP
한도(3)와 Railway static outbound IP(3)가 정확히 같아 여유가 0이라, web 이 직접 부르면 등록되지
않은 IP 라 차단된다. 코드로 고정하지 않으면 나중에 "여기서 한 번만" 이 들어온다.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from db import db_session
from foms.services.integrations.naver_commerce import watermark as wm
from foms.services.integrations.naver_commerce.client import KST
from foms.services.integrations.naver_commerce.ingest import run_sweep
from models import ExternalOrderLink, Order, SystemSetting, User

_REPO_ROOT = Path(__file__).resolve().parents[3]
_START_SH = _REPO_ROOT / "start.sh"
_RUNNER = _REPO_ROOT / "scripts" / "maintenance" / "run_naver_order_sync.py"


# --------------------------------------------------------------------------- #
# WORKER 단일 출구 (IP 제약)
# --------------------------------------------------------------------------- #

#: web/api 에서 등장하면 안 되는 심볼 — HTTP 를 내거나 수집을 직접 도는 것들.
#: 워터마크·만료일 같은 **DB 전용 조회 헬퍼는 금지 대상이 아니다**(관리 화면이 읽어야 한다).
_WEB_FORBIDDEN = (
    "naver_commerce.client",
    "naver_commerce import client",
    "naver_commerce.ingest",
    "naver_commerce import ingest",
    "NaverCommerceClient",
    "run_sweep",
    "sync_naver_orders",
    # NAVER-INGEST-BACKFILL: 소급 수집도 WORKER 몫이다(web 은 enqueue 만).
    "run_backfill",
)


def test_web_layer_never_runs_the_naver_http_client():
    """web/api 계층은 네이버 HTTP 클라이언트·수집 파이프라인을 직접 쓰지 않는다.

    허용되는 유일한 실행 경로는 rq enqueue 헬퍼다(실행은 WORKER 가 한다). 관리 화면이
    워터마크·만료일 같은 **DB 상태**를 읽는 것은 HTTP 가 아니므로 금지 대상이 아니다.
    """
    offenders: list[str] = []
    for base in ("foms/web", "foms/api"):
        root = _REPO_ROOT / base
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8", errors="replace")
            hits = [symbol for symbol in _WEB_FORBIDDEN if symbol in source]
            if hits:
                offenders.append(f"{path.relative_to(_REPO_ROOT)} -> {hits}")
    assert offenders == [], (
        "web/api 는 네이버 클라이언트·수집 파이프라인을 직접 쓰면 안 된다(WORKER 단일 출구). "
        f"위반: {offenders}. enqueue_naver_order_sync() 를 쓸 것."
    )


def test_enqueue_helper_only_queues_and_makes_no_http_call():
    """enqueue 헬퍼는 큐에 넣기만 한다 — 그 자체로 네이버를 부르지 않는다."""
    source = (_REPO_ROOT / "foms" / "services" / "jobs" / "queue.py").read_text(encoding="utf-8")
    body = source.split("def enqueue_naver_order_sync", 1)[1]
    assert "run_naver_order_sync_task" in body
    assert "naver_commerce" not in body, "enqueue 경로에서 클라이언트를 직접 만들면 IP 가 틀어진다"


def test_worker_task_is_registered_for_rq():
    """rq job 경로가 실제로 존재해야 enqueue 가 죽지 않는다."""
    from foms.services.jobs import tasks

    assert hasattr(tasks, "run_naver_order_sync_task")
    assert "run_naver_order_sync_task" in tasks.__all__


# --------------------------------------------------------------------------- #
# start.sh 게이트
# --------------------------------------------------------------------------- #

def test_start_sh_gate_is_off_by_default_and_inside_worker_branch():
    """수집 루프는 WORKER 분기 안에서, 환경변수 게이트가 1일 때만 뜬다."""
    text = _START_SH.read_text(encoding="utf-8")
    assert 'if [ "$FOMS_NAVER_SYNC_ENABLED" = "1" ]; then' in text, "게이트 없이 항상 뜨면 안 된다"

    worker_branch = text.split('if [ "$USE_RQ_WORKER" = "1" ]; then', 1)[1].split("\nelse\n", 1)[0]
    assert "run_naver_order_sync.py" in worker_branch, "수집 루프는 WORKER 분기 안에 있어야 한다"
    # gunicorn(web) 분기에는 없어야 한다.
    web_branch = text.split("\nelse\n", 1)[1]
    assert "run_naver_order_sync.py" not in web_branch


def test_start_sh_loop_runs_in_background_with_interval_default():
    """루프는 백그라운드 서브셸(&)로 띄워 rq worker 본체를 막지 않는다. 기본 간격 300초."""
    text = _START_SH.read_text(encoding="utf-8")
    block = text.split("run_naver_order_sync.py", 1)[1].split("fi", 1)[0]
    assert "--loop" in block and block.rstrip().endswith("&")
    assert "${FOMS_NAVER_SYNC_INTERVAL_SECONDS:-300}" in block


def test_runner_exposes_expected_cli_flags():
    """T1 실검증이 쓰는 --once --dry-run --json 과 배선용 --loop/--interval 이 있어야 한다."""
    source = _RUNNER.read_text(encoding="utf-8")
    for flag in ("--once", "--dry-run", "--json", "--loop", "--interval"):
        assert f'"{flag}"' in source, f"러너에 {flag} 가 없다"


# --------------------------------------------------------------------------- #
# 워터마크
# --------------------------------------------------------------------------- #

def _now() -> datetime:
    return datetime(2026, 8, 13, 12, 0, tzinfo=KST)


def test_first_run_looks_back_one_day(app):
    """워터마크가 없으면 하루치만 되돌아본다(그 이전은 손으로 입력된 주문이다)."""
    start, end = wm.resolve_window(db_session, now=_now())
    assert end == _now() - wm.END_SAFETY_MARGIN
    assert start == _now() - wm.DEFAULT_LOOKBACK


def test_window_starts_at_stored_watermark(app):
    """워터마크가 있으면 거기서 이어 훑는다."""
    mark = _now() - timedelta(hours=2)
    wm.advance(db_session, success_to=mark, now=_now())
    db_session.commit()
    start, _end = wm.resolve_window(db_session, now=_now())
    assert start == mark


def test_watermark_never_moves_backwards(app):
    """늦게 끝난 실행이 앞선 워터마크를 되돌리면 같은 구간을 영영 다시 훑는다."""
    later = _now() - timedelta(hours=1)
    wm.advance(db_session, success_to=later, now=_now())
    wm.advance(db_session, success_to=_now() - timedelta(hours=5), now=_now())
    db_session.commit()
    assert wm.read_watermark(db_session) == later


def test_failure_records_error_without_advancing(app):
    """실패는 워터마크를 전진시키지 않는다 — 유실 방지의 핵심."""
    mark = _now() - timedelta(hours=3)
    wm.advance(db_session, success_to=mark, now=_now())
    wm.record_failure(db_session, error="HTTP 500 boom", now=_now())
    db_session.commit()
    assert wm.read_watermark(db_session) == mark
    assert wm.read_state(db_session)["last_error"] == "HTTP 500 boom"


def test_corrupt_watermark_falls_back_to_default_window(app):
    """저장값이 깨져도 수집이 죽지 않고 기본 구간으로 돈다."""
    db_session.add(SystemSetting(setting_key=wm.SETTING_KEY,
                                 setting_value={"last_success_to": "쓰레기"}))
    db_session.commit()
    start, _end = wm.resolve_window(db_session, now=_now())
    assert start == _now() - wm.DEFAULT_LOOKBACK


# --------------------------------------------------------------------------- #
# 스윕 통합 (워터마크 + 수집)
# --------------------------------------------------------------------------- #

class _StubClient:
    """수집 1건을 주고, 호출된 구간을 기록하는 스텁."""

    def __init__(self, changed=None, details=None, explode: bool = False):
        self.changed = changed if changed is not None else []
        self.details = details if details is not None else []
        self.explode = explode
        self.windows: list[tuple] = []

    def get_last_changed_statuses(self, start, end):
        self.windows.append((start, end))
        if self.explode:
            raise RuntimeError("naver down")
        return self.changed

    def get_product_orders(self, ids):
        wanted = set(ids)
        return [d for d in self.details if d["productOrder"]["productOrderId"] in wanted]


def _accounts() -> None:
    from foms.services.integrations.naver_commerce import ingest as ingest_mod

    db_session.add_all([
        User(username=ingest_mod.ACTOR_USERNAME, password="pw-not-committed",
             name="봇", role="MANAGER", team="CS", is_active=True),
        User(username=ingest_mod.OWNER_USERNAME, password="pw-not-committed",
             name="미배정", role="STAFF", team="SALES", is_active=True),
    ])
    db_session.commit()


def _detail(pid: str = "PO-1") -> dict:
    return {
        "order": {"orderId": "2026081399", "ordererName": "김주문",
                  "ordererTel": "010-1111-2222", "orderDate": "2026-08-13T09:00:00.000+09:00"},
        "productOrder": {
            "productOrderId": pid, "productOrderStatus": "PAYED",
            "productName": "붙박이장", "productOption": "화이트", "quantity": 1,
            "totalPaymentAmount": 900000,
            "shippingAddress": {"name": "이수취", "tel1": "010-3333-4444",
                                "baseAddress": "서울 강남구 1", "detailedAddress": "101호",
                                "zipCode": "06232"},
        },
    }


def _changed(pid: str = "PO-1") -> dict:
    return {"productOrderId": pid, "productOrderStatus": "PAYED"}


def test_sweep_collects_and_advances_watermark(app):
    """성공 스윕은 수집분을 남기고 워터마크를 구간 끝으로 옮긴다(주문은 안 만든다 — T12)."""
    _accounts()
    client = _StubClient([_changed()], [_detail()])
    payload = run_sweep(db_session, client=client, now=_now())

    assert payload["collected"] == 1
    assert payload["created"] == 0, "수집이 주문을 만들면 안 된다"
    assert db_session.query(Order).count() == 0
    assert wm.read_watermark(db_session) == _now() - wm.END_SAFETY_MARGIN
    assert wm.read_state(db_session)["last_summary"]["collected"] == 1


def test_failed_sweep_keeps_watermark_so_window_is_retried(app):
    """조회가 터지면 워터마크를 그대로 둬 다음 실행이 같은 구간을 다시 훑는다."""
    _accounts()
    with pytest.raises(RuntimeError):
        run_sweep(db_session, client=_StubClient(explode=True), now=_now())
    assert wm.read_watermark(db_session) is None
    assert "naver down" in wm.read_state(db_session)["last_error"]

    # 다음 실행은 여전히 기본 구간(= 놓친 구간 포함)을 훑는다.
    client = _StubClient([_changed()], [_detail()])
    run_sweep(db_session, client=client, now=_now())
    assert client.windows[0][0] == _now() - wm.DEFAULT_LOOKBACK


def test_dry_run_sweep_does_not_move_watermark(app):
    """dry-run 은 아무것도 만들지 않고 워터마크도 건드리지 않는다."""
    _accounts()
    payload = run_sweep(db_session, client=_StubClient([_changed()], [_detail()]),
                        dry_run=True, now=_now())
    assert payload["dry_run"] is True and payload["created"] == 0
    assert db_session.query(Order).count() == 0
    assert db_session.query(ExternalOrderLink).count() == 0
    assert wm.read_watermark(db_session) is None


def test_second_sweep_resumes_from_watermark(app):
    """연속 실행은 구간이 겹치지 않게 이어진다(중복 조회 낭비 방지)."""
    _accounts()
    first = _StubClient([_changed()], [_detail()])
    run_sweep(db_session, client=first, now=_now())
    later = _now() + timedelta(minutes=10)
    second = _StubClient([], [])
    run_sweep(db_session, client=second, now=later)
    assert second.windows[0][0] == first.windows[0][1]
