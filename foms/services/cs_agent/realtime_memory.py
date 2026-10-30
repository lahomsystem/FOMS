"""빠른 길 프로세스 메모리 — 거른 수신 줄 id · '다시 볼 필요 없음' 판정(시간 상한) · 멈춤 뒤 기다림(:mod:`.realtime` 이 쓴다).

:mod:`.realtime` 이 500줄 상한에 닿지 않게 따로 뒀다. 재시작하면 비어서 시작한다 — 그때는 한 번씩 더 열고 더 볼 뿐이다.

- **거른 줄(R10-4)**: 원본을 열었는데 상태 표에 흔적이 남지 않은 수신 줄 id. 크기 상한(넘치면 먼저 넣은 것부터 버림).
- **판정(검수 R13-4)**: (상담, 마지막 손님 글) 을 '다시 볼 필요 없음'으로 기억하되 :data:`DECIDE_TTL` 뒤엔 다시 본다 — 15분
  보정이 앞 글을 늦게 넣어도 그 상담이 재시작 전까지 숨지 않는다. 설정 판이 바뀌어도 지운다.
- **기다림(검수 R13-2)**: 돈 상한 · 준비 안 됨 · 키 없음으로 멈춘 뒤엔 같은 차례를 5초마다 다시 집지 않는다 — 돈 상한은 그날
  (KST) 끝까지, 준비 안 됨 · 키 없음은 :data:`NOT_READY_WAIT` 까지(그 사이 승인 지식 같은 것을 고칠 수 있다). 날짜나 설정 판이
  바뀌면 바로 푼다.
"""

from __future__ import annotations

import datetime
from collections import OrderedDict
from typing import Any, Hashable, Optional

from foms.services.cs_agent.state import KST

__all__ = ["DECIDE_TTL", "NOT_READY_WAIT", "TickMemory"]

#: 판정 기억 시간 상한(검수 R13-4 — 약 10분).
DECIDE_TTL = datetime.timedelta(minutes=10)
#: 준비 안 됨 · 키 없음으로 멈춘 뒤 기다리는 최대 시간(돈 상한은 그날 끝까지).
NOT_READY_WAIT = datetime.timedelta(minutes=30)


class _Bounded(OrderedDict):
    """크기 상한이 있는 사전(넣은 순서 — 넘치면 가장 먼저 넣은 것부터 버린다). 값은 만료 시각이거나 ``None``."""

    def __init__(self, limit: int) -> None:
        """상한을 정한다."""
        super().__init__()
        self.limit = int(limit)

    def add(self, key: Hashable, value: Any = None) -> None:
        """하나 넣는다(있으면 맨 뒤로)."""
        self[key] = value
        self.move_to_end(key)
        while len(self) > self.limit:
            self.popitem(last=False)


class TickMemory:
    """차례 사이에 남기는 프로세스 메모리 — 거른 수신 줄 id · 판정 · 멈춤 뒤 기다림. 거른 줄 · 판정은 크기 상한."""

    def __init__(self, limit: int = 2000) -> None:
        """빈 메모리."""
        self.filtered = _Bounded(limit)
        self.decided = _Bounded(limit)
        self.settings_version: Optional[int] = None
        self.paused_until: Optional[datetime.datetime] = None
        self.paused_code: Optional[str] = None

    # ── 판정 ──
    def decide(self, key: Hashable, now: datetime.datetime) -> None:
        """'다시 볼 필요 없음'으로 :data:`DECIDE_TTL` 동안 기억한다."""
        self.decided.add(key, now + DECIDE_TTL)

    def is_decided(self, key: Hashable, now: datetime.datetime) -> bool:
        """기억한 판정이 아직 살아 있나(지난 것은 지운다)."""
        until = self.decided.get(key)
        if until is None:
            return False
        if now >= until:
            del self.decided[key]
            return False
        return True

    # ── 설정 판 ──
    def follow_settings(self, version: int) -> None:
        """설정 판이 바뀌었으면 판정 · 기다림을 지운다(묵은 상담 기준 · 돈 상한 같은 값이 바뀌면 다시 본다)."""
        if self.settings_version != version:
            self.decided.clear()
            self.paused_until = self.paused_code = None
            self.settings_version = version

    # ── 멈춤 뒤 기다림 ──
    def pause(self, code: str, now: datetime.datetime, *, whole_day: bool) -> None:
        """멈춘 까닭 ``code`` 로 기다린다 — ``whole_day`` 면 그날(KST) 끝까지, 아니면 :data:`NOT_READY_WAIT` 와 그날 끝 가운데 앞."""
        local = now.astimezone(KST)
        midnight = datetime.datetime(local.year, local.month, local.day, tzinfo=KST) + datetime.timedelta(days=1)
        self.paused_until = midnight if whole_day else min(midnight, local + NOT_READY_WAIT)
        self.paused_code = code

    def paused(self, now: datetime.datetime) -> Optional[str]:
        """기다리는 중이면 그 까닭 코드, 아니면 ``None``(시각이 지났으면 푼다)."""
        if self.paused_until is None or now >= self.paused_until:
            self.paused_until = self.paused_code = None
            return None
        return self.paused_code
