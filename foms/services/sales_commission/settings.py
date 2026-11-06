"""프리랜서 설정 — 맞출 이름 · 시작 달 · 세금 방식 · 요율 이력(설계서 FCOMM-01 §4.1 · J5 · J7 · J8).

저장소가 공개라 요율 숫자는 코드에 두지 않고 SystemSetting 한 줄(:data:`SETTINGS_KEY`)에 둔다. 관리자(ADMIN)가
``/admin/sales-freelancers`` 에서 넣는다. 모양::

    {"freelancers": {"<user_id>": {
        "match_name": str, "start_month": "YYYY-MM", "tax_type": "WITHHOLD_3_3" | "VAT_10" | "NONE", "active": bool,
        "rates": [{"effective_month": "YYYY-MM", "lahom_bp": int, "haud_bp": int, "personal_bp": int,
                   "by": user_id, "at": iso}]}}}

저장은 선례 :mod:`foms.services.partners.statement_profile` 와 같은 틀이다 — 줄을 ``FOR UPDATE`` 로 잠그고, 화면이 본
version 과 다르면 409, 값을 새로 대입한 뒤 ``flag_modified`` · version + 1, 줄이 없으면 만든다. 커밋은 부르는 쪽.
수수료 주인은 ``User.name`` 이 아니라 맞출 이름으로 정한다(J8) — 그래서 맞출 이름이 다른 활성 사용자 이름과 겹치면 거부한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_kst
from foms.services.orders.order_mutation_policy import normalize_team
from foms.services.sales_commission.names import normalize_name
from models import SystemSetting, User

SETTINGS_KEY = "sales_freelancer_settings"
TAX_TYPES: tuple[str, ...] = ("WITHHOLD_3_3", "VAT_10", "NONE")
RATE_FIELDS: tuple[str, ...] = ("lahom_bp", "haud_bp", "personal_bp")
BP_MAX = 10000
MATCH_NAME_MAX = 40
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_G_CACHE_ATTR = "_sales_freelancer_ids"


class FreelancerSettingsError(ValueError):
    """화면에 그대로 보일 수 있는 거부 이유. ``status`` 는 HTTP 코드(409 = 그사이 다른 사람이 저장함)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class FreelancerRate:
    """요율 한 줄 — ``effective_month`` 달(시공 완료 달)부터 적용. 단위 basis point(100bp = 1%)."""

    effective_month: str
    lahom_bp: int
    haud_bp: int
    personal_bp: int
    by: Optional[int] = None
    at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"effective_month": self.effective_month, "lahom_bp": self.lahom_bp, "haud_bp": self.haud_bp,
                "personal_bp": self.personal_bp, "by": self.by, "at": self.at}


@dataclass(frozen=True)
class FreelancerConfig:
    """프리랜서 한 명 설정. ``rates`` 는 ``effective_month`` 오름차순."""

    user_id: int
    match_name: str
    start_month: str
    tax_type: str
    active: bool
    rates: tuple[FreelancerRate, ...] = ()

    def rate_for(self, month: str) -> Optional[FreelancerRate]:
        """``month``(YYYY-MM)에 적용되는 요율 — ``effective_month ≤ month`` 중 가장 늦은 것. 없으면 None."""
        found = None
        for rate in self.rates:
            if rate.effective_month <= month:
                found = rate
        return found

    def as_dict(self) -> dict[str, Any]:
        return {"user_id": self.user_id, "match_name": self.match_name, "start_month": self.start_month,
                "tax_type": self.tax_type, "active": self.active, "rates": [r.as_dict() for r in self.rates]}


# --------------------------------------------------------------------------
# 읽기
# --------------------------------------------------------------------------
def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_rate(raw: Any) -> Optional[FreelancerRate]:
    if not isinstance(raw, dict) or not _MONTH_RE.match(str(raw.get("effective_month") or "")):
        return None
    values = [_int_or_none(raw.get(name)) for name in RATE_FIELDS]
    if any(v is None for v in values):
        return None
    return FreelancerRate(str(raw["effective_month"]), values[0], values[1], values[2],
                          _int_or_none(raw.get("by")), str(raw.get("at") or ""))


def _parse_config(user_id: int, raw: Any) -> Optional[FreelancerConfig]:
    if not isinstance(raw, dict):
        return None
    rates = [r for r in (_parse_rate(x) for x in (raw.get("rates") or [])) if r is not None]
    rates.sort(key=lambda r: r.effective_month)
    return FreelancerConfig(
        user_id=user_id, match_name=normalize_name(raw.get("match_name")),
        start_month=str(raw.get("start_month") or ""), tax_type=str(raw.get("tax_type") or "NONE"),
        active=bool(raw.get("active")), rates=tuple(rates),
    )


def _row(db, *, lock: bool = False) -> Optional[SystemSetting]:
    query = db.query(SystemSetting).filter(SystemSetting.setting_key == SETTINGS_KEY)
    return (query.with_for_update() if lock else query).first()


