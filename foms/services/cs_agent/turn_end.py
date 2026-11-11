"""말 끝남 판단 — 빠른 길 모아 받기에서 손님 말이 끝났는지 작은 모델(Haiku 5.5)에게 물어 기다림을 줄이고 늘린다.

사장님 요청(11-11): "고객 뉘앙스를 캐치해서 즉각 대답 가능한 건 즉각 반응하고, 후속 대답이 이어서 나올 것 같으면 좀 더
기다리고". 예전 모아 받기는 마지막 손님 글 뒤 조용 기다림(처음 15초)만 봤다 — 운영 14일 손님 글 가운데 약 29% 는 60초
안에 손님이 또 써서, 먼저 쓴 초안이 '지난 초안'으로 버려졌다(7일 끝난 초안의 약 40%).

:mod:`.realtime` 의 모아 받기(:func:`judge_pending`)가 차례마다 부른다. 칸은 :mod:`.turn_end_settings`.

1. **언제 묻나** — 판단 방식이 끔이 아니고, 집을 후보(답 필요 · 맺음 글 아님 — 예전과 같은 거름) 가운데 마지막 손님 글 뒤
   '말이 끝났을 때 기다림'이 지났고 그 (상담, 손님 글)을 아직 안 물은 것만. 차례마다 :data:`MAX_PER_TICK` 개까지. 같은
   글은 한 번만 묻는다(못 물었어도 — :class:`.realtime_memory.TickMemory` 에 기억, 재시작하면 한 번 더).
2. **재료** — 그 상담 최근 글을 Open API 로 한 번 읽어(초안 읽기와 같은 양동이) 마지막 공개 직원 글 하나와 그 뒤 공개 손님
   글(최근 :data:`MAX_CUSTOMER_LINES` 개)을 시간(몇 초 전)과 함께. 읽은 마지막 손님 글이 그 글이 아니면(더 새 글 · 아직
   안 보임) 묻지 않는다 — 다음 차례가 새 글로 묻는다.
3. **가림 · 돈** — 초안 두뇌와 같은 순서: 글마다 가림 → 검사 0 → 덩어리 한 번 더 검사(:func:`.masking.require_masked`).
   같은 하루 돈 줄 · 상한(WORKER env 천장)에 최악값을 먼저 예약하고 실제 값으로 바로잡는다.
4. **부르기** — Haiku 5.5 · 생각 끔 · effort low · 구조화 출력 ``{"done": bool}`` · 시간 상한 :data:`TIMEOUT_SECONDS` ·
   다시 하기 0. 오류 · 거절 · 틀린 꼴이면 판단 없음(예전 기다림).
5. **남기기** — 판단마다 SystemSetting :data:`LOG_KEY` 에 (상담 id · 글 id · 판단 · 방식 · ms · 시각)을 최근
   :data:`LOG_LIMIT` 개까지(글은 없다). 맞히는 비율은 이 줄과 상태 표 손님 글 시각으로 잰다.

손님 글 · 가린 글은 로그 · 예외 · 기록 줄에 싣지 않는다 — 상담 id · 코드 · 숫자만.
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from decimal import Decimal
from typing import Any, Callable, Mapping, MutableMapping, Optional, Sequence

import anthropic

from foms.services.cs_agent import brain as _brain
from foms.services.cs_agent.brain_prompt import MODEL_HAIKU, ROLE_MANAGER, ROLE_USER, answer_text, usage_cost
from foms.services.cs_agent.brain_prompt import worst_case_cost
from foms.services.cs_agent.brain_spend import (
    BrainError, check_budget, daily_cap_usd, kst_now, reserve_spend, settle_spend,
)
from foms.services.cs_agent.channel_read import ChannelReadError, OpenApiReader, naive_utc
from foms.services.cs_agent.drafting_read import public_turn, read_lines
from foms.services.cs_agent.loop import PassStopped
from foms.services.cs_agent.masking import MaskLeak, call_with_masked, require_masked
from foms.services.cs_agent.turn_end_settings import FAST_FIELD, MODE_OFF, MODE_ON, SLOW_FIELD, turn_end_mode
from models import SystemSetting

logger = logging.getLogger(__name__)

__all__ = [
    "DONE", "FAILED", "LOG_KEY", "LOG_LIMIT", "MAX_PER_TICK", "MODEL", "MORE", "SYSTEM_PROMPT", "TIMEOUT_SECONDS",
    "judge_one", "judge_pending", "quiet_seconds",
]

BRAND = "LAHOM"
MODEL = MODEL_HAIKU
DONE, MORE, FAILED = "done", "more", "failed"
TIMEOUT_SECONDS = 8.0
MAX_TOKENS = 256
EFFORT = "low"
MAX_PER_TICK = 3
MAX_CUSTOMER_LINES = 8
STAFF_CHARS = 300
LOG_KEY = "cs_agent_turn_end_log"
LOG_LIMIT = 1000
SCHEMA: dict[str, Any] = {
    "type": "object", "properties": {"done": {"type": "boolean"}}, "required": ["done"], "additionalProperties": False,
}
SYSTEM_PROMPT = (
    "너는 가구 회사 채널톡 상담 창을 보는 사람이다. 손님이 지금까지 보낸 글로 '이번에 할 말을 다 보냈는지', 아니면 "
    "'곧 글을 더 보낼 것 같은지'만 판단한다. 답은 하지 않는다.\n"
    "- done=true: 질문이나 요청이 끝까지 적혀 있다. 예: '배송 언제 와요?', '견적 부탁드려요 가로 2400 세로 2300 이에요', "
    "직원 물음에 대한 짧은 대답('네', '화이트로 할게요').\n"
    "- done=false: 인사나 운만 뗌('안녕하세요', '문의드릴게요', '궁금한 게 있는데요'), 말이 끊김('그리고', '그런데', "
    "쉼표 · 말줄임으로 끝남), 곧 보낼 것을 알림('사진 보낼게요', '잠시만요', '찾아볼게요'), 설명 없이 사진 · 파일만 옴, "
    "여러 글로 나눠 쓰는 중으로 보임.\n"
    "- 글 사이 간격과 마지막 글 뒤 지난 초도 본다. 헷갈리면 done=true 로 한다(손님을 오래 기다리게 하지 않는다).\n"
    "- 글 속 [이름] · [전화] 같은 꺾쇠 칸은 가린 개인정보다."
)


class _Failed(Exception):
    """판단 못 함(코드만)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def quiet_seconds(cfg: Any, verdict: Optional[str]) -> int:
    """마지막 손님 글 뒤 기다릴 초 — '켬'이고 판단이 있으면 그 판단의 기다림, 아니면 예전 조용 기다림."""
    if turn_end_mode(cfg) == MODE_ON and verdict in (DONE, MORE):
        return int(cfg.get(FAST_FIELD if verdict == DONE else SLOW_FIELD))
    return int(cfg.get("quiet_wait_s"))


