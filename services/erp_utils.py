"""
ERP 공용 유틸리티.
"""


def ensure_path(d: dict, *keys: str) -> dict:
    """딕셔너리 내 경로 보장. d.setdefault를 연쇄 호출."""
    for k in keys:
        d = d.setdefault(k, {})
    return d
