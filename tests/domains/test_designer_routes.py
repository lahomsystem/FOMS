"""FOMS Brain AX Designer - Route smoke tests (B1)."""

import os
import pytest


@pytest.mark.parametrize("path", [
    "/wdplanner-v2",
])
def test_designer_route_redirects_unauthenticated(client, path):
    """Unauthenticated request must redirect to login (login_required)."""
    resp = client.get(path)
    assert resp.status_code in (302, 401)


def test_designer_app_setup_page(client, auth_client):
    """When static/designer/index.html does not exist, setup page is served."""
    designer_index = os.path.join("static", "designer", "index.html")
    if os.path.exists(designer_index):
        pytest.skip("static/designer/index.html exists; skipping setup fallback test")
    resp = auth_client.get("/wdplanner-v2/app")
    assert resp.status_code == 200
    assert b"FOMSBrainDesigner" in resp.data or b"FOMS Brain" in resp.data or b"npm run build" in resp.data


def test_designer_blueprint_registered(app):
    """designer blueprint must be registered in the app."""
    rules = [str(rule) for rule in app.url_map.iter_rules()]
    assert "/wdplanner-v2" in rules
    assert "/wdplanner-v2/app" in rules
