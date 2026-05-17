"""Static contract checks for FOMSBrainDesigner C-phase frontend wiring."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "Add In Program" / "FOMSBrainDesigner" / "src"
TEMPLATE = ROOT / "templates" / "designer" / "wdplanner_v2.html"


def _read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


def _read_template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


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


def test_block_library_shows_current_design_module_candidates():
    panel = _read("ui/BlockLibraryPanel.tsx")

    assert "const localCandidates = useMemo<BlockDef[]>" in panel
    assert "현재 설계 후보" in panel
    assert "초안 저장" in panel
    assert "include_drafts=true" in panel


def test_cabinet_scene_renders_box_components_as_transparent_layout_shells():
    scene = _read("canvas/CabinetScene.tsx")

    assert "const isLayoutBox = c.kind === 'box'" in scene
    assert "depthWrite={!isLayoutBox}" in scene
    assert "wireframe={isLayoutBox}" in scene


def test_wdplanner_load_to_3d_prefers_fresh_candidate_graph():
    template = _read_template()

    assert "const freshDesignGraph = candidate.design_graph_candidate || json.data.design_graph_candidate || currentDesignGraphCandidate || null" in template
    assert "currentDesignGraphCandidate = freshDesignGraph" in template
    assert "design_graph: freshDesignGraph" in template


def test_wdplanner_save_learning_discloses_raw_sample_storage():
    template = _read_template()

    assert "designer_corrections" in template
    assert "after_json.redacted_extraction" in template
    assert "승인 corpus가 아니며 검수/재학습 분석용 샘플입니다." in template
    assert "Gemini 학습 컨텍스트" not in template
