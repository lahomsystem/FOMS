"""도면 마감 알림 종류(``DRAWING_DEADLINE_DUE``) 등록 — 폰 P1 · 빠른 배달 · 링크 두 곳(폰 · 벨 목록) · 배너 글(설계서 2026-11-22 §9-5)."""
from __future__ import annotations

import json
from types import SimpleNamespace

from foms.services.notifications import drawing_deadline_alert as alert
from foms.services.notifications import push_sender

# --------------------------------------------------------------------------- #
# 종류 등록 — 폰 P1 · 빠른 배달 · 링크 두 곳 · 배너 글
# --------------------------------------------------------------------------- #
def test_폰_P1_목록과_링크_두_곳(app):
    from foms.api.notifications import _resolve_notification_deep_link as bell_link

    assert alert.NOTIFICATION_TYPE == "DRAWING_DEADLINE_DUE" and alert.NOTIFICATION_TYPE in push_sender._DEFAULT_P1_TYPES
    notif = SimpleNamespace(id=5, notification_type="DRAWING_DEADLINE_DUE", is_urgent=False, order_id=7,
                            title="오늘 도면 마감이에요", message="#7 김가짜 · 붙박이장 — 가짜시 010-1234-5678")
    assert push_sender._should_push(notif) and push_sender._urgency(notif) == "high"
    assert push_sender._deep_link(notif) == "/erp/drawing-workbench/7"
    assert bell_link(notif, {})["deep_link_url"] == "/erp/drawing-workbench/7"
    payload = push_sender._build_payload(notif, "김가짜")
    assert payload["title"] == "오늘 도면 마감이에요 · 김가짜"
    assert payload["body"] == "주문 #7 (김가짜) 오늘까지 도면이 생산으로 내려와야 해요"
    assert payload["data"]["deep_link"] == "/erp/drawing-workbench/7"
    notif.title = "아무 글 010-0000-0000"  # 알려진 제목이 아니면 일반 제목(알림 글은 배너에 안 싣는다)
    assert push_sender._build_payload(notif, "")["title"] == "도면 마감 알림"
    assert "010" not in json.dumps(push_sender._build_payload(notif, ""), ensure_ascii=False)
