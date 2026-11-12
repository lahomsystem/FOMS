"""회사 지식 물어보기(직원 챗봇) 설정 — SystemSetting 한 줄 :data:`SETTINGS_KEY`(설계서 10.1 · 10.2 · 12절 · 사장님 D88 · D99).

**돈이 드는 칸은 처음에 꺼져 있거나 보수적이다**:

- 물어보기 스위치 처음 **끔**. 여는 단계 처음 ``admin``(ADMIN 만 2주 → 팀장 → 내부 직원 전부 — D99 · 13절 2).
- 모델 처음 Sonnet 5.5(13절 8 · D99) · 생각 깊이 낮음 · 최대 출력 4,000 · 시간 상한 30초(다시 보내지 않는다).
- 하루 돈 상한 처음 **비움 = 부르지 않음**(막는 쪽 — 공개 저장소라 금액을 코드에 두지 않는다, 상담 학습 돈 상한과 같은 꼴).
  상담 초안 하루 상한과 **따로** 돈 줄(:data:`SPEND_KEY`)을 쓴다. env :data:`CAP_ENV` 가 있으면 그 값이 천장이다(틀리면 막음).
- 사람마다 하루 질문 수 처음 20. 빈 지식 묶기(주 1회 Haiku) · AI 제안 부딪침 판정(Haiku)은 처음 끔.
- 의미 찾기(D114 — Voyage AI) ``brain_embeddings_enabled`` 처음 **끔** · 의미 찾기 하루 돈 상한 처음 비움(따로 돈 줄) · 한 번
  시간 상한 8초 · 상담 사례 벡터 ``cs_case_embeddings_enabled`` 처음 **끔**(백필만). 켜기 전 개인정보 처리방침 국외 이전 항목에
  Voyage AI(상담 글 포함 — 사장님 확인, 설계서 10.4).

칸 꼴 · 값 검사는 상담 관리 패널 칸(:class:`foms.services.cs_agent.settings_field.Field` ·
:func:`foms.services.cs_agent.settings.check_value`)을 그대로 쓴다. 저장은 ADMIN 만 — 버전 대조 · 감사 한 줄(값 대신 바뀐 칸 이름).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services.cs_agent.brain_prompt import MODEL_HAIKU, MODEL_SONNET
from foms.services.cs_agent.settings import MONEY_MAX, check_value
from foms.services.cs_agent.settings_field import (
    EFFORT_CHOICES, KIND_BOOL, KIND_CHOICE, KIND_INT, KIND_MONEY, MODEL_CHOICES, Field,
)
from foms.services.datetime_kst import now_utc_naive
from models import SecurityLog, SystemSetting

SETTINGS_KEY = "brain_chat_settings"
#: 챗봇 · 빈 지식 묶기 · AI 제안 부딪침 판정이 같이 쓰는 돈 줄(상담 초안 돈 줄과 따로 — 10.2 '모델').
SPEND_KEY = "brain_chat_spend"
#: 하루 돈 천장 env(있으면 화면 값보다 높게 쓰지 않는다 · 틀리면 부르지 않는다). 이름만 — 값은 서비스 env 에만.
CAP_ENV = "FOMS_BRAIN_CHAT_DAILY_USD"
STAGE_ADMIN, STAGE_LEADS, STAGE_ALL = "admin", "leads", "all"
STAGES: tuple[str, ...] = (STAGE_ADMIN, STAGE_LEADS, STAGE_ALL)
GROUP_OPEN, GROUP_MODEL, GROUP_LIMIT, GROUP_HELP = "켜기 · 여는 단계", "모델", "돈 · 남용 막기", "빈 지식 · 관문"
GROUP_EMBED = "의미 찾기(Voyage AI — D114)"
EMBED_FIELD = "brain_embeddings_enabled"
#: 상담 사례(가린 손님 질문 + 가린 직원 답) 벡터 — 백필 스크립트로 채운다. 상담 초안의 비슷한 사례 고르기는 상담 관리 칸
#: '뜻으로도 비슷한 상담 찾기'(:mod:`foms.services.cs_agent.case_meaning`)가 켜졌을 때만 이 벡터를 쓴다.
CASE_FIELD = "cs_case_embeddings_enabled"

FIELDS: tuple[Field, ...] = (
    Field("enabled", "물어보기 스위치", KIND_BOOL, False, GROUP_OPEN,
          help="끄면 아무도 묻지 못해요. 관리자는 꺼져 있어도 이 설정을 봐요"),
    Field("stage", "여는 단계", KIND_CHOICE, STAGE_ADMIN, GROUP_OPEN,
          ((STAGE_ADMIN, "관리자만"), (STAGE_LEADS, "팀장까지"), (STAGE_ALL, "내부 직원 전부")),
          help="관리자만 2주 → 팀장까지 → 내부 직원 전부 차례로 열어요. 협력사 같은 바깥 사람은 어느 단계에서도 못 써요"),
    Field("model", "챗봇 모델", KIND_CHOICE, MODEL_SONNET, GROUP_MODEL, MODEL_CHOICES, help="처음엔 Sonnet 5.5 를 써요"),
    Field("effort", "생각 깊이", KIND_CHOICE, "low", GROUP_MODEL, EFFORT_CHOICES),
    Field("max_tokens", "최대 출력", KIND_INT, 4000, GROUP_MODEL, low=1000, high=16000, unit="토큰"),
    Field("timeout_s", "시간 상한", KIND_INT, 30, GROUP_LIMIT, low=10, high=60, unit="초",
          help="이 시간을 넘으면 답 없이 끝내요(다시 묻지 않아요)"),
    Field("daily_cap_usd", "하루 돈 상한", KIND_MONEY, None, GROUP_LIMIT, high=int(MONEY_MAX), unit="달러",
          help="비우면 AI 를 부르지 않아요. 상담 초안 하루 상한과 따로 계산해요(빈 지식 묶기 · 부딪침 판정도 여기에 들어가요)"),
    Field("per_person_daily", "사람마다 하루 질문 수", KIND_INT, 20, GROUP_LIMIT, low=1, high=200, unit="번"),
    Field("gap_enabled", "빈 지식 묶기(주 1회)", KIND_BOOL, False, GROUP_HELP,
          help="'모름' · '틀림' 질문을 뜻이 비슷한 것끼리 묶어, 비어 있는 지식 목록을 한 주에 한 번 밤에 만들어요(보조 모델)"),
    Field("judge_enabled", "AI 제안 부딪침 판정", KIND_BOOL, False, GROUP_HELP,
          help="AI 가 낸 제안이 승인된 지식과 부딪치는지 순서를 바꿔 두 번 봐요. 끄면 AI 제안은 '승인 대기'에 들어가지 않아요"),
    Field("helper_model", "보조 모델", KIND_CHOICE, MODEL_HAIKU, GROUP_HELP, MODEL_CHOICES,
          help="빈 지식 묶기 · 부딪침 판정에 써요(처음엔 Haiku 5.5)"),
    Field(EMBED_FIELD, "의미 찾기", KIND_BOOL, False, GROUP_EMBED,
          help="켜면 글자 · 비슷한 말로 찾을 때 뜻이 비슷한 지식도 함께 찾아요. 켜기 전에 개인정보 처리방침의 '국외 이전'에 "
               "Voyage AI 를 올려야 해요(사장님 확인). 연결 열쇠가 없거나 실패하면 글자로만 찾아요"),
    Field("embed_daily_cap_usd", "의미 찾기 하루 돈 상한", KIND_MONEY, None, GROUP_EMBED, high=int(MONEY_MAX), unit="달러",
          help="비우면 뜻 찾기 자료를 만들지 않아요(질문 · 지식 모두). 물어보기 하루 상한과 따로 계산해요"),
    Field("embed_timeout_s", "의미 찾기 시간 상한", KIND_INT, 8, GROUP_EMBED, low=3, high=30, unit="초",
          help="한 번 부를 때 이 시간을 넘으면 그 질문은 글자로만 찾아요"),
    Field(CASE_FIELD, "상담 사례 벡터(백필만)", KIND_BOOL, False, GROUP_EMBED,
          help="개인정보를 가린 손님 질문과 직원 답으로 뜻 찾기 자료를 만들어요(지난 상담을 한꺼번에 채울 때 — 상담 초안은 상담 "
               "관리의 '뜻으로도 비슷한 상담 찾기'가 켜졌을 때만 이 자료를 써요). 켜기 전에 개인정보 처리방침의 '국외 이전'에 Voyage AI 와 '상담 글'을 "
               "올려야 해요(사장님 확인)"),
)
FIELD_BY_NAME: dict[str, Field] = {f.name: f for f in FIELDS}
DEFAULTS: dict[str, Any] = {f.name: f.default for f in FIELDS}


class ChatSettingsError(ValueError):
    """설정 저장 거절 — ``code`` 로 가른다(값은 싣지 않는다)."""

    code = "BRAIN_CHAT_SETTINGS"

    def __init__(self, code: str, fields: tuple[str, ...] = ()) -> None:
        """코드 · 칸 이름만."""
        super().__init__(f"{code}: {', '.join(fields)}")
        self.code, self.fields = code, fields


@dataclass(frozen=True)
class ChatSettings:
    """검사한 값 · 버전(0 = 넣은 적 없음)."""

    values: Mapping[str, Any]
    version: int = 0

    def get(self, name: str) -> Any:
        """칸 값 하나."""
        return self.values[name]

    @property
    def enabled(self) -> bool:
        """물어보기 스위치."""
        return bool(self.values["enabled"])

    @property
    def stage(self) -> str:
        """여는 단계."""
        return self.values["stage"]


def _valid(stored: Any) -> dict[str, Any]:
    """저장 값 → 칸마다 쓰는 값(빠지거나 틀린 칸은 처음 값)."""
    source = stored if isinstance(stored, dict) else {}
    out = {}
    for field in FIELDS:
        ok, value = check_value(field, source.get(field.name, field.default))
        out[field.name] = value if ok else field.default
    return out


def read_chat_settings(session: Any) -> ChatSettings:
    """설정을 읽는다(매번 DB 에서 새로 — 저장하면 다음 질문부터)."""
    row = session.get(SystemSetting, SETTINGS_KEY, populate_existing=True)
    if row is None:
        return ChatSettings(dict(DEFAULTS))
    return ChatSettings(_valid(row.setting_value), int(row.version or 0))


def env_cap(environ: Optional[Mapping[str, str]] = None) -> tuple[bool, Optional[Decimal]]:
    """env 천장 — (맞나, 값). 없으면 (True, None), 틀리면 (False, None)."""
    raw = (os.environ if environ is None else environ).get(CAP_ENV)
    if raw is None or not raw.strip():
        return True, None
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        return False, None
    return (True, value) if value.is_finite() and value >= 0 else (False, None)


def daily_cap(cfg: ChatSettings, environ: Optional[Mapping[str, str]] = None) -> Optional[Decimal]:
    """쓰는 하루 상한 — 화면 값(비우면 ``None`` = 부르지 않음)과 env 천장 가운데 작은 것. env 가 틀리면 ``None``."""
    panel = cfg.get("daily_cap_usd")
    ok, ceiling = env_cap(environ)
    if panel is None or not ok:
        return None
    value = Decimal(str(panel))
    return value if ceiling is None else min(value, ceiling)


def settings_view(cfg: ChatSettings) -> dict[str, Any]:
    """화면 표(ADMIN) — 칸마다 이름 · 꼴 · 값 · 고른 값 · 범위 · 설명."""
    return {"version": cfg.version, "fields": [
        {"name": f.name, "label": f.label, "kind": f.kind, "group": f.group, "value": cfg.get(f.name),
         "choices": [{"value": v, "label": label} for v, label in f.choices], "low": f.low, "high": f.high,
         "unit": f.unit, "help": f.help} for f in FIELDS]}


def save_chat_settings(session: Any, *, actor_id: int, changes: Mapping[str, Any], version: Any,
                       now: Any = None) -> ChatSettings:
    """받은 칸을 지금 값에 얹어 저장한다(ADMIN 확인은 부르는 쪽). 틀린 칸이 하나라도 있으면 통째 거절. 커밋은 부르는 쪽.

    Raises:
        ChatSettingsError: ``invalid``(모르는 칸 · 고를 수 없는 값) · ``conflict``(버전이 다름) · ``no_change``.
    """
    if not isinstance(changes, Mapping) or not changes:
        raise ChatSettingsError("invalid", ("changes",))
    wrong = tuple(sorted(str(k)[:40] for k in changes if k not in FIELD_BY_NAME or not check_value(
        FIELD_BY_NAME[k], changes[k])[0]))
    if wrong:
        raise ChatSettingsError("invalid", wrong)
    row = session.get(SystemSetting, SETTINGS_KEY, with_for_update=True, populate_existing=True)
    seen = int(row.version or 0) if row is not None else 0  # 줄이 없으면 읽은 판은 0
    if version is not None and (isinstance(version, bool) or not isinstance(version, int) or version != seen):
        raise ChatSettingsError("conflict")
    if row is None:
        row = SystemSetting(setting_key=SETTINGS_KEY, setting_value=dict(DEFAULTS), version=0,
                            description="회사 지식 물어보기(직원 챗봇) 설정 — 설계서 10절")
        session.add(row)
    before = _valid(row.setting_value)
    after = {**before, **{k: check_value(FIELD_BY_NAME[k], v)[1] for k, v in changes.items()}}
    changed = tuple(sorted(k for k in after if after[k] != before[k]))
    if not changed:
        raise ChatSettingsError("no_change")
    row.setting_value = after
    flag_modified(row, "setting_value")
    row.version = int(row.version or 0) + 1
    session.add(SecurityLog(user_id=int(actor_id), action="BRAIN_CHAT_SETTINGS", target_type="system_setting",
                            target_id=None, timestamp=now or now_utc_naive(),
                            message=f"BRAIN_CHAT_SETTINGS version={row.version} fields={','.join(changed)}",
                            detail={"fields": list(changed), "version": row.version}))
    session.flush()
    return ChatSettings(after, int(row.version))
