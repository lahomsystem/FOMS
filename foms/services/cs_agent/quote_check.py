"""계산기 값 확인 날 — 사장님 결정 D74(검수 R17-5 · R17-8). 계산기 설정 저장 시각 대신 CS 쪽 기록으로 잰다.

**확인 날 = 제품 · 옵션 값이 실제로 바뀐 때와 관리 화면 [계산기 값 확인했어요]를 누른 때 가운데 늦은 것.** 그 날부터
:data:`FRESH_DAYS` 일이 지나면 '확인 필요'다(계산기 금액은 손님 글에 쓰지 않는다 — 설계서 7.1 의 5 · 17.4).

- **값 지문**: 계산기 설정의 제품 목록 + 추가 옵션 목록(JSON 정렬)의 sha256. 비고 · 현장 스펙 프리셋은 넣지 않는다 — 그
  저장은 확인 날을 바꾸지 않는다. 계산기 저장 길(``foms/api/wdcalculator/blueprint.py``)은 손대지 않고, 견적을 계산할 때
  (:func:`observe`) · 버튼을 누를 때(:func:`confirm`) 지문을 견준다.
- **기록**: SystemSetting :data:`KEY` 한 줄 — 지문 · 바뀐 때 · 확인한 때 · 확인한 사람(사용자 id). 시각은 시간대 있는 UTC ISO
  글이다(DB ``func.now()`` · 서버 시간대에 기대지 않는다 — R17-8).
- **처음 보는 지문**은 적기만 하고 '바뀜'으로 세지 않는다(버튼이 있어야 확인 날이 생긴다). **지문을 적다가 실패하면** 그
  차례는 '확인 필요'다. 처음 채우기 파일(계산기 설정 줄 없음)도 늘 '확인 필요'다.
- **버튼**: 관리 화면 스위치를 바꿀 수 있는 사람(ADMIN)만 — 공용 CSRF · Origin 가드 뒤, 감사 원장 한 줄을 같은 트랜잭션에.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.wdcalculator.catalog import Catalog, read_catalog
from models import SecurityLog, SystemSetting, User

logger = logging.getLogger(__name__)

__all__ = ["AUDIT_ACTION", "FRESH_DAYS", "KEY", "CheckError", "PriceCheck", "confirm", "fingerprint", "observe", "view"]

KEY = "cs_agent_calculator_check"
AUDIT_ACTION = "CS_AGENT_CALCULATOR_CHECK"
#: 확인 날에서 이만큼(일) 지나면 '확인 필요'(설계서 7.1 의 5 — 원장 R10-25).
FRESH_DAYS = 14
UTC = datetime.timezone.utc
KST = datetime.timezone(datetime.timedelta(hours=9))


class CheckError(ValueError):
    """버튼을 눌러도 확인할 값이 없다(계산기 설정 줄이 아직 없다 — 처음 채우기 파일)."""


def fingerprint(catalog: Catalog) -> str:
    """제품 · 옵션 값 지문(비고 · 프리셋 제외)."""
    body = json.dumps({"products": list(catalog.products), "options": list(catalog.option_categories)},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _utc(now: datetime.datetime) -> datetime.datetime:
    """시간대 있는 시각 → UTC(시간대 없는 시각은 받지 않는다 — 섞이면 9시간이 조용히 틀린다)."""
    if now.tzinfo is None:
        raise ValueError("시간대가 없는 시각은 받지 않는다")
    return now.astimezone(UTC)


def _parse(value: Any) -> Optional[datetime.datetime]:
    """기록의 ISO 글 → 시간대 있는 UTC(없거나 꼴이 틀리거나 시간대가 없으면 ``None``)."""
    try:
        stamp = datetime.datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None
    return stamp.astimezone(UTC) if stamp is not None and stamp.tzinfo is not None else None


@dataclass(frozen=True)
class PriceCheck:
    """확인 날 판정 재료. 시각은 모두 시간대 있는 UTC."""

    changed_at: Optional[datetime.datetime] = None
    checked_at: Optional[datetime.datetime] = None
    checked_by: Optional[int] = None
    failed: bool = False  # 지문을 적지 못함
    seed: bool = False  # 처음 채우기 파일(계산기 설정 줄 없음)

    @property
    def confirmed_at(self) -> Optional[datetime.datetime]:
        """확인 날 — 바뀐 때 · 확인한 때 가운데 늦은 것(둘 다 없으면 ``None``)."""
        stamps = [s for s in (self.changed_at, self.checked_at) if s is not None]
        return max(stamps) if stamps else None

    def needs_check(self, now: datetime.datetime) -> bool:
        """'확인 필요'인가 — 실패 · 처음 채우기 파일 · 확인 날 없음 · :data:`FRESH_DAYS` 일 넘김."""
        confirmed = self.confirmed_at
        if self.failed or self.seed or confirmed is None:
            return True
        return _utc(now) - confirmed > datetime.timedelta(days=FRESH_DAYS)

    def day(self) -> str:
        """확인 날(한국 날짜 글 — 없으면 '없음')."""
        confirmed = self.confirmed_at
        return f"{confirmed.astimezone(KST):%Y-%m-%d}" if confirmed is not None else "없음"


def _state(value: Any) -> dict[str, Any]:
    """기록 값 → 꼴을 맞춘 dict(모르는 칸 · 틀린 칸은 버린다)."""
    source = value if isinstance(value, dict) else {}
    by = source.get("checked_by")
    return {"fingerprint": source.get("fingerprint") if isinstance(source.get("fingerprint"), str) else None,
            "changed_at": source.get("changed_at") if _parse(source.get("changed_at")) else None,
            "checked_at": source.get("checked_at") if _parse(source.get("checked_at")) else None,
            "checked_by": by if isinstance(by, int) and not isinstance(by, bool) else None}


def _check(state: dict[str, Any]) -> PriceCheck:
    """기록 → 판정 재료."""
    return PriceCheck(changed_at=_parse(state["changed_at"]), checked_at=_parse(state["checked_at"]),
                      checked_by=state["checked_by"])


def _put(session: Any, row: Optional[SystemSetting], state: dict[str, Any]) -> None:
    """기록 줄을 쓴다(없으면 만든다 — 커밋은 부르는 쪽)."""
    if row is None:
        session.add(SystemSetting(setting_key=KEY, setting_value=dict(state), version=1,
                                  description="AI 상담 견적 — 계산기 값 지문 · 바뀐 때 · 확인한 때(D74)"))
        return
    row.setting_value = dict(state)
    flag_modified(row, "setting_value")
    row.version = int(row.version or 0) + 1


def observe(session: Any, catalog: Catalog, *, now: datetime.datetime) -> PriceCheck:
    """견적을 계산할 때 — 지문이 바뀌었으면 바뀐 때를 적고 커밋한다(처음 보는 지문은 적기만). 실패하면 '확인 필요'."""
    if catalog.from_seed:
        return PriceCheck(seed=True)
    at = _utc(now)
    digest = fingerprint(catalog)
    try:
        row = session.get(SystemSetting, KEY, populate_existing=True, with_for_update=True)
        state = _state(row.setting_value if row is not None else None)
        if state["fingerprint"] != digest:
            first = state["fingerprint"] is None
            state["fingerprint"] = digest
            if not first:  # 처음 보는 지문은 '바뀜'이 아니다 — 버튼이 있어야 확인 날이 생긴다
                state["changed_at"] = at.isoformat(timespec="seconds")
            _put(session, row, state)
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.warning("[CS 견적] 계산기 값 지문을 적지 못해 '확인 필요'로 본다 why=%s", type(exc).__name__)
        return PriceCheck(failed=True)
    return _check(state)


def confirm(session: Any, catalog: Catalog, *, actor_user_id: int, now: datetime.datetime) -> PriceCheck:
    """[계산기 값 확인했어요] — 지금 값 지문 · 확인한 때 · 사람을 적고 감사 원장 한 줄(커밋은 부르는 쪽).

    Raises:
        CheckError: 계산기 설정 줄이 아직 없다(처음 채우기 파일 — 확인할 값이 없다).
    """
    if catalog.from_seed:
        raise CheckError("계산기 설정이 아직 저장된 적이 없다")
    at = _utc(now).isoformat(timespec="seconds")
    digest = fingerprint(catalog)
    row = session.get(SystemSetting, KEY, populate_existing=True, with_for_update=True)
    state = _state(row.setting_value if row is not None else None)
    if state["fingerprint"] not in (None, digest):
        state["changed_at"] = at  # 아직 못 본 값 바꿈도 같은 때로 적는다
    state.update(fingerprint=digest, checked_at=at, checked_by=int(actor_user_id))
    _put(session, row, state)
    session.add(SecurityLog(user_id=int(actor_user_id), action=AUDIT_ACTION, target_type="system_setting",
                            message=f"{AUDIT_ACTION} key={KEY} at={at}",
                            detail={"key": KEY, "at": at, "fingerprint": digest[:12]}))
    session.flush()
    return _check(state)


def _label(stamp: Optional[datetime.datetime]) -> Optional[str]:
    """시각 → 한국 시각 'MM-DD HH:MM'(없으면 ``None``)."""
    return f"{stamp.astimezone(KST):%m-%d %H:%M}" if stamp is not None else None


def view(session: Any, *, now: datetime.datetime,
         catalog_reader: Callable[[], Catalog] = read_catalog) -> dict[str, Any]:
    """관리 화면 읽기판 — 확인 날 · 바뀐 때 · 확인한 때 · 누가 · '확인 필요' · 아직 못 본 값 바꿈이 있나(읽기만, 쓰지 않는다).

    아직 못 본 값 바꿈(``pending``)은 다음 견적 계산 때 '바뀐 때'로 적힌다 — 그래서 '확인 필요'에는 넣지 않는다.
    """
    row = session.get(SystemSetting, KEY, populate_existing=True)
    state = _state(row.setting_value if row is not None else None)
    check = _check(state)
    try:
        catalog = catalog_reader()
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("[CS 견적] 관리 화면이 계산기 설정을 못 읽었다 why=%s", type(exc).__name__)
        catalog = None
    seed = catalog.from_seed if catalog is not None else None
    pending = None if catalog is None or seed else state["fingerprint"] != fingerprint(catalog)
    who = session.get(User, check.checked_by) if check.checked_by is not None else None
    confirmed = check.confirmed_at
    stale = PriceCheck(changed_at=check.changed_at, checked_at=check.checked_at, seed=bool(seed)).needs_check(now)
    return {"confirmed": _label(confirmed), "changed": _label(check.changed_at), "checked": _label(check.checked_at),
            "checked_by": (who.name if who is not None else "(지운 계정)") if check.checked_by is not None else None,
            "needs_check": stale, "pending": pending, "seed": seed, "fresh_days": FRESH_DAYS}
