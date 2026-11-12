"""의미 찾기 — Voyage AI 벡터(사장님 D114 · 설계서 7절 '비슷한 것 찾기' · 7.5 끝). **처음 끔**(설정 ``brain_embeddings_enabled``).

근원 종류는 셋(:data:`foms.persistence.brain.vectors.SOURCE_KINDS` — 회사 지식 항목 · 물어보기 가린 질문 · 상담 사례 가린 질문 +
가린 직원 답)이고 근원별 넣기는 :mod:`.embed_sources` 다. 상담 사례는 백필만(설정 ``cs_case_embeddings_enabled`` 처음 끔).

공급처 · 꼴(공식 문서 docs.voyageai.com 2026-11-02 열람): 모델 :data:`MODEL` ``voyage-4``(다국어 일반 찾기 · 기본 1024 차원 ·
백만 토큰당 0.06달러 — 새 v4 모델은 2억 토큰 무료 몫이 있지만 돈 상한은 정가로 센다), ``POST https://api.voyageai.com/v1/embeddings``
본문 ``{"input": [...], "model", "input_type": "query" | "document", "output_dimension": 1024}`` · 머리 ``Authorization: Bearer
<VOYAGE_API_KEY>`` · 답 ``data[].embedding`` · ``data[].index`` · ``usage.total_tokens``. 새 패키지 없이 ``requests`` 로 부른다.

- **넣는 글**: 반영(``active``) 정체 유형 항목의 대표 이름 · 다른 · 숨은 이름 · 위 낱말 · 글 앞부분만(:func:`doc_text`). 보기
  범위 ``price`` · ``admin`` 항목은 넣지 않는다(가격 재량 · 관리 글을 새 바깥 처리자에게 보내지 않는다 — 그 항목은 글자 찾기로만).
  개인정보 꼴이 보이는 글(:func:`foms.services.cs_agent.masking.leak_counts`)과 계좌 같은 긴 번호(:func:`account_like`)가 보이는
  글은 건너뛴다. 질문은 **가린 글만** 벡터로 바꾼다(:mod:`.chat_answer`).
- **돈 · 시간**: 부를 때마다 어림값을 의미 찾기 돈 줄(:data:`SPEND_KEY` — 챗봇 · 상담 줄과 따로)에 예약하고 실제 토큰으로 바로잡는다.
  하루 상한(설정 ``embed_daily_cap_usd`` — 비우면 부르지 않음) · 한 번 시간 상한(``embed_timeout_s``).
- **물러남**: 꺼짐 · 열쇠 env 없음 · 표 없음(pgvector 없는 DB) · 상한 · 실패 — 질문 벡터는 ``None`` 이 되고 찾기는 지금의 글자 찾기
  그대로 돈다(:func:`query_vector` 는 던지지 않는다).
- **가까운 항목**(:func:`nearest`): 보기 범위 · 유효 기간 · 반영 · 정체 유형 조건을 SQL 에 걸고 그 안에서 코사인 거리 순(PostgreSQL
  ``<=>`` 정확 찾기 · SQLite 시험은 파이썬 코사인). 볼 수 없는 항목은 순위에도 들지 않는다.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import logging
import math
import os
import re
from decimal import Decimal
from typing import Any, Callable, Iterable, Iterator, Optional

import requests
from sqlalchemy import Float, String, bindparam, cast, delete, insert, inspect, select, text, update
from sqlalchemy.exc import SQLAlchemyError

from foms.persistence.brain.models import BrainObject
from foms.persistence.brain.vectors import DIMENSION, SOURCE_KINDS, TABLE, _PgVector, brain_embeddings
from foms.services.brain.chat_settings import EMBED_FIELD, ChatSettings
from foms.services.brain.constants import IDENTITY_TYPES, SCOPE_ADMIN, SCOPE_PRICE, STATUS_ACTIVE
from foms.services.brain.labels import aliases_of, broader_of, pref_of
from foms.services.brain.read import effective_clauses
from foms.services.brain.scope import Viewer
from foms.services.cs_agent.brain_spend import BrainError, check_budget, reserve_spend, settle_spend
from foms.services.cs_agent.masking import leak_counts

logger = logging.getLogger(__name__)

MODEL = "voyage-4"
PRICE_PER_MILLION = Decimal("0.06")
API_URL = "https://api.voyageai.com/v1/embeddings"
KEY_ENV = "VOYAGE_API_KEY"
SPEND_KEY = "brain_embed_spend"
SOURCE_ITEM, SOURCE_QUESTION, SOURCE_CASE = SOURCE_KINDS
MAX_BATCH, DOC_CHARS = 64, 800
#: 넣지 않는 보기 범위(가격 재량 · 관리).
HELD_SCOPES = frozenset({SCOPE_PRICE, SCOPE_ADMIN})
Embedder = Callable[[list[str], str, float], tuple[list[list[float]], int]]


class EmbedUnavailable(RuntimeError):
    """벡터를 만들 수 없다 — ``code`` 만(글 · 열쇠 없음)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def voyage_embedder(texts: list[str], input_type: str, timeout: float) -> tuple[list[list[float]], int]:
    """Voyage AI 한 번(다시 하지 않는다). (벡터들, 토큰 수). 실패는 :class:`EmbedUnavailable`."""
    key = (os.environ.get(KEY_ENV) or "").strip()
    if not key:
        raise EmbedUnavailable("no_key")
    try:
        response = requests.post(API_URL, timeout=timeout, headers={"Authorization": f"Bearer {key}"},
                                 json={"input": texts, "model": MODEL, "input_type": input_type,
                                       "output_dimension": DIMENSION})
    except requests.Timeout:
        raise EmbedUnavailable("timeout") from None
    except requests.RequestException:
        raise EmbedUnavailable("network") from None
    if response.status_code != 200:
        raise EmbedUnavailable(f"http_{response.status_code}")
    try:
        body = response.json()
        rows = sorted(body["data"], key=lambda d: int(d["index"]))
        return [list(map(float, r["embedding"])) for r in rows], int(body["usage"]["total_tokens"])
    except (ValueError, KeyError, TypeError):
        raise EmbedUnavailable("bad_response") from None