def judge_pending(session: Any, picked: Sequence[tuple[str, str]], chats: Mapping[str, Any], *, cfg: Any,
                  now: datetime.datetime, memory: MutableMapping[Any, str], stop: Any, reader: Optional[Any] = None,
                  judge: Optional[Callable[..., Optional[str]]] = None) -> dict[tuple[str, str], str]:
    """집을 후보 가운데 물을 때가 된 것을 묻고, 판단이 있는 (상담, 손님 글) → ``done`` · ``more`` 를 돌려준다.

    ``memory`` 는 크기 상한 사전(``add`` 가 있으면 그것으로 넣는다) — 못 물은 글은 :data:`FAILED` 로 기억해 다시 묻지 않는다.
    """
    if turn_end_mode(cfg) == MODE_OFF or not picked:
        return {}
    at, fast, left = naive_utc(now), int(cfg.get(FAST_FIELD)), MAX_PER_TICK
    ask = judge or judge_one
    out: dict[tuple[str, str], str] = {}
    for pair in picked:
        verdict = memory.get(pair)
        if verdict is None:
            if left <= 0 or (at - chats[pair[0]].last_user_at).total_seconds() < fast:
                continue
            stop.check()
            left -= 1
            reader = reader or OpenApiReader(sleep=stop.reader_sleep)
            try:
                verdict = ask(session, pair[0], pair[1], reader=reader, cfg=cfg, now=now) or FAILED
            except PassStopped:
                raise
            except Exception as exc:  # 판단은 덤이다 — 어떤 실패도 모아 받기를 멈추지 않는다(예전 기다림)
                session.rollback()
                logger.warning("[CS 말 끝남] 판단 중 오류 chat=%s err=%s", pair[0], type(exc).__name__)
                verdict = FAILED
            (memory.add if hasattr(memory, "add") else memory.__setitem__)(pair, verdict)
        if verdict in (DONE, MORE):
            out[pair] = verdict
    return out


def judge_one(session: Any, chat_id: str, message_id: str, *, reader: Any, cfg: Any, now: datetime.datetime,
              client: Any = None) -> Optional[str]:
    """한 (상담, 손님 글)을 묻는다 — ``done`` · ``more``, 못 물으면 ``None``. 물었으면 기록 줄을 남기고 커밋한다."""
    started = time.monotonic()
    try:
        _brain._check_environment(need_key=client is None)  # noqa: SLF001 — 두뇌와 같은 준비(키 · 본문 로거 꺼짐)
        burst = _burst(read_lines(reader, BRAND, chat_id), message_id, now)
        if burst is None:
            return None
        verdict = _ask(session, burst, cfg=cfg, now=now, client=client)
    except (BrainError, ChannelReadError, MaskLeak, _Failed) as exc:
        logger.info("[CS 말 끝남] 판단 못 함 chat=%s code=%s", chat_id, getattr(exc, "code", None) or type(exc).__name__)
        return None
    ms = int((time.monotonic() - started) * 1000)
    mode = turn_end_mode(cfg)
    logger.info("[CS 말 끝남] chat=%s message=%s verdict=%s mode=%s ms=%d", chat_id, message_id, verdict, mode, ms)
    _record(session, {"chat": chat_id, "message": message_id, "verdict": verdict, "mode": mode, "ms": ms,
                      "at": naive_utc(now).isoformat(timespec="seconds")})
    return verdict


