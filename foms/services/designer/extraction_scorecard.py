"""FOMS Brain PG-B0A — Extraction Scorecard.

Computes precision/recall/field accuracy for furniture drawing extraction.

Contract:
- Scorecard compares extraction result against approved expected JSON.
- wdh_accuracy target: >= 95% (PG-B6 acceptance)
- parts_recall target: >= 90% (PG-B5 acceptance)
- No extraction result is accepted as ground truth without human approval.
- Scorecard is run against fixture corpus (PG-B2: 17 drawings).
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Thresholds (from PG plan acceptance criteria)
# ──────────────────────────────────────────────────────────

WDH_ACCURACY_TARGET = 0.95   # W/D/H extraction accuracy target
PARTS_RECALL_TARGET = 0.90   # Parts table recall target
WDH_TOLERANCE_MM = 5         # ±5mm tolerance for dimension matching


# ──────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────

@dataclass
class FieldScore:
    """Score for a single extraction field."""
    field_name: str
    extracted_value: Any
    expected_value: Any
    correct: bool
    tolerance_used: bool = False
    notes: str = ""


@dataclass
class ExtractionScore:
    """Score for a single drawing extraction against approved expected JSON."""
    fixture_id: str
    furniture_type_correct: bool
    wdh_scores: list[FieldScore] = field(default_factory=list)
    parts_scores: list[FieldScore] = field(default_factory=list)
    field_scores: list[FieldScore] = field(default_factory=list)
    latency_ms: int = 0
    cost_usd: float = 0.0
    error: str | None = None

    @property
    def wdh_accuracy(self) -> float:
        """W/D/H field accuracy (0.0–1.0). Tolerates ±WDH_TOLERANCE_MM mm."""
        if not self.wdh_scores:
            return 0.0
        return sum(1 for s in self.wdh_scores if s.correct) / len(self.wdh_scores)

    @property
    def parts_recall(self) -> float:
        """Parts table recall: correct parts / expected parts."""
        if not self.parts_scores:
            return 1.0  # no parts expected → not penalized
        return sum(1 for s in self.parts_scores if s.correct) / len(self.parts_scores)

    @property
    def overall_score(self) -> float:
        """Weighted overall score: 60% W/D/H + 30% parts + 10% furniture_type."""
        ft_score = 1.0 if self.furniture_type_correct else 0.0
        return (
            0.60 * self.wdh_accuracy
            + 0.30 * self.parts_recall
            + 0.10 * ft_score
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "furniture_type_correct": self.furniture_type_correct,
            "wdh_accuracy": round(self.wdh_accuracy, 4),
            "parts_recall": round(self.parts_recall, 4),
            "overall_score": round(self.overall_score, 4),
            "latency_ms": self.latency_ms,
            "cost_usd": round(self.cost_usd, 6),
            "error": self.error,
            "wdh_scores": [
                {
                    "field": s.field_name,
                    "extracted": s.extracted_value,
                    "expected": s.expected_value,
                    "correct": s.correct,
                }
                for s in self.wdh_scores
            ],
            "parts_scores": [
                {
                    "code": s.field_name,
                    "correct": s.correct,
                    "notes": s.notes,
                }
                for s in self.parts_scores
            ],
        }


@dataclass
class ScorecardReport:
    """Aggregate scorecard over all fixture drawings."""
    scores: list[ExtractionScore] = field(default_factory=list)
    run_timestamp: str = ""
    model: str = ""
    fixture_manifest_path: str = ""

    @property
    def total_fixtures(self) -> int:
        return len(self.scores)

    @property
    def error_count(self) -> int:
        return sum(1 for s in self.scores if s.error is not None)

    @property
    def mean_wdh_accuracy(self) -> float:
        valid = [s.wdh_accuracy for s in self.scores if s.error is None]
        return statistics.mean(valid) if valid else 0.0

    @property
    def mean_parts_recall(self) -> float:
        valid = [s.parts_recall for s in self.scores if s.error is None]
        return statistics.mean(valid) if valid else 0.0

    @property
    def mean_overall_score(self) -> float:
        valid = [s.overall_score for s in self.scores if s.error is None]
        return statistics.mean(valid) if valid else 0.0

    @property
    def total_cost_usd(self) -> float:
        return sum(s.cost_usd for s in self.scores)

    @property
    def latency_p95_ms(self) -> int:
        latencies = sorted(s.latency_ms for s in self.scores if s.error is None)
        if not latencies:
            return 0
        idx = int(len(latencies) * 0.95)
        return latencies[min(idx, len(latencies) - 1)]

    @property
    def wdh_gate_pass(self) -> bool:
        """True if mean W/D/H accuracy meets PG-B6 target (>= 95%)."""
        return self.mean_wdh_accuracy >= WDH_ACCURACY_TARGET

    @property
    def parts_gate_pass(self) -> bool:
        """True if mean parts recall meets PG-B5 target (>= 90%)."""
        return self.mean_parts_recall >= PARTS_RECALL_TARGET

    def summary(self) -> dict[str, Any]:
        return {
            "total_fixtures": self.total_fixtures,
            "error_count": self.error_count,
            "mean_wdh_accuracy": round(self.mean_wdh_accuracy, 4),
            "mean_parts_recall": round(self.mean_parts_recall, 4),
            "mean_overall_score": round(self.mean_overall_score, 4),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "latency_p95_ms": self.latency_p95_ms,
            "wdh_gate_pass": self.wdh_gate_pass,
            "parts_gate_pass": self.parts_gate_pass,
            "model": self.model,
            "run_timestamp": self.run_timestamp,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "per_fixture": [s.to_dict() for s in self.scores],
        }


# ──────────────────────────────────────────────────────────
# Scoring functions
# ──────────────────────────────────────────────────────────

def score_wdh(
    extracted_params: dict[str, Any],
    expected_params: dict[str, Any],
    fixture_id: str,
) -> list[FieldScore]:
    """Score W/D/H dimensions with ±WDH_TOLERANCE_MM tolerance."""
    scores = []
    for dim in ("width", "depth", "height"):
        extracted = extracted_params.get(dim)
        expected = expected_params.get(dim)
        if expected is None:
            # Field not in expected JSON — skip (not counted)
            continue
        if extracted is None:
            scores.append(FieldScore(
                field_name=dim,
                extracted_value=None,
                expected_value=expected,
                correct=False,
                notes="missing",
            ))
            continue
        try:
            diff = abs(int(extracted) - int(expected))
            correct = diff <= WDH_TOLERANCE_MM
        except (TypeError, ValueError):
            correct = False
            diff = -1
        scores.append(FieldScore(
            field_name=dim,
            extracted_value=extracted,
            expected_value=expected,
            correct=correct,
            tolerance_used=correct and diff > 0,
            notes=f"diff={diff}mm" if diff >= 0 else "type_error",
        ))
    return scores


def score_parts_table(
    extracted_parts: list[dict[str, Any]],
    expected_parts: list[dict[str, Any]],
    fixture_id: str,
) -> list[FieldScore]:
    """Score parts table by code-level recall.

    A part code is recalled correctly if extracted_parts contains that code
    (case-insensitive). Quantity matching is tracked but not penalized.
    """
    if not expected_parts:
        return []

    extracted_codes = {
        str(p.get("code", "")).upper().strip()
        for p in extracted_parts
    }

    scores = []
    for ep in expected_parts:
        code = str(ep.get("code", "")).upper().strip()
        correct = code in extracted_codes
        scores.append(FieldScore(
            field_name=code,
            extracted_value=code if correct else None,
            expected_value=code,
            correct=correct,
            notes="" if correct else "not_found_in_extraction",
        ))
    return scores


def score_single_extraction(
    fixture_id: str,
    extracted: dict[str, Any],
    expected: dict[str, Any],
) -> ExtractionScore:
    """Score one extraction result against one approved expected JSON.

    Args:
        fixture_id: Drawing fixture identifier.
        extracted: Raw dict from gemini_provider or vision_extractor.
        expected: Human-approved expected JSON dict.

    Returns:
        ExtractionScore with per-field results.
    """
    metrics = extracted.get("_metrics", {})
    score = ExtractionScore(
        fixture_id=fixture_id,
        furniture_type_correct=(
            extracted.get("furniture_type") == expected.get("furniture_type")
        ),
        latency_ms=metrics.get("latency_ms", 0),
        cost_usd=metrics.get("cost_usd", 0.0),
    )

    score.wdh_scores = score_wdh(
        extracted.get("extracted_params", {}),
        expected.get("extracted_params", {}),
        fixture_id,
    )
    score.parts_scores = score_parts_table(
        extracted.get("parts_table", []),
        expected.get("parts_table", []),
        fixture_id,
    )
    return score


# ──────────────────────────────────────────────────────────
# Fixture manifest loader
# ──────────────────────────────────────────────────────────

def load_fixture_manifest(manifest_path: str | Path) -> dict[str, Any]:
    """Load and return fixture manifest JSON.

    Returns:
        dict with 'fixtures' list.

    Raises:
        FileNotFoundError: If manifest does not exist.
        ValueError: If manifest format is invalid.
    """
    path = Path(manifest_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Fixture manifest not found: {path}. "
            "Run PG-B2 to create the drawing fixture corpus."
        )
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if "fixtures" not in data:
        raise ValueError(f"Invalid manifest: missing 'fixtures' key in {path}")
    return data


def get_available_fixtures(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return fixtures with file_status='available' and non-null expected_json."""
    return [
        f for f in manifest.get("fixtures", [])
        if f.get("file_status") == "available"
        and f.get("expected_json") is not None
    ]


