"""워커 프로세스의 Sentry 배선 계약 (F-7, 2026-09-09 한 벌로 통일).

``start.sh`` 의 루프들은 ``&`` 로 뜨는 **별개 프로세스**라 프로세스마다 init 이 필요하다.
``capture_exception``(loop_heartbeat)은 스스로 초기화하지 않으므로, init 없는 프로세스는
DSN 을 넣어도 한 건도 보내지 않는다 — 큐 소비 본체(``run_rq_worker``)가 정확히 그랬다.

더 큰 문제는 배선 방식이 러너마다 달랐다는 것이다: 사설 복제본 2벌이 있었고 그중 하나는
env 이름을 문자열로 박아 정본 상수 일치 계약 밖에 있었다(갈라짐이 이미 시작돼 있었다).
여기서 지키는 것은 **전 러너가 같은 공용 게이트를 진입 함수에서 부른다** 하나다.

이 파일은 `test_loop_heartbeat_wiring.py` 에서 갈라져 나왔다(500줄 래칫).
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
from types import SimpleNamespace

import pytest

from foms.services import loop_heartbeat

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_START_SH = _REPO_ROOT / "start.sh"
_RQ_RUNNER = _REPO_ROOT / "tools" / "ops" / "run_rq_worker.py"


def _loop_runners_in_start_sh() -> list:
    """``start.sh`` 가 ``--loop`` 로 띄우는 러너 파일 이름들(중복 제거·정렬).

    모집단을 코드가 아니라 ``start.sh`` 에서 읽는 것이 핵심이다 — 새 루프를 배선하면서
    Sentry 를 빠뜨리면 그 순간 이 파일이 빨개진다.
    """
    text = _START_SH.read_text(encoding="utf-8")
    found = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "--loop" not in stripped:
            continue
        match = re.search(r"scripts/maintenance/([A-Za-z0-9_]+)\.py", stripped)
        if match:
            found.add(match.group(1))
    return sorted(found)


def _load(path: pathlib.Path):
    """스크립트를 파일 경로로 읽어 온다(``scripts/``·``tools/`` 는 패키지가 아니다)."""
    spec = importlib.util.spec_from_file_location(f"{path.stem}_ut", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# 5. SIDEFX outbox 워커 — 잡은 예외가 Sentry 로 간다 (F-7)
# --------------------------------------------------------------------------- #
def _init_sentry_with(monkeypatch, *, dsn: str, client_active: bool) -> list:
    """``init_sentry_once`` 를 주어진 상태에서 돌리고 init 호출 횟수를 돌려준다."""
    import sentry_sdk
    from foms.platform import sentry_setup

    calls = []
    if dsn:
        monkeypatch.setenv(loop_heartbeat.SENTRY_DSN_ENV, dsn)
    else:
        monkeypatch.delenv(loop_heartbeat.SENTRY_DSN_ENV, raising=False)
    monkeypatch.setattr(sentry_sdk, "get_client",
                        lambda: SimpleNamespace(is_active=lambda: client_active))
    monkeypatch.setattr(sentry_setup, "init_sentry", lambda: calls.append(True) or True)

    loop_heartbeat.init_sentry_once()
    return calls


def test_worker_sentry_is_attached_when_a_dsn_is_set(monkeypatch):
    """app.py 를 안 거치는 워커도 DSN 이 있으면 Sentry 를 붙인다."""
    assert _init_sentry_with(monkeypatch, dsn="https://public@example.invalid/1",
                             client_active=False) == [True]


def test_worker_sentry_is_not_reinitialized(monkeypatch):
    """음성 대조군 — 이미 붙어 있으면 다시 부르지 않는다(앞 클라이언트가 교체된다)."""
    assert _init_sentry_with(monkeypatch, dsn="https://public@example.invalid/1",
                             client_active=True) == []


def test_worker_sentry_is_skipped_without_a_dsn(monkeypatch):
    """DSN 이 없으면 아무것도 하지 않는다(foms.platform 을 열지 않기 위해서다)."""
    assert _init_sentry_with(monkeypatch, dsn="", client_active=False) == []


def test_sentry_env_name_matches_the_platform_constant():
    """게이트가 보는 env 이름이 정본과 갈리면 워커가 조용히 Sentry 없이 뜬다."""
    from foms.platform.sentry_setup import SENTRY_DSN_ENV

    assert loop_heartbeat.SENTRY_DSN_ENV == SENTRY_DSN_ENV


def test_outbox_worker_initializes_sentry_and_reports_step_failures(monkeypatch):
    """SIDEFX 워커의 잡은 예외가 지금까지 아무 데도 안 갔다 — 이제 Sentry 로 간다."""
    outbox = _load(_REPO_ROOT / "tools" / "ops" / "run_domain_side_effect_outbox.py")
    captured = []
    monkeypatch.setattr(outbox, "capture_exception", lambda *a, **k: captured.append(True))

    def _boom():
        raise RuntimeError("delivery step exploded")

    assert outbox._safe(_boom, "delivery") is False
    assert captured == [True], "잡은 예외가 Sentry 로 안 갔다"
    assert outbox._safe(lambda: None, "delivery") is True
    assert captured == [True], "성공한 step 까지 Sentry 로 보냈다"


def test_outbox_worker_calls_the_sentry_gate_on_startup():
    """호출처가 없으면 배선이 있어도 안 붙는다 — main 이 게이트를 부르는지 본다."""
    source = (_REPO_ROOT / "tools" / "ops" / "run_domain_side_effect_outbox.py").read_text(
        encoding="utf-8")
    assert "init_sentry_once(" in source.split("def main(", 1)[1]


# --------------------------------------------------------------------------- #
# 6. Sentry 게이트 배선 — 워커 프로세스마다 자기 init 이 있다 (B)
# --------------------------------------------------------------------------- #
#: 공용 게이트 호출만 인정하는 패턴. 앞에 ``_`` 가 붙은 사설 복제본
#: (``run_geocode_sweep._init_sentry_once``)은 여기서 통과하지 못한다 — 같은 일을 두 벌로
#: 두면 한쪽만 고쳐지고(실측: 복제본은 env 이름을 문자열로 하드코딩해 SENTRY_DSN_ENV
#: 정본 일치 계약 밖에 있다) 그 갈라짐을 아무도 못 본다.
_SENTRY_GATE_CALL = re.compile(r"(?<![A-Za-z0-9_])init_sentry_once\(")


def _entry_runner_paths() -> list:
    """워커 컨테이너가 프로세스로 띄우는 러너들의 저장소 상대 경로.

    ``start.sh`` 의 ``--loop`` 러너 목록(:func:`_loop_runners_in_start_sh`)을 그대로 재사용해
    뽑는다. 이름을 손으로 나열하지 않는 것이 요점이다 — 다음 사람이 새 루프를 배선하면
    목록에 자동으로 들어와 Sentry 배선을 빠뜨릴 수 없다.

    Returns:
        경로 문자열 목록(큐 소비 본체 러너를 마지막에 붙인다).
    """
    paths = [f"scripts/maintenance/{name}.py" for name in _loop_runners_in_start_sh()]
    paths.append(str(_RQ_RUNNER.relative_to(_REPO_ROOT)).replace("\\", "/"))
    return paths


def _entry_function_name(source: str) -> str:
    """``if __name__ == '__main__':`` 이 실제로 부르는 진입 함수 이름.

    진입 함수 이름을 테스트에 적어 두면 러너마다 ``run``/``main`` 으로 갈리는 현실과
    어긋난다 — 프로세스의 진짜 시작점은 ``__main__`` 가드가 부르는 그 함수다.

    Args:
        source: 러너 파일 전문.

    Returns:
        진입 함수 이름(예 ``run``·``main``).

    Raises:
        AssertionError: ``__main__`` 가드가 없거나 함수를 부르지 않을 때.
    """
    tail = re.split(r"^if __name__ == ['\"]__main__['\"]:", source, maxsplit=1, flags=re.M)
    assert len(tail) == 2, "__main__ 가드가 없다 — 프로세스 진입점을 특정할 수 없다"
    match = re.search(r"(?:sys\.exit|SystemExit)\(\s*([A-Za-z_][A-Za-z0-9_]*)\(", tail[1])
    assert match, f"__main__ 가드가 진입 함수를 부르지 않는다: {tail[1][:80]!r}"
    return match.group(1)


def test_sentry_gate_population_is_not_empty():
    """음성 대조군 — 목록을 못 뽑으면 아래 파라미터화가 조용히 0건으로 통과한다."""
    paths = _entry_runner_paths()
    assert len(paths) >= 6, paths
    assert "tools/ops/run_rq_worker.py" in paths, paths
    for rel in paths:
        assert (_REPO_ROOT / rel).is_file(), rel


@pytest.mark.parametrize("runner_rel", _entry_runner_paths())
def test_every_worker_process_calls_the_sentry_gate_at_its_entry(runner_rel):
    """워커 프로세스는 저마다 자기 Sentry init 을 갖는다.

    ``start.sh`` 의 루프들은 ``&`` 로 뜨는 **별개 프로세스**라 프로세스마다 init 이 필요하다.
    ``capture_exception``(loop_heartbeat)은 스스로 초기화하지 않으므로, init 없는 프로세스는
    DSN 을 넣어도 한 건도 보내지 않는다(실측: run_rq_worker 는 import 직후
    ``sentry_sdk.get_client().is_active()`` 가 False 였다).

    ``_run_loop`` 이 아니라 **진입 함수**에서 찾는 이유: ``--once`` 로 손으로 돌리는 운영
    실행도 같은 관측을 받아야 하고, 루프 안에 두면 "프로세스당 1회" 를 코드가 아니라 우연이
    보장하게 된다.
    """
    source = (_REPO_ROOT / runner_rel).read_text(encoding="utf-8")
    entry = _entry_function_name(source)
    body = source.split(f"def {entry}(", 1)
    assert len(body) == 2, f"{runner_rel} 에 진입 함수 def {entry}( 가 없다"
    # 진입 함수 **본문까지만** 본다. 파일 끝까지 훑으면 그 아래 헬퍼 안의 호출이 대신
    # 통과시켜, 정작 진입 함수에서 배선이 빠져도 초록이 된다.
    body[1] = re.split(r"^(?:def |class |if __name__)", body[1], maxsplit=1, flags=re.M)[0]
    assert _SENTRY_GATE_CALL.search(body[1]), (
        f"{runner_rel} 의 {entry}() 가 init_sentry_once( 를 부르지 않는다 — "
        "이 프로세스의 예외는 아무 데도 가지 않는다"
    )
