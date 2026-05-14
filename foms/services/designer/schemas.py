"""FOMS Brain AX Designer – Pydantic schemas for request/response validation.

PV2-B0: schema v2 models added alongside v1 legacy.
v1 schemas are kept for backward compat; v2 schemas are the new standard.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────
# Schema V1 (legacy — kept for backward compat)
# ──────────────────────────────────────────────────────────

class Position3D(BaseModel):
    x: float = 0
    y: float = 0
    z: float = 0


class CabinetDimensions(BaseModel):
    width: float = Field(..., gt=0, le=10000)
    height: float = Field(..., gt=0, le=4000)
    depth: float = Field(..., gt=0, le=1200)


class DesignComponent(BaseModel):
    id: str
    type: str
    name: str
    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)
    depth: float = Field(..., gt=0)
    position: Position3D = Field(default_factory=Position3D)


class DesignJson(BaseModel):
    schema_version: int = 1
    unit: str = "mm"
    cabinet: CabinetDimensions
    components: list[DesignComponent] = Field(default_factory=list)
    relations: list[Any] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────
# Schema V2 (Design Kernel V1 — kernel-v1 ontology)
# ──────────────────────────────────────────────────────────

class DimensionsV2(BaseModel):
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    depth: int = Field(..., gt=0)


class Position3DV2(BaseModel):
    x: int = 0
    y: int = 0
    z: int = 0


class ComponentV2(BaseModel):
    id: str
    kind: str
    role: str
    name: str
    parent_id: Optional[str] = None
    material_id: Optional[str] = None
    dimensions: DimensionsV2
    position: Position3DV2 = Field(default_factory=Position3DV2)
    edge_banding: dict[str, bool] = Field(default_factory=dict)
    formula_refs: list[str] = Field(default_factory=list)
    custom_props: dict[str, Any] = Field(default_factory=dict)


class ModuleV2(BaseModel):
    id: str
    type: str
    name: str
    dimensions: DimensionsV2
    position: Position3DV2 = Field(default_factory=Position3DV2)
    component_ids: list[str] = Field(default_factory=list)
    door_type: str = "open"


class AssemblyV2(BaseModel):
    id: str
    type: str
    name: str
    dimensions: DimensionsV2
    modules: list[ModuleV2] = Field(default_factory=list)
    ep_left: int = 50
    ep_right: int = 50
    ep_top: int = 50
    base_height: int = 60
    top_sr: int = 50
    module_count: int = 1
    door_type: str = "open"


class ConstraintV2(BaseModel):
    id: str
    type: str
    severity: str = "error"
    params: dict[str, Any] = Field(default_factory=dict)


class RelationV2(BaseModel):
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    type: str

    model_config = {"populate_by_name": True}


class DesignGraphV2(BaseModel):
    """Schema version 2 design graph root. Used for all new projects."""
    schema_version: int = Field(2, frozen=True)
    unit: str = "mm"
    assembly: AssemblyV2
    components: list[ComponentV2] = Field(default_factory=list)
    constraints: list[ConstraintV2] = Field(default_factory=list)
    relations: list[RelationV2] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────
# DesignCommand schema (V2 contract)
# ──────────────────────────────────────────────────────────

class CommandTargetV2(BaseModel):
    component_id: str
    fallback_path: Optional[str] = None


class DesignCommandSchema(BaseModel):
    command_id: str
    source: str = "manual_json"
    intent: str
    target: CommandTargetV2
    operation: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    preview_only: bool = True


class CommandPreviewRequest(BaseModel):
    project_id: int
    version_id: Optional[int] = None
    command: DesignCommandSchema


class CommandApplyRequest(BaseModel):
    project_id: int
    version_id: Optional[int] = None
    command: DesignCommandSchema


# ──────────────────────────────────────────────────────────
# LUI schema (PV2-B1)
# ──────────────────────────────────────────────────────────

class LuiParseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    project_id: Optional[int] = None
    selected_component_id: Optional[str] = None
    design_context: Optional[dict] = None


# ──────────────────────────────────────────────────────────
# Request/Response schemas (shared)
# ──────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    order_id: Optional[int] = None


class CreateVersionRequest(BaseModel):
    design_json: dict


class ValidateRequest(BaseModel):
    design_json: dict


class CreateAIRunRequest(BaseModel):
    project_id: Optional[int] = None
    prompt: str = Field(..., min_length=1)
    design_json: Optional[dict] = None


class ResumeAIRunRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
