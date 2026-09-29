"""내용 해시 자산 URL(``asset_url``) 시범 전환 뒤 기존 시험이 쓰는 기대값 계산기.

``templates/orders/partials/erp_order_js.html`` 의 css/js 37개는 손 날짜 핀(``?v=20260929a``)
대신 ``{{ asset_url('…') }}`` 를 쓴다(계획 ``docs/plans/2026-09-29-asset-content-hash-url-plan.md``).
그래서 그 파일의 자산을 글자로 고정하던 시험은 "날짜 핀" 대신 "도우미 호출"과
"실제 파일 내용 해시 URL" 을 단언한다.

기대값은 **구현(foms/services/asset_urls.py)을 거치지 않고** hashlib 로 여기서 직접 계산한다 —
구현이 틀리면 시험이 따라 틀리는 순환을 막는다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = REPO_ROOT / "static"

#: asset_url 시범 파일(이 파일의 css/js 만 날짜 핀이 없다).
ASSET_URL_PILOT_TEMPLATE = "templates/orders/partials/erp_order_js.html"

#: 계획서가 고정한 버전 길이(sha256 16진 앞 12자리).
ASSET_HASH_LENGTH = 12


def expected_asset_version(rel_path: str) -> str:
    """static 기준 상대 경로 파일의 sha256 16진 앞 12자리."""
    data = (STATIC_ROOT / rel_path).read_bytes()
    return hashlib.sha256(data).hexdigest()[:ASSET_HASH_LENGTH]


def hashed_asset_ref(rel_path: str) -> str:
    """렌더된 HTML 에 나와야 하는 ``<rel_path>?v=<내용 해시>`` 조각."""
    return f"{rel_path}?v={expected_asset_version(rel_path)}"


def asset_url_call(rel_path: str) -> str:
    """시범 템플릿 원문에 있어야 하는 ``{{ asset_url('<rel_path>') }}`` 호출 글자."""
    return "{{ asset_url('%s') }}" % rel_path
