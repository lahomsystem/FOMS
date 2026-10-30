"""관리 패널 설정 — 두뇌 · 돈 · 고르기 손잡이를 SystemSetting 한 줄(:data:`SETTINGS_KEY`)에 둔다(설계서 16.1 · 16.6 단계 1).

칸마다 고를 수 있는 값 목록이나 범위와 처음 값이 :data:`FIELDS` 에 있다. 처음 값은 오늘 코드 상수(두뇌 :mod:`.brain` · 초안
바퀴 :mod:`.drafting`)와 같다 — 줄이 없으면 예전과 똑같이 돈다(시험이 둘을 맞춘다). 두뇌 · 초안 바퀴는 부를 때마다 새로 읽어
저장하면 **다음 차례부터** 적용된다(재배포 없음).

- **잠긴 칸(다음 단계)**: 사장님이 단계 1 로 승인한 것은 스위치 · 두뇌(돈 상한 포함) · 기록이다. 고르기 칸(한 바퀴 두뇌 상한 ·
  묵은 상담 기준)은 승인 밖이고, 의도 고르기 · 실시간 다시 시도 칸은 아직 그 길이 없어 효과가 없다 — :attr:`Field.locked` 칸은
  화면에 값만 보이고, 바꾸는 저장은 :class:`SettingsLockedError` 로 거절하며, 읽을 때는 저장 값과 상관없이 늘 처음 값이다.
- **빠른 길 칸(C10-1 · 설계서 17.1 · 17.3)**: 빠른 길 스위치(처음 끔) · 조용 기다림(10~120초, 처음 15초 — D65) · 최대
  기다림(20~300초, 처음 60초)을 새로 두고, 시간 상한 ``realtime_timeout_s``(처음 45초 · 20~60)는 값은 그대로 두고 잠금만
  풀었다. 학습 돈 상한(처음 값 비움 — 공개 저장소라 금액을 코드에 두지 않는다)은 학습 길(17.6)이 쓸 자리다.
- **읽기(:func:`read_settings`)**: 칸마다 따로 검사해 빠지거나 틀린 칸만 처음 값으로 둔다(경고 로그엔 칸 이름만 — 초안 바퀴가
  바퀴마다 한 번만 남긴다).
- **쓰기(:func:`save_settings`)**: 받은 칸을 지금 값 위에 얹는다. 칸 하나라도 틀리면(모르는 칸 포함) 통째로 거절한다
  (:class:`SettingsInvalidError` — 칸 이름 목록). 저장 값에 있던 모르는 칸 · 잠긴 칸(뒤 단계 것)은 그대로 이어 붙여 남기고,
  틀려서 처음 값으로 쓰던 칸은 수정 기록 ``changed`` 에 ``repaired`` 로 적는다. 그다음은 지식 저장소(:mod:`.knowledge`)와 같은
  설정 쓰기 길 — 줄 ``FOR UPDATE`` → 버전 대조(:class:`SettingsConflictError`) → 값 · 버전 +1 → 수정 기록
  (``SystemSettingReceipt`` — 바뀐 칸 · 전체 값) + 감사 원장(``SecurityLog``)을 한 트랜잭션에. 커밋은 호출자 몫이다.
- **돈 천장**: WORKER(두뇌가 도는 곳) env 하루 상한이 늘 천장이다. 이 화면(web)은 env 를 읽지 않고, 감시 루프가 하트비트에
  남긴 값(:func:`.brain_spend.worker_daily_cap`)으로 천장을 본다 — 그 값을 모르면 칸의 최댓값(:data:`MONEY_MAX`)으로만 막는다.
  쓰는 값은 늘 둘 가운데 작은 것(:meth:`PanelSettings.daily_cap`) — 두뇌가 부를 때 자기 env 로 다시 자른다.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.cs_agent.brain_prompt import (
    CACHE_TTL_1H, CACHE_TTL_5M, MODEL, MODEL_HAIKU, MODEL_SONNET, PRICES, PURPOSE_DRAFT, PURPOSE_INTENT,
    SERVER_FALLBACK_MODELS,
)
from foms.services.cs_agent.brain_spend import worker_daily_cap
from foms.services.datetime_kst import now_utc_naive
from models import SecurityLog, SystemSetting, SystemSettingReceipt

logger = logging.getLogger(__name__)

__all__ = [
    "CACHE_ALWAYS", "CACHE_DAYTIME", "CACHE_OFF", "DAILY_CAP_FIELD", "DEFAULTS", "FIELDS", "FIELD_BY_NAME", "POLICY_ID",
    "SETTINGS_KEY",
    "LOCKED_FIELDS", "Field", "PanelSettings", "SettingsConflictError", "SettingsError", "SettingsInvalidError",
    "SettingsLockedError", "SettingsNoChangeError", "SettingsSaveResult", "check_value", "field_view",
    "read_settings", "save_settings", "value_label",
]

SETTINGS_KEY = "cs_agent_settings"
#: 수정 기록(``SystemSettingReceipt.policy_id``) 이름 — 관리 화면 기록 표가 이 이름으로 고른다.
POLICY_ID = "CS_AGENT_SETTINGS"
#: 수정 기록 ``expires_at`` — 지식 기록처럼 길게 둔다(다른 설정 영수증의 24시간 지우기 창에 걸리지 않게).
RECEIPT_KEEP = datetime.timedelta(days=3650)
KIND_CHOICE, KIND_INT, KIND_BOOL, KIND_MONEY = "choice", "int", "bool", "money"
CACHE_DAYTIME, CACHE_ALWAYS, CACHE_OFF = "daytime", "always", "off"
GROUP_BRAIN, GROUP_TIME, GROUP_CACHE = "모델 · 생각 깊이 · 최대 출력", "시간 상한 · 다시 시도", "캐시 · 대체 모델"
GROUP_MONEY, GROUP_PICK = "돈", "고르기"
GROUP_REALTIME = "빠른 길(실시간 초안)"
#: WORKER env 하루 상한이 천장인 돈 칸(화면 값) — 학습 돈 상한은 실시간과 따로라 이 천장을 쓰지 않는다(설계서 17.6).
DAILY_CAP_FIELD = "daily_cap_usd_panel"
#: 돈 칸 최댓값(달러) — WORKER 상한을 모를 때는 이 값으로만 막는다.
MONEY_MAX = Decimal("10000")
_CENT = Decimal("0.01")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,47}")
_PURPOSE_PREFIX = {PURPOSE_DRAFT: "draft", PURPOSE_INTENT: "intent"}
_MODEL_NAMES = {MODEL: "Opus 5.5", MODEL_SONNET: "Sonnet 5.5", MODEL_HAIKU: "Haiku 5.5"}


@dataclass(frozen=True)
class Field:
    """칸 하나. ``choices`` 는 (값, 화면 이름) 목록, 정수 칸은 ``low`` ~ ``high``. ``help`` 는 화면 설명 한 줄.

    ``locked`` 면 다음 단계 칸이다 — 화면은 값만 보이고, 바꾸는 저장은 거절하고, 읽을 때는 늘 처음 값이다.
    """

    name: str
    label: str
    kind: str
    default: Any
    group: str
    choices: tuple[tuple[Any, str], ...] = ()
    low: Optional[int] = None
    high: Optional[int] = None
    unit: str = ""
    help: str = ""
    locked: bool = False


_MODEL_CHOICES = tuple((model, name) for model, name in _MODEL_NAMES.items())
_MODEL_HELP = " · ".join(f"{_MODEL_NAMES[m]} ${PRICES[m].input} / ${PRICES[m].output}" for m in _MODEL_NAMES) + (
    " (백만 토큰당 입력 / 출력). Haiku 5.5 는 서버 쪽 대체가 없고, 10만 토큰 넘는 프롬프트는 5배 값이다")
_EFFORT_CHOICES = (("low", "낮음"), ("medium", "보통"), ("high", "높음"), ("max", "최고"))
_CACHE_CHOICES = ((CACHE_DAYTIME, "운영 시간만"), (CACHE_ALWAYS, "늘"), (CACHE_OFF, "끔"))
_TTL_CHOICES = ((CACHE_TTL_1H, "1시간"), (CACHE_TTL_5M, "5분"))
_WAIT_CHOICES = ((0.5, "운영일 반나절"), (1, "운영일 1일"), (2, "운영일 2일"))

#: 단계 1 칸 — 처음 값은 오늘 상수 그대로(:mod:`.brain` 의 MODEL · EFFORTS · MAX_TOKENS · 시간 · 다시 하기, :mod:`.drafting` 의
#: MAX_BRAIN_CALLS · MAX_WAIT_BUSINESS_DAYS). 하루 상한 화면 값의 처음 값은 비움(WORKER env 그대로)이다. ``locked=True`` 는
#: 다음 단계 칸(의도 고르기 · 실시간 다시 시도는 아직 그 길이 없고, 고르기는 승인 밖이다). 빠른 길 칸은 :mod:`.realtime` 이 쓴다.
FIELDS: tuple[Field, ...] = (
    Field("draft_model", "초안 모델", KIND_CHOICE, MODEL, GROUP_BRAIN, _MODEL_CHOICES, help=_MODEL_HELP),
    Field("intent_model", "의도 고르기 모델", KIND_CHOICE, MODEL, GROUP_BRAIN, _MODEL_CHOICES, locked=True),
    Field("draft_effort", "초안 생각 깊이", KIND_CHOICE, "high", GROUP_BRAIN, _EFFORT_CHOICES),
    Field("intent_effort", "의도 고르기 생각 깊이", KIND_CHOICE, "low", GROUP_BRAIN, _EFFORT_CHOICES, locked=True),
    Field("draft_max_tokens", "초안 최대 출력", KIND_INT, 16000, GROUP_BRAIN, low=2000, high=32000, unit="토큰",
          help="생각도 이 안에서 쓴다 — 너무 낮으면 답이 잘려 쓸 수 없는 답이 된다"),
    Field("intent_max_tokens", "의도 고르기 최대 출력", KIND_INT, 8000, GROUP_BRAIN, low=2000, high=32000, unit="토큰",
          locked=True),
    Field("realtime_timeout_s", "실시간 길 시간 상한", KIND_INT, 45, GROUP_TIME, low=20, high=60, unit="초",
          help="빠른 길 두뇌가 이만큼 넘으면 그 차례는 실패로 두고 사람에게(다시 보내지 않는다)"),
    Field("batch_timeout_s", "15분 루프 길 시간 상한(밤 · 견적)", KIND_INT, 90, GROUP_TIME, low=30, high=120,
          unit="초"),
    Field("realtime_retries", "실시간 길 다시 시도", KIND_INT, 0, GROUP_TIME, low=0, high=1, unit="번",
          help="요청이 하나도 안 나간 연결 실패만 다시 한다 — 시간 초과는 다시 보내지 않는다", locked=True),
    Field("cache_policy", "캐시 켜는 때", KIND_CHOICE, CACHE_DAYTIME, GROUP_CACHE, _CACHE_CHOICES,
          help="캐시 쓰기는 보통 입력보다 비싸다 — 손님이 드문 밤에는 끄는 쪽이 싸다"),
    Field("cache_ttl", "캐시 길이", KIND_CHOICE, CACHE_TTL_1H, GROUP_CACHE, _TTL_CHOICES,
          help="지시문 · 지식 · 교훈 앞부분에 거는 캐시 — 1시간 쓰기는 입력의 2배, 5분 쓰기는 1.25배(읽기는 같다). "
               "상담이 5분보다 드물게 오면 1시간이 싸다"),
    Field("fallback_enabled", "서버 쪽 대체 모델", KIND_BOOL, True, GROUP_CACHE,
          help="거절된 요청을 공식 대체 모델로 한 번 더 — Haiku 5.5 는 대체가 없어 늘 보내지 않는다"),
    Field(DAILY_CAP_FIELD, "하루 돈 상한(화면 값)", KIND_MONEY, None, GROUP_MONEY, high=int(MONEY_MAX), unit="달러",
          help="비우면 WORKER env 그대로 — 그보다 높게는 저장되지 않는다(쓰는 값은 둘 가운데 작은 것). "
               "상한에 닿아 멈춘 날도 상한을 올리면 다음 바퀴부터 다시 돈다(콘솔 상한에 닿은 날은 그날 멈춤)"),
    Field("learning_cap_usd_panel", "학습 돈 상한", KIND_MONEY, None, GROUP_MONEY, high=int(MONEY_MAX), unit="달러",
          help="스스로 배우기(설계서 17.6)에 쓰는 돈을 실시간 초안과 따로 묶는 칸 — 학습 길이 생기면 쓴다(지금은 효과 없음)"),
    Field("max_brain_calls_per_pass", "한 바퀴 두뇌 상한", KIND_INT, 10, GROUP_PICK, low=1, high=20, unit="번",
          locked=True),
    Field("max_wait_business_days", "묵은 상담 기준", KIND_CHOICE, 1, GROUP_PICK, _WAIT_CHOICES,
          help="마지막 손님 글이 운영 시간으로 이만큼 넘게 묵은 상담은 초안을 쓰지 않는다", locked=True),
    Field("realtime_enabled", "빠른 길 스위치", KIND_BOOL, False, GROUP_REALTIME,
          help="켜면 5초마다 새 손님 글을 보고 조용 기다림 뒤 초안을 쓴다(초안 스위치가 저장만 · 메모이고 비상 정지가 아닐 "
               "때만). 켜 있는 동안 15분 바퀴는 초안을 쓰지 않는다(보정 · 아침 보고만)"),
    Field("quiet_wait_s", "조용 기다림", KIND_INT, 15, GROUP_REALTIME, low=10, high=120, unit="초",
          help="마지막 손님 글 뒤 이만큼 새 글이 없으면 집는다(D65) — 짧을수록 갈아 끼움 · 두뇌 부름이 는다"),
    Field("max_wait_s", "최대 기다림", KIND_INT, 60, GROUP_REALTIME, low=20, high=300, unit="초",
          help="손님이 계속 써도 첫 미답 글부터 이만큼 지나면 집는다(그 사이 이 상담 초안이 한 번도 없었을 때만)"),
)
FIELD_BY_NAME: dict[str, Field] = {f.name: f for f in FIELDS}
DEFAULTS: dict[str, Any] = {f.name: f.default for f in FIELDS}
LOCKED_FIELDS: frozenset[str] = frozenset(f.name for f in FIELDS if f.locked)


# ── 오류 ─────────────────────────────────────────────────────────────────
class SettingsError(ValueError):
    """설정 쓰기 거절 — 호출부는 :attr:`code` 로 가른다. 값은 싣지 않는다."""

    code = "CS_SETTINGS_ERROR"


class SettingsInvalidError(SettingsError):
    """고를 수 없는 값 · 모르는 칸 — :attr:`fields` 에 칸 이름만."""

    code = "CS_SETTINGS_INVALID"

    def __init__(self, fields: Sequence[str]) -> None:
        """틀린 칸 이름을 싣는다."""
        self.fields = tuple(fields)
        super().__init__("고를 수 없는 값: " + ", ".join(self.fields))


class SettingsLockedError(SettingsInvalidError):
    """다음 단계 칸(잠김)을 바꾸려 했다 — 이 단계에서는 처음 값 그대로다. :attr:`fields` 에 칸 이름만."""

    code = "CS_SETTINGS_LOCKED"

    def __init__(self, fields: Sequence[str]) -> None:
        """잠긴 칸 이름을 싣는다."""
        super().__init__(fields)
        self.args = ("다음 단계 칸이라 바꿀 수 없다: " + ", ".join(self.fields),)


class SettingsConflictError(SettingsError):
    """읽은 버전과 지금 버전이 다르다(다른 사람이 먼저 저장했다) — 새로 읽고 다시."""

    code = "REVISION_CONFLICT"

    def __init__(self, current_version: int) -> None:
        """지금 버전을 싣는다."""
        super().__init__(f"버전이 다르다 — 지금 버전 {current_version}")
        self.current_version = int(current_version)


class SettingsNoChangeError(SettingsError):
    """바뀐 칸이 없다 — 같은 값으로 버전만 늘리지 않는다."""

    code = "CS_SETTINGS_NO_CHANGE"


# ── 칸 검사 ──────────────────────────────────────────────────────────────
def _same(value: Any, choice: Any) -> bool:
    """고르기 값 같음 — 글자는 글자끼리, 숫자는 숫자끼리(참 · 거짓은 숫자가 아니다)."""
    if isinstance(choice, str):
        return isinstance(value, str) and value == choice
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == choice


def _money_of(value: Any) -> tuple[bool, Optional[str]]:
    """돈 칸 — 비움(``None`` · 빈 글) 또는 0 이상 · 센트까지 · :data:`MONEY_MAX` 이하. 맞으면 (True, 센트까지 쓴 글)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return True, None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return False, None
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        return False, None
    if not amount.is_finite() or amount < 0 or amount > MONEY_MAX or amount != amount.quantize(_CENT):
        return False, None
    return True, str(amount.quantize(_CENT))


