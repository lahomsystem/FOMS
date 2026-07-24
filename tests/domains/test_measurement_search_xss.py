"""FE-XSS — measurement dashboard search term must not be a raw JS-string sink.

P0-5: three measurement dashboards injected the user search term into a JS
string literal via ``const searchQuery = "{{ search_query|safe }}";`` — a
hostile ``</script>`` / quote payload broke out and executed. Root fix: emit
the value with Flask's ``tojson`` (HTML-safe JSON), which escapes ``< > & '``
to unicode and quotes the literal.

This test (1) statically forbids the vulnerable pattern in the measurement
templates and (2) proves Flask's ``tojson`` neutralises a hostile payload.
The full hostile-browser persona check lives in the §6 acceptance gate.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEASURE_DIR = ROOT / "templates" / "measurement"

# The three dashboards that carried the sink.
SINK_TEMPLATES = [
    "metropolitan_dashboard.html",
    "regional_dashboard.html",
    "self_measurement_dashboard.html",
]


def test_no_raw_safe_search_query_sink() -> None:
    """No measurement template may pipe search_query through |safe into JS."""
    offenders: list[str] = []
    for path in MEASURE_DIR.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"search_query\s*\|\s*safe", text):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, f"search_query|safe sink still present: {offenders}"


def test_search_query_uses_tojson() -> None:
    """Each dashboard assigns searchQuery via tojson (escaped literal)."""
    missing: list[str] = []
    for name in SINK_TEMPLATES:
        text = (MEASURE_DIR / name).read_text(encoding="utf-8")
        if "search_query" not in text:
            continue  # search removed entirely is also acceptable
        if not re.search(r"searchQuery\s*=\s*\{\{\s*\(?search_query.*tojson", text):
            missing.append(name)
    assert not missing, f"searchQuery not emitted via tojson in: {missing}"


def test_flask_tojson_neutralises_hostile_search() -> None:
    """Flask's tojson must escape a </script> breakout payload."""
    import app as app_module

    flask_app = getattr(app_module, "app", None) or app_module.create_app()
    hostile = '</script><script>alert(1)</script>"'
    rendered = flask_app.jinja_env.from_string(
        "const searchQuery = {{ (search_query or '')|tojson }};"
    ).render(search_query=hostile)

    payload = rendered.split("=", 1)[1].strip().rstrip(";").strip()
    # No literal breakout sequence survives.
    assert "</script>" not in rendered, rendered
    # It is a valid JS/JSON string literal that round-trips to the original.
    assert json.loads(payload) == hostile, rendered
