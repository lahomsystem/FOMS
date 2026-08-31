"""실측 동선 지도(map_view) 지오코딩 폴링 계약 테스트.

지키는 계약:
  1. pending 이 풀려도 전체 재로딩(loadMap())이 아니라 부분 갱신(updateMarkers)을 탄다
     — 전체 재로딩은 showLoading() 으로 지도를 숨기고 setBounds 로 사용자가 보던
       확대/이동 시점까지 리셋한다. 단일 RQ 워커가 한 건씩 채우는 동안 그 깜빡임이
       건수만큼 반복됐다.
  2. 부분 갱신 경로가 폴링 루프를 스스로 이어간다 (전체 재로딩에 의존하지 않는다)
  3. 진행이 있는 회차는 재시도 횟수를 소모하지 않되 백오프 간격은 되감기지 않는다
  4. 무한 폴링 방지용 전체 상한(라운드 수 · 총 경과시간)이 존재한다
  5. 진행 배너가 남은 pending 건수를 사람이 읽을 수 있게 노출한다
  6. 담당자 저장 후 전체 재로딩(마커 색 동기)은 그대로다 — 이번 변경 범위 밖
"""
import re
from pathlib import Path

TEMPLATE = Path("templates/measurement/map_view.html")


def _read() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _poll_block() -> str:
    """auto-poll 분기(loadMap(true) 경로) 소스만 잘라낸다."""
    content = _read()
    start = content.index("// ── auto-poll:")
    end = content.index("// ── 최초 로드 / 필터 변경", start)
    return content[start:end]


def test_resolved_pending_does_not_full_reload_on_kakao_render():
    block = _poll_block()

    # 전체 재로딩은 부분 갱신 수단이 없는 folium 폴백에서만 남는다.
    assert "if (resolvedPending && !kakaoActive) {" in block
    # 무조건 전체 재로딩하던 옛 분기가 되살아나면 안 된다.
    assert not re.search(r"if \(resolvedPending\) \{\s*clearGeocodePoll\(\);\s*loadMap\(\);", block)


def test_resolved_pending_uses_partial_marker_update():
    block = _poll_block()

    assert "const kakaoActive = !!(window.FomsMapViewKakao && window.FomsMapViewKakao.isActive());" in block
    assert "if (kakaoActive) {" in block
    assert "window.FomsMapViewKakao.updateMarkers(" in block
    # 부분 갱신 경로는 지도를 숨기지 않는다(스피너 = 전체 재로딩 전용).
    assert "showLoading()" not in block


def test_poll_loop_continues_itself_after_partial_update():
    block = _poll_block()

    # 폴링 재무장이 전체 재로딩(loadMap())이 아니라 auto-poll 재귀로 이뤄진다.
    assert "geocodePollTimeoutId = setTimeout(function () { loadMap(true); }, delay);" in block


def test_progress_does_not_consume_retry_and_does_not_reset_backoff():
    block = _poll_block()

    # 진행이 있으면 시도 횟수 미소모 — 간격은 유지(1.5초 되감기 금지).
    assert "if (!resolvedPending) geocodePollRetries++;" in block
    assert "geocodePollRetries = 1;" not in block


def test_poll_has_overall_cap():
    content = _read()
    block = _poll_block()

    assert "const GEOCODE_POLL_MAX_ROUNDS = " in content
    assert "const GEOCODE_POLL_MAX_ELAPSED_MS = " in content
    assert "geocodePollRounds >= GEOCODE_POLL_MAX_ROUNDS" in block
    assert "(Date.now() - geocodePollStartedAt) >= GEOCODE_POLL_MAX_ELAPSED_MS" in block
    # 상한에 걸리면 기존 경고 배너로 끝낸다.
    assert "geocodePollFailed();" in block
    assert "일부 주소가 변환되지 않았습니다." in content


def test_poll_banner_reports_remaining_pending_count():
    content = _read()

    assert "function geocodePollProgressText(pendingCount, delayMs)" in content
    assert "'주소 변환 중... ' + pendingCount + '건 남음 ('" in content
    assert "geocodePollProgressText(pendingCount, delay)" in content


def test_manager_save_full_reload_is_untouched():
    """마커 색 동기용 전체 재로딩은 이번 변경 범위 밖 — 회귀 가드."""
    content = _read()

    # res.ok 동반 검사는 2026-08-31 CSRF 403 대응으로 추가됨(실패 사유 표시). 성공 분기의
    # 계약(applyMapManagerValue → loadMap)만 고정하고 조건식 형태는 느슨하게 둔다.
    assert re.search(
        r"if \([^)]*data\.success\) \{\s*applyMapManagerValue\(orderId, cleanName\);\s*loadMap\(\);",
        content,
    )
