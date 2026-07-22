"""Shell FOUC audit — page-local CSS in full-page styles/head must also ride in fragment.

erp-shell `preloadFragmentStylesheets` only extracts `<link rel=stylesheet>` from fragment
HTML before #main-content swap. CSS that lives only in `{% block styles %}` / `head_extra`
never loads on bottom-tab / rail first entry.

This module is a static source audit (no HTTP): for each FRAGMENT_READY tab, every
stylesheet token listed in the full-page styles surface must appear in the fragment
template (or a body partial the fragment includes).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from foms.services.common.erp_navigation_contract import ERP_FRAGMENT_READY_PATHS

ROOT = Path(__file__).resolve().parents[2]

# path -> (full_page_html, fragment_or_body_html that shell returns)
# Stylesheet tokens are harvested from the full page's styles/head_extra blocks
# (and for pages without those blocks, from known body includes).
_TAB_TEMPLATES: dict[str, tuple[str, tuple[str, ...]]] = {
    "/erp/dashboard": (
        "templates/orders/dashboard.html",
        ("templates/orders/partials/dashboard_main.html",),
    ),
    "/erp/measurement": (
        "templates/measurement/dashboard.html",
        ("templates/measurement/partials/dashboard_fragment.html",),
    ),
    "/erp/drawing-workbench": (
        "templates/drawing/workbench_dashboard.html",
        ("templates/drawing/partials/workbench_dashboard_fragment.html",),
    ),
    "/erp/production/dashboard": (
        "templates/production/dashboard.html",
        ("templates/production/partials/dashboard_fragment.html",),
    ),
    "/erp/shipment": (
        "templates/shipment/dashboard.html",
        ("templates/shipment/partials/dashboard_fragment.html",),
    ),
    "/erp/as": (
        "templates/cs/as_dashboard.html",
        (
            "templates/cs/partials/as_dashboard_fragment.html",
            "templates/cs/partials/as_dashboard_body.html",
        ),
    ),
    "/erp/construction/dashboard": (
        "templates/construction/dashboard.html",
        ("templates/construction/partials/dashboard_fragment.html",),
    ),
    "/erp/completion": (
        "templates/cs/completion_dashboard.html",
        (
            "templates/cs/partials/completion_dashboard_fragment.html",
            "templates/cs/partials/completion_dashboard_body.html",
            "templates/cs/partials/completion_styles.html",
        ),
    ),
    "/erp/history/": (
        "templates/orders/history_dashboard.html",
        (
            "templates/orders/partials/history_dashboard_fragment.html",
            "templates/orders/partials/history_dashboard_body.html",
        ),
    ),
}

_LINK_RE = re.compile(
    r"""url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+\.css)['\"]""",
    re.IGNORECASE,
)
_BLOCK_STYLES_RE = re.compile(
    r"\{%\s*block\s+(?:styles|head|head_extra)\s*%\}(.*?)\{%\s*endblock",
    re.IGNORECASE | re.DOTALL,
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _page_local_css_from_full(full_html: str) -> list[str]:
    """Collect .css filenames from styles/head/head_extra blocks (not whole file)."""
    blocks = _BLOCK_STYLES_RE.findall(full_html)
    if not blocks:
        return []
    found: list[str] = []
    for block in blocks:
        for name in _LINK_RE.findall(block):
            if name not in found:
                found.append(name)
    return found


def test_fragment_ready_paths_have_template_map():
    """Every FRAGMENT_READY path must be covered by this audit map."""
    assert set(ERP_FRAGMENT_READY_PATHS) == set(_TAB_TEMPLATES.keys())


@pytest.mark.parametrize("path", list(ERP_FRAGMENT_READY_PATHS))
def test_shell_fragment_includes_full_page_stylesheet_links(path: str):
    """Full-page styles/head CSS links must also appear in the shell fragment tree."""
    full_rel, frag_rels = _TAB_TEMPLATES[path]
    full = _read(full_rel)
    required = _page_local_css_from_full(full)
    if not required:
        # Page keeps CSS in body includes (AS/completion/history) or inline only (drawing).
        return

    frag_blob = "\n".join(_read(rel) for rel in frag_rels)
    missing = [name for name in required if name not in frag_blob]
    assert not missing, (
        f"{path}: page-local CSS missing from shell fragment → FOUC on first tab entry. "
        f"missing={missing} full={full_rel} fragment={frag_rels}"
    )


def test_orders_dashboard_fragment_runtime_css(client, monkeypatch):
    """HTTP: orders fragment must carry cs-hero + call-log (same ?v= as dashboard.html)."""
    from werkzeug.security import generate_password_hash

    from db import db_session
    from models import User

    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = User(
        username="fouc_orders_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="FOUC Orders Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    for token in (
        "foms-v2-cs-hero.css') }}?v=20260714a",
        "foms-call-log.css') }}?v=20260712b",
    ):
        assert token in _read("templates/orders/dashboard.html")
        assert token in _read("templates/orders/partials/dashboard_main.html")

    frag = client.get(
        "/erp/dashboard?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    ).get_data(as_text=True)
    assert "foms-v2-cs-hero.css" in frag
    assert "foms-call-log.css" in frag
    assert "v=20260714a" in frag
    assert "v=20260712b" in frag


def test_shipment_dashboard_fragment_runtime_css(client, monkeypatch):
    """HTTP: shipment fragment must carry packing (+ shipment-mobile when not v3)."""
    from werkzeug.security import generate_password_hash

    from db import db_session
    from models import User

    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    user = User(
        username="fouc_shipment_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        team="CS",
        name="FOUC Shipment Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    # v2 셸(비-v3): shipment-mobile + packing 둘 다 렌더. V2 자격=FOMS_V3_SHELL_COHORT.
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    monkeypatch.delenv("FOMS_SHELL_V3_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_SHELL_V3_COHORT", raising=False)
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role

    frag = client.get(
        "/erp/shipment?view=fragment",
        headers={"X-FOMS-ERP-SHELL": "1"},
    ).get_data(as_text=True)
    assert "foms-packing.css" in frag
    assert "v=20260714a" in frag
    assert "foms-shipment-mobile.css" in frag
    assert "v=20260721a" in frag


def test_tablet_split_order_detail_fragment_has_wdc_split_css():
    """HTMX tablet split fragment must carry erp-wdc-split.css (no layout head)."""
    frag = _read("templates/partials/shared/foms_order_detail_fragment.html")
    edit = _read("templates/orders/edit_order.html")
    token = "erp-wdc-split.css') }}?v=20260713a"
    assert token in edit
    assert token in frag