_EMBEDDERS: list[Embedder] = []


@contextlib.contextmanager
def embedder_source(embedder: Embedder) -> Iterator[None]:
    """벡터 만드는 함수를 잠시 바꾼다(시험 · 도구 — 운영 길은 :func:`voyage_embedder`)."""
    _EMBEDDERS.append(embedder)
    try:
        yield
    finally:
        _EMBEDDERS.remove(embedder)


def _embedder() -> Optional[Embedder]:
    """지금 쓸 함수 — 바꿔 끼운 것, 아니면 열쇠 env 가 있을 때만 Voyage."""
    if _EMBEDDERS:
        return _EMBEDDERS[-1]
    return voyage_embedder if (os.environ.get(KEY_ENV) or "").strip() else None


def table_ready(session: Any) -> bool:
    """벡터 표가 있나(pgvector 없는 DB · 만들지 않은 시험 DB 는 없음). 세션의 연결로 본다 — 엔진에서 연결을 따로 빌리면
    연결 하나를 나눠 쓰는 풀(SQLite)에서 돌려줄 때 되돌리기가 일어나 세션의 아직 커밋 안 한 쓰기가 사라진다."""
    try:
        return inspect(session.connection()).has_table(TABLE)
    except SQLAlchemyError:  # failopen: fail-closed: 표를 확인 못 하면 없는 것으로 — 의미 찾기를 끄고 글자 찾기로
        return False


def daily_cap(cfg: ChatSettings) -> Optional[Decimal]:
    """의미 찾기 하루 상한(비우면 ``None`` = 부르지 않음)."""
    raw = cfg.get("embed_daily_cap_usd")
    return None if raw is None else Decimal(str(raw))


def off_reason(session: Any, cfg: ChatSettings, switch: str = EMBED_FIELD) -> Optional[str]:
    """지금 벡터를 쓸 수 없는 까닭(쓸 수 있으면 ``None``). ``switch`` 는 근원의 설정 칸(상담 사례는 따로 — 처음 끔)."""
    if not cfg.get(switch):
        return "off"
    if _embedder() is None:
        return "no_key"
    if daily_cap(cfg) is None:
        return "no_cap"
    if not table_ready(session):
        return "no_table"
    return None


def estimate_cost(texts: list[str]) -> Decimal:
    """어림값(예약) — 글자 수의 2배 + 줄마다 16 토큰을 정가로(한글은 글자보다 토큰이 많을 수 있어 넉넉히)."""
    tokens = sum(len(t) for t in texts) * 2 + 16 * len(texts)
    return Decimal(tokens) * PRICE_PER_MILLION / Decimal(1_000_000)


