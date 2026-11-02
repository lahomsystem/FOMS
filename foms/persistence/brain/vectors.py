"""의미 찾기 표(``brain_embeddings``) — **판 행과 따로 · 근원 종류별 하나의 표**(사장님 D114 · 설계서 7절 '비슷한 것 찾기').

- 근원 종류(``source_kind``): ``brain_item``(회사 지식 항목 — 근원 키 = 항목 키, 근원 판 = 그 판 번호) · ``chatbot_question``
  (물어보기 가린 질문 — 근원 키 = 질문 번호) · ``cs_case``(상담 사례 — 가린 손님 질문 + 가린 직원 답, 근원 키 = 상담 차례 번호).
  (근원 종류, 근원 키, 모델)마다 한 줄 — 근원이 바뀌면 그 줄을 바꾼다(쌓기만 하는 판 행 ``brain_objects`` 에는 벡터를 넣지 않는다).
- **이 표는 ORM ``Base`` 밖이다**(따로 :data:`vector_metadata`) — PostgreSQL ``vector`` 형은 pgvector 확장이 있어야 하는데
  CI PG 레인 이미지(postgres:17)에는 없어 ``create_all`` 이 통째로 죽는다. 운영 · 스테이징은 마이그레이션 ``brain_02`` 가 pgvector 가
  있을 때만 만든다(없으면 만들지 않고 의미 찾기는 꺼진 채 — 글자 찾기로 돈다). SQLite 시험은 벡터를 JSON 글로 담는다.
- 정확 찾기(색인 없음) — 이 크기(수천 줄)에서 충분하다. HNSW 는 pgvector 0.8.4 이상(0.8.3 · 0.8.4 가 HNSW 손상 버그를 고침)으로
  올리고 수만 줄을 넘을 때(설계서 7.5 끝).
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, MetaData, String, Table, func
from sqlalchemy.types import Text, TypeDecorator, UserDefinedType

DIMENSION = 1024
TABLE = "brain_embeddings"


class _PgVector(UserDefinedType):
    """PostgreSQL ``vector(n)`` 형(pgvector) — DDL 글만(값은 ``[..]`` 글로 오간다)."""

    cache_ok = True

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def get_col_spec(self, **_kw: Any) -> str:
        return f"vector({self.dim})"


class VectorType(TypeDecorator):
    """벡터 칸 — PostgreSQL 은 ``vector(n)``, 그 밖(SQLite 시험)은 글. 값은 늘 ``list[float]``(글 꼴 ``[a,b,…]`` = JSON)."""

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = DIMENSION) -> None:
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect: Any) -> Any:
        return dialect.type_descriptor(_PgVector(self.dim) if dialect.name == "postgresql" else Text())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return "[" + ",".join(repr(float(x)) for x in value) + "]"

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return [float(x) for x in (json.loads(value) if isinstance(value, str) else value)]


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


vector_metadata = MetaData()

#: 근원 종류(정본 목록 — 마이그레이션 ``brain_02`` 의 검사 제약과 같다).
SOURCE_KINDS: tuple[str, ...] = ("brain_item", "chatbot_question", "cs_case")

brain_embeddings = Table(
    TABLE, vector_metadata,
    Column("id", Integer, primary_key=True),
    Column("source_kind", String(24), nullable=False),
    Column("source_key", String(120), nullable=False),
    Column("source_version", Integer, nullable=True),
    Column("model", String(40), nullable=False),
    Column("dimension", Integer, nullable=False),
    Column("embedding", VectorType(DIMENSION), nullable=False),
    Column("text_hash", String(64), nullable=False),
    Column("created_at", DateTime, nullable=False, default=_utcnow, server_default=func.now()),
    CheckConstraint("source_kind IN ('brain_item','chatbot_question','cs_case')", name="ck_brain_embeddings_source_kind"),
    Index("uq_brain_embeddings_source_model", "source_kind", "source_key", "model", unique=True),
)
