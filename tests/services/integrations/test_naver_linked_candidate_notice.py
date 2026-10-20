"""주문이 이미 붙은 수집분에도 **비슷한 기존 주문**을 알린다(2026-10-20).

운영 #5768(강민주)·#5774(이재천)는 후보가 안 보여 새로 만든 주문이었다. 후보 칸이
주문 생성 전에만 그려져서, 만든 뒤에는 잘못을 알아챌 자리가 없었다.
"""

from __future__ import annotations

from tests.services.integrations.naver_candidate_pair_helpers import (  # noqa: F401
    _link,
    _login,
    _order,
    _pane,
    workbench_on,
)

NOTICE = "같은 고객일 수 있는 다른 주문"


def test_linked_link_lists_other_candidate_orders(app, client, workbench_on):
    _login(client)
    old_id = _order(tel="010-1111-0001")
    new_id = _order(tel="010-1111-0001")
    link = _link(order_no="N-LINKED-1", tel="010-1111-0001", amount=1000, order_id=new_id)
    body = _pane(client, link_id=link.id)
    assert NOTICE in body
    assert f"#{old_id}" in body


def test_linked_link_without_candidates_has_no_notice(app, client, workbench_on):
    """음성 대조군 — 다른 주문이 없으면 안내도 없다."""
    _login(client)
    only_id = _order(tel="010-1111-0002", name="혼자고객")
    link = _link(order_no="N-LINKED-2", tel="010-1111-0002", amount=1000,
                 order_id=only_id, name="혼자고객")
    assert NOTICE not in _pane(client, link_id=link.id)