def check_value(field: Field, value: Any) -> tuple[bool, Any]:
    """값 하나를 칸 규칙으로 검사한다 — (맞나, 저장할 꼴). 틀리면 (False, None)."""
    if field.kind == KIND_BOOL:
        return (True, value) if isinstance(value, bool) else (False, None)
    if field.kind == KIND_INT:
        ok = isinstance(value, int) and not isinstance(value, bool) and field.low <= value <= field.high
        return (True, value) if ok else (False, None)
    if field.kind == KIND_MONEY:
        return _money_of(value)
    for choice, _label in field.choices:
        if _same(value, choice):
            return True, choice
    return False, None


def _valid_values(stored: Any) -> tuple[dict[str, Any], list[str], list[str]]:
    """저장 값 → (칸마다 쓰는 값, 처음 값으로 돌린 칸, 그 가운데 값이 있었는데 틀린 칸).

    잠긴 칸은 저장 값과 상관없이 늘 처음 값이다(돌린 칸으로 세지 않는다). 저장 값이 dict 가 아니면 모든 칸이 틀린 칸이다.
    """
    source = stored if isinstance(stored, dict) else {}
    broken = stored is not None and not isinstance(stored, dict)
    values: dict[str, Any] = {}
    fallback: list[str] = []
    wrong: list[str] = []
    for field in FIELDS:
        if field.locked:
            values[field.name] = field.default
            continue
        present = field.name in source
        ok, value = check_value(field, source[field.name]) if present else (False, None)
        values[field.name] = value if ok else field.default
        if not ok:
            fallback.append(field.name)
            if present or broken:
                wrong.append(field.name)
    return values, fallback, wrong