def _configs_from_row(row: Optional[SystemSetting]) -> dict[int, FreelancerConfig]:
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    raw = value.get("freelancers") if isinstance(value.get("freelancers"), dict) else {}
    out: dict[int, FreelancerConfig] = {}
    for key, item in raw.items():
        uid = _int_or_none(key)
        config = _parse_config(uid, item) if uid is not None else None
        if config is not None:
            out[uid] = config
    return out


def _version(row: Optional[SystemSetting]) -> int:
    return int(row.version or 1) if row is not None else 0


def load_settings(db) -> tuple[int, dict[int, FreelancerConfig]]:
    """``(version, {user_id: FreelancerConfig})``. 줄이 없으면 ``(0, {})``."""
    row = _row(db)
    return _version(row), _configs_from_row(row)


def active_freelancers(db) -> dict[int, FreelancerConfig]:
    """켜진 프리랜서만."""
    return {uid: c for uid, c in load_settings(db)[1].items() if c.active}


def match_name_map(db) -> dict[str, int]:
    """켜진 프리랜서의 ``{정리한 맞출 이름: user_id}`` — 주문 이름 칸과 완전 일치로 주인을 정한다(§3.1)."""
    return {c.match_name: uid for uid, c in active_freelancers(db).items() if c.match_name}


def is_freelancer(db, user: Any) -> bool:
    """켜진 프리랜서인지. 요청 안에서는 flask ``g`` 에 한 번만 읽어 둔다(요청 밖에서도 안전)."""
    uid = _int_or_none(getattr(user, "id", None)) if user is not None else None
    if uid is None:
        return False
    ids = None
    try:
        from flask import g, has_app_context
        if has_app_context():
            ids = getattr(g, _G_CACHE_ATTR, None)
            if ids is None:
                ids = frozenset(active_freelancers(db))
                setattr(g, _G_CACHE_ATTR, ids)
    except ImportError:  # pragma: no cover — flask 는 늘 있다
        ids = None
    if ids is None:
        ids = frozenset(active_freelancers(db))
    return uid in ids


def latest_closed_month(db, user_id: int) -> Optional[str]:
    """이 프리랜서의 가장 늦은 마감 달(YYYY-MM). 마감 표(``sales_commission_closings``)는 2단계 T9 에서 생긴다.

    그 전까지는 늘 None 이다 — 곧 "마감된 달 이하 적용 달 거부" 검사는 T9 전에는 건너뛴다. T9 가 이 함수 몸통만
    마감 표 조회로 바꾸면 검사가 켜진다.
    """
    del db, user_id
    return None


