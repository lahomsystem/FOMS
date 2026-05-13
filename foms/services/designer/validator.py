"""FOMS Brain AX Designer – Design Validator (V1 legacy + V2 dispatch gate).

Hard rules enforced here are the final gate before any design data
is persisted. No save is permitted if valid is False.

DK-B3 upgrade: schema v2 designs are validated via constraint_engine.
Schema v1 designs continue to use the legacy cabinet-level rules below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationError:
    code: str
    message: str
    path: str

    def model_dump(self) -> dict:
        return {"code": self.code, "message": self.message, "path": self.path}


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": [e.model_dump() for e in self.errors],
            "warnings": [w.model_dump() for w in self.warnings],
        }


def validate_design(design_json: Any) -> ValidationResult:
    """Validate a raw design_json dict against hard rules.

    Schema v2: delegates to constraint_engine.validate_design_graph_from_dict.
    Schema v1: uses legacy cabinet-level rules.

    Returns ValidationResult. If valid is False, callers MUST NOT persist.
    """
    if isinstance(design_json, dict) and design_json.get("schema_version") == 2:
        return _validate_v2(design_json)
    return _validate_v1(design_json)


def _validate_v2(design_json: dict) -> ValidationResult:
    """Validate schema v2 DesignGraph via constraint engine."""
    from foms.services.designer.constraint_engine import validate_design_graph_from_dict
    result = validate_design_graph_from_dict(design_json)
    errors = [
        ValidationError(
            code=v.code,
            message=v.message,
            path=v.path,
        )
        for v in result.violations
        if v.severity == "error"
    ]
    warnings = [
        ValidationError(
            code=v.code,
            message=v.message,
            path=v.path,
        )
        for v in result.violations
        if v.severity == "warning"
    ]
    return ValidationResult(valid=result.valid, errors=errors, warnings=warnings)


def _validate_v1(design_json: Any) -> ValidationResult:
    """Legacy schema v1 cabinet-level validation."""
    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []

    if not isinstance(design_json, dict):  # type: ignore[arg-type]
        errors.append(ValidationError(code="INVALID_FORMAT", message="design_json은 객체여야 합니다.", path="$"))
        return ValidationResult(valid=False, errors=errors)

    cabinet = design_json.get("cabinet", {})
    if not isinstance(cabinet, dict):
        errors.append(ValidationError(code="MISSING_CABINET", message="cabinet 필드가 없습니다.", path="cabinet"))
        return ValidationResult(valid=False, errors=errors)

    # cabinet dimension rules
    width = cabinet.get("width")
    height = cabinet.get("height")
    depth = cabinet.get("depth")

    if not isinstance(width, (int, float)) or width <= 0:
        errors.append(ValidationError(code="WIDTH_INVALID", message="폭은 0보다 커야 합니다.", path="cabinet.width"))
    elif width > 10000:
        errors.append(ValidationError(code="WIDTH_TOO_LARGE", message="폭은 10000mm 이하만 허용됩니다.", path="cabinet.width"))

    if not isinstance(height, (int, float)) or height <= 0:
        errors.append(ValidationError(code="HEIGHT_INVALID", message="높이는 0보다 커야 합니다.", path="cabinet.height"))
    elif height > 4000:
        errors.append(ValidationError(code="HEIGHT_TOO_LARGE", message="높이는 4000mm 이하만 허용됩니다.", path="cabinet.height"))

    if not isinstance(depth, (int, float)) or depth <= 0:
        errors.append(ValidationError(code="DEPTH_INVALID", message="깊이는 0보다 커야 합니다.", path="cabinet.depth"))
    elif depth > 1200:
        errors.append(ValidationError(code="DEPTH_TOO_LARGE", message="깊이는 1200mm 이하만 허용됩니다.", path="cabinet.depth"))

    # component rules
    components = design_json.get("components", [])
    if not isinstance(components, list):
        errors.append(ValidationError(code="INVALID_COMPONENTS", message="components는 배열이어야 합니다.", path="components"))
    else:
        seen_ids: set[str] = set()
        for i, comp in enumerate(components):
            if not isinstance(comp, dict):
                continue
            comp_id = comp.get("id")
            if comp_id in seen_ids:
                errors.append(ValidationError(code="DUPLICATE_COMPONENT_ID", message=f"부재 id '{comp_id}'가 중복됩니다.", path=f"components[{i}].id"))
            else:
                seen_ids.add(str(comp_id) if comp_id is not None else f"__null_{i}")

            # panel thickness check (width/height/depth all must be > 0)
            for dim in ("width", "height", "depth"):
                v = comp.get(dim)
                if isinstance(v, (int, float)) and v <= 0:
                    errors.append(ValidationError(code="PANEL_DIM_ZERO", message=f"부재 '{comp_id}'의 {dim}은 0보다 커야 합니다.", path=f"components[{i}].{dim}"))

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