# ── 읽기 ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PanelSettings:
    """검사한 설정 값 · 버전(0 = 넣은 적 없음) · 처음 값으로 돌린 칸 이름. 두뇌 · 초안 바퀴가 쓰는 꼴로 꺼내 준다."""

    values: Mapping[str, Any]
    version: int = 0
    fallback_fields: tuple[str, ...] = ()

    def get(self, name: str) -> Any:
        """칸 값 하나."""
        return self.values[name]

    def model_for(self, purpose: str) -> str:
        """그 일(초안 · 의도 고르기)의 모델."""
        return self.values[f"{_PURPOSE_PREFIX[purpose]}_model"]

    def effort_for(self, purpose: str) -> str:
        """그 일의 생각 깊이(effort)."""
        return self.values[f"{_PURPOSE_PREFIX[purpose]}_effort"]

    def max_tokens_for(self, purpose: str) -> int:
        """그 일의 최대 출력."""
        return self.values[f"{_PURPOSE_PREFIX[purpose]}_max_tokens"]

    def cache_on(self, daytime: bool) -> bool:
        """캐시 표시를 달까 — 방침이 '늘'이면 늘, '운영 시간만'이면 운영 시간에만, '끔'이면 안 단다."""
        policy = self.values["cache_policy"]
        return policy == CACHE_ALWAYS or (policy == CACHE_DAYTIME and daytime)

    def cache_ttl_for(self, daytime: bool) -> Optional[str]:
        """이번 요청의 캐시 길이(1h · 5m) — 캐시 표시를 달지 않으면 ``None``."""
        return self.values["cache_ttl"] if self.cache_on(daytime) else None

    def fallback_on(self, model: str) -> bool:
        """서버 쪽 대체를 보낼까 — 켬이고 그 모델이 대체를 받을 때만(Haiku 5.5 는 늘 안 보낸다)."""
        return bool(self.values["fallback_enabled"]) and model in SERVER_FALLBACK_MODELS

    def daily_cap(self, env_cap: Decimal) -> Decimal:
        """쓰는 하루 상한 = env 와 화면 값 가운데 작은 것(화면 값을 비웠으면 env)."""
        panel = self.values[DAILY_CAP_FIELD]
        return env_cap if panel is None else min(env_cap, Decimal(panel))