# --------------------------------------------------------------------------
# 검사
# --------------------------------------------------------------------------
def _month(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not _MONTH_RE.match(text):
        raise FreelancerSettingsError(f"{label}은 2026-11 처럼 연도-월로 적어 주세요.")
    return text


def _bp(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise FreelancerSettingsError(f"{label} 요율을 숫자로 적어 주세요.")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int):
        try:
            value = int(str(value).strip())
        except (TypeError, ValueError):
            raise FreelancerSettingsError(f"{label} 요율을 숫자로 적어 주세요.") from None
    if value < 0 or value > BP_MAX:
        raise FreelancerSettingsError(f"{label} 요율은 0% 에서 100% 사이로 적어 주세요.")
    return value


def _target_user(db, user_id: Any, *, require_eligible: bool) -> User:
    uid = _int_or_none(user_id)
    user = db.get(User, uid) if uid is not None else None
    if user is None:
        raise FreelancerSettingsError("고른 계정을 찾을 수 없어요.", 404)
    if not require_eligible:
        return user
    if not user.is_active:
        raise FreelancerSettingsError("꺼진 계정은 프리랜서로 정할 수 없어요.")
    if getattr(user, "partner_org_id", None) is not None:
        raise FreelancerSettingsError("협력사 계정은 프리랜서로 정할 수 없어요.")
    if str(user.role or "").strip().upper() != "STAFF" or normalize_team(user.team) != "SALES":
        raise FreelancerSettingsError("직원 · 영업팀 계정만 프리랜서로 정할 수 있어요.")
    return user


def _check_match_name(db, name: str, user_id: int, configs: dict[int, FreelancerConfig], *, active: bool) -> None:
    if not name:
        raise FreelancerSettingsError("맞출 이름을 적어 주세요.")
    if len(name) > MATCH_NAME_MAX:
        raise FreelancerSettingsError(f"맞출 이름은 {MATCH_NAME_MAX}자까지 적을 수 있어요.")
    for uid, config in configs.items():
        if uid != user_id and config.match_name == name:
            raise FreelancerSettingsError("다른 프리랜서가 이미 이 맞출 이름을 쓰고 있어요.")
    if not active:
        return
    others = db.query(User.id, User.name).filter(User.is_active.is_(True), User.id != user_id).all()
    if any(normalize_name(other_name) == name for _oid, other_name in others):
        raise FreelancerSettingsError("이 맞출 이름은 다른 직원 이름과 같아요. 주문이 엉뚱한 사람에게 붙지 않게 다른 이름을 적어 주세요.")


def _clean_rate(db, user_id: int, raw: Any, existing: tuple[FreelancerRate, ...], actor_user_id: Any) -> FreelancerRate:
    raw = raw if isinstance(raw, dict) else {}
    month = _month(raw.get("effective_month"), "적용 달")
    closed = latest_closed_month(db, user_id)
    if closed is not None and month <= closed:
        raise FreelancerSettingsError(f"{closed} 까지는 이미 마감했어요. 그 다음 달부터 적용해 주세요.")
    if any(r.effective_month == month for r in existing):
        raise FreelancerSettingsError("같은 달 요율이 이미 있어요.")
    values = [_bp(raw.get(name), label) for name, label in zip(RATE_FIELDS, ("라홈", "하우드", "개인영업"))]
    return FreelancerRate(month, values[0], values[1], values[2], _int_or_none(actor_user_id), now_kst().isoformat())


# --------------------------------------------------------------------------
# 저장
# --------------------------------------------------------------------------
def _lock_and_check(db, base_version: Any) -> tuple[Optional[SystemSetting], int, dict[int, FreelancerConfig]]:
    row = _row(db, lock=True)
    current = _version(row)
    base = _int_or_none(base_version)
    if base is None or base != current:
        raise FreelancerSettingsError("그사이 다른 사람이 프리랜서 설정을 저장했어요. 화면을 새로 고친 뒤 다시 해 주세요.", 409)
    return row, current, _configs_from_row(row)


def _write(db, row: Optional[SystemSetting], current: int, configs: dict[int, FreelancerConfig]) -> int:
    value = dict(row.setting_value) if row is not None and isinstance(row.setting_value, dict) else {}
    value["freelancers"] = {str(uid): {k: v for k, v in c.as_dict().items() if k != "user_id"}
                            for uid, c in sorted(configs.items())}
    if row is None:
        row = SystemSetting(setting_key=SETTINGS_KEY, description="프리랜서 영업 수수료 설정", version=1)
        db.add(row)
    else:
        row.version = current + 1
    row.setting_value = value
    flag_modified(row, "setting_value")
    db.flush()
    return int(row.version)


def save_freelancer(db, user_id: Any, payload: Any, *, base_version: Any,
                    actor_user_id: Any) -> tuple[int, FreelancerConfig, list[str]]:
    """프리랜서 한 명을 추가하거나 고친다 → ``(새 version, 저장한 설정, 바뀐 칸 이름)``. 커밋은 부르는 쪽.

    ``payload`` = ``{match_name, start_month, tax_type, active, rate?}``. ``rate`` 는 새로 추가할 때만 받는 첫 요율이다.
    켜는 저장만 계정 자격(활성 · 직원 · 영업팀)과 다른 직원 이름 겹침을 본다 — 그만둔 계정도 끌 수는 있어야 한다.
    """
    payload = payload if isinstance(payload, dict) else {}
    row, current, configs = _lock_and_check(db, base_version)
    active = bool(payload.get("active", True))
    user = _target_user(db, user_id, require_eligible=active)
    name = normalize_name(payload.get("match_name"))
    _check_match_name(db, name, user.id, configs, active=active)
    start_month = _month(payload.get("start_month"), "시작 달")
    tax_type = str(payload.get("tax_type") or "").strip().upper()
    if tax_type not in TAX_TYPES:
        raise FreelancerSettingsError("세금 방식을 골라 주세요.")
    before = configs.get(user.id)
    rates = before.rates if before is not None else ()
    if before is None and isinstance(payload.get("rate"), dict):
        rates = (_clean_rate(db, user.id, payload["rate"], (), actor_user_id),)
    config = FreelancerConfig(user.id, name, start_month, tax_type, active, rates)
    old = before.as_dict() if before is not None else {}
    changed = [k for k, v in config.as_dict().items() if k != "user_id" and old.get(k) != v]
    configs[user.id] = config
    return _write(db, row, current, configs), config, changed


def add_rate(db, user_id: Any, rate_payload: Any, *, base_version: Any,
             actor_user_id: Any) -> tuple[int, FreelancerConfig, FreelancerRate]:
    """요율 한 줄을 이력에 더한다 → ``(새 version, 저장한 설정, 더한 요율)``. 같은 달이 이미 있으면 400."""
    row, current, configs = _lock_and_check(db, base_version)
    uid = _int_or_none(user_id)
    before = configs.get(uid) if uid is not None else None
    if before is None:
        raise FreelancerSettingsError("먼저 프리랜서로 추가해 주세요.", 404)
    rate = _clean_rate(db, uid, rate_payload, before.rates, actor_user_id)
    rates = tuple(sorted(before.rates + (rate,), key=lambda r: r.effective_month))
    config = FreelancerConfig(before.user_id, before.match_name, before.start_month, before.tax_type,
                              before.active, rates)
    configs[uid] = config
    return _write(db, row, current, configs), config, rate
