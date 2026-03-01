"""
Cursor 훅 공용 유틸. find_key_recursive 등 payload 추출 로직 공유.
"""
from __future__ import annotations

def find_key_recursive(data: object, target_keys: list[str], default: str | None = "unknown") -> str | None:
    """중첩 dict/list에서 target_keys 중 하나라도 있으면 해당 값을 반환. 없으면 default."""
    if isinstance(data, dict):
        for k, v in data.items():
            if k in target_keys and v:
                return v
            res = find_key_recursive(v, target_keys, default=None)
            if res is not None:
                return res
    elif isinstance(data, list):
        for item in data:
            res = find_key_recursive(item, target_keys, default=None)
            if res is not None:
                return res
    return default
