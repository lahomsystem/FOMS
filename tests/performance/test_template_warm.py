"""TEMPLATE-WARM-01: 부팅 선컴파일 계약.

Jinja 컴파일은 프로세스마다 첫 렌더 1회다 — 그 값을 사람이 기다리는 자리에서 부팅으로
옮긴다. 여기서 지키는 것 넷: 실제로 캐시에 들어가는가, 목록이 실재하는 템플릿인가,
없는 이름이 부팅을 깨지 않는가, 예산이 실제로 자르는가.
"""

from pathlib import Path

import app as app_module
from foms.services.common.template_warm import (
    WARM_TEMPLATES,
    warm_templates,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_warm_templates_compiles_and_caches() -> None:
    """데운 템플릿은 Jinja 캐시에 들어가고, 두 번째 조회는 사실상 0이다."""
    flask_app = app_module.app
    env = flask_app.jinja_env
    env.cache.clear()  # type: ignore[union-attr]

    warmed = warm_templates(flask_app, ["admin/naver_workbench.html"])

    assert [name for name, _ in warmed] == ["admin/naver_workbench.html"]
    # 캐시에 실제로 있는지 — 없으면 워밍이 아무 일도 안 한 것이다.
    import time

    t0 = time.perf_counter()
    env.get_template("admin/naver_workbench.html")
    second_ms = (time.perf_counter() - t0) * 1000.0
    assert second_ms < 5.0, f"두 번째 조회가 {second_ms:.1f}ms — 캐시가 안 먹었다"


def test_warm_list_names_exist_on_disk() -> None:
    """목록이 옛 경로를 들고 있으면 워밍이 조용히 아무것도 안 한다."""
    missing = [
        name for name in WARM_TEMPLATES
        if not (_REPO_ROOT / "templates" / name).is_file()
    ]
    assert not missing, f"templates/ 에 없는 워밍 대상: {missing}"


def test_missing_template_does_not_raise() -> None:
    """워밍 실패는 무해해야 한다 — 못 데워도 첫 렌더가 그때 컴파일한다."""
    warmed = warm_templates(app_module.app, ["does/not/exist.html"])
    assert warmed == []


def test_budget_stops_after_the_first_entry() -> None:
    """예산 0 이면 첫 항목만 시도하고 나머지는 건너뛴다(부팅을 붙잡지 않는다)."""
    warmed = warm_templates(
        app_module.app,
        ["admin/naver_workbench.html", "admin/partials/naver_workbench_pane.html"],
        budget_ms=0.0,
    )
    assert len(warmed) == 1


def test_factory_warms_only_on_deployed() -> None:
    """배선이 사라지거나 dev 까지 데우면 red — 부팅 지연을 dev 에 떠넘기지 않는다."""
    source = (_REPO_ROOT / "foms/platform/app_factory.py").read_text(encoding="utf-8")
    assert "warm_templates(app)" in source, "app_factory 의 워밍 호출이 사라졌다"
    gate = source.split("warm_templates(app)")[0]
    tail = gate.rstrip().splitlines()[-1]
    assert "is_production or is_railway" in tail, (
        f"워밍이 배포 게이트 밖에 있다 — 직전 줄: {tail!r}")
