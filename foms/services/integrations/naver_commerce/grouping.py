"""묶음('집') 키의 SQL 표현 — 화면들이 같은 정의를 쓰게 하는 한 곳.

왜 모듈 하나를 따로 두는가: 이력 표(``web/admin/naver_ingest``)와 nav 뱃지
(``triage_count``)가 각자 집을 세는데, 세는 식이 두 벌로 갈라지면 **이 모듈이
고치려는 버그가 그대로 재발한다**(2026-08-20 감사 결함 #1·#2 — 45집 vs 43집,
nav 140 vs 필터 43). 식은 여기 하나뿐이고 둘 다 이걸 부른다.

값 계산(파이썬)은 :func:`mapping.group_key_text` 가, 컬럼 기록은 수집·클레임 갱신
경로가 한다. 이 모듈은 **읽는 쪽**만 담당한다.
"""

from __future__ import annotations

from typing import Any


def group_key_expression() -> Any:
    """묶음키 SQL 식 — ``group_key`` → ``external_order_no`` → ``link:<id>`` 순 폴백.

    ``group_key`` 컬럼이 정본이다. 비어 있는 행(컬럼 신설 전 수집분·backfill 전)은
    예전 규칙인 주문번호로 떨어진다 — 정확도는 예전만 못해도 화면이 죽지 않는다.
    둘 다 없으면 링크 단독으로 센다.

    Returns:
        ``gk`` 라벨이 붙은 SQLAlchemy 식.
    """
    from sqlalchemy import String, cast, func, literal

    from models import ExternalOrderLink

    return func.coalesce(
        func.nullif(ExternalOrderLink.group_key, ""),
        func.nullif(ExternalOrderLink.external_order_no, ""),
        literal("link:") + cast(ExternalOrderLink.id, String),
    ).label("gk")


def resolve_group_key(link: Any) -> str:
    """파이썬 쪽 같은 규칙 — :func:`group_key_expression` 과 결과가 같아야 한다.

    **``.strip()`` 을 쓰지 않는다.** 묶음키의 구분자(:data:`mapping.GROUP_KEY_SEP`)는
    제어문자 U+001F 인데, 파이썬은 이걸 **공백문자로 친다**(``GROUP_KEY_SEP.isspace()``
    가 True). 전화·주소가 빈 집의 키(``"N-1" + SEP + SEP``)에서 ``.strip()`` 이 구분자를
    잘라 ``"N-1"`` 을 만드는데, SQL 쪽 ``nullif(group_key, '')`` 는 자르지 않는다 —
    같은 행이 두 키로 읽혀 이 모듈이 없애려던 '정의가 두 벌' 결함이 그대로 재발한다.
    빈 문자열만 값이 아닌 것으로 보는 것이 ``nullif`` 와 정확히 같은 판정이다.

    Args:
        link: ``ExternalOrderLink`` 행.

    Returns:
        묶음키 문자열.
    """
    stored = getattr(link, "group_key", None) or ""
    if stored:
        return stored
    return (getattr(link, "external_order_no", None) or "") or f"link:{link.id}"


__all__ = ["group_key_expression", "resolve_group_key"]
