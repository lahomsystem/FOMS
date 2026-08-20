"""묶음('집') 키 계약 — 파이썬과 SQL 이 **같은 값**을 만들어야 한다.

이 계약이 없으면 화면마다 집 수가 갈리는 결함(2026-08-20 감사 #1·#2 — 45집 vs 43집,
nav 140 vs 필터 43)이 그대로 재발한다. 값 계산은 :mod:`...mapping` 이, 읽기 규칙은
:mod:`...grouping` 이 담당하는데 **읽기 규칙이 두 벌**이면 같은 행이 두 키로 읽힌다.

특히 구분자 ``\x1f`` 는 파이썬이 **공백문자로 취급**한다(``'\x1f'.isspace() is True``).
그래서 ``.strip()`` 한 번이 전화·주소가 빈 집의 키에서 구분자를 잘라내 SQL 과 갈린다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.grouping import (
    group_key_expression,
    resolve_group_key,
)
from models import ExternalOrderLink

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


def _link(*, group_key: str | None, order_no: str | None) -> ExternalOrderLink:
    link = ExternalOrderLink(channel="NAVER", external_id=f"PO-GK-{_uid()}",
                             sync_status="COLLECTED", external_order_no=order_no,
                             group_key=group_key, raw_snapshot={})
    db_session.add(link)
    db_session.commit()
    return link


def _sql_key(link: ExternalOrderLink) -> str:
    """같은 행을 SQL 식으로 읽은 값."""
    db_session.expire_all()
    return db_session.query(group_key_expression()).filter(
        ExternalOrderLink.id == link.id).scalar()


def test_separator_is_whitespace_so_strip_would_break_the_contract():
    """구분자가 공백문자라는 사실 자체를 못 박는다 — 이걸 모르면 또 ``.strip()`` 을 부른다."""
    from foms.services.integrations.naver_commerce.mapping import GROUP_KEY_SEP

    assert GROUP_KEY_SEP.isspace() is True
    assert f"N-1{GROUP_KEY_SEP}{GROUP_KEY_SEP}".strip() == "N-1"


@pytest.mark.parametrize("stored,order_no", [
    # 전화·주소가 빈 집 — 구분자가 뒤에 남는다(claim_watch 갱신 등에서 실제로 나온다).
    ("N-GK-1\x1f\x1f", "N-GK-1"),
    # 주문번호가 없고 전화만 있는 집 — 구분자가 앞에 남는다.
    ("\x1f010-1111-2222\x1f서울 강남구 1", "N-GK-2"),
    # 셋 다 있는 보통 집.
    ("N-GK-3\x1f010-1111-2222\x1f서울 강남구 1", "N-GK-3"),
])
def test_python_and_sql_read_the_same_key(app, stored, order_no):
    """컬럼이 있으면 파이썬과 SQL 이 **글자 하나까지** 같은 키를 읽는다."""
    link = _link(group_key=stored, order_no=order_no)

    assert resolve_group_key(link) == _sql_key(link)
    assert resolve_group_key(link) == stored


def test_falls_back_to_order_no_like_sql_does(app):
    """컬럼이 비면 주문번호로 떨어진다 — SQL ``nullif`` 와 같은 지점에서."""
    link = _link(group_key=None, order_no="N-GK-FALLBACK")

    assert resolve_group_key(link) == "N-GK-FALLBACK"
    assert resolve_group_key(link) == _sql_key(link)


def test_empty_column_is_not_a_key(app):
    """빈 문자열은 값이 아니다(SQL 도 ``nullif(...,'')`` 로 같은 판정을 한다)."""
    link = _link(group_key="", order_no="N-GK-EMPTY")

    assert resolve_group_key(link) == "N-GK-EMPTY"
    assert resolve_group_key(link) == _sql_key(link)


def test_link_id_is_the_last_resort(app):
    """둘 다 없으면 링크 단독으로 센다 — 두 경로가 같은 모양이어야 한다."""
    link = _link(group_key=None, order_no=None)

    assert resolve_group_key(link) == f"link:{link.id}"
    assert resolve_group_key(link) == _sql_key(link)