def embed_texts(session: Any, texts: list[str], *, input_type: str, cfg: ChatSettings,
                now: datetime.datetime) -> list[list[float]]:
    """글들 → 벡터들(돈 예약 → 부르기 → 바로잡기). 세션을 커밋한다. 실패는 :class:`EmbedUnavailable`."""
    embedder, cap = _embedder(), daily_cap(cfg)
    if embedder is None or cap is None:
        raise EmbedUnavailable("not_ready")
    worst = estimate_cost(texts)
    try:
        check_budget(session, cap=cap, now=now, key=SPEND_KEY)
        reserve_spend(session, worst, cap=cap, now=now, key=SPEND_KEY)
    except BrainError as exc:
        raise EmbedUnavailable(exc.code) from None
    try:
        vectors, tokens = embedder(texts, input_type, float(cfg.get("embed_timeout_s")))
    except EmbedUnavailable:
        settle_spend(session, worst, worst, now=now, key=SPEND_KEY)  # 보냈을 수 있다 — 어림값을 남긴다(막는 쪽)
        raise
    settle_spend(session, worst, Decimal(int(tokens)) * PRICE_PER_MILLION / Decimal(1_000_000), now=now, key=SPEND_KEY)
    if len(vectors) != len(texts) or any(len(v) != DIMENSION for v in vectors):
        raise EmbedUnavailable("bad_shape")
    return vectors


def query_vector(session: Any, question: str, *, cfg: ChatSettings, now: datetime.datetime) -> Optional[list[float]]:
    """가린 질문 → 벡터(못 쓰면 ``None`` — 던지지 않는다, 찾기는 글자로만)."""
    if off_reason(session, cfg) is not None or not safe_text(question):
        return None
    try:
        return embed_texts(session, [question[:2000]], input_type="query", cfg=cfg, now=now)[0]
    except EmbedUnavailable as exc:
        logger.info("[회사 지식 의미 찾기] 질문 벡터를 못 만들어 글자 찾기로 code=%s", exc.code)
        return None


_DIGITS = re.compile(r"\d+(?:-\d+){0,5}")


def account_like(text: str) -> bool:
    """계좌 · 카드 같은 긴 번호 꼴(숫자 열 개 이상이 붙거나 줄표로 이어짐) — 날짜(숫자 여덟) · 치수는 아니다."""
    return any(sum(ch.isdigit() for ch in m.group(0)) >= 10 for m in _DIGITS.finditer(text or ""))


def safe_text(body: str) -> bool:
    """바깥 처리자에게 보내도 되는 글 — 가림 검사 0 · 계좌 같은 번호 없음(모든 근원이 같은 검사)."""
    return bool(body and body.strip()) and not any(leak_counts(body).values()) and not account_like(body)


def doc_text(row: BrainObject) -> Optional[str]:
    """넣을 글 — 대표 이름(+ 항목 이름) · 다른 · 숨은 이름 · 위 낱말 · 글 앞부분. 넣지 않을 항목(범위 · 상태 · 유형)과
    **가림 검사에 걸리거나 계좌 같은 번호가 보이는 글**은 ``None``(점검 '지금 5' — 바깥 처리자에게 보내지 않는다)."""
    if row.status != STATUS_ACTIVE or row.item_type not in IDENTITY_TYPES or row.visibility in HELD_SCOPES:
        return None
    pref = pref_of(row.name, row.payload)
    parts = [pref] + ([row.name] if row.name != pref else [])
    aliases, broader = aliases_of(row.payload), broader_of(row.payload)
    if aliases:
        parts.append("다른 이름: " + ", ".join(aliases))
    if broader:
        parts.append("위 낱말: " + broader)
    if row.text:
        parts.append(row.text[:DOC_CHARS])
    body = "\n".join(parts)
    return body if safe_text(body) else None


def text_hash(body: str) -> str:
    """글 지문(바뀌었나 견주기)."""
    return hashlib.sha256(f"{MODEL}\n{body}".encode("utf-8")).hexdigest()


def _literal(vector: list[float]) -> str:
    """벡터 → pgvector 글 꼴 ``[a,b,…]``."""
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


_PG_UPDATE = text(f"UPDATE {TABLE} SET source_version = :version, dimension = :dimension, "
                  "embedding = CAST(:vector AS vector), text_hash = :digest, created_at = :at "
                  "WHERE source_kind = :kind AND source_key = :key AND model = :model")
_PG_INSERT = text(f"INSERT INTO {TABLE} (source_kind, source_key, source_version, model, dimension, embedding, text_hash, "
                  "created_at) VALUES (:kind, :key, :version, :model, :dimension, CAST(:vector AS vector), :digest, :at)")


