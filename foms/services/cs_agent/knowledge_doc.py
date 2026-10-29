"""기준 답 문서 — 꼴 검사 · 승인 항목 · 개수 · 차이(순수 함수, DB 없음). 저장 · 읽기 길은 :mod:`.knowledge`.

플랜 C2-1 · 설계서 7.1(C2-0 확정안 1 · 2 · 5). 문서 하나 = 브랜드 하나::

    {"schema_version": 1, "brand": "LAHOM",
     "items": [{"id": "hours-weekday", "kind": "template", "intents": ["business_hours"], "text": "…",
                "status": "approved", "approved_by": "…", "approved_at": "2026-11-02",
                "checked_at": null, "source": "…", "tags": []}]}

- 종류(``kind``): 기준 답 문구(template — 의도가 하나 이상) · 사실(fact) · 정책(policy) · 가격 규칙(price_rule — 계산기
  재료, ``checked_at`` = 마지막 확인 날 — 승인하려면 꼭 있어야 한다) · 사장님 결정(owner_decision).
- 상태(``status``): draft · approved · retired. 승인(approved)은 ``approved_by`` · ``approved_at`` 이 있어야 하고, 재료가
  되는 것은 승인 항목뿐이다(:func:`approved_items`).
- 모르는 칸은 거절한다(정본 꼴 그대로만). 문제 글에는 자리 · 까닭만 싣고 항목 글은 싣지 않는다.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from foms.services.cs_agent.channel_read import CHANNEL_BRANDS
from foms.services.datetime_kst import get_today_kst

SCHEMA_VERSION = 1
#: 브랜드 이름 — 채널 짝(``channel_read.CHANNEL_BRANDS``)이 정본이다.
KNOWN_BRANDS: frozenset[str] = frozenset(CHANNEL_BRANDS.values())

KIND_TEMPLATE, KIND_FACT, KIND_POLICY = "template", "fact", "policy"
KIND_PRICE_RULE, KIND_OWNER_DECISION = "price_rule", "owner_decision"
KINDS: tuple[str, ...] = (KIND_TEMPLATE, KIND_FACT, KIND_POLICY, KIND_PRICE_RULE, KIND_OWNER_DECISION)
STATUS_DRAFT, STATUS_APPROVED, STATUS_RETIRED = "draft", "approved", "retired"
STATUSES: tuple[str, ...] = (STATUS_DRAFT, STATUS_APPROVED, STATUS_RETIRED)

MAX_ITEMS = 500
MAX_TEXT_LEN = 2000
MAX_INTENTS = 20
MAX_TAGS = 10
MAX_APPROVER_LEN = 100
MAX_SOURCE_LEN = 200  # 근거 파일 이름
MAX_PROBLEMS = 30  # 오류에 싣는 문제 수 상한

#: 정본 항목 칸(이 순서로 저장 · 비교한다).
ITEM_FIELDS: tuple[str, ...] = ("id", "kind", "intents", "text", "status", "approved_by", "approved_at",
                                "checked_at", "source", "tags")
_ITEM_KEYS = frozenset(ITEM_FIELDS)
_TOP_KEYS = frozenset({"schema_version", "brand", "items"})
_SLUG = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")  # 항목 id · 의도 id
_TAG = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
#: 승인 날 · 마지막 확인 날은 날짜만(시각 · 시간대를 섞으면 14일 낡음 계산이 꼬인다 — 원장 R6-15).
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
#: 오늘(KST)보다 이만큼 뒤 날짜까지만 받는다(시간대 차이 여유) — 미래 확인 날로 낡음 규칙을 피하지 못하게.
FUTURE_SLACK = datetime.timedelta(days=1)


class KnowledgeError(RuntimeError):
    """기준 답 저장을 진행할 수 없다(호출부가 ``code`` 로 가른다)."""

    code = "CS_KNOWLEDGE_ERROR"


class KnowledgeSchemaError(KnowledgeError):
    """문서 꼴이 틀렸다. ``problems`` 는 자리 · 까닭만 담는다(글은 담지 않는다)."""

    code = "CS_KNOWLEDGE_SCHEMA"

    def __init__(self, problems: Sequence[str]) -> None:
        """문제 목록을 상한까지만 싣는다."""
        shown = list(problems[:MAX_PROBLEMS])
        if len(problems) > MAX_PROBLEMS:
            shown.append(f"… 그 밖에 {len(problems) - MAX_PROBLEMS}건")
        super().__init__("; ".join(shown))
        self.problems: tuple[str, ...] = tuple(shown)


# ── 칸 검사 ──────────────────────────────────────────────────────────────
def _unknown_keys(raw: Mapping[str, Any], allowed: frozenset[str], where: str, problems: list[str]) -> None:
    """허용 밖 칸을 문제로 적는다(칸 이름만 — 값은 적지 않는다)."""
    extra = sorted(str(key)[:40] for key in raw if key not in allowed)
    if extra:
        problems.append(f"{where}: 모르는 칸 {extra}")


def _name(value: Any, pattern: re.Pattern[str], where: str, problems: list[str]) -> Optional[str]:
    """짧은 이름(id · 의도 · 꼬리표) — 소문자 · 숫자 · ``_.-`` 만."""
    if isinstance(value, str) and pattern.fullmatch(value):
        return value
    problems.append(f"{where}: 소문자 · 숫자 · '_' '.' '-' 로 된 짧은 이름이어야 한다")
    return None


def _choice(value: Any, choices: tuple[str, ...], where: str, problems: list[str]) -> Optional[str]:
    """정해진 값 가운데 하나."""
    if isinstance(value, str) and value in choices:
        return value
    problems.append(f"{where}: {' / '.join(choices)} 가운데 하나여야 한다")
    return None


def _text(value: Any, where: str, problems: list[str]) -> Optional[str]:
    """글 — 앞뒤 공백을 걷고 줄바꿈을 ``\\n`` 으로 맞춘다(1자 이상 · :data:`MAX_TEXT_LEN` 자 이하)."""
    if not isinstance(value, str) or not value.strip():
        problems.append(f"{where}: 글이 비었다")
        return None
    text = value.replace("\r\n", "\n").strip()
    if len(text) > MAX_TEXT_LEN:
        problems.append(f"{where}: {len(text)}자 — {MAX_TEXT_LEN}자를 넘는다")
        return None
    return text


def _names(value: Any, pattern: re.Pattern[str], limit: int, where: str, problems: list[str]) -> list[str]:
    """이름 목록(없으면 빈 목록). 겹침 · 꼴 틀림 · 개수 넘침은 문제."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        problems.append(f"{where}: {limit}개 이하의 목록이어야 한다")
        return []
    names: list[str] = []
    for index, entry in enumerate(value):
        name = _name(entry, pattern, f"{where}[{index}]", problems)
        if name is not None and name in names:
            problems.append(f"{where}[{index}]: 겹친다")
        elif name is not None:
            names.append(name)
    return names


