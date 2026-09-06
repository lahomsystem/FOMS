"""무감독 워커 루프의 하트비트·Sentry 배선 계약 (OPS-HEARTBEAT-01).

``start.sh`` 는 백그라운드 루프 5개를 ``&`` 로 띄우고 셸은 ``exec rq worker`` 로 자기를
대체한다. wait/trap/supervisor 가 0 이고 하트비트도 0 이라, "소비 프로세스가 안 돈다" 실패가
2026-02(워커 offline)와 2026-08-31(SIDEFX 미배포)에 반복됐고 **두 번 다 사용자가 지도에서
먼저 발견**했다. 그 위에 되돌릴 수 없는 조작(평일 16:50 KST 네이버 자동 발송)이 얹혀 있다.

**하트비트**(``run_naver_auto_dispatch.py``) — 실제 동작으로 못 박는다.

1. 루프 tick 1회 뒤 ``side_effect_worker_heartbeats`` 에 ``NAVER_AUTO_DISPATCH`` 행이
   생기고 ``last_heartbeat_at`` 이 채워진다 — **일을 안 한 tick(창 밖)도 그렇다**.
   그래야 "루프가 죽었다" 와 "지금은 일할 시각이 아니다" 가 갈린다.
2. 두 번째 tick 은 같은 행의 시각만 전진시킨다(upsert — 행이 늘지 않는다).
3. 음성 대조군: 하트비트가 실패해도 본 작업(자동 발송)은 그대로 수행되고, 실패는 삼켜지지
   않고 경고 로그 1건으로 남는다. 되돌릴 수 없는 조작이 관측 배선 때문에 멈추면 더 나쁜
   실패이고, 조용히 사라지면 배선이 없는 것과 같다.
4. 하트비트 metadata 에는 고객 정보(이름·전화·주소)가 실리지 않는다.

**Sentry**(``foms/services/jobs/tasks.py``) — worker 는 ``app.py`` 를 import 하지 않아
지금까지 이 프로세스의 예외가 아무 데도 가지 않았다. 배선하면서 두 가지가 같이 걸린다:
web 프로세스에서의 이중 초기화(앞 클라이언트가 교체돼 이벤트가 유실된다)와, DSN 이 없는
워커까지 ``foms.platform``(=app_factory·blueprints) 을 지고 뜨는 콜드스타트 회귀다.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import pathlib
import subprocess
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from db import engine
from models import SideEffectWorkerHeartbeat

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_RUNNER_PATH = _REPO_ROOT / "scripts" / "maintenance" / "run_naver_auto_dispatch.py"

#: 감시 도구가 이 이름으로 행을 찾는다. 러너 상수와 갈리면 하트비트가 있어도 안 보인다.
WORKER_KIND = "NAVER_AUTO_DISPATCH"


class _StopLoop(Exception):
    """테스트가 무한 루프를 끊는 신호(``time.sleep`` 자리에서 던진다)."""


def _load_runner():
    """러너 모듈을 파일 경로로 읽어 온다(``scripts/`` 는 패키지가 아니다).

    Returns:
        실행된 모듈 객체. 테스트마다 새로 읽어 monkeypatch 가 다음 테스트로 새지 않게 한다.
    """
    spec = importlib.util.spec_from_file_location("run_naver_auto_dispatch_ut", _RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def runner(app):
    """갓 읽은 러너 모듈(``app`` 픽스처가 DB 를 출발선으로 되돌린 뒤에 읽는다)."""
    return _load_runner()


def _args(**overrides) -> argparse.Namespace:
    """``start.sh`` 의 ``--loop`` 배선과 같은 기본값을 가진 CLI 인자.

    Args:
        **overrides: 바꿀 필드.

    Returns:
        :class:`argparse.Namespace`.
    """
    values = dict(once=False, force=False, json=True, loop=True,
                  at="16:50", window=10, tick=5)
    values.update(overrides)
    return argparse.Namespace(**values)


def _heartbeats() -> list:
    """``NAVER_AUTO_DISPATCH`` 하트비트 행 전부.

    Returns:
        ``(last_heartbeat_at, metadata_json)`` 행 리스트. 러너가 자기 세션으로 커밋하므로
        ORM 세션을 거치지 않고 엔진에서 직접 읽는다(낡은 식별 맵을 보지 않기 위해).
    """
    table = SideEffectWorkerHeartbeat.__table__
    with engine.connect() as conn:
        return list(conn.execute(
            select(table.c.last_heartbeat_at, table.c.metadata_json)
            .where(table.c.worker_kind == WORKER_KIND)
        ))


def _run_loop_for(runner, monkeypatch, *, ticks: int) -> None:
    """진짜 ``_run_loop`` 를 ``ticks`` 회만 돌린다.

    ``time.sleep`` 은 루프의 예외 방어 **밖**에 있으므로 거기서 던지면 루프가 끝난다 —
    tick 본체의 방어를 우회하지 않고 실제 루프를 그대로 태울 수 있는 유일한 지점이다.
    (전역 ``time.sleep`` 을 건드리지만 monkeypatch 가 테스트 종료 시 되돌린다.)

    Args:
        runner: 러너 모듈.
        monkeypatch: pytest monkeypatch 픽스처.
        ticks: 돌릴 tick 수.

    Returns:
        None.
    """
    seen = {"n": 0}

    def _sleep(_seconds):
        seen["n"] += 1
        if seen["n"] >= ticks:
            raise _StopLoop

    monkeypatch.setattr(runner.time, "sleep", _sleep)
    with pytest.raises(_StopLoop):
        runner._run_loop(_args())
    assert seen["n"] == ticks


# --------------------------------------------------------------------------- #
# 하트비트 (run_naver_auto_dispatch.py)
# --------------------------------------------------------------------------- #

def test_a_loop_tick_outside_the_window_still_writes_the_heartbeat(runner, monkeypatch):
    """일을 안 한 tick 도 하트비트를 남긴다 — 이게 이 배선의 목적이다.

    창 밖 tick 이 갱신을 건너뛰면 하루 23시간 50분 동안 하트비트가 낡아 보여 감시가
    무의미해진다("루프가 죽었다" 와 "지금은 일할 시각이 아니다" 가 구분되지 않는다).
    """
    monkeypatch.setattr(runner, "in_window", lambda *a, **k: False)
    assert _heartbeats() == [], "출발선에 이미 행이 있으면 이 테스트는 아무것도 증명하지 못한다"

    _run_loop_for(runner, monkeypatch, ticks=1)

    rows = _heartbeats()
    assert len(rows) == 1
    assert rows[0].last_heartbeat_at is not None
    assert rows[0].metadata_json["in_window"] is False
    assert rows[0].metadata_json["outcome"] is None


def test_a_second_tick_updates_the_same_heartbeat_row(runner, monkeypatch):
    """두 번째 tick 은 같은 행의 시각만 전진시킨다(ON CONFLICT DO UPDATE).

    행이 늘면 PK 가 아니라 append 로 쌓이고 있다는 뜻이고, 시각이 그대로면 upsert 가
    갱신을 안 하고 있다는 뜻이다 — 둘 다 "살아 있다" 판정을 못 하게 만든다.
    """
    monkeypatch.setattr(runner, "in_window", lambda *a, **k: False)
    at = runner.parse_at("16:50")

    runner._run_tick(_args(), at)
    first = _heartbeats()
    runner._run_tick(_args(), at)
    second = _heartbeats()

    assert len(first) == 1
    assert len(second) == 1, "tick 마다 행이 늘었다 — upsert 가 아니라 insert 다"
    assert second[0].last_heartbeat_at > first[0].last_heartbeat_at


def test_a_failing_heartbeat_does_not_stop_the_dispatch_tick(runner, monkeypatch, caplog):
    """음성 대조군 — 하트비트가 터져도 자동 발송은 그대로 수행되고, 실패는 로그로 남는다.

    되돌릴 수 없는 조작이 관측 배선 때문에 멈추면 더 나쁜 실패다. 동시에 ``except: pass``
    로 삼키면 배선이 없는 것과 같으므로 경고 1건이 반드시 남아야 한다.
    """
    monkeypatch.setattr(runner, "in_window", lambda *a, **k: True)
    dispatched: list = []

    def _dispatch(force):
        dispatched.append(force)
        return {"outcome": "no_target", "date": "2026-09-02",
                "queued": 0, "blocked": 0, "total": 0}

    def _boom(*args, **kwargs):
        raise RuntimeError("side_effect_worker_heartbeats is unreachable")

    monkeypatch.setattr(runner, "_dispatch_once", _dispatch)
    monkeypatch.setattr(runner, "upsert_heartbeat", _boom)

    with caplog.at_level(logging.WARNING, logger="naver_auto_dispatch"):
        runner._run_tick(_args(), runner.parse_at("16:50"))

    assert dispatched == [False], "하트비트 실패가 본 작업(자동 발송)을 막았다"
    records = [r for r in caplog.records if r.name == "naver_auto_dispatch"]
    assert len(records) == 1, "하트비트 실패가 조용히 사라졌다"
    assert records[0].levelno == logging.WARNING
    assert "heartbeat" in records[0].getMessage()
    assert _heartbeats() == []


def test_heartbeat_metadata_never_carries_customer_information(runner, monkeypatch):
    """metadata 는 고정 집계 키만 담는다 — 결과 dict 가 커져도 고객 정보가 새지 않는다."""
    monkeypatch.setattr(runner, "in_window", lambda *a, **k: True)
    monkeypatch.setattr(runner, "_dispatch_once", lambda force: {
        "outcome": "sent", "date": "2026-09-02",
        "queued": 2, "blocked": 1, "total": 3,
        # 서비스가 나중에 결과에 무엇을 더 담더라도 하트비트로 새면 안 된다.
        "orderer_name": "김주문", "receiver_tel": "010-1111-2222",
        "address": "서울시 어딘가 1-2",
    })

    runner._run_tick(_args(), runner.parse_at("16:50"))

    rows = _heartbeats()
    assert len(rows) == 1
    assert rows[0].metadata_json == {
        "in_window": True, "outcome": "sent", "queued": 2, "blocked": 1, "total": 3,
    }


# --------------------------------------------------------------------------- #
# Sentry (foms/services/jobs/tasks.py)
# --------------------------------------------------------------------------- #

def _init_worker_sentry_with(monkeypatch, *, client_active: bool) -> list:
    """DSN 이 있는 상태로 워커 Sentry 배선을 태우고 ``init_sentry`` 호출을 센다.

    Args:
        monkeypatch: pytest monkeypatch 픽스처.
        client_active: 이 프로세스에 이미 Sentry 클라이언트가 붙어 있는가.

    Returns:
        ``init_sentry`` 호출 기록 리스트(길이가 곧 호출 횟수).
    """
    import sentry_sdk

    from foms.platform import sentry_setup
    from foms.services.jobs import tasks

    calls: list = []
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setattr(sentry_sdk, "get_client",
                        lambda: SimpleNamespace(is_active=lambda: client_active))
    monkeypatch.setattr(sentry_setup, "init_sentry", lambda: calls.append(True) or True)

    tasks._init_worker_sentry()
    return calls


def test_worker_initializes_sentry_when_nothing_is_attached_yet(monkeypatch):
    """worker 프로세스(app.py 미경유)에서는 Sentry 를 붙인다 — 없으면 예외가 어디에도 안 간다."""
    assert _init_worker_sentry_with(monkeypatch, client_active=False) == [True]


def test_worker_does_not_reinitialize_sentry_when_a_client_is_already_attached(monkeypatch):
    """음성 대조군 — web 프로세스가 지연 import 해도 두 번째 init 은 하지 않는다.

    ``sentry_sdk.init`` 을 다시 부르면 앞 클라이언트가 통째로 교체돼 그 전송 스레드에
    남아 있던 이벤트가 유실된다.
    """
    assert _init_worker_sentry_with(monkeypatch, client_active=True) == []


def test_worker_sentry_gate_reads_the_same_env_name_as_sentry_setup():
    """게이트가 보는 env 이름은 ``sentry_setup`` 정본과 같아야 한다.

    워커는 그 상수를 import 하지 않는다(그러면 ``foms.platform`` 을 열게 된다). 값을 다시
    적은 대가로 드리프트 위험이 생기므로 여기서 묶는다 — 갈리면 워커가 조용히 Sentry 없이 뜬다.
    """
    from foms.platform.sentry_setup import SENTRY_DSN_ENV
    from foms.services.jobs import tasks

    assert tasks._SENTRY_DSN_ENV == SENTRY_DSN_ENV


def test_worker_task_import_stays_out_of_the_platform_package_without_a_dsn():
    """DSN 이 없으면 워커 import 가 ``foms.platform`` 도 ``sentry_sdk`` 도 열지 않는다.

    ``foms/platform/__init__.py`` 는 app_factory·blueprints 를 통째로 끌어온다. Sentry 배선을
    무심코 모듈 최상단으로 올리면 Sentry 를 쓰지 않는 워커까지 web import 그래프를 지고 뜬다
    (실측 971 → 1,415 모듈). 레이어 래칫은 지연 import 가 **느는** 것만 보므로 최상단으로
    올리는 방향은 아무도 막지 않는다 — 그래서 여기서 막는다.
    """
    env = {k: v for k, v in os.environ.items() if k != "SENTRY_DSN"}
    env["PYTHONIOENCODING"] = "utf-8"
    probe = (
        "import sys\n"
        "import foms.services.jobs.tasks\n"
        "print('platform=%s sdk=%s' % ('foms.platform' in sys.modules,"
        " 'sentry_sdk' in sys.modules))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe], cwd=str(_REPO_ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )

    assert done.returncode == 0, done.stderr
    assert "platform=False sdk=False" in done.stdout, done.stdout


def test_worker_task_import_attaches_sentry_when_a_dsn_is_set():
    """DSN 이 있으면 **모듈 import 만으로** Sentry 가 붙는다(``app.py`` 없이).

    ``rq worker`` 는 이 모듈을 점표기로 import 할 뿐이므로, 배선이 import 시점에 걸려 있지
    않으면 워커 예외는 계속 아무 데도 가지 않는다. ``environment`` 태그가 실제로 실리는지도
    같이 본다 — 태그가 없으면 staging 사고와 운영 사고가 한 통에 섞인다.
    """
    env = dict(os.environ)
    env["SENTRY_DSN"] = "https://public@example.invalid/1"
    env["FOMS_ENV"] = "ut-probe"
    env["PYTHONIOENCODING"] = "utf-8"
    probe = (
        "import foms.services.jobs.tasks\n"
        "import sentry_sdk\n"
        "client = sentry_sdk.get_client()\n"
        "print('active=%s env=%s' % (client.is_active(),"
        " client.options.get('environment')))\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe], cwd=str(_REPO_ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )

    assert done.returncode == 0, done.stderr
    assert "active=True env=ut-probe" in done.stdout, done.stdout
