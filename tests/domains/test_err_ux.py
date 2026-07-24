"""ERR-UX-01: 공용 mutation 에러 parser 계약 (2026-07-25).

docs/plans/2026-07-22-foms-full-system-bug-audit-report.md §5.2 ERR-UX-01:
timeout/malformed JSON/403/409/428 실패에서 visible error·reload 0·DOM
rollback·button re-enable 를 공용 parser(window.fomsMutationFetch, foms-write.js
SSOT)로 일원화한다. API policy/state 는 건드리지 않는 순수 클라 에러 표시라
서버 API 무변경 — 정적 텍스트 계약(다른 P2 계약군과 동일 스타일)으로 잠근다.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

WRITE_JS = "static/js/foms/foms-write.js"
PROD_STEPS_JS = "static/js/production/foms-production-steps.js"
KANBAN_JS = "static/js/foms/tablet-production-kanban.js"
CGATE_JS = "static/js/construction/foms-complete-gate.js"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# =====================================================================
# 1) foms-write.js — 공용 parser SSOT
# =====================================================================


def test_write_js_exposes_common_mutation_fetch() -> None:
    """window.fomsMutationFetch 가 공용 API 표면으로 정의된다."""
    js = _read(WRITE_JS)
    assert "window.fomsMutationFetch = function" in js
    assert "window.FOMS_MUTATION_TIMEOUT_MS" in js


def test_write_js_classifies_timeout_via_abort_controller() -> None:
    """timeout: AbortController 로 지정 시간 내 미응답 요청을 abort 하고 'timeout'으로 분류.
    (기존 코드는 fetch 에 타임아웃이 전혀 없어 서버가 응답을 미루면 무기한 무음 실패였다.)"""
    js = _read(WRITE_JS)
    assert "AbortController" in js
    assert "controller.abort()" in js
    assert "err.name === 'AbortError'" in js
    assert "kind: 'timeout'" in js


def test_write_js_classifies_malformed_json_and_network() -> None:
    """malformed JSON(파싱 실패)과 네트워크 오류를 별도 kind 로 분류(무음 실패 금지)."""
    js = _read(WRITE_JS)
    assert "kind: 'malformed'" in js
    assert "kind: 'network'" in js
    assert "kind: 'queued'" in js  # 오프라인 큐 적재는 실패가 아니라 큐잉으로 구분


def test_write_js_classifies_403_409_428_with_korean_messages() -> None:
    """403/409/428 각각 사람이 읽을 기본 메시지를 갖고, kind 로 상태코드가 구분된다."""
    js = _read(WRITE_JS)
    assert "403: '권한이 없습니다.'" in js
    assert "409: '다른 요청과 충돌했습니다" in js
    assert "428: '최신 정보가 아닙니다" in js
    assert (
        "kind = (res.status === 403 || res.status === 409 || res.status === 428) "
        "? String(res.status) : 'error'" in js
    )


def test_write_js_extracts_both_legacy_and_new_server_message_shapes() -> None:
    """서버 4xx 응답은 {error: string}(신규)과 {message: string}(레거시)이 혼재한다
    (production/orders.py 는 403 에 error, 409/428 은 message 를 쓴다) — 둘 다 지원."""
    js = _read(WRITE_JS)
    assert "function extractServerMessage(data)" in js
    assert "typeof data.error === 'string'" in js
    assert "typeof data.message === 'string'" in js


def test_write_js_mutation_fetch_never_rejects() -> None:
    """호출자가 catch 를 빼먹어도 무음 실패가 나지 않도록, 최상위 .catch 가 항상
    정규화된 { ok:false, ... } 객체를 resolve 한다(rethrow 없음)."""
    js = _read(WRITE_JS)
    fn = js.split("window.fomsMutationFetch = function", 1)[1]
    fn = fn[: fn.index("\n  };\n")]
    assert "throw" not in fn, "fomsMutationFetch 가 예외를 재throw 하면 호출자 무음 실패 위험"


# =====================================================================
# 2) production scripts — 공용 parser 소비 + 회귀 잠금
# =====================================================================


def test_production_steps_uses_common_parser() -> None:
    """toggleStep/reportDefect 가 공용 parser(mutationFetch → window.fomsMutationFetch)를
    경유한다(ad-hoc try/catch + res.json() 직접 파싱 제거)."""
    js = _read(PROD_STEPS_JS)
    assert "window.fomsMutationFetch" in js
    assert js.count("mutationFetch(") >= 3  # 정의 1 + toggleStep/reportDefect 호출 2


def test_production_steps_ad_hoc_silent_catch_removed() -> None:
    """이전 ad-hoc 패턴(개별 try/catch + console.error 후 뭉뚱그린 메시지)이 공용 경로로
    대체되어 더 이상 존재하지 않는다(회귀 잠금)."""
    js = _read(PROD_STEPS_JS)
    assert "production step toggle error:" not in js
    assert "production defect report error:" not in js


def test_production_steps_visible_error_uses_classified_message() -> None:
    """실패 시 사용자에게 분류된 메시지가 그대로 노출된다(무음 실패 금지)."""
    js = _read(PROD_STEPS_JS)
    assert "'공정 저장 실패: ' + result.message" in js
    assert "'보고 실패: ' + result.message" in js


def test_production_steps_button_reenabled_unconditionally() -> None:
    """toggleStep: 성공/실패 무관하게 버튼이 재활성화된다(finally 대체: await 직후 무조건 실행)."""
    js = _read(PROD_STEPS_JS)
    fn = js.split("async function toggleStep", 1)[1]
    fn = fn[: fn.index("\n  }\n")]
    assert "btn.disabled = false;" in fn
    # 재활성화가 결과 분기(if (!result.ok))보다 먼저 나와 두 경로 모두 적용됨을 보장.
    assert fn.index("btn.disabled = false;") < fn.index("if (!result.ok)")


def test_production_steps_never_reloads() -> None:
    """바텀시트 컴포넌트는 어떤 결과에도 전체 새로고침을 하지 않는다(reload 0)."""
    js = _read(PROD_STEPS_JS)
    assert "location.reload" not in js


# =====================================================================
# 3) tablet-production-kanban.js — 공용 parser 소비 + HOLD_ACTIVE 회귀 보존
# =====================================================================


def test_kanban_uses_common_parser_with_load_order_fallback() -> None:
    """공용 parser 우선 사용 + 로드 순서 방어 폴백(fetch 직접 라우트 제거)."""
    js = _read(KANBAN_JS)
    assert "window.fomsMutationFetch" in js
    assert "function mutationFetch(url, opts)" in js
    assert 'mutationFetch("/api/orders/' in js


def test_kanban_hold_active_retry_business_logic_preserved() -> None:
    """409 HOLD_ACTIVE 해제-후-재시도 전이 로직은 공용 parser 전환과 무관하게 보존된다
    (result.status/result.data 로 동일 판정)."""
    js = _read(KANBAN_JS)
    assert 'result.status === 409 && data.code === "HOLD_ACTIVE"' in js
    assert "retry.release_hold = true" in js


def test_kanban_ad_hoc_top_level_catch_removed() -> None:
    """이전 ad-hoc 최상위 .catch(네트워크 실패만 별도 처리)가 제거되고 공용 kind 분류로
    흡수된다(공용 parser 는 절대 reject 하지 않으므로 최상위 .catch 자체가 불필요)."""
    js = _read(KANBAN_JS)
    assert "[foms-kanban] 열 이동 실패" not in js


def test_kanban_visible_error_and_reload_only_on_success() -> None:
    """실패 시 alert 로 분류 메시지를 보여주고, reload 는 성공(result.ok) 분기에만 있다
    (reload 0 on error)."""
    js = _read(KANBAN_JS)
    assert 'window.alert("오류: " + result.message)' in js
    fn = js.split("function submitMove", 1)[1]
    fn = fn[: fn.index("\n  }\n")]
    assert fn.count("location.reload") == 1
    assert fn.index("if (result.ok)") < fn.index("location.reload")


# =====================================================================
# 4) foms-complete-gate.js — 공용 parser 소비 + 기존 낙관 rollback 보존
# =====================================================================


def test_cgate_uses_common_parser() -> None:
    js = _read(CGATE_JS)
    assert "window.fomsMutationFetch" in js
    assert "function mutationFetch(url, opts)" in js
    assert js.count("mutationFetch(") >= 4  # 정의 1 + upload/evidence/complete 호출 3


def test_cgate_photo_upload_optimistic_thumbnail_rollback_preserved() -> None:
    """유일한 낙관 업데이트 지점(사진 업로드 시 즉시 미리보기 썸네일 삽입)의 실패 rollback이
    공용 parser 전환 후에도 보존된다."""
    js = _read(CGATE_JS)
    fn = js.split("function handlePhotoUpload", 1)[1]
    fn = fn[: fn.index("\n  }\n")]
    assert "thumbs.appendChild(img)" in fn  # 낙관 삽입
    assert "img.parentNode.removeChild(img)" in fn  # 실패 시 rollback
    assert "err.fomsMessage" in fn  # 분류 메시지 노출


def test_cgate_buttons_reenabled_on_failure() -> None:
    """서명 저장 버튼과 완료 버튼 모두 실패 시 재활성화된다."""
    js = _read(CGATE_JS)
    save_fn = js.split("function saveSignature", 1)[1]
    save_fn = save_fn[: save_fn.index("\n  }\n")]
    assert "saveBtn.disabled = false" in save_fn
    complete_fn = js.split("function submitComplete", 1)[1]
    complete_fn = complete_fn[: complete_fn.index("\n  }\n")]
    assert "btn.disabled = false" in complete_fn


def test_cgate_complete_reloads_only_on_success() -> None:
    """완료 처리 실패 시 reload 없이 에러만 표시하고, 성공 시에만 시트를 닫고 reload한다."""
    js = _read(CGATE_JS)
    fn = js.split("function submitComplete", 1)[1]
    fn = fn[: fn.index("\n  }\n")]
    assert fn.count("location.reload") == 1
    assert fn.index("if (!result.ok)") < fn.index("location.reload")


def test_cgate_ad_hoc_manual_json_parsing_removed() -> None:
    """이전 ad-hoc 3중 반복(fetch→r.json().catch(()=>({}))→{ok,data} 조립)이 공용 parser 로
    대체되어 uploadAttachment/registerEvidence/submitComplete 에 더 이상 중복되지 않는다."""
    js = _read(CGATE_JS)
    assert js.count("return { ok: r.ok, data: data };") == 0


# =====================================================================
# 5) 정적 문법 + ?v 캐시버스터 회귀(회귀 0 확인용 — 별도 syntax 스위트가 있어도 로컬 중복 잠금)
# =====================================================================


def test_all_four_scripts_wired_deferred_with_bumped_cachebuster() -> None:
    """4개 스크립트 모두 defer + ?v= 를 유지하고, 기존 파일 변경이라 ?v 가 구 버전에서
    범프됐다(SW staticCacheFirst 회귀 방지, project_sw_stale_js_version_bump)."""
    checks = (
        ("templates/partials/shared/foms_app_shell.html", "foms-write.js", "20260713b"),
        ("templates/partials/shared/layout_head.html", "foms-write.js", "20260713b"),
        ("templates/production/partials/dashboard_body.html", "foms-production-steps.js", "20260713b"),
        ("templates/partials/shared/layout_scripts.html", "tablet-production-kanban.js", "20260724c"),
        ("templates/construction/dashboard.html", "foms-complete-gate.js", "20260712a"),
    )
    for rel, name, old_version in checks:
        html = _read(rel)
        m = re.search(r"<script[^>]*" + re.escape(name) + r"[^>]*>", html)
        assert m is not None, f"{name} not wired in {rel}"
        tag = m.group(0)
        assert "defer" in tag, f"{name} in {rel} must be defer (perf G1)"
        assert "?v=" in tag, f"{name} in {rel} must carry a ?v cachebuster"
        assert old_version not in tag, f"{name} in {rel}: ?v not bumped past {old_version}"
