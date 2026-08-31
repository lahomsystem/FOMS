"""CSRF 배선 계약 (WRITE-GUARD-01 보강).

운영 사고(2026-08-31): `templates/measurement/map_view.html` 은 `layout_head.html` 을
쓰지 않는 standalone 문서라 CSRF 토큰과 fetch 래퍼가 통째로 빠져 있었다. 그 결과
지도 화면의 주소 수정·담당자 저장이 ADMIN 계정에서도 403 `invalid_csrf_token` 으로
막혔고(security_logs 실기록), 약 2개월간 잠복했다.

기존 write-guard 테스트는 "모든 mutation route 가 manifest 에 있는가"만 강제했다.
여기서는 **그 route 를 호출하는 페이지가 토큰을 실을 수 있는가**를 강제한다.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "templates"
CSRF_PARTIAL = TEMPLATES_DIR / "partials" / "shared" / "csrf_bootstrap.html"

#: include 구문 매칭(따옴표 종류 무관).
_INCLUDE_RE = re.compile(r"""\{%-?\s*include\s+['"]partials/shared/csrf_bootstrap\.html['"]""")

#: fetch/XHR mutation 호출 흔적.
_MUTATION_RE = re.compile(
    r"""method\s*:\s*['"`](?:POST|PUT|PATCH|DELETE)['"`]""",
    re.IGNORECASE,
)

#: 전체 HTML 문서(= 다른 레이아웃에 include 되는 조각이 아님).
_STANDALONE_RE = re.compile(r"<!DOCTYPE\s+html", re.IGNORECASE)

_EXTENDS_RE = re.compile(r"\{%-?\s*extends\s")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_csrf_partial_carries_token_and_fetch_wrapper() -> None:
    """정본 partial 이 토큰 meta 와 자동 부착 래퍼를 모두 갖는다."""
    body = _read(CSRF_PARTIAL)
    assert '<meta name="csrf-token" content="{{ csrf_token() }}">' in body
    assert "window.__FOMS_CSRF_BOUND" in body
    assert "X-CSRF-Token" in body
    assert "window.fetch = function" in body
    assert "XMLHttpRequest.prototype.send" in body


def test_layout_head_includes_csrf_partial() -> None:
    """공용 레이아웃은 정본 partial 을 include 한다(규칙을 복제하지 않는다)."""
    body = _read(TEMPLATES_DIR / "partials" / "shared" / "layout_head.html")
    assert _INCLUDE_RE.search(body), "layout_head.html 이 csrf_bootstrap.html 을 include 하지 않는다"
    assert "window.__FOMS_CSRF_BOUND" not in body, "CSRF 래퍼 규칙이 layout_head 에 중복 정의됐다"


def test_map_view_standalone_document_includes_csrf_partial() -> None:
    """회귀 고정: 지도 화면(standalone 문서)이 CSRF 배선을 갖는다."""
    body = _read(TEMPLATES_DIR / "measurement" / "map_view.html")
    assert _STANDALONE_RE.search(body), "map_view.html 이 더 이상 standalone 문서가 아니다(계약 재검토 필요)"
    assert _INCLUDE_RE.search(body), (
        "map_view.html 에 csrf_bootstrap.html include 가 없다 — "
        "이 화면의 모든 mutation 이 403 invalid_csrf_token 이 된다"
    )


def test_every_standalone_template_with_mutation_has_csrf_wiring() -> None:
    """mutation 을 쏘는 standalone 템플릿은 예외 없이 CSRF 배선을 가져야 한다.

    조각(partial)은 대상이 아니다 — 이들은 base 를 extends 하는 페이지에 include 되어
    layout_head 경유로 배선을 얻는다.
    """
    offenders: list[str] = []
    for path in sorted(TEMPLATES_DIR.rglob("*.html")):
        body = _read(path)
        if not _STANDALONE_RE.search(body):
            continue
        if _EXTENDS_RE.search(body):
            continue
        if not _MUTATION_RE.search(body):
            continue
        if _INCLUDE_RE.search(body):
            continue
        offenders.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))

    assert not offenders, (
        "layout_head 를 쓰지 않는 standalone 템플릿이 mutation 을 쏘는데 "
        'CSRF 배선이 없다. {% include "partials/shared/csrf_bootstrap.html" %} 를 '
        f"head 에 추가하라: {offenders}"
    )


def test_map_view_reads_both_message_and_error_keys() -> None:
    """실패 안내가 유실되지 않는다.

    write guard 403 은 ``error`` 키만, 라우트 핸들러는 ``message`` 키만 채운다.
    한쪽만 읽으면 사용자에게 '알 수 없는 오류'만 보인다.
    """
    body = _read(TEMPLATES_DIR / "measurement" / "map_view.html")
    assert "function serverErrorText(" in body
    assert "d.message || d.error" in body
    assert "serverErrorText(res.status, data)" in body
