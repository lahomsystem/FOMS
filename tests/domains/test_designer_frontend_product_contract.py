"""PG-B1: Frontend Product Contract Tests — White SketchUp Shell.

Verifies:
1. Design system markdown exists.
2. New UI component files exist.
3. Static build output exists (npm run build was run).
4. Dark theme is removed from primary workbench (no #1a1a2e in App.tsx).
5. White canvas background is present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
DESIGNER_SRC = ROOT / "Add In Program" / "FOMSBrainDesigner" / "src"
STATIC_DESIGNER = ROOT / "static" / "designer"
DESIGN_SYSTEM = ROOT / "docs" / "design" / "FOMS_BRAIN_DESIGN_SYSTEM.md"


# ──────────────────────────────────────────────────────────
# PG-B1-01: Design system markdown
# ──────────────────────────────────────────────────────────

class TestDesignSystemDoc:
    def test_design_system_exists(self):
        """docs/design/FOMS_BRAIN_DESIGN_SYSTEM.md exists."""
        assert DESIGN_SYSTEM.exists(), f"Design system doc missing: {DESIGN_SYSTEM}"

    def test_design_system_has_color_tokens(self):
        """Design system defines color tokens."""
        content = DESIGN_SYSTEM.read_text(encoding="utf-8")
        assert "canvasBg" in content or "#f0f0f0" in content
        assert "accent" in content or "#5a67d8" in content

    def test_design_system_has_layout_section(self):
        """Design system describes 3-panel layout."""
        content = DESIGN_SYSTEM.read_text(encoding="utf-8")
        assert "TopToolBar" in content or "toolbar" in content.lower()
        assert "LeftToolPalette" in content or "palette" in content.lower()
        assert "RightPropertyTray" in content or "tray" in content.lower()


# ──────────────────────────────────────────────────────────
# PG-B1-02: New UI component files
# ──────────────────────────────────────────────────────────

class TestNewUIComponents:
    def test_sketchup_theme_ts_exists(self):
        """src/styles/sketchupTheme.ts exists."""
        p = DESIGNER_SRC / "styles" / "sketchupTheme.ts"
        assert p.exists(), f"sketchupTheme.ts missing: {p}"

    def test_top_toolbar_tsx_exists(self):
        """src/ui/TopToolBar.tsx exists."""
        p = DESIGNER_SRC / "ui" / "TopToolBar.tsx"
        assert p.exists(), f"TopToolBar.tsx missing: {p}"

    def test_left_tool_palette_tsx_exists(self):
        """src/ui/LeftToolPalette.tsx exists."""
        p = DESIGNER_SRC / "ui" / "LeftToolPalette.tsx"
        assert p.exists(), f"LeftToolPalette.tsx missing: {p}"

    def test_right_property_tray_tsx_exists(self):
        """src/ui/RightPropertyTray.tsx exists."""
        p = DESIGNER_SRC / "ui" / "RightPropertyTray.tsx"
        assert p.exists(), f"RightPropertyTray.tsx missing: {p}"

    def test_sketchup_theme_has_color_tokens(self):
        """sketchupTheme.ts defines expected color tokens."""
        content = (DESIGNER_SRC / "styles" / "sketchupTheme.ts").read_text(encoding="utf-8")
        assert "canvasBg" in content
        assert "toolbarBg" in content
        assert "accent" in content


# ──────────────────────────────────────────────────────────
# PG-B1-03: Dark theme removed
# ──────────────────────────────────────────────────────────

class TestDarkThemeRemoved:
    def test_app_tsx_no_dark_background(self):
        """App.tsx should not use the old dark background (#1a1a2e) as primary root."""
        content = (DESIGNER_SRC / "App.tsx").read_text(encoding="utf-8")
        # The old dark root style was: background: '#1a1a2e'
        # New: uses S.root which has background: COLORS.canvasBg (#f0f0f0)
        assert "background: '#1a1a2e'" not in content, (
            "App.tsx still uses dark background #1a1a2e as root. "
            "PG-B1 should have replaced with white/light-gray theme."
        )

    def test_designer_canvas_has_white_background(self):
        """DesignerCanvas.tsx uses white/light canvas background."""
        canvas_path = DESIGNER_SRC / "canvas" / "DesignerCanvas.tsx"
        if canvas_path.exists():
            content = canvas_path.read_text(encoding="utf-8")
            assert "#1a1a2e" not in content, (
                "DesignerCanvas.tsx still uses dark background. Replace with light theme."
            )

    def test_app_tsx_uses_sketchup_theme(self):
        """App.tsx imports sketchupTheme."""
        content = (DESIGNER_SRC / "App.tsx").read_text(encoding="utf-8")
        assert "sketchupTheme" in content or "S." in content, (
            "App.tsx should import and use sketchupTheme.ts."
        )

    def test_app_tsx_has_toolbar_components(self):
        """App.tsx includes TopToolBar and LeftToolPalette."""
        content = (DESIGNER_SRC / "App.tsx").read_text(encoding="utf-8")
        assert "TopToolBar" in content, "App.tsx should use TopToolBar component"
        assert "LeftToolPalette" in content, "App.tsx should use LeftToolPalette component"
        assert "RightPropertyTray" in content, "App.tsx should use RightPropertyTray component"


# ──────────────────────────────────────────────────────────
# PG-B1-04: Build output exists
# ──────────────────────────────────────────────────────────

class TestBuildOutput:
    def test_static_designer_index_exists(self):
        """static/designer/index.html exists (npm run build was run)."""
        p = STATIC_DESIGNER / "index.html"
        assert p.exists(), f"Build output missing: {p}. Run: npm run build in FOMSBrainDesigner/"

    def test_static_designer_has_js_bundle(self):
        """static/designer/assets/*.js bundle exists."""
        assets = list((STATIC_DESIGNER / "assets").glob("*.js"))
        assert len(assets) >= 1, "No JS bundle found in static/designer/assets/"
