"""nav 수집 뱃지는 **쓰는 화면에서만** 센다 (2026-09-11).

이 값은 컨텍스트 프로세서가 넣으므로 `render_template` 마다 계산됐다. 그런데 뱃지를 그리는
템플릿은 `layout_nav.html` · `orders/index.html` · `admin/naver_ingest.html` 셋뿐이고,
ERP 셸의 **프래그먼트 응답**(`?view=fragment`)은 레이아웃을 안 싣는데도 같은 값을 계산하고
버렸다. 탭 전환이 곧 프래그먼트 요청이라 "탭 왕복이 느리다"는 신고의 한 축이었다.

스테이징 실측(claude_master, 워크벤치 코호트 안, 35초 간격 콜드):

    /erp/dashboard                 render=423.0ms  nvbadge=382ms  layout_nav 렌더 O(뱃지 156)
    /erp/dashboard?view=fragment   render=590.2ms  nvbadge=552ms  layout_nav 렌더 X

세는 **정의는 건드리지 않는다**. 모집단을 SQL COUNT 로 옮기는 길은 계약상 막혀 있다
(`triage_count._workbench_group_count` docstring: 취소 표식 JSONB·발주확인 전 집 때문에
SQL 술어로는 같은 수가 안 나온다 — nav 67 · 탭 45 불일치 전례).
"""
from __future__ import annotations

from foms.services.context_processors import LazyBadgeCount


def test_does_not_count_until_the_template_uses_it() -> None:
    """값을 만들기만 하면 아무것도 안 센다 — 프래그먼트가 공짜가 되는 지점."""
    calls: list[int] = []
    lazy = LazyBadgeCount(lambda: (calls.append(1), 7)[1])

    assert calls == [], "생성만으로 계산하면 지연 평가가 아니다"

    assert bool(lazy) is True  # {% if naver_triage_pending %}
    assert str(lazy) == "7"    # {{ naver_triage_pending }}
    assert calls == [1], "여러 번 써도 계산은 1회여야 한다"


def test_behaves_like_the_int_it_replaces() -> None:
    """템플릿·파이썬이 예전 int 로 하던 것을 그대로 해야 한다(회귀 가드)."""
    lazy = LazyBadgeCount(lambda: 156)

    assert int(lazy) == 156
    assert lazy == 156
    assert f"{lazy}" == "156"
    assert bool(lazy) is True


def test_zero_is_falsy_so_the_badge_stays_hidden() -> None:
    """0 이면 `{% if %}` 가 거짓이어야 뱃지가 안 뜬다 — 0 을 빨간 뱃지로 그리면 오보다."""
    lazy = LazyBadgeCount(lambda: 0)

    assert bool(lazy) is False
    assert str(lazy) == "0"


def test_counting_definition_is_untouched() -> None:
    """정의는 그대로 `get_triage_pending_count` 를 부른다(SQL COUNT 로 갈아타지 않았다)."""
    import inspect

    from foms.services import context_processors as cp

    src = inspect.getsource(cp.inject_status_list)
    assert "LazyBadgeCount(" in src
    assert "get_triage_pending_count(" in src
    # 계측은 실제 계산 시점에 걸려야 헤더가 진실을 말한다.
    assert 'with phase("nvbadge")' in inspect.getsource(cp.LazyBadgeCount)
