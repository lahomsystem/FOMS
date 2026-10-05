"""렌더 입력 기록기 — 한 라우트의 렌더가 읽은 모든 입력을 이름으로 모은다.

렌더 전 304 키는 "렌더가 쓰는 모든 입력의 함수"여야 한다(설계서 2026-10-05 §3.1-1). 그 목록을
소스 독해로 닫으면 빠뜨림이 생긴다 — 그래서 실제 렌더를 돌리며 읽힌 것을 기록하고, 기록이
키 명세의 부분집합인지를 계약 테스트가 단언한다(§5.1-1).

기록하는 것(뷰 함수 진입부터 반환까지 — before/after_request 훅은 본문을 만들지 않으므로 뺀다):

- ``request.args`` · ``request.cookies`` · ``request.headers`` 에서 읽은 이름. 통째로 훑으면 ``*``.
- 세션에서 읽은 키(``SecureCookieSession`` 의 ``get``·``[]``·``in``).
- ``os.environ`` 에서 읽은 이름(``os.getenv`` 포함). 통째로 훑으면 ``*``.
- 실행된 SQL 이 건드린 표 이름, 쓰기 문장, ``system_settings`` 를 읽을 때 넘긴 설정 키.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from flask import request
from flask.sessions import SecureCookieSession
from sqlalchemy import event
from werkzeug.datastructures import ImmutableMultiDict

ALL = "*"
_TABLE_RE = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+\"?([a-zA-Z_][a-zA-Z0-9_]*)\"?", re.IGNORECASE)
_WRITE_RE = re.compile(r"^\s*(INSERT|UPDATE|DELETE)\b", re.IGNORECASE)


@dataclass
class RenderInputLog:
    """기록 결과(이름 집합)."""

    args: set[str] = field(default_factory=set)
    cookies: set[str] = field(default_factory=set)
    headers: set[str] = field(default_factory=set)
    session_keys: set[str] = field(default_factory=set)
    env: set[str] = field(default_factory=set)
    tables: set[str] = field(default_factory=set)
    writes: list[str] = field(default_factory=list)
    setting_keys: set[str] = field(default_factory=set)
    active: bool = False

    def note(self, bucket: str, name: Any) -> None:
        if self.active:
            getattr(self, bucket).add(str(name))


class _RecordingMultiDict(ImmutableMultiDict):
    """읽힌 이름을 적는 ``ImmutableMultiDict``(args·cookies 대역)."""

    def __init__(self, source: Any, log: RenderInputLog, bucket: str) -> None:
        super().__init__(source)
        self._rec = (log, bucket)

    def _note(self, name: Any) -> None:
        log, bucket = self._rec
        log.note(bucket, name)

    def __getitem__(self, key):  # noqa: D105
        self._note(key)
        return super().__getitem__(key)

    def get(self, key, default=None, type=None):  # noqa: A002, D102
        self._note(key)
        return super().get(key, default=default, type=type)

    def getlist(self, key, type=None):  # noqa: A002, D102
        self._note(key)
        return super().getlist(key, type=type)

    def __contains__(self, key) -> bool:  # noqa: D105
        self._note(key)
        return super().__contains__(key)

    def __iter__(self):  # noqa: D105
        self._note(ALL)
        return super().__iter__()

    def keys(self):  # noqa: D102
        self._note(ALL)
        return super().keys()

    def items(self, multi: bool = False):  # noqa: D102
        self._note(ALL)
        return super().items(multi=multi)

    def values(self):  # noqa: D102
        self._note(ALL)
        return super().values()

    def lists(self):  # noqa: D102
        self._note(ALL)
        return super().lists()

    def to_dict(self, flat: bool = True):  # noqa: D102
        self._note(ALL)
        return super().to_dict(flat=flat)


class _RecordingHeaders:
    """읽힌 헤더 이름을 적고 나머지는 원본에 넘긴다."""

    def __init__(self, source: Any, log: RenderInputLog) -> None:
        self._src = source
        self._log = log

    def get(self, key, default=None, type=None):  # noqa: A002
        self._log.note("headers", str(key).lower())
        return self._src.get(key, default=default, type=type)

    def __getitem__(self, key):
        self._log.note("headers", str(key).lower())
        return self._src[key]

    def __contains__(self, key) -> bool:
        self._log.note("headers", str(key).lower())
        return key in self._src

    def __iter__(self):
        self._log.note("headers", ALL)
        return iter(self._src)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._src, name)


class _RecordingEnviron(MutableMapping):
    """``os.environ`` 대역 — 읽힌 이름을 적는다(쓰기는 원본에 그대로)."""

    def __init__(self, source: Any, log: RenderInputLog) -> None:
        self._src = source
        self._log = log

    def __getitem__(self, key: str) -> str:
        self._log.note("env", key)
        return self._src[key]

    def __contains__(self, key: object) -> bool:
        self._log.note("env", key)
        return key in self._src

    def __setitem__(self, key: str, value: str) -> None:
        self._src[key] = value

    def __delitem__(self, key: str) -> None:
        del self._src[key]

    def __iter__(self) -> Iterator[str]:
        self._log.note("env", ALL)
        return iter(self._src)

    def __len__(self) -> int:
        return len(self._src)

    def copy(self) -> dict[str, str]:
        self._log.note("env", ALL)
        return dict(self._src)


def _wrap_session(monkeypatch: Any, log: RenderInputLog) -> None:
    orig_getitem = SecureCookieSession.__getitem__
    orig_get = SecureCookieSession.get
    orig_contains = dict.__contains__

    def _getitem(self, key):
        log.note("session_keys", key)
        return orig_getitem(self, key)

    def _get(self, key, default=None):
        log.note("session_keys", key)
        return orig_get(self, key, default)

    def _contains(self, key) -> bool:
        log.note("session_keys", key)
        return orig_contains(self, key)

    monkeypatch.setattr(SecureCookieSession, "__getitem__", _getitem)
    monkeypatch.setattr(SecureCookieSession, "get", _get)
    monkeypatch.setattr(SecureCookieSession, "__contains__", _contains)


def _sql_listener(log: RenderInputLog):
    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if not log.active:
            return
        for name in _TABLE_RE.findall(statement):
            log.tables.add(name.lower())
        if _WRITE_RE.match(statement):
            log.writes.append(statement.split("\n", 1)[0][:120])
        if "system_settings" in statement.lower():
            values = parameters.values() if isinstance(parameters, dict) else (parameters or ())
            for value in values:
                if isinstance(value, str):
                    log.setting_keys.add(value)

    return _before


@contextmanager
def record_render_inputs(app: Any, endpoint: str, monkeypatch: Any, engine: Any) -> Iterator[RenderInputLog]:
    """``endpoint`` 뷰가 도는 동안 읽힌 입력을 기록한다.

    Args:
        app: Flask 앱.
        endpoint: 기록할 뷰의 endpoint 이름.
        monkeypatch: pytest monkeypatch(끝나면 원상복구).
        engine: SQL 실행을 엿들을 SQLAlchemy 엔진.

    Yields:
        기록 결과. 블록 안에서 테스트 클라이언트로 요청을 보낸다.
    """
    log = RenderInputLog()
    original_view = app.view_functions[endpoint]

    def _recording_view(*args: Any, **kwargs: Any) -> Any:
        request.__dict__["args"] = _RecordingMultiDict(request.args, log, "args")
        request.__dict__["cookies"] = _RecordingMultiDict(request.cookies, log, "cookies")
        request.headers = _RecordingHeaders(request.headers, log)
        log.active = True
        try:
            return original_view(*args, **kwargs)
        finally:
            log.active = False

    monkeypatch.setitem(app.view_functions, endpoint, _recording_view)
    monkeypatch.setattr(os, "environ", _RecordingEnviron(os.environ, log))
    _wrap_session(monkeypatch, log)
    listener = _sql_listener(log)
    event.listen(engine, "before_cursor_execute", listener)
    try:
        yield log
    finally:
        event.remove(engine, "before_cursor_execute", listener)
