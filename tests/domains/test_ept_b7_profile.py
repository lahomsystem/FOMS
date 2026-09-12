"""EPT-B7: render profiling helper + static asset presence."""
import time
from pathlib import Path

from flask import Response

from foms.services.common.ept_b7_profile import (
    HEADER_RENDER_MS,
    HEADER_ROUTE,
    apply_ept_b7_render_headers,
    format_phases,
    template_mark,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_apply_ept_b7_render_headers_sets_diagnostic_headers() -> None:
    """Headers document Jinja render time only; not used for authorization."""
    resp = Response()
    apply_ept_b7_render_headers(resp, route_id="erp_test", render_ms=12.3456)
    assert resp.headers[HEADER_ROUTE] == "erp_test"
    assert resp.headers[HEADER_RENDER_MS] == "12.3"


def test_ept_b7_page_scoped_assets_exist() -> None:
    """HTML diet moved inline blocks to these paths (full + fragment parity)."""
    assert (_REPO_ROOT / "static/css/contexts/orders/dashboard-gateway-notifications.css").is_file()
    assert (_REPO_ROOT / "static/js/orders/dashboard-notifications.js").is_file()
    assert (_REPO_ROOT / "static/css/contexts/cs/as-dashboard-body.css").is_file()
    assert (_REPO_ROOT / "static/css/contexts/shipment/dashboard-table-extras.css").is_file()


def test_template_mark_records_a_span_between_paired_calls() -> None:
    """템플릿 안 쌍 호출이 구간 하나를 만들어 헤더로 나온다."""
    import app as _app_module

    flask_app = _app_module.app
    with flask_app.test_request_context("/"):
        assert template_mark("hist_rows") == ""
        time.sleep(0.01)
        assert template_mark("hist_rows") == ""
        phases = format_phases()
    assert "hist_rows=" in phases
    value = float(phases.split("hist_rows=")[1].split(";")[0])
    assert value >= 9.0


def test_template_mark_alone_records_nothing() -> None:
    """짝이 없는 한 번 호출은 기록하지 않는다(음성 대조군)."""
    import app as _app_module

    with _app_module.app.test_request_context("/"):
        template_mark("lonely")
        assert "lonely" not in format_phases()


def test_template_mark_outside_request_is_silent() -> None:
    """요청 밖에서 불려도 예외 없이 빈 문자열."""
    assert template_mark("no_request") == ""


def test_mark_is_registered_as_a_jinja_global() -> None:
    """셸 파셜이 `mark` 를 부른다 — 전역이 빠지면 모든 페이지가 UndefinedError 로 죽는다."""
    import app as _app_module

    assert _app_module.app.jinja_env.globals.get("mark") is template_mark


def test_template_marks_are_balanced_pairs() -> None:
    """마커는 **짝**이어야 구간이 된다. 홀수면 그 이름은 조용히 사라진다."""
    import re
    from collections import Counter

    watched = [
        "templates/admin/naver_workbench.html",
        "templates/partials/shared/layout_head.html",
        "templates/partials/shared/layout_nav.html",
        "templates/partials/shared/layout_scripts.html",
    ]
    counts: Counter = Counter()
    for rel in watched:
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        counts.update(re.findall(r"\{\{\s*mark\('([a-z0-9_]+)'\)\s*\}\}", text))
    assert counts, "마커가 하나도 없다 — 계측이 통째로 사라졌다"
    odd = {name: n for name, n in counts.items() if n % 2}
    assert not odd, f"짝이 안 맞는 마커: {odd}"
