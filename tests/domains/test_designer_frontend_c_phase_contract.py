"""Static contract checks for FOMSBrainDesigner C-phase frontend wiring."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "Add In Program" / "FOMSBrainDesigner" / "src"


def _read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


def test_iframe_messages_use_same_origin_not_wildcard():
    app = _read("App.tsx")
    review = _read("ui/DrawingReviewWorkspace.tsx")

    assert "postMessage({" in app
    assert "postMessage({" in review
    assert "}, '*')" not in app
    assert "}, '*')" not in review
    assert "e.origin !== SAME_ORIGIN" in app
    assert "e.origin !== SAME_ORIGIN" in review


def test_block_library_and_sketch_are_mounted():
    app = _read("App.tsx")

    assert "BlockLibraryPanel" in app
    assert "SketchCanvas" in app
    assert "rightTab === 'library'" in app
    assert "rightTab === 'sketch'" in app


def test_designer_write_fetches_send_write_header():
    files = [
        "stores/designerStore.ts",
        "ui/BlockLibraryPanel.tsx",
        "ui/SketchCanvas.tsx",
        "ui/InspectorPanel.tsx",
    ]
    for relative in files:
        text = _read(relative)
        assert "'X-FOMS-Designer-Write': '1'" in text, relative


def test_block_list_uses_backend_blocks_array_contract():
    panel = _read("ui/BlockLibraryPanel.tsx")

    assert "data.data?.blocks" in panel
    assert "setBlocks(data.data ?? [])" not in panel
