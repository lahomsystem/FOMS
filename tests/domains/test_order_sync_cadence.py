"""수집 루프의 하트비트 주기 분리 계약 (2026-09-09).

수집 루프는 1800초마다 한 번 일한다. 예전에는 그 1800 을 그대로 신고해서 예산이
max(등록부 900, 1800 x 3) = 5400초가 됐고, 잠든 사이 프로세스가 죽으면 감시 주기 60초를
더해 **최대 90분 넘게** 아무도 몰랐다.

예산을 좁히는 것은 답이 아니다 — 스윕이 길어지는 복구 직후에 헛알림이 나 2026-09-08
사고가 그대로 되돌아온다(`docs/incidents/2026-09-09-worker-watchdog-false-stall-flap.md`).
그래서 **일하는 주기와 살아 있다고 말하는 주기를 나눈다**: 잠을 60초로 쪼개 조각마다
하트비트를 남기고 조각은 60 을 신고해 예산을 900 으로 좁히되, 스윕 **앞** 하트비트는
1800 을 신고해 스윕 구간 예산을 5400 으로 넓힌다.

이 파일은 `test_worker_loop_heartbeat.py` 에서 갈라져 나왔다(500줄 래칫).
"""
from __future__ import annotations

import importlib.util
import pathlib
from types import SimpleNamespace

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# 하트비트 주기 분리 (run_naver_order_sync.py)
#
# 수집 루프는 1800초마다 한 번 일한다. 예전에는 그 1800 을 그대로 신고해서 예산이
# max(등록부 900, 1800 x 3) = 5400초가 됐고, 잠든 사이에 프로세스가 죽으면 감시 주기
# 60초를 더해 **최대 90분 넘게** 아무도 몰랐다. 예산을 좁히는 것은 답이 아니다(스윕이
# 길어지는 복구 직후에 헛알림이 나 2026-09-08 사고가 되돌아온다). 그래서 잠을 60초로
# 쪼개 조각마다 하트비트를 남기고, **조각 하트비트만** 60 을 신고해 예산을 900 으로
# 좁힌다. 스윕 직전 하트비트는 1800 을 신고해 스윕 구간의 예산을 5400 으로 되넓힌다.
# --------------------------------------------------------------------------- #

_ORDER_SYNC_PATH = _REPO_ROOT / "scripts" / "maintenance" / "run_naver_order_sync.py"

#: 운영 수집 주기(초). ``start.sh`` 가 ``FOMS_NAVER_SYNC_INTERVAL_SECONDS`` 로 넣는 실측값.
_ORDER_SYNC_INTERVAL = 1800

#: 잠 한 조각의 길이(초) = 계약이 요구하는 값. 러너 상수를 읽어 오지 않고 여기 다시 적는다 —
#: 러너가 이 값을 바꾸면(예 600초) 감지 지연이 도로 늘어나므로 그때 빨개져야 한다.
_ORDER_SYNC_TICK = 60


class _StopCadence(BaseException):
    """주기 테스트가 무한 루프를 끊는 신호.

    ``_run_loop`` 의 스윕 방어(``except Exception``)에 잡히면 루프가 계속 돌아 테스트가
    멎지 않으므로 :class:`BaseException` 을 상속한다.
    """


