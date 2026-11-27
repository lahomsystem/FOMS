"""생산 태블릿 작은 흐름 고침 둘(사장님 결정 2026-11-26).

① 작업 시트에서 보류 사유 줄을 공정 칸 바로 위로(보류 중이고 사유가 있을 때만).
② [바뀐 것] 탭의 [확인했어요]는 화면을 다시 읽지 않고 그 줄만 지운다(다른 화면은 지금처럼 다시 읽기).
"""
from __future__ import annotations

from pathlib import Path

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from tests.domains.test_production_sheet_page import SHEET_URL, _make_user, _seed_order

ROOT = Path(__file__).resolve().parents[2]


def _scroll(html: str) -> str:
    return html.split('class="foms-prod-page__side-scroll"', 1)[1].split('class="foms-prod-page__foot"', 1)[0]


def test_보류_중이고_사유가_있으면_보류_사유가_공정_칸_바로_위(client) -> None:
    _make_user(client, "g3_hold_on", "PRODUCTION")
    order = _seed_order()
    sd = dict(order.structured_data)
    sd["production"] = {**sd["production"], "hold": {"active": True, "reason": "자재 기다림", "at": now_utc_naive().isoformat()}}
    order.structured_data = sd
    db_session.commit()
    scroll = _scroll(client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True))
    hold = scroll.find("보류 · <strong>자재 기다림</strong>")
    steps = scroll.find('aria-label="공정"')
    assert 0 <= hold < steps
    between = scroll[hold:steps]
    assert "<section" in between and between.count("<section") == 1  # 보류 줄 다음 첫 상자가 공정(<section 의 시작 글자만 걸림)
    assert scroll.count("보류 · <strong>") == 1  # 아래 자리에 한 번 더 그리지 않는다


def test_보류가_아니면_공정이_맨_위_그대로(client) -> None:
    _make_user(client, "g3_hold_off", "PRODUCTION")
    order = _seed_order()
    scroll = _scroll(client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True))
    assert "callout--hold" not in scroll
    assert scroll[: scroll.find('aria-label="공정"')].count("<section") == 1


def test_보류_사유가_없으면_줄을_그리지_않는다(client) -> None:
    _make_user(client, "g3_hold_noreason", "PRODUCTION")
    order = _seed_order()
    sd = dict(order.structured_data)
    sd["production"] = {**sd["production"], "hold": {"active": True, "reason": "", "at": now_utc_naive().isoformat()}}
    order.structured_data = sd
    db_session.commit()
    scroll = _scroll(client.get(SHEET_URL.format(id=order.id)).get_data(as_text=True))
    assert "callout--hold" not in scroll


def test_보류_줄은_마크업_순서로_옮겼다_CSS_order_아님() -> None:
    tpl = (ROOT / "templates/production/sheet.html").read_text(encoding="utf-8")
    assert tpl.index("callout--hold") < tpl.index('aria-label="공정"') < tpl.index('aria-label="변경 알림"')
    css = (ROOT / "static/css/contexts/production/sheet.css").read_text(encoding="utf-8")
    import re
    assert not re.search(r"(?<![\w-])order\s*:", css)


# --------------------------------------------------------------------------- #
# ② [바뀐 것] 탭 [확인했어요] = 그 줄만 지운다
# --------------------------------------------------------------------------- #
JS = "static/js/foms/tablet-domain-sheets.js"
PIN = "20261127p"  # 2026-11-27 옛 생산 칸반 몫을 지우며 한 번 더 올렸다(싣는 곳 셋 · 출고 진입이 같은 값)


def _ack_fn(js: str) -> str:
    return js.split("function changeAck(orderId, inboxRow) {", 1)[1].split("// 출고 서랍 저장", 1)[0]


def test_바뀐_것_탭_줄만_지우고_다른_길은_다시_읽기가_남는다_원문_계약() -> None:
    js = (ROOT / JS).read_text(encoding="utf-8")
    body = _ack_fn(js)
    # 다시 읽기는 [바뀐 것] 탭 줄 길(removeInboxRow 가 true)에서만 빠진다 — 나머지 길은 지금 그대로 다시 읽는다
    assert "if (!removeInboxRow(inboxRow)) window.location.reload();" in body
    assert body.count("window.location.reload()") == 1
    # 눌린 단추가 [바뀐 것] 탭 줄 안일 때만 그 줄을 넘긴다(작업 시트 · 날짜 탭 줄은 null)
    assert 'changeAck(ackBtn.getAttribute("data-order-id"), ackBtn.closest("[data-foms-home-inbox]"));' in js
    # 실패 · 연결 끊김 글은 그대로
    assert '"처리하지 못했어요"' in body and "연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요." in body
    # 빈 글은 서버 템플릿 글 그대로(새 글 금지)
    tpl = (ROOT / "templates/production/partials/home_changes.html").read_text(encoding="utf-8")
    assert "새로 바뀐 것이 없어요." in tpl and '"새로 바뀐 것이 없어요."' in js
    assert 'class="foms-prod-home__empty"' in tpl and 'empty.className = "foms-prod-home__empty";' in js


def test_바뀐_것_탭_줄만_받는_표지가_템플릿에_있다() -> None:
    tpl = (ROOT / "templates/production/partials/home_changes.html").read_text(encoding="utf-8")
    assert 'data-foms-home-inbox="{{ it.id }}"' in tpl
    home = (ROOT / "templates/production/partials/home_body.html").read_text(encoding="utf-8")
    assert "aria-current=\"page\"" in home and "is-hot" in home


def test_스크립트_핀은_싣는_곳_전부_같이_올랐다() -> None:
    for rel in ("templates/production/partials/home_body.html", "templates/production/sheet.html"):
        assert f"tablet-domain-sheets.js') }}}}?v={PIN}" in (ROOT / rel).read_text(encoding="utf-8"), rel
    assert f"'/static/js/foms/tablet-domain-sheets.js?v={PIN}'" in (ROOT / "static/js/shipment/shipment-entry.js").read_text(encoding="utf-8")
    assert f"shipment-entry.js') }}}}?v={PIN}" in (ROOT / "templates/shipment/partials/dashboard_scripts.html").read_text(encoding="utf-8")


def test_확인했어요_동작은_Node_로_돈다_줄_삭제_숫자_빈_글_다른_화면은_다시_읽기() -> None:
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        import pytest
        pytest.skip("node 없음")
    proc = subprocess.run([node, str(ROOT / "tests/support/production_change_ack_node_checks.js")], capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    assert proc.returncode == 0 and proc.stdout.strip().endswith("OK"), proc.stdout + proc.stderr
