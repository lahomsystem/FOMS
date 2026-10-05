"""jsonb 문서 **투영**(필요한 경로만 남긴 얇은 문서)을 SQL 로 조립할 때 쓰는 공용 조각.

처음에는 네이버 처리 목록(:mod:`foms.web.admin.naver_list_snapshot`)에만 있었다. 정산 모집단
(:mod:`foms.services.settlement_source`)도 같은 수를 쓰게 되면서 서비스 계층이 웹 관리자 패키지를
import 하지 않도록 여기로 옮겼다(그 패키지는 import 만으로 관리자 라우트 전부를 싣는다).

- :class:`json_object_absent` — ``JSON_OBJECT(k VALUE v, … ABSENT ON NULL RETURNING json)``.
  ``jsonb_build_object`` 는 없는 키를 ``null`` 로 채워 원본과 모양이 달라진다.
- :func:`jsonb_key_order` — jsonb 가 객체 키를 저장하는 순서(출력 키 순서를 원본과 맞춘다).
- :func:`supports_sql_projection` — ``ABSENT ON NULL`` 이 있는 PostgreSQL 16 이상인가.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.types import NullType

__all__ = [
    "MIN_SERVER_VERSION",
    "json_object_absent",
    "jsonb_key_order",
    "supports_sql_projection",
]

#: ``JSON_OBJECT … ABSENT ON NULL`` 은 PostgreSQL 16 부터다(CI PG 레인 16, 스테이징·운영 17).
MIN_SERVER_VERSION = (16,)


class json_object_absent(FunctionElement):  # noqa: N801 — SQL 함수 식이라 소문자 이름(func.* 와 같은 결)
    """``JSON_OBJECT(k VALUE v, … ABSENT ON NULL RETURNING json)`` — 있는 키만 담는다.

    ``jsonb_build_object`` 는 없는 키를 ``null`` 로 채운다(원본과 모양이 달라진다).
    인자는 ``(키, 값, 키, 값, …)`` 순서다. 키는 호출자가 검사한 상수 글자다.
    """

    name = "json_object"
    inherit_cache = True
    type = NullType()


@compiles(json_object_absent, "postgresql")
def _compile_json_object_absent(element: json_object_absent, compiler: Any, **kw: Any) -> str:
    """PostgreSQL 문법으로 펼친다(다른 방언에서는 이 식을 만들지 않는다)."""
    args = list(element.clauses)
    pairs = ", ".join(f"{compiler.process(key, **kw)} VALUE {compiler.process(value, **kw)}"
                      for key, value in zip(args[0::2], args[1::2], strict=True))
    return f"JSON_OBJECT({pairs} ABSENT ON NULL RETURNING json)"


def jsonb_key_order(key: str) -> tuple[int, bytes]:
    """jsonb 가 객체 키를 저장하는 순서(길이 먼저, 같으면 바이트) — 출력 순서를 맞춘다."""
    raw = key.encode("utf-8")
    return (len(raw), raw)


def supports_sql_projection(db: Any) -> bool:
    """이 세션에서 SQL 투영을 쓸 수 있는가(PostgreSQL 16 이상).

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        SQL 투영을 쓰면 True. 아니면 호출자가 통째로 읽고 파이썬 정본으로 줄인다
        (결과는 같고 비용만 옛날 값이다 — SQLite 테스트 레인·옛 로컬 PG 보호).
    """
    # 엔진의 첫 연결 전에는 서버 버전을 모른다 — 연결을 먼저 잡아 판정이 흔들리지 않게 한다
    # (어차피 바로 다음 조회가 같은 트랜잭션을 연다).
    dialect = getattr(db.connection(), "dialect", None)
    if getattr(dialect, "name", "") != "postgresql":
        return False
    version = getattr(dialect, "server_version_info", None) or ()
    return tuple(version[:1]) >= MIN_SERVER_VERSION
