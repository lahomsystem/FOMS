"""상담 전체 대화 — 쪽을 넘겨 처음부터 읽은 공개 손님 · 직원 글(가린 글 · 시간 순)을 메모리에서만 다룬다(설계서 17.11.2 · D173).

사장님 11-05 '사진이 각 상담의 전체 대화 내용과 같이 학습해야 맥락 이해가 된다'. 사진 읽기(초안 때 — :mod:`.image_read`) · 사진
학습(:mod:`.photo_learning`) · 주간 고침 안(:mod:`.weekly_fix`)이 쓴다. 초안 두뇌는 지금처럼 최근 30줄(돈 · 시간)이고, 비슷한 지난
상담 칸(:mod:`.brain_cases`)도 그대로다.

- **읽기(:func:`read_talk`)**: Open API 글 목록을 새 글부터 50개씩 쪽을 넘겨(:func:`next_page`) 패널 '전체 대화 글 수 상한'까지
  읽고 시간 순으로 둔다. 공개 손님 · 직원 글만(:func:`.drafting_read.public_turn` — 초안 재료와 같은 규칙, 파일이 온 글은 첨부
  표시 줄). 채널톡 읽기 양동이(``message``)를 같이 쓴다. 글 수 상한이 0 이면 읽지 않는다(예전 재료 그대로).
- **가림**: 글마다 가린다(:func:`.masking.mask`). 한 글이라도 가림 검사가 0 이 아니면 전체 대화를 쓰지 않는다(``None`` — 부르는
  쪽은 지금 재료로 가고, 지금 재료는 지금처럼 검사를 다시 지난다).
- **실패는 지금 재료로**: 첫 쪽 읽기가 실패하면 ``None``. 다음 쪽이 실패하거나 시간(``left``)이 다 되면 읽은 데까지 쓰고 맨 앞에
  줄임 표시를 단다 — 학습 · 초안이 멈추지 않게.
- **글로 펴기(:func:`talk_text`)**: 자 수 상한을 넘으면 앞 글부터 덜고 맨 앞에 '(앞 대화 K줄 줄임)' 한 줄. 표시 줄(사진 · 그림)은
  그 글 바로 뒤에 끼우고, 그 글이 없으면(줄였거나 못 읽음) 기준 글(질문) 뒤 · 그것도 없으면 끝에 둔다. 펼친 글은 가림 검사를
  한 번 더 지난다(아니면 ``None``).
- **저장하지 않는다**: 원문 · 가린 전체 대화는 표 · 로그에 두지 않는다(쓸 때마다 다시 읽는다). 로그엔 숫자 · 코드만.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import quote

from foms.services.cs_agent import brain_prompt as prompt
from foms.services.cs_agent.channel_read import MESSAGE_PAGE_LIMIT, ChannelReadError
from foms.services.cs_agent.drafting_read import ChatLine, parse_lines, public_turn
from foms.services.cs_agent.edit_detail_settings import TALK_CASES_FIELD, TALK_CHARS_FIELD, TALK_MESSAGES_FIELD
from foms.services.cs_agent.masking import leak_counts, mask
from foms.services.cs_agent.read_budget import BUCKET_MESSAGE

logger = logging.getLogger(__name__)

__all__ = [
    "LEARN_BUDGET_CHARS", "MAX_PAGES", "MIN_CASE_CHARS", "PictureTalk", "Talk", "case_limit", "case_talks", "char_cap",
    "cut_line", "learn_cases", "message_cap", "next_page", "picture_talk", "quote_talk", "read_talk", "talk_on",
    "talk_text", "with_talks",
]

#: 쪽 수 안전 상한(글 수 상한 1,000 ÷ 50) — 쪽이 덜 차서 와도 끝없이 넘기지 않는다.
MAX_PAGES = 20
#: 학습 한 번(주간 고침 안 · 사진 학습 부르기 하나)에 싣는 전체 대화 자 수 합 — 사례 수로 나눠 사례마다 상한을 낮춘다.
LEARN_BUDGET_CHARS = 120_000
#: 학습 사례 하나의 자 수 하한(사례가 많아도 이만큼은 싣는다 — 8묶음 × 8사례면 합 128,000자).
MIN_CASE_CHARS = 2_000


@dataclass(frozen=True)
class Talk:
    """상담 하나의 전체 대화 — (말한 사람, 가린 글) 시간 순 · 같은 차례의 메시지 id · 앞 글을 덜 읽었나(글 수 상한 · 다음 쪽
    실패 · 시간). 글은 repr 에 없다."""

    turns: tuple[tuple[str, str], ...] = field(repr=False)
    ids: tuple[str, ...] = field(repr=False)
    more: bool = False


def message_cap(cfg: Any) -> int:
    """패널 '전체 대화 글 수 상한'(0 이면 끔)."""
    value = cfg.get(TALK_MESSAGES_FIELD)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def talk_on(cfg: Any) -> bool:
    """전체 대화를 읽나(글 수 상한이 0 보다 큼)."""
    return message_cap(cfg) > 0


def char_cap(cfg: Any) -> int:
    """패널 '전체 대화 자 수 상한'(가린 글)."""
    value = cfg.get(TALK_CHARS_FIELD)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else MIN_CASE_CHARS


def learn_cases(cfg: Any) -> int:
    """패널 '사진 학습 묶음당 사례 수'."""
    value = cfg.get(TALK_CASES_FIELD)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 1


def case_limit(cfg: Any, cases: int) -> int:
    """학습 사례 하나의 자 수 상한 — 패널 상한과 한 번 합(:data:`LEARN_BUDGET_CHARS`) ÷ 사례 수 가운데 작은 것(하한
    :data:`MIN_CASE_CHARS`)."""
    return max(MIN_CASE_CHARS, min(char_cap(cfg), LEARN_BUDGET_CHARS // max(1, cases)))


def next_page(data: Mapping[str, Any], params: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """글 목록 다음 쪽(더 오래된 글) 요청 칸 — 없으면 ``None``(한 쪽으로 끝).

    **스테이징에서 잰다.** 2026-06-01 판 상담 목록은 요청 ``cursor`` → 응답 ``nextCursor`` · ``hasNext`` 였다(10-28 실측 — 원장
    Q1). 글 목록도 같은 꼴로 보고, 옛 판 꼴(응답 ``next`` → 요청 ``since``)도 받는다. ``hasNext`` 가 거짓이거나 다음 표지가 없거나
    지난 표지와 같으면 끝이다 — 꼴이 다르면 첫 쪽(지금 재료와 같은 최근 50개)만 쓴다.
    """
    if data.get("hasNext") is False:
        return None
    for answer_key, request_key in (("nextCursor", "cursor"), ("next", "since")):
        token = data.get(answer_key)
        if isinstance(token, (str, int)) and not isinstance(token, bool) and str(token).strip():
            token = str(token).strip()
            return None if token == params.get(request_key) else {**params, request_key: token}
    return None


def _pages(reader: Any, brand: str, chat_id: str, cap: int,
           left: Optional[Callable[[], float]]) -> Optional[tuple[list[ChatLine], bool]]:
    """새 글부터 쪽을 넘겨 ``cap`` 개까지 — (글들, 앞 글을 덜 읽었나). 첫 쪽이 실패하면 ``None``."""
    path = f"/open/user-chats/{quote(chat_id, safe='')}/messages"
    params: dict[str, Any] = {"limit": min(MESSAGE_PAGE_LIMIT, cap), "sortOrder": "desc"}
    found: dict[str, ChatLine] = {}
    read = 0
    for page in range(MAX_PAGES):
        try:
            data = reader._get(brand, path, params, BUCKET_MESSAGE)  # noqa: SLF001 — 같은 패키지 읽기 도우미(원문이 있어야 한다)
        except (ChannelReadError, ValueError) as exc:
            logger.warning("[CS 전체 대화] 쪽 읽기 실패 page=%d status=%s", page + 1, getattr(exc, "status", None))
            return (list(found.values()), True) if page else None
        items = data.get("messages") if isinstance(data.get("messages"), list) else []
        read += len(items)
        before = len(found)
        for line in parse_lines(brand, chat_id, items):
            found.setdefault(line.meta.message_id, line)
        following = next_page(data, params)
        if following is None:
            return list(found.values()), False
        if len(found) == before or read >= cap or (left is not None and left() <= 0):
            return list(found.values()), True
        params = {**following, "limit": min(MESSAGE_PAGE_LIMIT, cap - read)}
    return list(found.values()), True


def read_talk(reader: Any, brand: str, chat_id: str, cfg: Any, *,
              left: Optional[Callable[[], float]] = None) -> Optional[Talk]:
    """상담 하나의 전체 대화(모듈 설명). 끔 · 읽기 실패 · 가림 검사 · 보낼 글 없음이면 ``None``(지금 재료로).

    Args:
        left: 남은 시간(초)을 주는 함수 — 0 이하면 첫 쪽도 읽지 않고, 쪽 사이에서 멈춘다(초안 때 그림 읽기 시간 상한).
    """
    cap = message_cap(cfg)
    if cap <= 0 or (left is not None and left() <= 0):
        return None
    got = _pages(reader, brand, chat_id, cap, left)
    if got is None:
        return None
    lines, more = got
    turns: list[tuple[str, str]] = []
    ids: list[str] = []
    for line in sorted(lines, key=lambda one: one.key):
        turn = public_turn(line)
        masked = mask(turn[1]).strip() if turn is not None else ""
        if not masked:
            continue
        counts = leak_counts(masked)
        if any(counts.values()):
            logger.warning("[CS 전체 대화] 가림 검사 0 아님 — 예전 재료로 %s",
                           " · ".join(f"{key} {value}" for key, value in counts.items() if value))
            return None
        turns.append((turn[0], masked))
        ids.append(line.meta.message_id)
    return Talk(tuple(turns), tuple(ids), more) if turns else None


def cut_line(dropped: int, more: bool) -> str:
    """맨 앞 줄임 표시 — 덜어 낸 줄 수(앞 글을 덜 읽었으면 '넘게'). 줄인 것이 없으면 빈 글."""
    if more:
        return f"(앞 대화 {dropped}줄 넘게 줄임)" if dropped else "(앞 대화 줄임)"
    return f"(앞 대화 {dropped}줄 줄임)" if dropped else ""


def talk_text(talk: Talk, *, limit: int, marks: Optional[Mapping[str, Sequence[str]]] = None,
              anchor: str = "") -> Optional[str]:
    """전체 대화 → 글(모듈 설명 '글로 펴기'). 가림 검사가 0 이 아니면 ``None``.

    Args:
        limit: 가린 글 자 수 상한(줄임 · 표시 줄은 빼고 센다 — 마지막 글 하나가 넘으면 그 글을 자른다).
        marks: 메시지 id → 그 글 바로 뒤에 끼울 표시 줄(사진 · 그림 — 가린 글).
        anchor: 표시 줄의 글이 없을 때 대신 놓을 글(질문)의 메시지 id.
    """
    sizes = [len(text) for _, text in talk.turns]
    start, total = 0, sum(sizes)
    while total > limit and start < len(sizes) - 1:
        total, start = total - sizes[start], start + 1
    marks = dict(marks or {})
    shown = set(talk.ids[start:])
    loose = [line for key, extra in marks.items() if key not in shown for line in extra]
    lines = [cut_line(start, talk.more)] if start or talk.more else []
    for (role, text), key in zip(talk.turns[start:], talk.ids[start:]):
        lines.append(prompt.render_conversation([(role, text[:limit])]))
        lines += marks.get(key, ())
        if key == anchor and anchor in shown:
            lines, loose = lines + loose, []
    body = "\n".join([*lines, *loose])
    if any(leak_counts(body).values()):
        logger.warning("[CS 전체 대화] 펼친 글 가림 검사 0 아님 — 예전 재료로")
        return None
    return body


#: 그림 읽기(초안 때)에 넘기는 읽기 함수 꼴 — (남은 시간 함수, 메시지 id → 그 글의 그림 차례) → 전체 대화 글 또는 ``None``.
PictureTalk = Callable[[Callable[[], float], Mapping[str, Sequence[int]]], Optional[str]]


def picture_talk(reader: Any, brand: str, chat_id: str, cfg: Any) -> Optional[PictureTalk]:
    """그림 읽기 두뇌(Sonnet)에 줄 전체 대화를 **두뇌를 부를 때만** 읽는 함수(다시 쓴 결과 · 상한 · 끔이면 읽지 않는다). 끔이면
    ``None``(예전 그대로 최근 30줄). 이번에 보낸 그림은 그 글 뒤에 ``▶ 그림 0 · 그림 1 (이번에 보낸 그림)`` 표시 줄로 둔다."""
    if not talk_on(cfg):
        return None

    def build(left: Callable[[], float], pictures: Mapping[str, Sequence[int]]) -> Optional[str]:
        talk = read_talk(reader, brand, chat_id, cfg, left=left)
        if talk is None:
            return None
        marks = {key: [f"▶ {' · '.join(f'그림 {i}' for i in indexes)} (이번에 보낸 그림)"]
                 for key, indexes in pictures.items() if indexes}
        return talk_text(talk, limit=char_cap(cfg), marks=marks)

    return build


def quote_talk(text: str) -> list[str]:
    """학습 재료 줄 — 줄마다 ``| `` 앞표(머리표 흉내 막기 — :mod:`.brain_cases` 와 같은 뜻)."""
    return [f"| {line}".rstrip() for line in text.splitlines()] or ["| (없음)"]


def case_talks(reader: Any, cfg: Any, cases: Sequence[Mapping[str, Any]], *, brand: str) -> dict[int, str]:
    """학습 사례마다 전체 대화 글 — 차례 id → 글. 상담마다 한 번만 읽고(이 부르기 메모리에서만), 못 읽은 사례는 빠진다(부르는
    쪽은 예전 재료). 사례 dict 의 ``marks`` · ``anchor`` 는 :func:`talk_text` 와 같다. 끔이거나 읽기 도우미가 없으면(감시 바퀴
    밖에서 부름 — 몰래 새 읽기 도우미를 만들지 않는다) 읽지 않고 빈 dict."""
    if not talk_on(cfg) or not cases or reader is None:
        return {}
    limit = case_limit(cfg, len(cases))
    talks: dict[str, Optional[Talk]] = {}
    out: dict[int, str] = {}
    for case in cases:
        chat = str(case.get("chat_id") or "")
        if chat and chat not in talks:
            talks[chat] = read_talk(reader, brand, chat, cfg)
        talk = talks.get(chat)
        anchor = str(case.get("anchor") or "")
        text = talk_text(talk, limit=limit, marks=case.get("marks"), anchor=anchor) if talk else None
        if text:
            out[case["turn_id"]] = text
    logger.info("[CS 전체 대화] 학습 사례 %d 가운데 %d 전체 대화 · 읽은 상담 %d · 사례 상한 %d자", len(cases), len(out),
                len(talks), limit)
    return out


def with_talks(groups: Sequence[Any], reader: Any, cfg: Any, *, brand: str, shown: int) -> list[Any]:
    """학습 묶음(사례 dict 튜플 ``cases`` 를 가진 dataclass)마다 앞 ``shown`` 사례에 전체 대화(``talk`` 칸)를 붙인 사본 — 끔이거나
    못 읽은 사례는 그대로(부르는 쪽 예전 재료)."""
    talks = case_talks(reader, cfg, [case for group in groups for case in group.cases[:shown]], brand=brand)
    if not talks:
        return list(groups)
    return [dataclasses.replace(group, cases=tuple({**case, "talk": talks[case["turn_id"]]}
                                                   if case["turn_id"] in talks else case for case in group.cases))
            for group in groups]
