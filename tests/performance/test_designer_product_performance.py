"""PG-B12: FOMS Brain Performance Contract Tests.

These tests verify performance budgets for core operations.
They run against the in-process service layer (no HTTP overhead).

Targets from PG-B12:
  - validate p95 < 300ms
  - command preview p95 < 500ms
  - factory regen < 250ms for 100 components
  - parts parse < 50ms for typical table
  - dimension parse < 50ms for typical text
  - ontology map < 100ms per extraction

Tests use timeit-style loops with p95 measurement.
"""

from __future__ import annotations

import statistics
import time
import pytest


def _p95(times: list[float]) -> float:
    return sorted(times)[int(len(times) * 0.95)] * 1000  # ms


# ──────────────────────────────────────────────────────────
# PG-B12-01: Factory regen performance
# ──────────────────────────────────────────────────────────

class TestFactoryRegenPerformance:
    def test_wardrobe_regen_under_250ms(self):
        """Wardrobe regen p95 < 250ms."""
        from foms.services.designer.assembly_factories import (
            WardrobeParams, create_wardrobe_assembly,
        )
        p = WardrobeParams(width=3000, height=2400, depth=620, module_count=5)
        times = []
        for _ in range(20):
            t0 = time.monotonic()
            create_wardrobe_assembly(p)
            times.append(time.monotonic() - t0)
        p95 = _p95(times)
        assert p95 < 250, f"Wardrobe regen p95={p95:.1f}ms exceeds 250ms"

    def test_shoe_rack_regen_under_100ms(self):
        from foms.services.designer.factories.shoe_rack import (
            create_shoe_rack_assembly, ShoeRackParams,
        )
        p = ShoeRackParams(tier_count=6)
        times = []
        for _ in range(20):
            t0 = time.monotonic()
            create_shoe_rack_assembly(p)
            times.append(time.monotonic() - t0)
        assert _p95(times) < 100

    def test_kitchen_base_regen_under_200ms(self):
        from foms.services.designer.factories.kitchen import (
            create_kitchen_base_assembly, KitchenBaseParams,
        )
        p = KitchenBaseParams(module_count=5)
        times = []
        for _ in range(20):
            t0 = time.monotonic()
            create_kitchen_base_assembly(p)
            times.append(time.monotonic() - t0)
        assert _p95(times) < 200


# ──────────────────────────────────────────────────────────
# PG-B12-02: Validator performance
# ──────────────────────────────────────────────────────────

class TestValidatorPerformance:
    def test_validate_wardrobe_under_300ms(self):
        """Validator p95 < 300ms (API target)."""
        from foms.services.designer.assembly_factories import (
            WardrobeParams, create_wardrobe_assembly,
        )
        from foms.services.designer.constraint_engine import validate_design_graph
        graph = create_wardrobe_assembly(WardrobeParams(module_count=5))
        graph_dict = graph.to_dict()
        times = []
        for _ in range(30):
            t0 = time.monotonic()
            validate_design_graph(graph_dict)
            times.append(time.monotonic() - t0)
        p95 = _p95(times)
        assert p95 < 300, f"Validate p95={p95:.1f}ms exceeds 300ms"


# ──────────────────────────────────────────────────────────
# PG-B12-03: Parser performance
# ──────────────────────────────────────────────────────────

class TestParserPerformance:
    PARTS_TEXT = "\n".join([
        "[SR] 60*2440=6",
        "[EP] 70*2440=4",
        "[DOOR] 595*345=3",
        "마이다 2",
        "옷봉 1",
        "보조목 3",
        "서랍 2",
    ] * 5)

    DIMENSION_TEXT = "W 2400\nH 2200\nD 620\n현장규격 2400*500*2200\n250/300/250/300"

    def test_parts_parse_under_50ms(self):
        from foms.services.designer.parts_table_parser import parse_text
        times = []
        for _ in range(50):
            t0 = time.monotonic()
            parse_text(self.PARTS_TEXT)
            times.append(time.monotonic() - t0)
        assert _p95(times) < 50

    def test_dimension_parse_under_50ms(self):
        from foms.services.designer.dimension_parser import parse_ocr_text
        times = []
        for _ in range(50):
            t0 = time.monotonic()
            parse_ocr_text(self.DIMENSION_TEXT)
            times.append(time.monotonic() - t0)
        assert _p95(times) < 50


# ──────────────────────────────────────────────────────────
# PG-B12-04: Ontology mapper performance
# ──────────────────────────────────────────────────────────

class TestOntologyMapperPerformance:
    EXTRACTION = {
        "furniture_type": "wardrobe",
        "extracted_params": {
            "width": 2400, "height": 2200, "depth": 620,
            "module_widths": [800, 800, 800],
        },
        "confidence": 0.9,
        "parts_table": [{"code": "[SR]"}, {"code": "[EP]"}],
    }

    def test_build_candidate_under_100ms(self):
        from foms.services.designer.ontology_mapper import build_candidate
        times = []
        for _ in range(30):
            t0 = time.monotonic()
            build_candidate(self.EXTRACTION, run_validator=True)
            times.append(time.monotonic() - t0)
        assert _p95(times) < 100


# ──────────────────────────────────────────────────────────
# PG-B12-05: RAG retrieval performance (empty DB)
# ──────────────────────────────────────────────────────────

class TestRAGPerformance:
    def test_rag_context_under_200ms(self):
        """build_rag_context with empty DB under 200ms."""
        from foms.services.designer.design_retrieval import build_rag_context
        times = []
        for _ in range(10):
            t0 = time.monotonic()
            build_rag_context(furniture_type="wardrobe", width_mm=2400)
            times.append(time.monotonic() - t0)
        assert _p95(times) < 200