def read_settings(session: Any, *, log: bool = True) -> PanelSettings:
    """설정을 읽는다(매번 DB 에서 새로). 줄이 없으면 처음 값, 틀린 칸만 처음 값 + 칸 이름 경고(``log`` 일 때만).

    경고는 초안 바퀴가 바퀴마다 한 번 남긴다 — 두뇌 · 준비 확인 · 화면은 ``log=False`` 로 읽는다.
    """
    row = session.get(SystemSetting, SETTINGS_KEY, populate_existing=True)
    if row is None:
        return PanelSettings(dict(DEFAULTS))
    values, fallback, _wrong = _valid_values(row.setting_value)
    if fallback and log:
        logger.warning("[CS 설정] 저장된 설정 칸이 빠지거나 틀려 처음 값으로 둔다 key=%s version=%s fields=%s",
                       SETTINGS_KEY, row.version, ",".join(fallback))
    return PanelSettings(values, int(row.version or 0), tuple(fallback))


def value_label(name: str, value: Any) -> str:
    """칸 값의 화면 글 — 고르기는 화면 이름, 켬끔은 켬 · 끔, 돈 비움은 'env 그대로', 정수는 단위를 붙인다."""
    field = FIELD_BY_NAME.get(name)
    if field is None:
        return str(value)
    if field.kind == KIND_BOOL:
        return "켬" if value else "끔"
    if field.kind == KIND_MONEY:
        empty = "env 그대로" if name == DAILY_CAP_FIELD else "비움"
        return empty if value is None else f"${value}"
    if field.kind == KIND_INT:
        return f"{value:,} {field.unit}".strip() if isinstance(value, int) else str(value)
    return next((label for choice, label in field.choices if _same(value, choice)), str(value))


