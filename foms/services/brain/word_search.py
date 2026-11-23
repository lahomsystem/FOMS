"""한글 낱말 찾기 — 형태소로 나눈 낱말(``kiwipiepy`` · Apache-2.0) + BM25 점수(``bm25s`` · MIT). 설계서
``docs/specs/2026-11-23-brain-learning-upgrade_SPEC.md`` 5.2 '한글 낱말 찾기 섞기'.

글자 찾기(:func:`foms.services.brain.chat_tools.search_objects`)는 조사를 몇 개만 떼어 '도면을 보냈어요' · '도면이 왔나요' 처럼
끝만 다른 말을 잘 못 잇는다. 여기서는 낱말을 형태소로 나눠 뜻 있는 조각(체언 · 용언 · 어근 · 영문 · 숫자 —
:func:`tokens`)만 남기고 BM25 로 줄 세운다(:func:`rank`). 운영 실측(11-23 · 같은 말 묶음 61개 · 짝 452개): 짝이 앞 6 안에
드는 비율 — 글자 + 뜻(그때까지) 50.7% · 낱말만 69.2%.

- **모두 우리 서버 안에서만 돈다** — 바깥으로 글이 나가지 않는다.
- **두 꾸러미는 함수 안에서만 불러온다**: 형태소 모델이 메모리에 수백 MB 라 ``import app``(웹 · gevent)이 그것을 지지 않게 한다.
  처음 쓰는 순간 한 번 읽고(약 1초) 다시 쓴다(:func:`_kiwi` — 잠금으로 한 번만). 밤 배우기 한 바퀴가 끝나면 놓는다(:func:`release`).
- **낱말 기억**(:func:`item_tokens`): (항목 키, 판) → 낱말. 한 밤 동안 바뀐 항목만 다시 나눈다(:data:`CACHE_SIZE` 개까지).
- **쓸 수 없음**: 꾸러미 없음 · 모델 읽기 실패 · 꾸러미 안 오류는 모두 :class:`WordSearchUnavailable` 로 올린다(부르는 쪽은
  예전 찾기로). 로그는 코드만 — 글은 남기지 않는다. 꾸러미 없음 · 모델 읽기 실패는 기억해 두고 다시 읽지 않는다.
"""

from __future__ import annotations

import gc
import logging
import threading
from collections import OrderedDict
from typing import Any, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

__all__ = ["CACHE_SIZE", "WordSearchUnavailable", "available", "interleave", "item_tokens", "rank", "release", "tokens"]

#: 남기는 형태소 꼴 — 체언(``N…``) · 용언(``V…``)은 앞 글자로, 어근 · 영문 · 숫자는 그대로(11-23 견주기와 같은 규칙).
KEEP_HEADS, KEEP_TAGS = ("N", "V"), frozenset({"XR", "SL", "SN"})
#: 낱말 기억 상한(항목 판 수) — 지식 항목이 수백 개라 한 밤의 항목이 모두 든다.
CACHE_SIZE = 4096
#: 형태소 나누개 읽는 값 — 다중 낱말 사전 · 오타 사전을 읽지 않는다. 11-23 견주기(같은 말 묶음 짝 452개)에서 점수가 같았고
#: (낱말만 69.2% · 번갈아 67.5%) 메모리가 약 580 MB → 약 300 MB 로 준다.
MODEL_OPTIONS: dict[str, Any] = {"load_multi_dict": False, "load_typo_dict": False}
#: 한 글에서 나누는 글자 상한(아주 긴 글이 한 번에 붙잡지 않게).
MAX_CHARS = 4000


