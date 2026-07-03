"""HTTP helpers for ERP shell + fragment requests."""

from __future__ import annotations

from flask import Request, Response

from foms.services.common import erp_navigation_contract as enc


def get_erp_shell_view_mode(req: Request) -> str | None:
    """Return ``fragment`` / ``critical`` / ``heavy`` when shell tab body is requested.

    Requires active shell header **and** ``view`` matching a known mode. Otherwise
    ``None`` (full HTML document — direct GET, refresh, JS off).

    Full page and fragment must use the same handler and data path (single truth).
    """
    if req.headers.get(enc.ERP_SHELL_REQUEST_HEADER) != enc.ERP_SHELL_REQUEST_HEADER_ACTIVE:
        return None
    raw = (req.args.get(enc.ERP_VIEW_QUERY_PARAM) or "").strip()
    if raw == enc.VIEW_FRAGMENT:
        return enc.VIEW_FRAGMENT
    if raw == enc.VIEW_CRITICAL:
        return enc.VIEW_CRITICAL
    if raw == enc.VIEW_HEAVY:
        return enc.VIEW_HEAVY
    return None


def wants_erp_shell_tab_body(req: Request) -> bool:
    """True when the client should receive tab-body HTML (partial), not a full document."""
    return get_erp_shell_view_mode(req) is not None


def wants_erp_tab_fragment(req: Request) -> bool:
    """Backward-compatible name: any shell body mode (fragment/critical/heavy).

    Deprecated alias for :func:`wants_erp_shell_tab_body`.
    """
    return wants_erp_shell_tab_body(req)


def apply_erp_shell_fragment_headers(response: Response, req: Request) -> None:
    """Set fragment response headers when ``get_erp_shell_view_mode`` is non-None.

    Wave 4.1 (conditional fragment): the ERP shell fragment body is large
    (dashboard ~640KB / production ~550KB decompressed) and the client heartbeat
    re-fetches it every 50s/240s to keep the warm cache alive. When the tab body
    has not actually changed, re-sending the whole payload is pure waste.

    We attach a strong ``ETag`` and call :meth:`Response.make_conditional`. On a
    matching client ``If-None-Match`` the response collapses to **304** (empty
    body) and the client simply extends its warm-cache TTL instead of
    re-downloading/decompressing the fragment.

    ETag/Compress 실제 경로 (주의 — 비자명): 이 helper는 뷰 시점(after_request의
    Flask-Compress 이전)에 돌아 무압축 body의 강한 ETag를 계산한다. 그런데
    Flask-Compress는 압축한 200 응답의 ETag를 ``"abc"`` → ``"abc:br"`` 처럼
    **재작성**하고, ``COMPRESS_EVALUATE_CONDITIONAL_REQUEST``(기본 True)로 압축 후
    조건부 평가를 **재실행**한다. 실브라우저(Accept-Encoding 전송)에서 클라가
    저장·에코하는 ETag는 접미사 붙은 값이므로, 프로덕션 304는 여기의
    ``make_conditional``이 아니라 Flask-Compress의 재평가로 성립한다. 여기 것은
    무압축 경로(테스트 클라·curl)를 커버한다. 그 config가 꺼지면 304가 소리 없이
    영구 200으로 퇴화하므로 app_factory에서 명시 고정 + 압축 경로 회귀 테스트로 방어.
    브라우저 HTTP 캐시 정책과 무관하게 조건부 재검증의 주체는 우리 JS warm 캐시다.
    """
    mode = get_erp_shell_view_mode(req)
    if mode is None:
        return
    response.headers[enc.ERP_FRAGMENT_RESPONSE_HEADER] = enc.ERP_FRAGMENT_RESPONSE_ACTIVE
    response.headers[enc.ERP_FRAGMENT_VIEW_TIER_HEADER] = mode
    # Conditional GET only makes sense for body-bearing GET/HEAD fetches.
    # ``make_conditional`` self-guards to GET/HEAD, but we mirror that guard so a
    # future non-GET caller of this helper is never turned conditional.
    if req.method in ("GET", "HEAD"):
        response.add_etag()
        response.make_conditional(req)