def field_view(field: Field, value: Any) -> dict[str, Any]:
    """화면 · API 가 그리는 칸 하나(JSON 꼴)."""
    return {"name": field.name, "label": field.label, "kind": field.kind, "group": field.group, "value": value,
            "default": field.default, "default_label": value_label(field.name, field.default),
            "choices": [{"value": c, "label": label} for c, label in field.choices],
            "low": field.low, "high": field.high, "unit": field.unit, "help": field.help, "locked": field.locked}


# ── 쓰기(기존 설정 쓰기 길) ──────────────────────────────────────────────
@dataclass(frozen=True)
class SettingsSaveResult:
    """쓰기 결과 — 새 버전 · 수정 기록 id · 바뀐 칸 이름."""

    version: int
    receipt_id: str
    changed: tuple[str, ...]


def _checked_changes(values: Any, ceiling: Optional[Decimal]) -> dict[str, Any]:
    """받은 칸 검사(잠금 전) → {칸: 저장할 꼴}. 틀린 칸 · 모르는 칸이 하나라도 있으면 :class:`SettingsInvalidError`."""
    if not isinstance(values, Mapping):
        raise SettingsInvalidError(("values",))
    checked: dict[str, Any] = {}
    bad: set[str] = set()
    for name, raw in values.items():
        field = FIELD_BY_NAME.get(name) if isinstance(name, str) else None
        ok, value = check_value(field, raw) if field is not None else (False, None)
        if ok and name == DAILY_CAP_FIELD and value is not None and ceiling is not None and Decimal(value) > ceiling:
            ok = False  # WORKER env 가 천장 — 화면은 그보다 낮게만(학습 돈 상한은 따로라 이 천장을 쓰지 않는다)
        if ok:
            checked[name] = value
        else:
            bad.add(name if isinstance(name, str) and _NAME.fullmatch(name) else "(이름 꼴 아님)")
    if bad:
        raise SettingsInvalidError(sorted(bad))
    return checked