class WordSearchUnavailable(RuntimeError):
    """낱말 찾기를 쓸 수 없다 — ``code`` 는 까닭 코드(``missing_package`` · ``model_load`` · ``tokenize`` · ``rank``)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"kiwi": None, "failed": None}
_CACHE: "OrderedDict[tuple[str, int], tuple[str, ...]]" = OrderedDict()


def _kiwi() -> Any:
    """형태소 나누개 하나(처음 부를 때 읽는다 · 프로세스에 하나). 읽지 못하면 그 까닭을 기억하고 :class:`WordSearchUnavailable`."""
    with _LOCK:
        if _STATE["kiwi"] is not None:
            return _STATE["kiwi"]
        if _STATE["failed"]:
            raise WordSearchUnavailable(_STATE["failed"])
        try:
            from kiwipiepy import Kiwi
        except ImportError:
            _STATE["failed"] = "missing_package"
            logger.warning("[회사 지식 낱말 찾기] 쓸 수 없어 예전 찾기로 code=%s", _STATE["failed"])
            raise WordSearchUnavailable(_STATE["failed"]) from None
        try:
            kiwi = Kiwi(**MODEL_OPTIONS)
            kiwi.tokenize("")  # 모델은 처음 나눌 때 읽힌다 — 여기서 읽어 실패를 한 곳에서 본다
        except Exception as exc:  # 모델 파일 · 메모리 — 꾸러미 안 오류 모두(코드만 적는다)
            _STATE["failed"] = "model_load"
            logger.warning("[회사 지식 낱말 찾기] 쓸 수 없어 예전 찾기로 code=%s kind=%s", _STATE["failed"],
                           type(exc).__name__)
            raise WordSearchUnavailable(_STATE["failed"]) from None
        _STATE["kiwi"] = kiwi
        return kiwi


def available() -> bool:
    """낱말 찾기를 쓸 수 있나(처음이면 모델을 읽는다)."""
    try:
        _kiwi()
    except WordSearchUnavailable:
        return False
    return True


def tokens(text: Optional[str]) -> list[str]:
    """글 → 뜻 있는 낱말(조사 · 어미 · 부호는 뺀다 · 영문은 소문자). 빈 글은 빈 목록."""
    body = (text or "").strip()[:MAX_CHARS]
    if not body:
        return []
    kiwi = _kiwi()
    try:
        with _LOCK:
            parts = kiwi.tokenize(body)
        return [str(t.form).lower() for t in parts if t.tag.startswith(KEEP_HEADS) or t.tag in KEEP_TAGS]
    except Exception as exc:  # 꾸러미 안 오류(코드만 적는다)
        logger.warning("[회사 지식 낱말 찾기] 낱말 나누기 실패 code=tokenize kind=%s", type(exc).__name__)
        raise WordSearchUnavailable("tokenize") from None


def item_tokens(key: str, version: Optional[int], text: Optional[str]) -> tuple[str, ...]:
    """항목 한 판의 낱말 — (키, 판)으로 기억한다(판이 없으면 기억하지 않고 나눈다)."""
    if version is None:
        return tuple(tokens(text))
    slot = (key, int(version))
    with _LOCK:
        if slot in _CACHE:
            _CACHE.move_to_end(slot)
            return _CACHE[slot]
    found = tuple(tokens(text))
    with _LOCK:
        _CACHE[slot] = found
        _CACHE.move_to_end(slot)
        while len(_CACHE) > CACHE_SIZE:
            _CACHE.popitem(last=False)
    return found


def rank(query: str, docs: Sequence[tuple[str, str]], *, limit: int,
         versions: Optional[Mapping[str, int]] = None) -> list[str]:
    """질의 글과 가까운 글의 키 — BM25 점수 순 앞 ``limit`` 개(점수 0 은 뺀다 · 같은 키는 처음 것만). ``docs`` 는 (키, 글),
    ``versions`` 는 키 → 판(주면 그 판의 낱말을 기억해 다시 쓴다). 디스크에 아무것도 쓰지 않는다."""
    seen: dict[str, None] = {}
    keys, corpus = [], []
    for key, text in docs:
        if key in seen:
            continue
        seen[key] = None
        keys.append(key)
        corpus.append(list(item_tokens(key, (versions or {}).get(key), text)))
    asked = tokens(query)
    if not keys or not asked or limit <= 0 or not any(corpus):
        return []
    try:
        import bm25s
    except ImportError:
        logger.warning("[회사 지식 낱말 찾기] 쓸 수 없어 예전 찾기로 code=missing_package")
        raise WordSearchUnavailable("missing_package") from None
    try:
        index = bm25s.BM25()
        index.index(corpus, show_progress=False)
        found, scores = index.retrieve([asked], k=min(int(limit), len(keys)), show_progress=False,
                                       backend_selection="numpy")
    except Exception as exc:  # 꾸러미 안 오류(코드만 적는다)
        logger.warning("[회사 지식 낱말 찾기] 줄 세우기 실패 code=rank kind=%s", type(exc).__name__)
        raise WordSearchUnavailable("rank") from None
    return [keys[int(i)] for i, score in zip(found[0].tolist(), scores[0].tolist()) if score > 0]


def interleave(first: Sequence[str], second: Sequence[str], limit: int) -> list[str]:
    """두 순위를 번갈아(앞 줄 먼저 · 겹치면 처음 것만) 앞 ``limit`` 개."""
    out: dict[str, None] = {}
    for at in range(max(len(first), len(second))):
        for ranked in (first, second):
            if at < len(ranked) and len(out) < limit:
                out.setdefault(ranked[at], None)
    return list(out)


def release() -> None:
    """형태소 나누개를 놓는다(낱말 기억 · 실패 기록은 그대로) — 학습 몫 한 바퀴(:mod:`foms.services.cs_agent.learning_pass`)가 끝나면 부른다. 감시 루프 프로세스가
    모델을 밤새 쥐고 있지 않게(실측: 놓으면 약 300 MB 가운데 절반쯤 돌아온다). 다음에 쓰면 다시 읽는다(약 1초)."""
    with _LOCK:
        _STATE["kiwi"] = None
    gc.collect()


def _reset_for_tests() -> None:
    """기억 · 실패 기록을 비운다(시험만)."""
    with _LOCK:
        _STATE["failed"] = None
        _CACHE.clear()
