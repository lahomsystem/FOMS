"""정적 자산 URL 에 파일 내용 해시 버전(``?v=``)을 붙이는 템플릿 도우미.

왜 필요한가: 지금까지는 CSS·JS 를 고칠 때마다 템플릿의 ``?v=20260929a`` 같은 날짜 핀을
사람이 손으로 올렸다. 깜빡하면 폰·PC 가 옛 파일을 최대 하루(``?v=`` 가 붙은 css/js 는
``foms/platform/app_factory.py`` 의 ``_versioned_static_cache_middleware`` 가
``max-age=86400`` 을 준다) 계속 쓴다. 이 도우미는 핀을 **파일 내용에서** 만든다 — 내용이
바뀌면 URL 이 저절로 바뀌고, 같으면 워커·컨테이너가 달라도 같은 URL 이 된다.

URL 모양은 일부러 ``?v=`` 그대로다. 하루 캐시 미들웨어와 서비스 워커(``static/sw.js`` 는
쿼리까지 포함한 URL 로 캐시한다)를 고치지 않아도 된다.

시범 범위(2026-09-29 계획 ``docs/plans/2026-09-29-asset-content-hash-url-plan.md``):
``templates/orders/partials/erp_order_js.html`` 한 파일만 이 도우미를 쓴다.
"""

from __future__ import annotations

import hashlib
import logging
import os
import stat

from flask import current_app, url_for
from werkzeug.security import safe_join

logger = logging.getLogger(__name__)

__all__ = [
    "ASSET_HASH_LENGTH",
    "AssetNotFoundError",
    "asset_url",
    "clear_asset_url_cache",
    "content_hash",
]

#: 버전 문자열 길이(sha256 16진 앞자리). 12자리 = 48비트라 자산 수백 개에서 충돌 걱정이 없다.
ASSET_HASH_LENGTH = 12

_READ_CHUNK_BYTES = 64 * 1024

#: (static 폴더, 상대 경로) -> (파일 수정 시각 ns, 버전). 버전이 ``None`` 이면 "없는 파일".
#: 프로세스마다 처음 쓸 때 채운다. dict 대입은 원자적이라 경합해도 같은 값을 두 번 계산할 뿐이다.
_VERSION_CACHE: dict[tuple[str, str], tuple[int | None, str | None]] = {}

#: 운영에서 "없는 파일" 경고를 이미 찍은 경로.
_WARNED_MISSING: set[str] = set()


class AssetNotFoundError(FileNotFoundError):
    """``asset_url`` 에 넘긴 정적 파일이 없다(시험·개발 모드에서만 올린다)."""


def content_hash(file_path: str) -> str:
    """파일 바이트의 sha256 16진 앞 :data:`ASSET_HASH_LENGTH` 자리를 돌려준다.

    Args:
        file_path: 읽을 파일의 절대 경로.

    Returns:
        소문자 16진 문자열(길이 :data:`ASSET_HASH_LENGTH`).
    """
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()[:ASSET_HASH_LENGTH]


def clear_asset_url_cache() -> None:
    """프로세스 캐시를 비운다(시험 전용 — 운영 코드는 부르지 않는다)."""
    _VERSION_CACHE.clear()
    _WARNED_MISSING.clear()


def _file_mtime_ns(file_path: str | None) -> int | None:
    """일반 파일이면 수정 시각(ns), 없거나 폴더면 ``None``."""
    if not file_path:
        return None
    try:
        info = os.stat(file_path)
    except OSError:
        return None
    return info.st_mtime_ns if stat.S_ISREG(info.st_mode) else None


def _asset_version(static_root: str, rel_path: str, *, watch_mtime: bool) -> str | None:
    """상대 경로의 내용 해시 버전을 돌려준다. 없는 파일이면 ``None``.

    운영에서는 처음 계산한 값을 프로세스 수명 동안 그대로 쓴다(배포 = 새 컨테이너).
    ``watch_mtime`` 이면 매번 수정 시각을 보고 바뀌었을 때만 다시 계산한다(개발 모드).
    """
    key = (static_root, rel_path)
    cached = _VERSION_CACHE.get(key)
    if cached is not None and not watch_mtime:
        return cached[1]

    file_path = safe_join(static_root, rel_path)
    mtime_ns = _file_mtime_ns(file_path)
    if cached is not None and cached[0] == mtime_ns:
        return cached[1]

    version = content_hash(file_path) if (file_path and mtime_ns is not None) else None
    _VERSION_CACHE[key] = (mtime_ns, version)
    return version


def asset_url(path: str) -> str:
    """``url_for('static', filename=path)`` 뒤에 내용 해시 ``?v=`` 를 붙여 돌려준다.

    Jinja 전역으로 등록돼 템플릿에서 ``{{ asset_url('js/orders/erp-share.js') }}`` 로 쓴다.

    Args:
        path: static 폴더 기준 상대 경로(``url_for('static', filename=...)`` 과 같은 값).

    Returns:
        ``/static/<path>?v=<sha256 앞 12자리>``. 운영에서 파일이 없으면 쿼리 없는 URL.

    Raises:
        AssetNotFoundError: 시험(``TESTING``)·개발(``DEBUG``) 모드에서 파일이 없을 때 —
            템플릿 오타를 그 자리에서 잡는다.
    """
    app = current_app
    url = url_for("static", filename=path)
    static_root = app.static_folder or ""
    version = _asset_version(static_root, path, watch_mtime=bool(app.debug))
    if version is not None:
        return f"{url}?v={version}"

    if app.testing or app.debug:
        raise AssetNotFoundError(f"asset_url: 정적 파일이 없다 — {path!r} (static={static_root!r})")
    # 운영: 화면은 떠야 한다. 경고는 경로당 프로세스에서 한 번만 찍는다(렌더마다 도배 금지).
    if path not in _WARNED_MISSING:
        _WARNED_MISSING.add(path)
        logger.warning("asset_url: 정적 파일이 없어 버전 없이 내보낸다 — %s", path)
    return url