def _hash_of(values: Mapping[str, Any]) -> str:
    """전체 값의 sha256(수정 기록 ``request_hash``)."""
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _put_value(session: Any, row: Optional[SystemSetting], values: dict[str, Any]) -> SystemSetting:
    """값을 통째로 갈아 끼운다(줄이 없으면 버전 0 으로 만든다 — 호출부가 1 로 올린다)."""
    if row is None:
        row = SystemSetting(setting_key=SETTINGS_KEY, version=0,
                            description="AI 상담팀원 관리 패널 설정 — 두뇌 · 돈 · 고르기(설계서 16.1, 다음 차례부터 적용)")
        try:
            with session.begin_nested():  # 없는 줄은 FOR UPDATE 가 못 잠근다 — 같은 때 첫 저장이 겹치면 여기서 갈린다
                session.add(row)
                session.flush()
        except IntegrityError:
            existing = session.get(SystemSetting, SETTINGS_KEY, populate_existing=True)
            raise SettingsConflictError(int(existing.version or 0) if existing is not None else 0) from None
    row.setting_value = copy.deepcopy(values)
    flag_modified(row, "setting_value")
    return row


def _document(stored: Any, before: Mapping[str, Any], edits: Mapping[str, Any]) -> dict[str, Any]:
    """저장할 문서 — 저장 값의 모르는 칸 · 잠긴 칸은 그대로 이어 붙이고(뒤 단계 것), 고칠 수 있는 칸은 지금 값 + 받은 값."""
    kept = ({name: copy.deepcopy(value) for name, value in stored.items()
             if name not in FIELD_BY_NAME or name in LOCKED_FIELDS} if isinstance(stored, dict) else {})
    return {**kept, **{f.name: edits.get(f.name, before[f.name]) for f in FIELDS if not f.locked}}


