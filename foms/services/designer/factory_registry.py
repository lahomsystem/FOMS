"""FOMS Brain Post-V1 — Furniture Factory Registry.

PV2-B2: Multi-furniture factory dispatcher.

All factories produce schema v2 DesignGraph and must pass hard validator.
generate_layout command routes through this registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from foms.services.designer.ontology_types import DesignGraph


# ──────────────────────────────────────────────────────────
# Furniture types
# ──────────────────────────────────────────────────────────

FURNITURE_TYPES = frozenset({
    "wardrobe",
    "shoe_rack",
    "kitchen_base",
    "kitchen_wall",
    "custom_storage",
})


# ──────────────────────────────────────────────────────────
# Registry entry
# ──────────────────────────────────────────────────────────

@dataclass
class FactoryEntry:
    furniture_type: str
    create_fn: Callable[..., DesignGraph]
    params_cls: type
    default_params_fn: Callable[[], dict]
    validate_params_fn: Callable[[dict], list[str]]  # returns list of error messages


_REGISTRY: dict[str, FactoryEntry] = {}


def register(
    furniture_type: str,
    create_fn: Callable,
    params_cls: type,
    default_params_fn: Callable,
    validate_params_fn: Callable,
) -> None:
    """Register a furniture factory."""
    if furniture_type not in FURNITURE_TYPES:
        raise ValueError(f"Unknown furniture type: {furniture_type!r}. Must be one of: {sorted(FURNITURE_TYPES)}")
    _REGISTRY[furniture_type] = FactoryEntry(
        furniture_type=furniture_type,
        create_fn=create_fn,
        params_cls=params_cls,
        default_params_fn=default_params_fn,
        validate_params_fn=validate_params_fn,
    )


def get_registered_types() -> list[str]:
    return sorted(_REGISTRY.keys())


# ──────────────────────────────────────────────────────────
# Public interface
# ──────────────────────────────────────────────────────────

def create_assembly(furniture_type: str, params: dict[str, Any]) -> DesignGraph:
    """Create a DesignGraph for the given furniture type.

    Raises ValueError for unknown type or invalid params.
    All output passes schema v2 + hard validator.
    """
    entry = _REGISTRY.get(furniture_type)
    if entry is None:
        raise ValueError(
            f"Unknown furniture type: {furniture_type!r}. "
            f"Registered: {sorted(_REGISTRY.keys())}"
        )

    errors = entry.validate_params_fn(params)
    if errors:
        raise ValueError(f"Invalid params for {furniture_type!r}: {'; '.join(errors)}")

    # Build params object from dict (allow extra fields to be ignored)
    import dataclasses
    if dataclasses.is_dataclass(entry.params_cls):
        valid_fields = {f.name for f in dataclasses.fields(entry.params_cls)}
        filtered = {k: v for k, v in params.items() if k in valid_fields}
        params_obj = entry.params_cls(**filtered)
    else:
        params_obj = entry.params_cls(**params)

    graph = entry.create_fn(params_obj)

    # Safety: validate output
    from foms.services.designer.constraint_engine import validate_design_graph
    result = validate_design_graph(graph)
    if not result.valid:
        errors_str = "; ".join(v.message for v in result.errors)
        raise RuntimeError(
            f"Factory {furniture_type!r} produced invalid graph: {errors_str}"
        )
    return graph


def validate_params(furniture_type: str, params: dict[str, Any]) -> list[str]:
    """Return list of validation error messages for given params."""
    entry = _REGISTRY.get(furniture_type)
    if entry is None:
        return [f"Unknown furniture type: {furniture_type!r}"]
    return entry.validate_params_fn(params)


def default_params(furniture_type: str) -> dict[str, Any]:
    """Return default params dict for given furniture type."""
    entry = _REGISTRY.get(furniture_type)
    if entry is None:
        raise ValueError(f"Unknown furniture type: {furniture_type!r}")
    return entry.default_params_fn()


# ──────────────────────────────────────────────────────────
# Auto-registration on import
# ──────────────────────────────────────────────────────────

def _bootstrap() -> None:
    """Register all built-in factories."""
    # Wardrobe (V1)
    from foms.services.designer.assembly_factories import (
        WardrobeParams,
        create_wardrobe_assembly,
    )

    def _wardrobe_defaults() -> dict:
        import dataclasses
        return {f.name: f.default for f in dataclasses.fields(WardrobeParams)
                if f.default is not dataclasses.MISSING}

    def _wardrobe_validate(params: dict) -> list[str]:
        errors = []
        w = params.get("width", 2400)
        h = params.get("height", 2200)
        d = params.get("depth", 600)
        mc = params.get("module_count", 2)
        dt = params.get("door_type", "sliding")
        if not isinstance(w, (int, float)) or w <= 0:
            errors.append("width must be > 0")
        if not isinstance(h, (int, float)) or h <= 0:
            errors.append("height must be > 0")
        if not isinstance(d, (int, float)) or d <= 0:
            errors.append("depth must be > 0")
        if not isinstance(mc, int) or mc < 1 or mc > 8:
            errors.append("module_count must be 1–8")
        if dt not in ("sliding", "swing", "open"):
            errors.append("door_type must be sliding/swing/open")
        return errors

    register(
        "wardrobe",
        create_wardrobe_assembly,
        WardrobeParams,
        _wardrobe_defaults,
        _wardrobe_validate,
    )

    # Shoe rack (PV2-B3)
    from foms.services.designer.factories.shoe_rack import (
        ShoeRackParams,
        create_shoe_rack_assembly,
        _validate_shoe_rack_params,
    )

    def _shoe_rack_defaults() -> dict:
        import dataclasses
        return {f.name: f.default for f in dataclasses.fields(ShoeRackParams)
                if f.default is not dataclasses.MISSING}

    register(
        "shoe_rack",
        create_shoe_rack_assembly,
        ShoeRackParams,
        _shoe_rack_defaults,
        _validate_shoe_rack_params,
    )

    # Kitchen (PV2-B4) — registered in kitchen.py bootstrap
    try:
        from foms.services.designer.factories.kitchen import _register_kitchen_factories
        _register_kitchen_factories()
    except ImportError:
        pass  # Kitchen factory not yet implemented — non-blocking


_bootstrap()
