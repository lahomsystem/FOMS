"""FOMS Brain Post-V1 — Vision Input Types.

PV2-B5: VisionInput contract.

Vision NEVER modifies design_json directly.
Flow: intake -> manual calibration -> fake/real extractor -> candidate -> human review -> apply.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


VISION_SOURCES = frozenset({"drawing_photo", "site_photo", "manual_upload"})
PERSPECTIVE_MODES = frozenset({"frontal", "oblique", "top_down", "unknown"})
VALID_FURNITURE_TYPES = frozenset({"wardrobe", "shoe_rack", "kitchen_base", "kitchen_wall", "custom_storage"})


@dataclass
class CalibrationParams:
    """Manual calibration so vision coordinates can be converted to mm."""
    known_length_mm: Optional[int] = None       # known real-world dimension in image
    image_segment_px: Optional[int] = None      # pixel span of that known length
    origin_hint: Optional[str] = None           # e.g. "top_left_corner"
    perspective_mode: str = "unknown"

    def is_calibrated(self) -> bool:
        return (
            self.known_length_mm is not None
            and self.image_segment_px is not None
            and self.image_segment_px > 0
        )

    def px_to_mm(self, px: float) -> float:
        if not self.is_calibrated():
            raise ValueError("Calibration incomplete — known_length_mm and image_segment_px required")
        scale = self.known_length_mm / self.image_segment_px
        return px * scale


@dataclass
class VisionInput:
    """Raw image intake record. Does NOT contain design truth."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    image_url: Optional[str] = None          # URL or path
    attachment_id: Optional[int] = None      # FOMS attachment id
    source: str = "manual_upload"
    calibration: CalibrationParams = field(default_factory=CalibrationParams)
    target_furniture_type: Optional[str] = None
    notes: Optional[str] = None
    project_id: Optional[int] = None

    def validate(self) -> list[str]:
        """Return list of validation errors."""
        errors: list[str] = []
        if not self.image_url and not self.attachment_id:
            errors.append("image_url 또는 attachment_id 중 하나는 필요합니다.")
        if self.source not in VISION_SOURCES:
            errors.append(f"source must be one of: {sorted(VISION_SOURCES)}")
        if self.target_furniture_type and self.target_furniture_type not in VALID_FURNITURE_TYPES:
            errors.append(f"target_furniture_type must be one of: {sorted(VALID_FURNITURE_TYPES)}")
        if self.calibration.perspective_mode not in PERSPECTIVE_MODES:
            errors.append(f"perspective_mode must be one of: {sorted(PERSPECTIVE_MODES)}")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "image_url": self.image_url,
            "attachment_id": self.attachment_id,
            "source": self.source,
            "calibration": {
                "known_length_mm": self.calibration.known_length_mm,
                "image_segment_px": self.calibration.image_segment_px,
                "origin_hint": self.calibration.origin_hint,
                "perspective_mode": self.calibration.perspective_mode,
            },
            "target_furniture_type": self.target_furniture_type,
            "notes": self.notes,
            "project_id": self.project_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VisionInput":
        cal_d = d.get("calibration", {})
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            image_url=d.get("image_url"),
            attachment_id=d.get("attachment_id"),
            source=d.get("source", "manual_upload"),
            calibration=CalibrationParams(
                known_length_mm=cal_d.get("known_length_mm"),
                image_segment_px=cal_d.get("image_segment_px"),
                origin_hint=cal_d.get("origin_hint"),
                perspective_mode=cal_d.get("perspective_mode", "unknown"),
            ),
            target_furniture_type=d.get("target_furniture_type"),
            notes=d.get("notes"),
            project_id=d.get("project_id"),
        )


@dataclass
class DesignGraphCandidate:
    """Vision extraction result — NOT design truth until human-approved."""
    candidate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    vision_input_id: str = ""
    furniture_type: str = "wardrobe"
    extracted_params: dict[str, Any] = field(default_factory=dict)
    unresolved_fields: list[str] = field(default_factory=list)  # must be empty before apply
    confidence: float = 0.0    # 0.0–1.0
    source: str = "fake_extractor"
    validated: bool = False
    validation_result: Optional[dict] = None
    approved: bool = False

    def can_apply(self) -> bool:
        """True only if fully resolved, validated, and approved."""
        return (
            len(self.unresolved_fields) == 0
            and self.validated
            and self.approved
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "vision_input_id": self.vision_input_id,
            "furniture_type": self.furniture_type,
            "extracted_params": self.extracted_params,
            "unresolved_fields": self.unresolved_fields,
            "confidence": self.confidence,
            "source": self.source,
            "validated": self.validated,
            "validation_result": self.validation_result,
            "approved": self.approved,
            "can_apply": self.can_apply(),
        }
