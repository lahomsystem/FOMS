"""Queue big pytest runs (2+ xdist workers) so only one runs at a time on this machine.

Spec: docs/specs/2026-11-07-test-run-speed_SPEC.md §2.1.

Why: several Claude / Codex / Cursor windows share one Windows PC. When two full
suites overlap, each takes about 5 times longer (measured 230 s alone vs 1,257 s
overlapped). The xdist workers (about 1 GB each) also run the commit charge out,
and runs die with MemoryError. pytest itself holds a named mutex, so every
session and every tool gets the same rule without remembering it.

- Windows only. CI (Linux) does nothing.
- Only the xdist master with numprocesses >= 2 takes the lock. Single-process
  runs of a few files never wait.
- If the holder dies, Windows marks the mutex abandoned and the next run takes
  it at once, so no stale lock can remain.
- After MAX_WAIT_S the run stops waiting, prints a warning and proceeds, so a
  hung run cannot block everyone forever.
- FOMS_PYTEST_NO_LOCK=1 turns it off.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Mapping

MUTEX_NAME = "Local\\FOMS_PYTEST_BIG_RUN"
INFO_FILE = os.path.join(os.environ.get("TEMP") or os.environ.get("TMP") or ".", "foms_pytest_big_run.json")
WAIT_STEP_MS = 30_000
MAX_WAIT_S = 30 * 60

_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED = 0x00000080
_WAIT_TIMEOUT = 0x00000102

_state: dict[str, Any] = {}


def should_lock(platform: str, is_worker: bool, numprocesses: Any, env: Mapping[str, str]) -> bool:
    """Decide whether this pytest process must queue (pure function, unit tested)."""
    if platform != "win32" or is_worker:
        return False
    if env.get("FOMS_PYTEST_NO_LOCK") == "1":
        return False
    if isinstance(numprocesses, str):
        return numprocesses in ("auto", "logical")
    try:
        return int(numprocesses or 0) >= 2
    except (TypeError, ValueError):
        return False


def _say(config: Any, message: str) -> None:
    """Print past pytest's output capture so a waiting user sees it at once."""
    line = f"[FOMS 줄 서기] {message}"
    capman = config.pluginmanager.getplugin("capturemanager") if config is not None else None
    try:
        if capman is not None:
            with capman.global_and_fixture_disabled():
                print(line, flush=True)
            return
    except Exception:
        pass
    print(line, file=sys.__stderr__, flush=True)


def _holder() -> str:
    try:
        with open(INFO_FILE, encoding="utf-8") as fh:
            info = json.load(fh)
        return f"PID {info.get('pid')} · {info.get('cwd')} · {info.get('started')} 시작"
    except Exception:
        return "누구인지 모름"


def acquire(config: Any = None) -> bool:
    """Wait for the machine-wide mutex. True = held (release later), False = proceeding without it."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    k32.WaitForSingleObject.restype = wintypes.DWORD
    k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)

    handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return False
    started = time.monotonic()
    announced = False
    while True:
        rc = k32.WaitForSingleObject(handle, 0 if not announced else WAIT_STEP_MS)
        if rc in (_WAIT_OBJECT_0, _WAIT_ABANDONED):
            break
        if rc != _WAIT_TIMEOUT:
            k32.CloseHandle(handle)
            return False
        waited = int(time.monotonic() - started)
        if waited >= MAX_WAIT_S:
            _say(config, f"{waited // 60}분을 기다렸지만 앞 시험({_holder()})이 안 끝나 기다리지 않고 시작합니다.")
            k32.CloseHandle(handle)
            return False
        _say(config, f"다른 창의 큰 시험이 끝나기를 기다립니다 — {_holder()} (기다린 시간 {waited}초)")
        announced = True
    if announced:
        _say(config, f"앞 시험이 끝났습니다. {int(time.monotonic() - started)}초 기다린 뒤 시작합니다.")
    _state["handle"] = handle
    _state["k32"] = k32
    try:
        with open(INFO_FILE, "w", encoding="utf-8") as fh:
            json.dump(
                {"pid": os.getpid(), "cwd": os.getcwd(), "started": time.strftime("%H:%M:%S")},
                fh,
                ensure_ascii=False,
            )
    except Exception:
        pass
    return True


def release() -> None:
    handle = _state.pop("handle", None)
    k32 = _state.pop("k32", None)
    if not handle or k32 is None:
        return
    try:
        with open(INFO_FILE, encoding="utf-8") as fh:
            mine = json.load(fh).get("pid") == os.getpid()
        if mine:
            os.remove(INFO_FILE)
    except Exception:
        pass
    k32.ReleaseMutex(handle)
    k32.CloseHandle(handle)


def configure(config: Any) -> None:
    is_worker = hasattr(config, "workerinput")
    numprocesses = getattr(config.option, "numprocesses", 0)
    if should_lock(sys.platform, is_worker, numprocesses, os.environ):
        acquire(config)


def unconfigure(config: Any) -> None:
    release()
