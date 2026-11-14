"""AI 할 일 제안 승인 대기 폰 알림 — 글 · 주소 · 발송기 갈래 · 서비스 워커 주소 허용(설계서 2026-11-14-foms-graft 3.14 · D210).

완료 기준:
- 잠금화면: 제목 'AI 제안 승인 대기' · 본문 '<할 일 이름> · 주문 #<번호>' — 주문에 손님 이름이 있어도 이름 · 주소 · 날짜를 싣지
  않는다(이름을 읽지도 않는다). 꼴이 아닌 알림 글은 일반 글.
- 누르면 ``/brain?tab=inbox&proposal=<번호>`` — 주문이 걸려 있어도 주문 화면이 아니다. 같은 제안은 꼬리표 하나로 접힌다.
- 이 종류는 보낼 종류(P1)에 있다. 다른 종류의 글 · 주소는 그대로다(공지 · 주문 알림 대조군).
- 서비스 워커는 같은 출처 ``/brain`` 만 더 받는다 — 바깥 출처 · ``//`` · ``/brainx`` 는 계속 대시보드로.
바깥 호출 없음(푸시 서비스 · Redis 를 부르지 않는다). 합성 값만.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from foms.services.notifications import erp_action_push as eap
from foms.services.notifications import push_sender
from foms.services.notifications.erp_action_push import (
    ERP_ACTION_PROPOSAL_TYPE,
    erp_action_deep_link,
    erp_action_message,
    erp_action_push_text,
    erp_action_tag,
)

ROOT = Path(__file__).resolve().parents[2]
SW = ROOT / "static/sw.js"
_NODE = shutil.which("node")


def _notif(message: str, *, order_id: int | None = 12, ntype: str = ERP_ACTION_PROPOSAL_TYPE, nid: int = 501):
    return SimpleNamespace(id=nid, is_urgent=False, notification_type=ntype, order_id=order_id, message=message,
                           title="AI 제안 승인 대기", created_at=None, target_user_id=3)


# ── 글 · 주소 모듈 ───────────────────────────────────────────────────────
def test_message_round_trip_gives_lock_screen_text_link_and_tag():
    message = erp_action_message("방문 옮기기(시공)", 12, 34)
    assert message == "방문 옮기기(시공) · 주문 #12 · 제안 #34"
    assert erp_action_push_text(message) == ("AI 제안 승인 대기", "방문 옮기기(시공) · 주문 #12")
    assert erp_action_deep_link(message) == "/brain?tab=inbox&proposal=34"
    assert erp_action_tag(message) == "foms-erp-action-34"


def test_odd_messages_fall_back_to_generic_text_and_the_inbox():
    for odd in ("", None, "합성 글", "방문 옮기기 · 주문 #12 · 제안 #34\n덧붙인 줄", "x · 주문 #1 · 제안 #2 https://evil"):
        assert erp_action_push_text(odd) == ("AI 제안 승인 대기", eap.ERP_ACTION_GENERIC_BODY)
        assert erp_action_deep_link(odd) == "/brain?tab=inbox" and erp_action_tag(odd) is None
    assert erp_action_message("샵#표시\n둘째 줄" + "가" * 60, 1, 2).count("#") == 2  # 이름 안 '#' 은 지운다


def test_module_imports_no_other_service():
    source = (ROOT / "foms/services/notifications/erp_action_push.py").read_text(encoding="utf-8")
    assert "\nimport foms" not in source and "\nfrom foms" not in source and "\nfrom models" not in source


# ── 발송기 갈래 ──────────────────────────────────────────────────────────
def test_payload_has_no_customer_name_date_or_address_and_opens_the_proposal():
    message = erp_action_message("시공 잡기", 12, 34)
    payload = push_sender._build_payload(_notif(message), "가짜손님")  # 이름을 줘도 싣지 않는다
    assert payload["title"] == "AI 제안 승인 대기" and payload["body"] == "시공 잡기 · 주문 #12"
    assert payload["data"] == {"notification_id": 501, "deep_link": "/brain?tab=inbox&proposal=34"}
    assert payload["tag"] == "foms-erp-action-34" and "requireInteraction" not in payload
    text = json.dumps(payload, ensure_ascii=False)
    for private in ("가짜손님", "2030-", "월 ", "주소"):
        assert private not in text, private


def test_sender_does_not_even_read_the_customer_name(app):
    class _NoQuery:
        def query(self, *args, **kwargs):
            raise AssertionError("손님 이름을 읽으면 안 된다")

    assert push_sender._order_customer_name(_NoQuery(), _notif(erp_action_message("시공 잡기", 12, 34))) == ""


def test_type_is_pushed_and_link_skips_the_order_screen(monkeypatch):
    monkeypatch.delenv("FOMS_PUSH_P1_TYPES", raising=False)
    notif = _notif(erp_action_message("단계 넘기기", 12, 7))
    assert push_sender._should_push(notif) is True and ERP_ACTION_PROPOSAL_TYPE in push_sender._DEFAULT_P1_TYPES
    assert push_sender._deep_link(notif) == "/brain?tab=inbox&proposal=7"  # 주문 #12 화면이 아니다
    assert push_sender._urgency(notif) == "normal"


def test_other_types_keep_their_text_and_links():
    order_note = _notif("주소 합성", ntype="ERP_ORDER_CHANGED", order_id=99)
    assert push_sender._deep_link(order_note) == "/erp/drawing-workbench/99?tab=timeline"
    title, body = push_sender._build_payload(order_note, "가짜손님")["title"], push_sender._build_payload(
        order_note, "가짜손님")["body"]
    assert "가짜손님" in title and body.startswith("주문 #99 (가짜손님)")  # 주문 알림은 지금처럼 이름을 싣는다(대조군)
    notice = _notif("", ntype="FOMS_NOTICE", order_id=None)
    assert push_sender._build_payload(notice)["data"]["deep_link"] == "/notices"


# ── 서비스 워커 주소 허용 ────────────────────────────────────────────────
_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const ctx = { self: { addEventListener: function () {}, location: { origin: 'https://foms.example.com' } },
              caches: {}, clients: {}, fetch: function () {}, URL: URL, Promise: Promise, setTimeout: setTimeout,
              console: { debug: function(){}, log: function(){}, error: function(){}, warn: function(){} } };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.env.FOMS_SW_PATH, 'utf8'), ctx);
const san = ctx.sanitizePushDeepLink;
const cases = ['/brain?tab=inbox&proposal=34', '/brain', '/brain/items/a', '/brainx', '/brain-evil',
               'https://evil.com/brain?tab=inbox', '//evil.com/brain', 'javascript:alert(1)', '/erp/orders/5',
               '/partner/orders/5', '/admin'];
process.stdout.write(JSON.stringify(cases.map(san)));
"""


@pytest.mark.skipif(_NODE is None, reason="node 없음")
def test_service_worker_accepts_same_origin_brain_only():
    proc = subprocess.run([_NODE, "-e", _HARNESS], capture_output=True, text=True, encoding="utf-8",
                          env={**__import__("os").environ, "FOMS_SW_PATH": str(SW)})
    assert proc.returncode == 0, proc.stderr
    fallback = "/erp/dashboard"
    assert json.loads(proc.stdout) == [
        "/brain?tab=inbox&proposal=34", "/brain", "/brain/items/a", fallback, fallback, fallback, fallback, fallback,
        "/erp/orders/5", "/partner/orders/5", fallback]


@pytest.mark.skipif(_NODE is None, reason="node 없음")
def test_service_worker_still_parses():
    proc = subprocess.run([_NODE, "--check", str(SW)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert 'CACHE_VERSION = "foms-p2-v11"' in SW.read_text(encoding="utf-8")  # 판 값은 그대로(캐시와 무관한 갈래)