def _changes(stored: Any, before: Mapping[str, Any], document: Mapping[str, Any],
             wrong: Sequence[str]) -> dict[str, Any]:
    """수정 기록의 바뀐 칸(칸 순서) — 받은 값으로 바뀐 칸 + 틀려서 처음 값으로 쓰던 칸(``repaired`` — 저장돼 있던 값을 적는다)."""
    changed: dict[str, Any] = {}
    for field in FIELDS:
        name = field.name
        if field.locked:
            continue
        if name in wrong:
            raw = stored.get(name) if isinstance(stored, dict) else None
            changed[name] = {"from": copy.deepcopy(raw), "to": document[name], "repaired": True}
        elif before[name] != document[name]:
            changed[name] = {"from": before[name], "to": document[name]}
    return changed


def _record(session: Any, *, values: dict[str, Any], changed: dict[str, Any], version: int, actor_user_id: int,
            now: datetime.datetime) -> str:
    """수정 기록(바뀐 칸 · 전체 값) + 감사 원장 한 줄을 같은 트랜잭션에 넣는다. 수정 기록 id 를 돌려준다."""
    receipt_id = str(uuid.uuid4())
    body = {"success": True, "data": {"version": version, "changed": copy.deepcopy(changed),
                                      "values": copy.deepcopy(values), "at": now.isoformat(timespec="seconds")}}
    session.add(SystemSettingReceipt(
        read_receipt_id=receipt_id, actor_user_id=actor_user_id, setting_key=SETTINGS_KEY, policy_id=POLICY_ID,
        idempotency_key=None, request_hash=_hash_of(values), response_status=200, response_body=body,
        resulting_version=version, expires_at=now + RECEIPT_KEEP))
    session.add(SecurityLog(
        user_id=actor_user_id, action="CS_AGENT_SETTINGS_UPDATE", target_type="system_setting",
        message=f"CS_AGENT_SETTINGS_UPDATE key={SETTINGS_KEY} version={version} fields={','.join(changed)}",
        detail={"key": SETTINGS_KEY, "version": version, "fields": list(changed)}))
    session.flush()
    return receipt_id