def _load_order_sync():
    """수집 루프 러너를 파일 경로로 새로 읽어 온다(``scripts/`` 는 패키지가 아니다).

    Returns:
        실행된 모듈 객체. 테스트마다 새로 읽어 monkeypatch 가 새지 않게 한다.
    """
    spec = importlib.util.spec_from_file_location("run_naver_order_sync_ut", _ORDER_SYNC_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _drive_cadence(monkeypatch, *, interval: int = _ORDER_SYNC_INTERVAL):
    """진짜 ``_run_loop`` 를 잠 한 주기만 태우고 sleep·하트비트·스윕 호출을 기록한다.

    끊는 지점은 **잠의 총합이 ``interval`` 에 닿은 뒤 처음 나오는 하트비트**다. 잠을 어떻게
    쪼개든(안 쪼개든) "한 주기" 라는 기준이 같고, 스윕 직전 하트비트까지 기록에 들어온다.

    하트비트는 PK upsert 라 DB 에는 마지막 1건만 남는다 — 신고값의 **순서**를 봐야 하므로
    러너 쪽 ``emit_heartbeat`` 이름을 갈아 호출을 그대로 모은다. ``time.sleep`` 은 루프의
    스윕 방어 밖에 있어, 진짜 루프를 우회 없이 태울 수 있는 지점이다.

    Args:
        monkeypatch: pytest monkeypatch 픽스처.
        interval: ``_run_loop`` 에 넘길 스윕 주기(초).

    Returns:
        ``naps``(sleep 인자)·``beats``(하트비트 metadata)·``sweeps``(스윕이 받은 dry_run
        인자)와 셋을 시간순으로 엮은 ``events`` 를 담은 :class:`types.SimpleNamespace`.
    """
    naps: list = []
    beats: list = []
    sweeps: list = []
    # ('sleep'|'beat'|'sweep', 값) 순서 기록 — 하트비트가 잠 조각 뒤에 온 것인지를
    # 자리번호가 아니라 사실로 가른다(스윕 앞뒤 하트비트가 늘어도 계약이 안 흔들린다).
    events: list = []

    def _sleep(seconds):
        naps.append(seconds)
        events.append(("sleep", seconds))
        # 설계가 깨져 끊는 지점에 못 닿으면 무한 루프가 된다 — 매달리는 대신 실패시킨다.
        assert len(naps) <= 10 * _ORDER_SYNC_INTERVAL // _ORDER_SYNC_TICK, "루프가 끊기지 않았다"

    def _sweep(dry_run):
        sweeps.append(dry_run)
        events.append(("sweep", dry_run))
        return {"changed": 0, "candidates": 0, "created": 0, "pending_review": 0}

    def _emit(_engine, _kind, *, metadata=None, logger=None, **_kw):
        beats.append(dict(metadata or {}))
        events.append(("beat", dict(metadata or {})))
        if sum(naps) >= interval:
            raise _StopCadence

    runner_module = _load_order_sync()
    monkeypatch.setattr(runner_module, "_sweep_once", _sweep)
    monkeypatch.setattr(runner_module, "emit_heartbeat", _emit)
    monkeypatch.setattr(runner_module.time, "sleep", _sleep)

    with pytest.raises(_StopCadence):
        runner_module._run_loop(interval, False, True)
    return SimpleNamespace(naps=naps, beats=beats, sweeps=sweeps, events=events)


def test_the_order_sync_loop_splits_its_sleep_into_one_minute_naps(monkeypatch):
    """한 번에 1800초를 자면 그 사이 아무 생존 신호도 없다 — 60초씩 쪼개 잔다.

    이 한 줄이 "진짜로 멎어도 90분 침묵" 을 없애는 구조 그 자체다. 잠이 한 덩어리면
    신고값을 어떻게 손봐도 다음 신호까지의 공백이 1800초라 예산을 좁힐 수 없다.
    """
    seen = _drive_cadence(monkeypatch)

    assert seen.naps == [_ORDER_SYNC_TICK] * (_ORDER_SYNC_INTERVAL // _ORDER_SYNC_TICK), (
        f"잠이 쪼개지지 않았다(sleep 인자={sorted(set(seen.naps))}, 호출={len(seen.naps)}회)")


def test_naps_declare_a_one_minute_gap_so_the_budget_narrows(monkeypatch):
    """자는 동안의 하트비트는 60 을 신고한다 — 예산이 max(900, 60x3) = 900 으로 좁혀진다.

    신고값이 예산의 유일한 입력이다(``effective_heartbeat_budget``). 조각을 남기면서
    1800 을 신고하면 조각을 아무리 잘게 쪼개도 예산은 5400 그대로라 감지가 안 빨라진다.
    """
    seen = _drive_cadence(monkeypatch)

    # 잠 조각 하트비트 = 직전 이벤트가 sleep 인 것. 마지막 조각 뒤 하트비트는 곧바로
    # 스윕이 오므로 예산을 되넓히는 것이 계약이라(아래 전용 테스트) 여기서 뺀다.
    after_naps = [cur[1] for prev, cur in zip(seen.events, seen.events[1:])
                  if prev[0] == "sleep" and cur[0] == "beat"]
    during_sleep = [beat["interval_seconds"] for beat in after_naps[:-1]]
    assert len(during_sleep) == _ORDER_SYNC_INTERVAL // _ORDER_SYNC_TICK - 1, (
        f"자는 동안의 하트비트가 {len(during_sleep)}건뿐이다")
    assert set(during_sleep) == {_ORDER_SYNC_TICK}, (
        f"조각 하트비트가 신고한 값={sorted(set(during_sleep))} — 60 이 아니면 예산이 안 좁혀진다")