# ──────────────────────────────────────────────────────────
# Scorecard runner
# ──────────────────────────────────────────────────────────

def run_scorecard_from_manifest(
    manifest_path: str | Path,
    extractor_fn: Any,  # callable(image_path: str) -> dict
    model: str = "gemini-2.0-flash",
) -> ScorecardReport:
    """Run extraction scorecard over all available fixtures in manifest.

    Args:
        manifest_path: Path to fixture manifest JSON.
        extractor_fn: Function that takes image_path str and returns extraction dict.
        model: Gemini model name used (for report metadata).

    Returns:
        ScorecardReport with per-fixture and aggregate results.
    """
    import datetime

    manifest = load_fixture_manifest(manifest_path)
    available = get_available_fixtures(manifest)

    if not available:
        logger.warning(
            "[SCORECARD] No available fixtures found in %s. "
            "Add drawings with file_status='available' and approved expected_json.",
            manifest_path,
        )

    report = ScorecardReport(
        run_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        model=model,
        fixture_manifest_path=str(manifest_path),
    )

    for fixture in available:
        fid = fixture["id"]
        image_path = fixture.get("file_path", "")
        expected = fixture.get("expected_json", {})

        try:
            extracted = extractor_fn(image_path)
            score = score_single_extraction(fid, extracted, expected)
        except Exception as exc:
            logger.error("[SCORECARD] fixture=%s error=%s", fid, exc)
            score = ExtractionScore(
                fixture_id=fid,
                furniture_type_correct=False,
                error=str(exc),
            )
        report.scores.append(score)

    logger.info(
        "[SCORECARD] done fixtures=%d errors=%d wdh=%.2f parts=%.2f cost=$%.4f",
        report.total_fixtures,
        report.error_count,
        report.mean_wdh_accuracy,
        report.mean_parts_recall,
        report.total_cost_usd,
    )
    return report
