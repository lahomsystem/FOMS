"""부팅 때 무거운 Jinja 템플릿을 미리 컴파일한다(TEMPLATE-WARM-01).

Jinja 는 템플릿을 **프로세스마다 첫 렌더에서 한 번** 컴파일하고 그 뒤로는 캐시를 쓴다.
그래서 재배포 직후 각 프로세스의 **첫 방문자 한 사람**이 컴파일 비용을 혼자 치른다.

2026-09-12 운영 실측(수집 워크벤치 이력 탭, `X-FOMS-EPT-B7-PHASES`):

    wb_template = 594ms / 9ms / 551ms      ← 같은 구간이 두 값을 낸다
    (그 안 마커 합은 어느 쪽이든 6ms)

로컬에서 컴파일만 따로 재면 원인이 갈린다 — 워크벤치 75ms + pane 파셜 112ms, 두 번째
호출은 0.01ms. 운영은 web 2 replica × gunicorn 2 worker = **4 프로세스**라 배포마다
네 사람이 이 값을 치렀다.

여기서 미리 컴파일하면 그 비용이 **사람이 기다리는 자리에서 부팅으로** 옮겨간다.
렌더 결과를 캐시하는 것이 아니라 **템플릿 코드 객체**만 만들어 두는 것이므로 화면 내용·
권한 판정·요청 컨텍스트와 무관하다. 실패는 무해하다 — 못 데워도 첫 렌더가 그때 컴파일한다.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

#: 데워 둘 템플릿. **컴파일 실측으로 고른 것**이고 추측이 아니다(2026-09-12 로컬 ms).
#: 포함 파셜은 따로 적는다 — 부모를 컴파일해도 `{% include %}` 대상은 첫 렌더에서 컴파일된다.
WARM_TEMPLATES: Sequence[str] = (
    "admin/partials/naver_workbench_pane.html",   # 112ms
    "drawing/partials/workbench_detail_body.html",  # 78ms
    "admin/naver_workbench.html",                 # 75ms
    "measurement/partials/dashboard_main.html",    # 54ms
    "measurement/regional_dashboard.html",         # 47ms
    "orders/index.html",                           # 43ms
    "measurement/metropolitan_dashboard.html",     # 33ms
    "measurement/self_measurement_dashboard.html",  # 23ms
    "partials/shared/layout_head.html",            # 16ms
    "partials/shared/layout_scripts.html",         # 15ms
    "partials/shared/layout_nav.html",             # 10ms
)

#: 부팅을 붙잡는 상한. 닿으면 남은 것은 첫 렌더에 맡긴다 — 워밍이 배포를 늦추는 것이
#: 첫 방문자 한 사람보다 나쁠 수 있어서 시간을 자른다.
DEFAULT_BUDGET_MS = 2500.0


def warm_templates(app: Any, names: Iterable[str] = WARM_TEMPLATES,
                   budget_ms: float = DEFAULT_BUDGET_MS) -> list[tuple[str, float]]:
    """템플릿을 미리 컴파일하고 걸린 시간을 돌려준다.

    Args:
        app: Flask 앱(``jinja_env`` 를 쓴다).
        names: 데울 템플릿 이름들(템플릿 루트 기준 상대 경로).
        budget_ms: 전체 상한(밀리초). 넘으면 **남은 것을 건너뛴다**. 첫 항목은 항상 시도한다.

    Returns:
        ``[(이름, 밀리초), ...]`` — 실제로 컴파일한 것만. 없거나 깨진 템플릿은 빠진다.
    """
    env = getattr(app, "jinja_env", None)
    if env is None:  # pragma: no cover - Flask 앱이면 항상 있다
        return []
    warmed: list[tuple[str, float]] = []
    started = time.perf_counter()
    for index, name in enumerate(names):
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if index and elapsed_ms >= budget_ms:
            logger.info("[TEMPLATE-WARM] 예산 %.0fms 초과 — %s 부터 건너뛴다",
                        budget_ms, name)
            break
        t0 = time.perf_counter()
        try:
            env.get_template(name)
        except Exception:  # noqa: BLE001 - 워밍 실패가 부팅을 깨선 안 된다
            logger.warning("[TEMPLATE-WARM] %s 데우기 실패(무해)", name, exc_info=True)
            continue
        warmed.append((name, (time.perf_counter() - t0) * 1000.0))
    total = sum(ms for _, ms in warmed)
    logger.info("[TEMPLATE-WARM] %s개 템플릿 %.0fms 선컴파일", len(warmed), total)
    return warmed
