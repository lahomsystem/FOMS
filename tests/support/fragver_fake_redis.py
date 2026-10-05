"""렌더 전 304 그림자 관측 테스트용 최소 Redis 대역(문자열·해시·목록·파이프라인)."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from typing import Any


class FakeRedis:
    """``decode_responses=True`` Redis 처럼 문자열을 돌려주는 메모리 대역."""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.hashes: dict[str, dict[str, float]] = {}
        self.lists: dict[str, list[str]] = {}

    # --- 문자열 ---
    def get(self, key: str) -> str | None:
        return self.kv.get(key)

    def mget(self, keys: list[str]) -> list[str | None]:
        return [self.kv.get(k) for k in keys]

    def set(self, key: str, value: Any, nx: bool = False, ex: int | None = None) -> bool:  # noqa: ARG002
        if nx and key in self.kv:
            return False
        self.kv[key] = str(value)
        return True

    def setex(self, key: str, ttl: int, value: Any) -> bool:  # noqa: ARG002
        self.kv[key] = str(value)
        return True

    def incr(self, key: str, amount: int = 1) -> int:
        self.kv[key] = str(int(self.kv.get(key, "0")) + int(amount))
        return int(self.kv[key])

    def delete(self, *keys: str) -> int:
        return sum(1 for k in keys if self.kv.pop(k, None) is not None)

    def unlink(self, *keys: str) -> int:
        return self.delete(*keys)

    def scan_iter(self, match: str = "*", count: int | None = None) -> Iterator[str]:  # noqa: ARG002
        yield from [k for k in list(self.kv) if fnmatch.fnmatchcase(k, match)]

    # --- 해시 ---
    def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        row = self.hashes.setdefault(key, {})
        row[field] = row.get(field, 0) + int(amount)
        return int(row[field])

    def hincrbyfloat(self, key: str, field: str, amount: float) -> float:
        row = self.hashes.setdefault(key, {})
        row[field] = row.get(field, 0.0) + float(amount)
        return row[field]

    def hgetall(self, key: str) -> dict[str, str]:
        return {k: str(v) for k, v in self.hashes.get(key, {}).items()}

    def expire(self, key: str, ttl: int) -> bool:  # noqa: ARG002
        return True

    # --- 목록 ---
    def lpush(self, key: str, value: str) -> int:
        self.lists.setdefault(key, []).insert(0, value)
        return len(self.lists[key])

    def ltrim(self, key: str, start: int, end: int) -> bool:
        self.lists[key] = self.lists.get(key, [])[start : end + 1]
        return True

    def pipeline(self) -> "_Pipeline":
        return _Pipeline(self)


class _Pipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str) -> Any:
        def _queue(*args: Any, **kwargs: Any) -> "_Pipeline":
            self._ops.append((name, args, kwargs))
            return self

        return _queue

    def execute(self) -> list[Any]:
        out = [getattr(self._redis, name)(*args, **kwargs) for name, args, kwargs in self._ops]
        self._ops = []
        return out