def store_vector(session: Any, kind: str, key: str, version: Optional[int], vector: list[float], digest: str,
                 now: datetime.datetime) -> None:
    """(근원 종류, 근원 키, 모델) 한 줄을 넣거나 바꾼다(PostgreSQL 은 ``CAST(… AS vector)`` 를 글로 적는다)."""
    if kind not in SOURCE_KINDS:
        raise ValueError("source_kind")
    at = now.astimezone(datetime.timezone.utc).replace(tzinfo=None) if now.tzinfo else now
    if session.get_bind().dialect.name == "postgresql":
        params = {"kind": kind, "key": key, "version": version, "model": MODEL, "dimension": DIMENSION,
                  "vector": _literal(vector), "digest": digest, "at": at}
        if not session.execute(_PG_UPDATE, params).rowcount:
            session.execute(_PG_INSERT, params)
        return
    values = {"source_version": version, "dimension": DIMENSION, "embedding": vector, "text_hash": digest,
              "created_at": at}
    hit = session.execute(update(brain_embeddings).where(
        brain_embeddings.c.source_kind == kind, brain_embeddings.c.source_key == key,
        brain_embeddings.c.model == MODEL).values(**values))
    if not hit.rowcount:
        session.execute(insert(brain_embeddings).values(source_kind=kind, source_key=key, model=MODEL, **values))


def stored(session: Any, kind: str) -> dict[str, tuple[Optional[int], str]]:
    """그 근원 종류의 벡터 줄 — 근원 키 → (근원 판, 글 지문)."""
    rows = session.execute(select(brain_embeddings.c.source_key, brain_embeddings.c.source_version,
                                  brain_embeddings.c.text_hash)
                           .where(brain_embeddings.c.source_kind == kind, brain_embeddings.c.model == MODEL)).all()
    return {key: (version, digest) for key, version, digest in rows}


def drop_vectors(session: Any, kind: str, keys: Iterable[str]) -> int:
    """그 근원 키들의 벡터 줄을 지운다(표가 없으면 0)."""
    wanted = sorted({str(k) for k in keys})
    if not wanted or not table_ready(session):
        return 0
    return session.execute(delete(brain_embeddings).where(brain_embeddings.c.source_kind == kind,
                                                          brain_embeddings.c.source_key.in_(wanted))).rowcount or 0


def store_question_vector(session: Any, question_id: int, masked: str, vector: Optional[list[float]],
                          now: datetime.datetime) -> bool:
    """물어보기 가린 질문의 벡터를 남긴다(찾기 때 이미 만든 것 — 돈 0). 표 없음 · 벡터 없음 · 검사에 걸리면 남기지 않는다."""
    if vector is None or not safe_text(masked) or not table_ready(session):
        return False
    store_vector(session, SOURCE_QUESTION, str(int(question_id)), None, vector, text_hash(masked), now)
    return True


def _cosine(a: list[float], b: list[float]) -> float:
    """코사인 비슷함(SQLite 시험 길)."""
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def nearest(session: Any, viewer: Viewer, vector: list[float], *, today: datetime.date,
            limit: int = 10) -> list[tuple[str, float]]:
    """가까운 항목 (키, 비슷함) — 보기 범위 · 유효 기간 · 반영 · 정체 유형 · 지금 판을 SQL 에 걸고 그 안에서 순위."""
    return nearest_where(session, vector, (*effective_clauses(viewer, today), BrainObject.item_type.in_(IDENTITY_TYPES)),
                         limit=limit)


def nearest_where(session: Any, vector: list[float], where: Iterable[Any], *, limit: int = 10) -> list[tuple[str, float]]:
    """가까운 회사 지식 항목 (키, 비슷함) — 부르는 쪽 조건(``where`` — 보기 범위 · 유형 · 판)을 SQL 에 걸고 그 안에서 순위.
    상담 초안의 물건 찾기(:mod:`foms.services.cs_agent.onto_meaning`)는 사람 대신 '보기 범위 모두' 조건을 건다."""
    join = ((brain_embeddings.c.source_key == BrainObject.item_key)
            & (brain_embeddings.c.source_version == BrainObject.version))
    conditions = (*where, brain_embeddings.c.source_kind == SOURCE_ITEM, brain_embeddings.c.model == MODEL)
    if session.get_bind().dialect.name == "postgresql":
        distance = brain_embeddings.c.embedding.op("<=>", return_type=Float)(
            cast(bindparam("query_vector", _literal(vector), type_=String), _PgVector(DIMENSION)))
        rows = session.execute(select(brain_embeddings.c.source_key, distance.label("d"))
                               .join_from(brain_embeddings, BrainObject, join)
                               .where(*conditions).order_by(distance).limit(int(limit))).all()
        return [(key, 1.0 - float(d)) for key, d in rows]
    rows = session.execute(select(brain_embeddings.c.source_key, brain_embeddings.c.embedding)
                           .join_from(brain_embeddings, BrainObject, join).where(*conditions)).all()
    scored = sorted(((key, _cosine(vector, emb)) for key, emb in rows), key=lambda kv: (-kv[1], kv[0]))
    return scored[:int(limit)]


