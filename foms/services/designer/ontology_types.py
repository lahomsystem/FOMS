"""FOMS Brain Design Kernel V1 — Atomic Ontology Types (Python backend canonical).

DK-B1: schema_version 2 frozen types.
이 파일은 backend의 design graph shape 기준이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

SCHEMA_VERSION: int = 2
ONTOLOGY_VERSION: str = "kernel-v1"

# ──────────────────────────────────────────────────────────
# Component kinds & roles
# ──────────────────────────────────────────────────────────

COMPONENT_KINDS = frozenset({
    "box", "panel", "door", "shelf", "drawer",
    "ep", "sr", "base", "hardware", "cutout",
})

COMPONENT_ROLES = frozenset({
    "left_ep", "right_ep", "top_ep",
    "top_sr", "bottom_sr",
    "base",
    "left_side", "right_side", "top_panel", "bottom_panel", "back_panel",
    "shelf", "door", "drawer",
    "inner_box", "generic",
})

DOOR_TYPES = frozenset({"sliding", "swing", "open"})

CONSTRAINT_SEVERITIES = frozenset({"error", "warning", "info"})

# ──────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────

@dataclass
class Dimensions:
    width: int
    height: int
    depth: int

    def to_dict(self) -> dict:
        return {"width": self.width, "height": self.height, "depth": self.depth}

    @classmethod
    def from_dict(cls, d: dict) -> "Dimensions":
        return cls(
            width=int(d["width"]),
            height=int(d["height"]),
            depth=int(d["depth"]),
        )


@dataclass
class Position3D:
    x: int
    y: int
    z: int

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, d: dict) -> "Position3D":
        return cls(x=int(d.get("x", 0)), y=int(d.get("y", 0)), z=int(d.get("z", 0)))


@dataclass
class Material:
    id: str
    name: str
    thickness: int      # mm
    max_width: int      # mm
    max_height: int     # mm
    category: str       # board / door / hardware / other

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "thickness": self.thickness,
            "max_width": self.max_width,
            "max_height": self.max_height,
            "category": self.category,
        }


@dataclass
class Formula:
    id: str
    expression: str
    target: str
    variables: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "expression": self.expression,
            "target": self.target,
            "variables": self.variables,
        }


@dataclass
class Constraint:
    id: str
    type: str       # sum_equals / within_bounds / max_size / gap_rule / thickness_rule / no_duplicate_uuid
    severity: str   # error / warning / info
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "params": self.params,
        }


@dataclass
class ConstraintViolation:
    constraint_id: str
    severity: str
    code: str
    message: str
    path: str

    def to_dict(self) -> dict:
        return {
            "constraint_id": self.constraint_id,
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }


@dataclass
class ConstraintResult:
    valid: bool
    violations: list[ConstraintViolation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "violations": [v.to_dict() for v in self.violations],
        }

    @property
    def errors(self) -> list[ConstraintViolation]:
        return [v for v in self.violations if v.severity == "error"]

    @property
    def warnings(self) -> list[ConstraintViolation]:
        return [v for v in self.violations if v.severity == "warning"]


@dataclass
class Component:
    id: str
    kind: str
    role: str
    name: str
    parent_id: Optional[str]
    material_id: Optional[str]
    dimensions: Dimensions
    position: Position3D
    edge_banding: dict[str, bool] = field(default_factory=dict)
    formula_refs: list[str] = field(default_factory=list)
    custom_props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "role": self.role,
            "name": self.name,
            "parent_id": self.parent_id,
            "material_id": self.material_id,
            "dimensions": self.dimensions.to_dict(),
            "position": self.position.to_dict(),
            "edge_banding": self.edge_banding,
            "formula_refs": self.formula_refs,
            "custom_props": self.custom_props,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Component":
        return cls(
            id=d["id"],
            kind=d["kind"],
            role=d.get("role", "generic"),
            name=d.get("name", ""),
            parent_id=d.get("parent_id"),
            material_id=d.get("material_id"),
            dimensions=Dimensions.from_dict(d["dimensions"]),
            position=Position3D.from_dict(d.get("position", {"x": 0, "y": 0, "z": 0})),
            edge_banding=d.get("edge_banding", {}),
            formula_refs=d.get("formula_refs", []),
            custom_props=d.get("custom_props", {}),
        )


@dataclass
class Module:
    id: str
    type: str
    name: str
    dimensions: Dimensions
    position: Position3D
    component_ids: list[str] = field(default_factory=list)
    door_type: str = "open"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "dimensions": self.dimensions.to_dict(),
            "position": self.position.to_dict(),
            "component_ids": self.component_ids,
            "door_type": self.door_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Module":
        return cls(
            id=d["id"],
            type=d.get("type", "storage_box"),
            name=d.get("name", ""),
            dimensions=Dimensions.from_dict(d["dimensions"]),
            position=Position3D.from_dict(d.get("position", {"x": 0, "y": 0, "z": 0})),
            component_ids=d.get("component_ids", []),
            door_type=d.get("door_type", "open"),
        )


@dataclass
class Assembly:
    id: str
    type: str
    name: str
    dimensions: Dimensions
    modules: list[Module] = field(default_factory=list)
    ep_left: int = 50
    ep_right: int = 50
    ep_top: int = 50
    base_height: int = 60
    top_sr: int = 50
    module_count: int = 1
    door_type: str = "open"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "dimensions": self.dimensions.to_dict(),
            "modules": [m.to_dict() for m in self.modules],
            "ep_left": self.ep_left,
            "ep_right": self.ep_right,
            "ep_top": self.ep_top,
            "base_height": self.base_height,
            "top_sr": self.top_sr,
            "module_count": self.module_count,
            "door_type": self.door_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Assembly":
        return cls(
            id=d["id"],
            type=d.get("type", "wardrobe"),
            name=d.get("name", ""),
            dimensions=Dimensions.from_dict(d["dimensions"]),
            modules=[Module.from_dict(m) for m in d.get("modules", [])],
            ep_left=int(d.get("ep_left", 50)),
            ep_right=int(d.get("ep_right", 50)),
            ep_top=int(d.get("ep_top", 50)),
            base_height=int(d.get("base_height", 60)),
            top_sr=int(d.get("top_sr", 50)),
            module_count=int(d.get("module_count", 1)),
            door_type=d.get("door_type", "open"),
        )


@dataclass
class Relation:
    from_id: str
    to_id: str
    type: str

    def to_dict(self) -> dict:
        return {"from": self.from_id, "to": self.to_id, "type": self.type}


@dataclass
class DesignGraph:
    """Schema version 2 design graph root."""
    schema_version: int
    unit: str
    assembly: Assembly
    components: list[Component]
    constraints: list[Constraint]
    relations: list[Relation]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "unit": self.unit,
            "assembly": self.assembly.to_dict(),
            "components": [c.to_dict() for c in self.components],
            "constraints": [c.to_dict() for c in self.constraints],
            "relations": [r.to_dict() for r in self.relations],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DesignGraph":
        return cls(
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            unit=d.get("unit", "mm"),
            assembly=Assembly.from_dict(d["assembly"]),
            components=[Component.from_dict(c) for c in d.get("components", [])],
            constraints=[
                Constraint(
                    id=c.get("id", ""),
                    type=c.get("type", ""),
                    severity=c.get("severity", "error"),
                    params=c.get("params", {}),
                )
                for c in d.get("constraints", [])
            ],
            relations=[
                Relation(
                    from_id=r.get("from", ""),
                    to_id=r.get("to", ""),
                    type=r.get("type", ""),
                )
                for r in d.get("relations", [])
            ],
            metadata=d.get("metadata", {}),
        )

    def get_component(self, component_id: str) -> Optional[Component]:
        for c in self.components:
            if c.id == component_id:
                return c
        return None

    def get_module(self, module_id: str) -> Optional[Module]:
        for m in self.assembly.modules:
            if m.id == module_id:
                return m
        return None


# ──────────────────────────────────────────────────────────
# DesignCommand
# ──────────────────────────────────────────────────────────

@dataclass
class DesignCommand:
    command_id: str
    source: str     # manual_json / lui / gizmo / touch
    intent: str     # move_component / resize_component / set_property / generate_layout
    target_component_id: str
    operation: dict[str, Any]
    constraints: list[str] = field(default_factory=list)
    preview_only: bool = True

    def to_dict(self) -> dict:
        return {
            "command_id": self.command_id,
            "source": self.source,
            "intent": self.intent,
            "target": {"component_id": self.target_component_id},
            "operation": self.operation,
            "constraints": self.constraints,
            "preview_only": self.preview_only,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DesignCommand":
        target = d.get("target", {})
        return cls(
            command_id=d.get("command_id", ""),
            source=d.get("source", "manual_json"),
            intent=d.get("intent", ""),
            target_component_id=target.get("component_id", ""),
            operation=d.get("operation", {}),
            constraints=d.get("constraints", []),
            preview_only=d.get("preview_only", True),
        )


# ──────────────────────────────────────────────────────────
# DesignPatch
# ──────────────────────────────────────────────────────────

@dataclass
class DesignPatch:
    target_id: str
    prop_path: str
    before: Any
    after: Any

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "prop_path": self.prop_path,
            "before": self.before,
            "after": self.after,
        }


# ──────────────────────────────────────────────────────────
# CorrectionDelta
# ──────────────────────────────────────────────────────────

@dataclass
class CorrectionDelta:
    correction_id: str
    target_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    reason: Optional[str]
    source: str    # user_manual_edit / command_apply / ai_suggestion
    validated: bool
    candidate_rule_hint: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "correction_id": self.correction_id,
            "target_id": self.target_id,
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
            "source": self.source,
            "validated": self.validated,
            "candidate_rule_hint": self.candidate_rule_hint,
        }
