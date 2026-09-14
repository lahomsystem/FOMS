# -*- coding: utf-8 -*-
"""유령 주문 '재결제 예정' · 부분 클레임 발송 — 화면 잠금 (2026-09-14).

버튼 id·문구·핸들러 등록·CSS 클래스를 **글자로** 못박는다. 이것들이 템플릿에서 사라져도
라우트는 그대로 살아 있어 서버 테스트가 전부 초록이고, 화면에서만 기능이 조용히 죽는다 —
표시를 켜는 입구가 이 버튼 하나뿐이라 그 침묵이 곧 기능 상실이다.

파일을 읽어서 재는 방식은 이 저장소의 기존 관례다(``test_naver_partial_claim_ui`` 의 JS
니들, ``test_naver_backfill_route`` 의 템플릿 문구).
"""
from __future__ import annotations

from tests.services.integrations.naver_ghost_repay_helpers import (
    BAND_TEMPLATE,
    BULK_BUTTON_TEMPLATE,
    PANE_TEMPLATE,
    STRIP_TEMPLATE,
    WORKBENCH_CSS,
    WORKBENCH_JS,
)


# --------------------------------------------------------------------------- #
# 화면 잠금 — 버튼 id · 문구 · 핸들러 등록 · CSS 클래스
# --------------------------------------------------------------------------- #

def test_both_ghost_screens_carry_the_repay_button():
    """띠와 pane 이 **같은 버튼 id·같은 문구**를 들고 있다.

    이 버튼이 표시를 켜는 유일한 입구다. 템플릿에서 사라져도 라우트는 살아 있어 서버
    테스트가 전부 초록이고 화면에서만 기능이 죽는다 — 글자로 못박는 수밖에 없다.
    """
    for path in (BAND_TEMPLATE, PANE_TEMPLATE):
        markup = path.read_text(encoding="utf-8")
        for needle in ('id="wb-ghost-repay-expected"', "data-expected=",
                       "재결제 기다림", "표시 풀기", "재결제 예정"):
            assert needle in markup, f"{path} 에 {needle} 가 없다"


def test_the_js_registers_the_repay_handler():
    """핸들러가 맵에 등록돼 있고, 라우트와 새로고침까지 같은 파일 안에 있다.

    맵에서 한 줄이 빠지면 버튼은 그대로 보이는데 눌러도 아무 일이 없다 — 화면이
    "아무 일도 안 났다"고 말해 주지 않으므로 사람은 한 번 더 누른다.
    """
    js = WORKBENCH_JS.read_text(encoding="utf-8")

    for needle in ("'wb-ghost-repay-expected': submitGhostRepayExpected",
                   "/repay-expected", "softRefresh()"):
        assert needle in js, f"{needle} 가 JS 에 없다"


def test_the_css_defines_the_repay_class():
    """``.wb-ghost__repay`` 가 CSS 에 있다 — 인라인 스타일 금지의 짝이다."""
    css = WORKBENCH_CSS.read_text(encoding="utf-8")

    assert ".wb-ghost__repay" in css, "새 색을 CSS 파일에 안 넣었다(인라인 스타일 금지)"


def test_both_bulk_screens_say_how_many_were_excluded():
    """벌크 발송 문장은 **두 화면이 같은 수**를 말한다(같은 미리보기를 함께 읽는다).

    첫 렌더(템플릿 2곳)와 폴링 렌더(공유 파셜의 ``paintRow``)까지 셋이 같은 문장을 내야
    한다 — 한 곳만 고치면 일괄 발송을 누른 뒤 제외 건수가 조용히 사라진다.
    """
    for path in (BAND_TEMPLATE, STRIP_TEMPLATE):
        markup = path.read_text(encoding="utf-8")
        assert "row.sendable_orders" in markup, f"{path} 가 아직 보낼 건수를 옛 키로 센다"
        assert "클레임 {{ row.claim_excluded }}건은 빼고 보냅니다" in markup, \
            f"{path} 가 제외 건수를 말하지 않는다"

    polling = BULK_BUTTON_TEMPLATE.read_text(encoding="utf-8")
    assert "row.claim_excluded" in polling, "폴링 렌더가 제외 건수를 다시 그리지 않는다"
    assert "'클레임 ' + row.claim_excluded + '건은 빼고 보냅니다'" in polling, \
        "폴링 문장이 템플릿 문장과 글자가 다르다"