def save_settings(session: Any, values: Any, *, expected_version: int, actor_user_id: int,
                  now: Optional[datetime.datetime] = None) -> SettingsSaveResult:
    """받은 칸을 지금 값 위에 얹어 새 버전으로 쓴다(커밋은 호출자). 검사는 잠금 전에 한다.

    Args:
        session: DB 세션.
        values: {칸 이름: 값}(신뢰하지 않는다 — 빠진 칸은 지금 값 그대로).
        expected_version: 화면이 읽은 지금 버전(넣은 적 없으면 0).
        actor_user_id: 저장하는 사람(켜진 ADMIN — 수정 기록 · 감사 주체).
        now: 시험 주입(UTC naive).

    Returns:
        :class:`SettingsSaveResult`.

    Raises:
        SettingsInvalidError: 틀린 칸 · 모르는 칸(:class:`SettingsLockedError` — 잠긴 칸을 바꾸려 함).
        SettingsConflictError: 버전이 다름. SettingsNoChangeError: 바뀐 칸 없음.
    """
    checked = _checked_changes(values, worker_daily_cap(session).cap)  # 모르면 None — 칸의 최댓값으로만 막는다
    row = session.get(SystemSetting, SETTINGS_KEY, populate_existing=True, with_for_update=True)
    current = int(row.version or 0) if row is not None else 0
    if expected_version != current:
        raise SettingsConflictError(current)
    stored = row.setting_value if row is not None else None
    before, _fallback, wrong = _valid_values(stored)
    locked = sorted(name for name, value in checked.items() if name in LOCKED_FIELDS and value != before[name])
    if locked:
        raise SettingsLockedError(locked)
    document = _document(stored, before, {n: v for n, v in checked.items() if n not in LOCKED_FIELDS})
    changed = _changes(stored, before, document, wrong)
    if not changed:
        raise SettingsNoChangeError(f"지금 버전 {current} 과 같은 값이다 — 쓰지 않는다")
    row = _put_value(session, row, document)
    row.version = current + 1
    receipt_id = _record(session, values=document, changed=changed, version=row.version,
                         actor_user_id=actor_user_id, now=now or now_utc_naive())
    return SettingsSaveResult(row.version, receipt_id, tuple(changed))