def _line(value: Any, limit: int, where: str, problems: list[str]) -> Optional[str]:
    """한 줄 짧은 글(없으면 ``None``) — 승인한 사람 · 근거 파일 이름."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() and len(value.strip()) <= limit and "\n" not in value:
        return value.strip()
    problems.append(f"{where}: {limit}자 이하 한 줄이어야 한다")
    return None


def _day(value: Any, latest: datetime.date, where: str, problems: list[str]) -> Optional[str]:
    """날짜(``YYYY-MM-DD`` 만 — 없으면 ``None``). 실제로 있는 날이고 ``latest`` 보다 뒤가 아니어야 한다."""
    if value is None:
        return None
    text = value.strip() if isinstance(value, str) else ""
    try:
        day = datetime.date.fromisoformat(text) if _DAY.fullmatch(text) else None
    except ValueError:  # 2월 30일처럼 없는 날
        day = None
    if day is None:
        problems.append(f"{where}: 날짜(YYYY-MM-DD)여야 한다")
        return None
    if day > latest:
        problems.append(f"{where}: 미래 날짜는 받지 않는다")
        return None
    return text


def _validate_item(raw: Any, latest: datetime.date, where: str, problems: list[str]) -> Optional[dict[str, Any]]:
    """항목 하나를 정본 dict 로(틀리면 문제를 적고 ``None``). ``latest`` = 받는 가장 늦은 날짜."""
    if not isinstance(raw, dict):
        problems.append(f"{where}: 객체여야 한다")
        return None
    before = len(problems)
    _unknown_keys(raw, _ITEM_KEYS, where, problems)
    item = {
        "id": _name(raw.get("id"), _SLUG, f"{where}.id", problems),
        "kind": _choice(raw.get("kind"), KINDS, f"{where}.kind", problems),
        "intents": _names(raw.get("intents"), _SLUG, MAX_INTENTS, f"{where}.intents", problems),
        "text": _text(raw.get("text"), f"{where}.text", problems),
        "status": _choice(raw.get("status"), STATUSES, f"{where}.status", problems),
        "approved_by": _line(raw.get("approved_by"), MAX_APPROVER_LEN, f"{where}.approved_by", problems),
        "approved_at": _day(raw.get("approved_at"), latest, f"{where}.approved_at", problems),
        "checked_at": _day(raw.get("checked_at"), latest, f"{where}.checked_at", problems),
        "source": _line(raw.get("source"), MAX_SOURCE_LEN, f"{where}.source", problems),
        "tags": _names(raw.get("tags"), _TAG, MAX_TAGS, f"{where}.tags", problems),
    }
    if item["kind"] == KIND_TEMPLATE and raw.get("intents") in (None, []):
        problems.append(f"{where}.intents: 기준 답 문구는 의도가 하나 이상 있어야 한다")
    if item["status"] == STATUS_APPROVED and (item["approved_by"] is None or item["approved_at"] is None):
        problems.append(f"{where}: 승인 항목은 approved_by · approved_at 이 있어야 한다")
    if item["status"] == STATUS_APPROVED and item["kind"] == KIND_PRICE_RULE and raw.get("checked_at") is None:
        # 낡은 가격 막기(설계서 7.1 C2-0 확정안 5)는 이 날짜로 잰다 — 날짜 없는 승인 가격은 받지 않는다
        problems.append(f"{where}: 승인된 가격 규칙은 checked_at(마지막 확인 날)이 있어야 한다")
    return item if len(problems) == before else None


def validate_document(doc: Any, *, brand: str, today: Optional[datetime.date] = None) -> dict[str, Any]:
    """문서를 검사해 정본(칸 순서 고정 · 글 다듬음)으로 돌려준다. 문제는 모아서 한 번에 낸다.

    Args:
        doc: 검사할 문서(신뢰하지 않는다).
        brand: 넣을 곳의 브랜드 — 문서의 ``brand`` 와 같아야 한다(브랜드 섞임 막기).
        today: 시험 주입(없으면 오늘 KST). 승인 날 · 확인 날은 오늘 + :data:`FUTURE_SLACK` 까지만 받는다.

    Returns:
        ``{"schema_version", "brand", "items": [정본 항목, …]}``.

    Raises:
        ValueError: 모르는 브랜드(호출부 잘못).
        KnowledgeSchemaError: 문서 꼴이 틀림.
    """
    if brand not in KNOWN_BRANDS:
        raise ValueError(f"모르는 브랜드: {brand!r}")
    if not isinstance(doc, dict):
        raise KnowledgeSchemaError(["문서: 객체여야 한다"])
    problems: list[str] = []
    _unknown_keys(doc, _TOP_KEYS, "문서", problems)
    if type(doc.get("schema_version")) is not int or doc.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version: {SCHEMA_VERSION} 이어야 한다")
    if doc.get("brand") != brand:
        problems.append(f"brand: 넣을 곳의 브랜드({brand})와 같아야 한다 — 다른 브랜드 문서는 넣지 않는다")
    raw_items = doc.get("items")
    if not isinstance(raw_items, list) or len(raw_items) > MAX_ITEMS:
        problems.append(f"items: {MAX_ITEMS}개 이하의 목록이어야 한다")
        raw_items = []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    latest = (today or get_today_kst()) + FUTURE_SLACK
    for index, raw in enumerate(raw_items):
        item = _validate_item(raw, latest, f"items[{index}]", problems)
        if item is not None and item["id"] in seen:
            problems.append(f"items[{index}].id: '{item['id']}' 가 겹친다")
        elif item is not None:
            seen.add(item["id"])
            items.append(item)
    if problems:
        raise KnowledgeSchemaError(problems)
    return {"schema_version": SCHEMA_VERSION, "brand": brand, "items": items}


# ── 승인 항목(재료) ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class KnowledgeItem:
    """승인 항목 하나(읽기 전용). ``text`` 는 repr 에 싣지 않는다 — 로그에 글이 따라가지 않게."""

    item_id: str
    kind: str
    status: str
    text: str = field(repr=False)
    intents: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    checked_at: Optional[str] = None
    source: Optional[str] = None


def approved_items(document: Optional[Mapping[str, Any]]) -> tuple[KnowledgeItem, ...]:
    """정본 문서에서 **승인 항목만**(문서 순서) — 초안 · 내림 항목은 재료가 되지 않는다. 문서가 없으면 빈 묶음."""
    rows = (document or {}).get("items") or []
    return tuple(KnowledgeItem(item_id=row["id"], kind=row["kind"], status=row["status"], text=row["text"],
                               intents=tuple(row["intents"]), tags=tuple(row["tags"]),
                               approved_by=row["approved_by"], approved_at=row["approved_at"],
                               checked_at=row["checked_at"], source=row["source"])
                 for row in rows if row.get("status") == STATUS_APPROVED)


@dataclass(frozen=True)
class ApprovedKnowledge:
    """한 브랜드의 승인 항목 묶음(초안 재료). ``problem`` 이 있으면 저장 값이 틀려 재료가 0 이다."""

    brand: str
    version: int  # 읽은 SystemSetting 버전(0 = 넣은 적 없음)
    items: tuple[KnowledgeItem, ...] = ()
    problem: Optional[str] = None

    def templates_for_intent(self, intent: str) -> tuple[KnowledgeItem, ...]:
        """그 의도의 승인된 기준 답 문구(문서 순서). 3a 자동 답은 이 글만 보낸다."""
        return tuple(i for i in self.items if i.kind == KIND_TEMPLATE and intent in i.intents)

    def template_intents(self) -> tuple[str, ...]:
        """승인된 기준 답 문구가 있는 의도 id(처음 나온 순서) — 모델이 고를 수 있는 목록."""
        seen: dict[str, None] = {}
        for item in self.items:
            if item.kind == KIND_TEMPLATE:
                seen.update(dict.fromkeys(item.intents))
        return tuple(seen)

    def of_kind(self, kind: str) -> tuple[KnowledgeItem, ...]:
        """그 종류의 승인 항목(문서 순서)."""
        return tuple(i for i in self.items if i.kind == kind)

    def get(self, item_id: str) -> Optional[KnowledgeItem]:
        """id 의 승인 항목(없거나 승인 안 됐으면 ``None``)."""
        return next((i for i in self.items if i.item_id == item_id), None)


# ── 개수 · 차이(글 없음) ─────────────────────────────────────────────────
def count_items(document: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """종류 · 상태별 개수 ``{"total": n, "kinds": {kind: {status: n}}}``."""
    kinds: dict[str, dict[str, int]] = {}
    rows = (document or {}).get("items") or []
    for row in rows:
        per = kinds.setdefault(str(row.get("kind")), {})
        per[str(row.get("status"))] = per.get(str(row.get("status")), 0) + 1
    return {"total": len(rows), "kinds": {k: dict(sorted(v.items())) for k, v in sorted(kinds.items())}}


@dataclass(frozen=True)
class KnowledgeDiff:
    """두 문서의 차이 — 개수와 항목 id · 바뀐 칸 이름만(글 · 가격 값 없음)."""

    before: dict[str, Any]
    after: dict[str, Any]
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: dict[str, tuple[str, ...]] = field(default_factory=dict)  # id → 바뀐 칸 이름
    became_live: tuple[str, ...] = ()  # 이번에 승인 상태가 되는 항목(재료에 새로 들어감)
    left_live: tuple[str, ...] = ()  # 재료에서 빠지는 항목(승인 → 초안 · 내림 · 뺌)
    live_changed: tuple[str, ...] = ()  # 승인 그대로 내용이 바뀌는 항목(손님에게 나갈 글이 바뀐다)
    reordered: bool = False

    def has_changes(self) -> bool:
        """차이가 하나라도 있는가."""
        return bool(self.added or self.removed or self.changed or self.reordered)

    def summary(self) -> dict[str, Any]:
        """JSON 한 덩어리(관리자 스크립트 출력)."""
        return {"before": self.before, "after": self.after, "added": list(self.added), "removed": list(self.removed),
                "changed": {k: list(v) for k, v in self.changed.items()}, "became_live": list(self.became_live),
                "left_live": list(self.left_live), "live_changed": list(self.live_changed),
                "reordered": self.reordered}


def diff_documents(before: Optional[Mapping[str, Any]], after: Optional[Mapping[str, Any]]) -> KnowledgeDiff:
    """정본 문서 둘(없으면 ``None``)의 차이."""
    old = {row["id"]: row for row in (before or {}).get("items") or []}
    new = {row["id"]: row for row in (after or {}).get("items") or []}
    changed = {key: tuple(f for f in ITEM_FIELDS if old[key].get(f) != row.get(f))
               for key, row in new.items() if key in old and old[key] != row}
    live_old = {key for key, row in old.items() if row.get("status") == STATUS_APPROVED}
    live_new = {key for key, row in new.items() if row.get("status") == STATUS_APPROVED}
    return KnowledgeDiff(
        before=count_items(before), after=count_items(after),
        added=tuple(key for key in new if key not in old), removed=tuple(key for key in old if key not in new),
        changed=changed, became_live=tuple(key for key in new if key in live_new and key not in live_old),
        left_live=tuple(key for key in old if key in live_old and key not in live_new),
        live_changed=tuple(key for key in changed if key in live_old and key in live_new),
        reordered=[key for key in old if key in new] != [key for key in new if key in old])