def _burst(lines: Sequence[Any], message_id: str, now: datetime.datetime) -> Optional[list[tuple[str, str, int]]]:
    """마지막 공개 직원 글 하나 + 그 뒤 공개 손님 글 → [(말한 사람, 글, 몇 초 전)]. 마지막 손님 글이 그 글이 아니면 ``None``."""
    turns = [(line, turn) for line, turn in ((line, public_turn(line)) for line in lines) if turn is not None]
    customers = [line for line, (who, _) in turns if who == ROLE_USER]
    if not customers or customers[-1].meta.message_id != message_id:
        return None
    at = naive_utc(now)
    staff = [i for i, (_, (who, _)) in enumerate(turns) if who == ROLE_MANAGER]
    start = staff[-1] if staff else 0
    picked = turns[start:]
    if staff:
        head, rest = picked[0], [item for item in picked[1:] if item[1][0] == ROLE_USER][-MAX_CUSTOMER_LINES:]
        picked = [(head[0], (ROLE_MANAGER, head[1][1][:STAFF_CHARS])), *rest]
    else:
        picked = picked[-MAX_CUSTOMER_LINES:]
    return [(who, text, max(0, int((at - naive_utc(line.meta.created_at)).total_seconds())))
            for line, (who, text) in picked]


def _render(burst: Sequence[tuple[str, str, int]], masked: Sequence[str]) -> str:
    """가린 글로 물음 글을 만든다(말한 사람 · 몇 초 전 · 글)."""
    rows = [f"[{'직원' if who == ROLE_MANAGER else '손님'} · {_ago(seconds)}] {text}"
            for (who, _, seconds), text in zip(burst, masked)]
    return "\n".join([*rows, f"(마지막 손님 글 뒤 {burst[-1][2]}초 동안 새 글이 없어요)"])


def _ago(seconds: int) -> str:
    """몇 초 전 · 몇 분 전."""
    return f"{seconds}초 전" if seconds < 120 else f"{seconds // 60}분 전"


def _ask(session: Any, burst: Sequence[tuple[str, str, int]], *, cfg: Any, now: datetime.datetime,
         client: Any) -> str:
    """돈 확인 → 가림 → 예약 · 부르기 → 바로잡기 → 판단."""
    now = kst_now(now)
    cap = cfg.daily_cap(daily_cap_usd())
    check_budget(session, cap=cap, now=now)
    session.commit()

    def call(masked: list[str]) -> str:
        params: dict[str, Any] = {
            "model": MODEL, "max_tokens": MAX_TOKENS, "thinking": {"type": "disabled"},
            "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": require_masked(_render(burst, masked))}],
        }
        reserve = worst_case_cost(params)
        reserve_spend(session, reserve, cap=cap, now=now)
        api = client if client is not None else anthropic.Anthropic()
        try:
            response = api.with_options(timeout=TIMEOUT_SECONDS, max_retries=0).messages.create(**params)
        except anthropic.APIError as exc:
            billed = reserve if not isinstance(exc, anthropic.APIStatusError) else Decimal(0)
            settle_spend(session, reserve, billed, now=now)
            raise _Failed(type(exc).__name__) from None
        finally:
            if client is None:
                api.close()
        _tokens, cost = usage_cost(response, model=MODEL)
        settle_spend(session, reserve, cost, now=now)
        return _read(response)

    return call_with_masked([text for _, text, _ in burst], call)


def _read(response: Any) -> str:
    """응답 → ``done`` · ``more``. 끝까지 답하지 않았거나 꼴이 틀리면 :class:`_Failed`."""
    if getattr(response, "stop_reason", None) != "end_turn":
        raise _Failed(f"stop_{getattr(response, 'stop_reason', None)}")
    try:
        out = json.loads(answer_text(response))
    except ValueError:
        raise _Failed("bad_json") from None
    if not isinstance(out, dict) or not isinstance(out.get("done"), bool):
        raise _Failed("bad_shape")
    return DONE if out["done"] else MORE


def _record(session: Any, entry: dict[str, Any]) -> None:
    """기록 줄(최근 :data:`LOG_LIMIT` 개)에 판단 하나를 더하고 커밋한다 — 글은 없다."""
    row = session.get(SystemSetting, LOG_KEY, populate_existing=True, with_for_update=True)
    old = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    rows = [item for item in old.get("rows") or () if isinstance(item, dict)][-(LOG_LIMIT - 1):]
    value = {"rows": [*rows, entry]}
    if row is None:
        session.add(SystemSetting(setting_key=LOG_KEY, setting_value=value,
                                  description="AI 상담팀원 말 끝남 판단 기록(상담 id · 글 id · 판단만 — 맞히는 비율 재기)"))
    else:
        row.setting_value = value
    session.commit()