def test_the_heartbeat_just_before_a_sweep_widens_the_budget_back(monkeypatch):
    """마지막 조각 뒤 하트비트는 1800 을 신고한다 — 스윕 중 헛알림을 막는 유일한 방어다.

    마지막 조각이 끝나면 곧바로 스윕이 시작된다. 거기서 60 을 신고하면 예산이 900 이라
    15분 넘는 스윕이 곧 헛알림이 된다. ``resolve_window`` 에는 구간 상한이 없어 며칠
    멎었다 살아난 첫 스윕은 24시간씩 쪼개 여러 번 돈다 — 그 복구 직후가 정확히 이번
    사고(2026-09-08)를 되풀이하는 경로다.
    """
    seen = _drive_cadence(monkeypatch)

    assert seen.beats[-1]["interval_seconds"] == _ORDER_SYNC_INTERVAL, (
        "스윕 직전 하트비트가 예산을 되넓히지 않았다"
        f"(신고={seen.beats[-1]['interval_seconds']})")


def test_loop_declares_the_sweep_budget_before_its_first_sweep(monkeypatch):
    """첫 스윕 **전에** 넓은 예산을 신고한다 — 재배포 직후가 무방비가 되면 안 된다.

    죽기 직전 표에 남은 신고가 tick(60)이면 예산은 900 이다. 재배포 + 부팅 + 밀린 구간을
    따라잡는 첫 스윕(``resolve_window`` 에 구간 상한이 없다)이 그보다 길면, 멀쩡히
    따라잡는 중인 루프에 2026-09-08 과 같은 헛알림이 난다.
    """
    seen = _drive_cadence(monkeypatch)

    first_sweep = next(i for i, (kind, _) in enumerate(seen.events) if kind == "sweep")
    before = [ev[1]["interval_seconds"] for ev in seen.events[:first_sweep] if ev[0] == "beat"]
    assert before, "첫 스윕 전에 하트비트가 하나도 없다 — 그 구간이 무방비다"
    assert before[-1] == _ORDER_SYNC_INTERVAL, (
        f"첫 스윕 직전 신고={before[-1]} — 스윕 구간 예산이 안 넓혀졌다")


def test_the_beat_after_a_sweep_declares_the_nap_not_the_sweep(monkeypatch):
    """스윕 직후 하트비트는 60 을 신고한다 — 그 다음에 오는 것은 스윕이 아니라 낮잠이다.

    여기서 1800 을 신고하면 잠자는 구간의 예산이 90분으로 되넓어져, 잠을 쪼갠 의미가
    매 주기 60초씩 사라진다(그 창에서 죽으면 90분 침묵).
    """
    seen = _drive_cadence(monkeypatch)

    after_sweep = next(cur[1] for prev, cur in zip(seen.events, seen.events[1:])
                       if prev[0] == "sweep" and cur[0] == "beat")
    assert after_sweep["interval_seconds"] == _ORDER_SYNC_TICK, (
        f"스윕 직후 신고={after_sweep['interval_seconds']} — 낮잠 구간이 90분 예산을 받는다")


def test_splitting_the_sleep_does_not_add_a_single_naver_call(monkeypatch):
    """음성 대조군 — 잠을 30조각으로 쪼개도 스윕은 한 주기에 1회다.

    커머스API 애플리케이션의 호출 IP 한도가 3개뿐이라 네이버로 나가는 HTTP 는 늘리면
    안 된다. 늘어도 되는 것은 하트비트 DB upsert 뿐이다. 조각마다 스윕까지 부르면
    쿼터가 30배로 타므로 여기서 못 박는다.
    """
    seen = _drive_cadence(monkeypatch)

    assert sum(seen.naps) == _ORDER_SYNC_INTERVAL, "한 주기만큼 자지 않았다"
    assert seen.sweeps == [False], f"한 주기에 스윕이 {len(seen.sweeps)}회 돌았다"
