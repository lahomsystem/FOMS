"""FOMS Brain AX Designer – Pydantic schemas for request/response validation."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


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
