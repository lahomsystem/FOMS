"""ERP shared utility helpers."""

__all__ = ["ensure_path"]


def ensure_path(d: dict, *keys: str) -> dict:
    """Ensure a nested dictionary path exists and return the deepest node."""
    for key in keys:
        d = d.setdefault(key, {})
    return d
