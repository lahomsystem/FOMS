"""대시보드 캡 발동 계약 — 조용한 축소 금지 (2026-08-23).

도면 작업실 사고(모집단 28건 중 1건만 표시)의 뿌리는 **캡으로 뽑은 뒤 파이썬에서
좁히는** 구조였고, 캡에 닿았다는 사실이 어디에도 남지 않아 몇 달간 아무도 몰랐다.
같은 구조를 쓰는 legacy 보드(지방·수도권·자가실측)와 실측 메인 목록에 대해
"캡 발동은 반드시 관측된다"를 계약으로 잠근다.

생산 칸반(foms/web/production/dashboard.py)이 이미 쓰는 규율과 같은 기준이다.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

from foms.services.erp_dashboard_search import LEGACY_DASHBOARD_ORDER_LIMIT
from foms.services.measurement_read_model import (
    MEASUREMENT_MAIN_DISPLAY_CAP,
    MEASUREMENT_MAIN_SEED_LIMIT,
)
from foms.web.measurement.dashboard import _fetch_legacy_dashboard_orders


def _query_returning(count: int) -> MagicMock:
    q = MagicMock()
    q.limit.return_value = q
    q.all.return_value = [MagicMock(id=i) for i in range(count)]
    return q


def test_legacy_fetch_returns_all_rows_under_cap():
    """캡 미만이면 전량 반환 — 경고도 없다."""
    q = _query_returning(10)

    rows = _fetch_legacy_dashboard_orders(q, label="테스트", cap=100)

    assert len(rows) == 10
    # 초과 판정을 위해 cap+1 을 요청한다(별도 count 쿼리 금지 — 추가 왕복 비용).
    q.limit.assert_called_with(101)


def test_legacy_fetch_logs_when_cap_reached(caplog):
    """캡을 넘으면 잘린 사실이 경고 로그로 남는다(조용한 축소 금지)."""
    q = _query_returning(101)

    with caplog.at_level(logging.WARNING):
        rows = _fetch_legacy_dashboard_orders(q, label="지방 대시보드", cap=100)

    assert len(rows) == 100, "캡 상한은 지켜야 한다"
    assert any("캡 발동" in r.message or "캡 발동" in r.getMessage() for r in caplog.records), (
        "캡에 닿았는데 로그가 없다 — 도면 작업실 사고가 몇 달 묻혔던 이유"
    )


def test_legacy_cap_exceeds_observed_population():
    """캡은 운영 실측 모집단(수도권 alert 후보 최대 949건)보다 커야 한다."""
    assert LEGACY_DASHBOARD_ORDER_LIMIT >= 1000, (
        "캡이 모집단보다 작으면 파이썬 분류 단계에서 섹션이 통째로 빈다"
    )


def test_measurement_seed_matches_display_cap():
    """seed 캡과 표시 상한이 어긋나면 상한 전에 행이 사라지거나 헛조회가 된다."""
    assert MEASUREMENT_MAIN_SEED_LIMIT == MEASUREMENT_MAIN_DISPLAY_CAP


def test_measurement_blob_carries_total_count():
    """상한 적용 전 모집단이 캐시 DTO 에 실려야 화면이 잘림을 알릴 수 있다."""
    from foms.services import measurement_read_model as m

    src = (m.__file__ or "")
    assert src
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert '"total_count": total_count,' in text
    assert "list_query.order_by(None).count()" in text


def test_measurement_template_discloses_truncation():
    """잘림 안내는 상시 노출이라 자동 닫힘(.alert 5초)에서 제외돼야 한다."""
    from pathlib import Path

    body = (
        Path(__file__).resolve().parents[2]
        / "templates/measurement/partials/dashboard_main.html"
    ).read_text(encoding="utf-8")
    assert "main_rows_truncated" in body
    assert "main_rows_total" in body
    assert "data-foms-no-autodismiss" in body
