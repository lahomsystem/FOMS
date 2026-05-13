"""FOMS Brain AX Designer - Blueprint registration contract tests."""


def test_designer_blueprint_is_importable():
    """designer_bp must be importable from foms.web.designer."""
    from foms.web.designer import designer_bp
    assert designer_bp is not None
    assert designer_bp.name == "designer"


def test_designer_blueprint_registered_in_app(app):
    """designer blueprint must be registered in the Flask app."""
    bp_names = [bp for bp in app.blueprints]
    assert "designer" in bp_names


def test_designer_routes_exist(app):
    """/wdplanner-v2 and /wdplanner-v2/app routes must exist."""
    rules = {str(r): r for r in app.url_map.iter_rules()}
    assert "/wdplanner-v2" in rules, "/wdplanner-v2 route not found"
    assert "/wdplanner-v2/app" in rules, "/wdplanner-v2/app route not found"
    assert "/wdplanner-v2/app/<path:filename>" in rules, "static asset route not found"
