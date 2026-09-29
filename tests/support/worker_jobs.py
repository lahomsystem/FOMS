"""WORKER 배경 작업 배선의 정본(``tools/ops/worker_supervisor.py`` 의 ``worker_jobs``)을 읽는 시험 도우미.

2026-09-29 까지는 ``start.sh`` 의 ``&`` 줄이 배선의 정본이라 여러 시험이 그 글자를 읽었다.
이제 작업 목록은 감독자 모듈에 있으므로, 시험은 여기서 같은 모집단을 얻는다 — 새 루프를
배선하면 자동으로 모든 계약(하트비트 등록·Sentry·켜짐 조건)에 들어온다.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
SUPERVISOR_PATH = REPO_ROOT / "tools" / "ops" / "worker_supervisor.py"


def load_supervisor():
    """감독자 모듈을 저장소 경로에서 직접 로드한다(부작용 없음 — 앱 import 없음)."""
    spec = importlib.util.spec_from_file_location("worker_supervisor_under_test", SUPERVISOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 가 자기 모듈을 sys.modules 에서 찾는다
    spec.loader.exec_module(module)
    return module


class AllEnabled(dict):
    """``*_ENABLED`` 로 끝나는 켜짐 조건은 모두 "1" 로 보이게 하는 env."""

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:  # type: ignore[override]
        if key in self:
            return super().get(key)
        return "1" if key.endswith("_ENABLED") else default


def jobs(env: Optional[Mapping[str, str]] = None, *, all_enabled: bool = False) -> list:
    """``worker_jobs`` 결과. ``all_enabled`` 면 켜짐 조건 env 를 모두 켠 상태."""
    mod = load_supervisor()
    source = AllEnabled(env or {}) if all_enabled else dict(env or {})
    return mod.worker_jobs(source, python="python")


def loop_runner_names() -> list:
    """켜질 수 있는 ``--loop`` 러너들의 파일 이름(``scripts/maintenance/<name>.py``), 정렬."""
    names = set()
    for job in jobs(all_enabled=True):
        if "--loop" not in job.argv:
            continue
        for part in job.argv:
            if part.startswith("scripts/maintenance/") and part.endswith(".py"):
                names.add(part[len("scripts/maintenance/"):-3])
    return sorted(names)


def job_by_script(script_stem: str, env: Optional[Mapping[str, str]] = None, *, all_enabled: bool = False):
    """``scripts/maintenance/<script_stem>.py`` 를 돌리는 작업(없으면 None)."""
    target = f"scripts/maintenance/{script_stem}.py"
    for job in jobs(env, all_enabled=all_enabled):
        if target in job.argv:
            return job
    return None


def worker_branch_of_start_sh() -> str:
    """``start.sh`` 의 ``USE_RQ_WORKER=1`` 분기 본문."""
    text = (REPO_ROOT / "start.sh").read_text(encoding="utf-8")
    return text.split('if [ "$USE_RQ_WORKER" = "1" ]; then', 1)[1].split("\nelse\n", 1)[0]


def web_branch_of_start_sh() -> str:
    """``start.sh`` 의 web(gunicorn) 분기 본문."""
    text = (REPO_ROOT / "start.sh").read_text(encoding="utf-8")
    return text.split("\nelse\n", 1)[1]
