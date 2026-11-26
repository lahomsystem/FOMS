"""밤 배우기 끝 이어 붙이기 — 그 밤 새로 배우거나 고친 지식을 이미 있는 회사 지식에 잇는다(설계 글
``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 7.1 · 7.2 · 사장님 11-26 '뻔한 것은 AI가 바로').

**도는 때**: 밤 배우기(:func:`.handoff_learning.run_handoff_learning`)의 바퀴 끝에서 부른다(:func:`attach_night`). 그 밤 사례
읽기가 끝났을 때만(그 밤을 닫음 · 부르기 횟수 상한 · 창 마지막 바퀴 — :func:`reading_done`, 다른 부르기가 도는 중이면 기다림)
바퀴마다 한 번, 한 밤 패널 '이어 붙이기 한 밤 횟수'까지 부른다. 횟수 · 잠깐 잠금 · 보낸 지식 표지는 설정 표 한 줄
(:data:`STORE_KEY`)에 둔다 — 15분 바퀴 · 재배포 · 두 컨테이너가 겹쳐도 상한이 지켜진다(부르기 전에 횟수를 먼저 남긴다).
패널 '밤 배우기 끝에 지식 이어 붙이기'가 꺼져 있으면 표를 읽지도 쓰지도 않고 모델도 부르지 않는다(처음 끔).

1. **이을 지식**: 그 KST 날 0시 뒤 지금 판이 생긴 살아 있는 지식 가운데 만든 이가 학습 에이전트(넘긴 상담 배우기 · 사진 학습)인
   사실 · 정책 · 상황 · 제작 조건(:data:`SOURCE_TYPES`) — 그 밤 이미 보낸 판은 빼고, 나가는 잇기가 없는 것부터 새 것부터
   :data:`MAX_ITEMS` 개.
2. **후보 둘을 겹친다**: (가) **글자 맞춤**(:func:`glyph_matches` — 재는 자 :func:`foms.services.brain.quality.mention_pairs` 와
   같은 이름 기준: 이름 · 한글 이름 · 다른 이름, 띄어쓰기 뺀 꼴 3자 이상) — 그 이름이 가리키는 살아 있는 지식이 하나뿐인지도 센다.
   (나) **AI**(:mod:`.handoff_learning_link_prompt` — 밤 배우기의 싼 쪽 모델 · 같은 캐시 앞부분) — 잇기 종류 · 대상 키 · 근거 한 줄 +
   같은 내용 후보 · 어긋나는 후보.
3. **코드가 거른다**(까닭별로 센다): 모르는 키 · 은퇴(기간 끝남 포함) · 자기 자신 · 이미 있는 잇기 · 허용 짝 밖 · 링크 제약 ·
   열린 같은 안 · 사장님이 거절했거나 'AI 가 배운 것'에서 지운 같은 잇기.
4. **넣는 길**(:func:`auto_block` — 7.2 조건 다섯이 모두 맞을 때만 바로): ① 글자 맞춤과 AI 가 같은 대상 ② 그 이름이 가리키는 지식이
   하나뿐 ③ 종류가 :data:`foms.services.brain.apply.AUTO_LINK_KINDS` 이고 허용 짝 ④ 양 끝 모두가 보는 지식 · 같은 브랜드(또는 한쪽
   공통) ⑤ 양 끝 어느 쪽도 사장님 결정 · 기준 답이 아님 — 그리고 패널 '배운 것 바로 반영'이 켜져 있을 때(:func:`.handoff_learning
   .auto_learn`). 바로 넣기는 제안 → 바로 반영 길(``apply`` 의 ``auto``)이라 'AI 가 배운 것'에 뜨고 거기서 뺀다. 나머지(AI 만 말한
   것 · 글자 맞춤만 있는 것 — 종류가 하나로 정해질 때만 · 금액 · 수량 · 꼭 같이 · 같이 안 됨 · 브랜드를 넘는 것)는 열린 제안으로만
   (``agent:cs_handoff_learning`` — 주 상한 밖, 승인 대기 ⑥ 규칙 잇기 칸 또는 ② 한 장씩).
5. **같은 내용 · 어긋남 후보**는 잇지 않는다(합치기는 늘 사장님) — 수만 센다.

로그 · 결과에는 숫자 · 코드만 싣는다(글 · 이름 · 키 없음).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.persistence.brain.models import BrainChange, BrainLink, BrainObject
from foms.services.brain import quality
from foms.services.brain.apply import AUTO_LINK_KINDS
from foms.services.brain.constants import (
    BRAND_COMMON, CHANGE_APPLIED, CHANGE_OPEN, CHANGE_REJECTED, IDENTITY_TYPES, MAX_EVIDENCE, OP_LINK_ADD, SCOPE_ALL,
    STATUS_ACTIVE, external_type, link_allowed,
)
from foms.services.brain.errors import BrainError as BrainStoreError
from foms.services.brain.errors import BrainLinkRuleError
from foms.services.brain.gates import FAIL, text_gates
from foms.services.brain.labels import norm
from foms.services.brain.link_rules import check_link_rules
from foms.services.brain.proposals import Proposer, propose_link
from foms.services.brain.store import current_link, current_object, in_force, is_current, kst_day
from foms.services.cs_agent import handoff_learning_link_prompt as lp
from foms.services.cs_agent import handoff_learning_prompt as hp
from foms.services.cs_agent import photo_learning
from foms.services.cs_agent import photo_learning_prompt as onto_prompt
from foms.services.cs_agent.brain_spend import BrainError
from foms.services.cs_agent.channel_read import naive_utc
from foms.services.cs_agent.handoff_learn_settings import LINK_CALLS_FIELD, LINK_FIELD
from foms.services.cs_agent.handoff_learning_cache import night_lists
from foms.services.cs_agent.handoff_learning_gates import AGENT, UNDONE_ACTION, _store_code, apply_now
from foms.services.cs_agent.handoff_learning_pick import EASY, model_for
from foms.services.cs_agent.learning_brain import call_learning
from foms.services.cs_agent.state import KST
from models import SystemSetting

logger = logging.getLogger(__name__)

__all__ = [
    "LEARN_AGENTS", "MAX_ITEMS", "SOURCE_TYPES", "STORE_KEY", "attach_night", "auto_block", "glyph_matches",
    "label_owners", "night_sources", "reading_done", "run_link",
]

STORE_KEY = "cs_agent_handoff_learn_link"
#: 한 번 부르기에 보내는 이을 지식 수 · 그 밤 보낸 판 표지 상한 · 한 지식에서 받는 AI 잇기 수 · 한 번 부르기에 넣는 잇기 수.
MAX_ITEMS, MAX_SENT, MAX_LINKS, MAX_FILED, MAX_SCAN, MAX_CANDIDATES = 20, 400, 10, 60, 500, 10
LEASE, LAST_TICK = datetime.timedelta(minutes=10), datetime.timedelta(minutes=15)
DEFAULT_CALLS = 3
#: 이을 지식의 만든 이 — 넘긴 상담 배우기 · 사진 학습(학습 에이전트가 쓰는 지식 유형만 — 제품 · 옵션의 다른 이름 고침은 빼고).
LEARN_AGENTS: tuple[str, ...] = tuple(Proposer.agent_named(name).name for name in (AGENT, photo_learning.AGENT))
SOURCE_TYPES: tuple[str, ...] = ("fact", "policy", "situation", "build_rule")
#: 7.2 조건 5 — 바로 잇지 않는 끝 유형(반영 동작 :data:`foms.services.brain.apply.AUTO_LINK_HELD_ENDS` 가 한 번 더 막는다).
OWNER_ENDS: frozenset[str] = frozenset({"owner_decision", "template"})
REASON_HEAD = "밤 배우기 이어 붙이기"
GLYPH_REASON = f"{REASON_HEAD} — 글에 그 지식 이름이 그대로 있어요(AI 는 잇지 않았어요)"


# ── 그 밤 표(SystemSetting 한 줄) ────────────────────────────────────────
def _doc(row: Any, day: str) -> dict[str, Any]:
    """저장 값 → 그 날 ``{"day", "calls", "lease", "sent", "done"}`` 사본(다른 날 · 틀린 칸은 새 날 값)."""
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    if value.get("day") != day:
        return {"day": day, "calls": 0, "lease": None, "sent": [], "done": False}
    calls = value.get("calls") if isinstance(value.get("calls"), int) and not isinstance(value.get("calls"), bool) else 0
    sent = [s for s in value.get("sent") or [] if isinstance(s, str)] if isinstance(value.get("sent"), list) else []
    lease = value.get("lease") if isinstance(value.get("lease"), str) else None
    return {"day": day, "calls": max(0, calls), "lease": lease, "sent": sent, "done": value.get("done") is True}


def _leased(doc: dict[str, Any], now: datetime.datetime) -> bool:
    """다른 붙이기 부르기가 아직 도는가."""
    try:
        return doc["lease"] is not None and datetime.datetime.fromisoformat(doc["lease"]) > now
    except ValueError:
        return False


def _locked(session: Any) -> Any:
    """표 줄을 잠가 읽는다(없으면 먼저 만들어 커밋 — 두 컨테이너가 같이 만들면 하나만 남는다)."""
    if session.get(SystemSetting, STORE_KEY) is None:
        session.add(SystemSetting(setting_key=STORE_KEY, setting_value={},
                                  description="AI 상담팀원 밤 배우기 끝 이어 붙이기 — 그 밤 부른 횟수 · 보낸 지식"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return session.get(SystemSetting, STORE_KEY, populate_existing=True, with_for_update=True)


def _put(row: Any, doc: dict[str, Any]) -> None:
    row.setting_value = doc
    flag_modified(row, "setting_value")


def _claim(session: Any, day: str, now: datetime.datetime, cap: int, marks: Sequence[str]) -> Optional[int]:
    """한 번 더 불러도 되면 횟수 · 잠깐 잠금을 남기고(커밋) 그 밤 몇 번째인지 — 상한 · 닫음 · 다른 부르기 중 · 고른 지식을 그 사이
    다른 쪽이 보냈으면 ``None``."""
    row = _locked(session)
    doc = _doc(row, day)
    if doc["done"] or doc["calls"] >= cap or _leased(doc, now) or set(marks) & set(doc["sent"]):
        session.rollback()
        return None
    _put(row, {**doc, "calls": doc["calls"] + 1, "lease": (now + LEASE).isoformat()})
    session.commit()
    return doc["calls"] + 1


def _finish(session: Any, day: str, marks: Sequence[str], *, done: bool) -> None:
    """잠금을 풀고 보낸 판 표지를 남긴다(커밋). ``done`` 이면 그 밤 붙이기를 닫는다(부르기 실패 · 돈 상한)."""
    row = _locked(session)
    doc = _doc(row, day)
    _put(row, {**doc, "sent": list(dict.fromkeys([*doc["sent"], *marks]))[-MAX_SENT:], "lease": None,
               "done": doc["done"] or done})
    session.commit()


def _cap(cfg: Any) -> int:
    """패널 '이어 붙이기 한 밤 횟수'."""
    value = cfg.get(LINK_CALLS_FIELD)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else DEFAULT_CALLS


def reading_done(session: Any, day: str, now: datetime.datetime) -> bool:
    """그 밤 사례 읽기가 끝났나 — 그 밤을 닫았거나 · 부르기 횟수 상한에 닿았거나 · 창 마지막 바퀴이고, 밤 배우기 부르기가 도는 중이
    아님(:mod:`.handoff_learning` 의 날 표)."""
    from foms.services.cs_agent import handoff_learning as hl  # 돌려 부르기 막기 — 그 모듈이 이 모듈을 부른다

    doc = hl._doc(session.get(SystemSetting, hl.STORE_KEY, populate_existing=True))  # noqa: SLF001 — 같은 날 표
    if hl._leased(doc, now):  # noqa: SLF001
        return False
    local = now.astimezone(KST)
    end = local.replace(hour=hl.WINDOW_HOURS[1], minute=0, second=0, microsecond=0)
    return day in doc["days"] or doc["runs"].get(day, 0) >= hl.MAX_RUNS or end - local <= LAST_TICK


# ── 이을 지식 · 글자 맞춤 ─────────────────────────────────────────────────
def _mark(row: Any) -> str:
    return f"{row.item_key}@{row.version}"


def _day_start(day: str) -> datetime.datetime:
    """KST 날 0시(UTC naive — 판 기록 시각과 같은 꼴)."""
    return datetime.datetime.combine(datetime.date.fromisoformat(day), datetime.time()) - datetime.timedelta(hours=9)


def night_sources(session: Any, day: str, sent: frozenset[str]) -> list[Any]:
    """이을 지식(모듈 설명 1) — 나가는 잇기가 없는 것 먼저, 그 안은 새 것부터."""
    rows = [row for row in session.scalars(
        select(BrainObject).where(is_current(BrainObject), BrainObject.status == STATUS_ACTIVE,
                                  BrainObject.created_by.in_(LEARN_AGENTS), BrainObject.item_type.in_(SOURCE_TYPES),
                                  BrainObject.recorded_at >= _day_start(day))
        .order_by(BrainObject.recorded_at.desc(), BrainObject.item_key).limit(MAX_SCAN)) if _mark(row) not in sent]
    keys = [row.item_key for row in rows]
    linked = set(session.scalars(select(BrainLink.from_key).where(is_current(BrainLink), BrainLink.from_key.in_(keys))
                                 .distinct())) if keys else set()
    return sorted(rows, key=lambda row: row.item_key in linked)[:MAX_ITEMS]


def label_owners(session: Any, today: datetime.date) -> dict[str, set[str]]:
    """이름(띄어쓰기 뺀 꼴) → 그 이름을 가진 살아 있는 지식 키 — 재는 자와 같은 이름 기준(:func:`.quality._labels`)."""
    owners: dict[str, set[str]] = {}
    rows = session.execute(select(BrainObject.item_key, BrainObject.name, BrainObject.payload).where(
        is_current(BrainObject), BrainObject.status == STATUS_ACTIVE, BrainObject.item_type.in_(IDENTITY_TYPES),
        in_force(BrainObject, today))).all()
    for row in rows:
        for label in quality._labels(row):  # noqa: SLF001 — 재는 자(글이 다른 지식 이름을 말함)와 같은 기준
            owners.setdefault(label, set()).add(row.item_key)
    return owners


def glyph_matches(text: Optional[str], key: str, owners: dict[str, set[str]]) -> dict[str, bool]:
    """그 지식 글에 이름이 글자 그대로 있는 다른 지식 → 그 이름이 가리키는 살아 있는 지식이 하나뿐인가(자기 자신도 센다)."""
    plain = norm(text)
    out: dict[str, bool] = {}
    for label, named in owners.items():
        if label in plain:
            for target in named - {key}:
                out[target] = out.get(target, False) or len(named) == 1
    return out


def auto_block(kind: str, source: Any, target: Any, *, matched: bool, unique: bool) -> Optional[str]:
    """7.2 바로 넣는 조건(모듈 설명 4) — 다 맞으면 ``None``, 아니면 처음 빠진 조건 코드. 허용 짝은 부르는 쪽이 먼저 본다."""
    if kind not in AUTO_LINK_KINDS:
        return "kind"
    if not matched:
        return "no_match"
    if not unique:
        return "not_unique"
    if target is None or source.visibility != SCOPE_ALL or target.visibility != SCOPE_ALL:
        return "scope"
    if source.brand != target.brand and BRAND_COMMON not in (source.brand, target.brand):
        return "brand"
    if {source.item_type, target.item_type} & OWNER_ENDS:
        return "owner_item"
    return None


# ── 거르기 · 넣기 ────────────────────────────────────────────────────────
def _asked(session: Any, kind: str, from_key: str, to_key: str) -> Optional[str]:
    """같은 잇기 안이 열려 있으면 ``open``, 사장님이 거절했거나 'AI 가 배운 것'에서 지웠으면 ``refused_before``."""
    same = and_(BrainChange.op == OP_LINK_ADD, BrainChange.link_kind == kind, BrainChange.link_from == from_key,
                BrainChange.link_to == to_key)
    rows = session.execute(select(BrainChange.status).where(same, or_(
        BrainChange.status.in_((CHANGE_OPEN, CHANGE_REJECTED)),
        and_(BrainChange.status == CHANGE_APPLIED, BrainChange.decided_action == UNDONE_ACTION)))).scalars().all()
    return "open" if CHANGE_OPEN in rows else "refused_before" if rows else None


def _target(session: Any, source: Any, kind: str, key: str, today: datetime.date) -> tuple[Optional[str], Any]:
    """대상 거르기(모듈 설명 3) — (버린 까닭, 대상 지금 줄 — 바깥 정본 자리면 ``None``)."""
    if key == source.item_key:
        return "self", None
    ext = external_type(key)
    row = None if ext is not None else current_object(session, key)
    if ext is None and row is None:
        return "unknown", None
    if row is not None and (row.status != STATUS_ACTIVE or (row.valid_to is not None and row.valid_to < today)):
        return "retired", None
    to_type = ext or row.item_type
    if not link_allowed(source.item_type, kind, to_type):
        return "not_allowed", None
    if current_link(session, kind, source.item_key, key) is not None:
        return "exists", None
    asked = _asked(session, kind, source.item_key, key)
    if asked is not None:
        return asked, None
    try:
        check_link_rules(session, source, kind, key, to_type, today)
    except BrainLinkRuleError:
        return "rule", None
    return None, row


def _only_kind(source: Any, target: Any) -> Optional[str]:
    """글자 맞춤만 있는 짝의 잇기 종류 — 고르기 목록에서 허용 짝이 하나뿐일 때만(아니면 ``None`` — 사장님께도 올리지 않는다)."""
    kinds = [kind for kind in lp.KINDS if link_allowed(source.item_type, kind, target.item_type)]
    return kinds[0] if len(kinds) == 1 else None


def _file(session: Any, source: Any, kind: str, key: str, *, reason: str, evidence: Sequence[str], auto: Any,
          now: datetime.datetime, wanted_auto: bool) -> str:
    """잇기 하나 넣기(안마다 커밋) — ``auto`` (바로 반영됨) · ``proposed`` (열린 제안) · ``auto_blocked`` (바로 못 넣고 열린 채) ·
    제안 길이 막은 까닭 코드."""
    try:
        change = propose_link(session, op=OP_LINK_ADD, kind=kind, from_key=source.item_key, to_key=key, reason=reason,
                              proposer=Proposer.agent_named(AGENT), evidence=list(evidence), now=naive_utc(now))
        session.commit()
    except BrainStoreError as exc:  # 근거 · 바깥 자리 · 거절된 같은 안 · 꼴 — 넣지 않고 센다
        session.rollback()
        return _store_code(exc)
    if not wanted_auto or auto is None:
        return "proposed"
    blocked = apply_now(session, change, auto, now)
    session.commit()
    return blocked or "auto"


def _bump(counts: dict[str, Any], code: str) -> None:
    if code in ("auto", "proposed"):
        counts[code] += 1
        return
    if code == "auto_blocked":
        counts["proposed"] += 1
    counts["dropped"][code] = counts["dropped"].get(code, 0) + 1


def _known(session: Any, keys: Any, own: str) -> int:
    """같은 내용 · 어긋남 후보 가운데 살아 있는 다른 지식 수(키 글만)."""
    wanted = {k.strip() for k in (keys if isinstance(keys, list) else [])[:MAX_CANDIDATES]
              if isinstance(k, str) and k.strip() and k.strip() != own}
    if not wanted:
        return 0
    return len(set(session.scalars(select(BrainObject.item_key).where(
        is_current(BrainObject), BrainObject.status == STATUS_ACTIVE, BrainObject.item_key.in_(sorted(wanted))))))


def _why(value: Any) -> tuple[Optional[str], Optional[str]]:
    """AI 근거 한 줄 → (막힌 까닭, 제안 까닭 글). 개인정보 꼴 · 가림 표시 · 한자가 있으면 넣지 않는다."""
    why = photo_learning._line(value, photo_learning.MAX_WHY)
    if why is None:
        return "form", None
    gates = text_gates([why], "")
    if FAIL in (gates["mask"], gates["hanja"]):
        return "mask", None
    return None, f"{REASON_HEAD} — {why}"[:500]


def _file_all(session: Any, raw: Sequence[dict[str, Any]], by_key: dict[str, Any], matches: dict[str, dict[str, bool]],
              evidence: dict[str, list[str]], *, auto: Any, now: datetime.datetime, today: datetime.date,
              counts: dict[str, Any]) -> None:
    """AI 안 → 거르기 → 넣는 길, 그다음 글자 맞춤만 있는 짝(모듈 설명 3 · 4 · 5)."""
    named: dict[str, set[str]] = {}  # 이을 지식 → AI 가 말한 대상 키(종류 · 꼴과 상관없이 — 글자 맞춤만 갈래에서 뺀다)
    for item in raw:
        source = by_key.get(item.get("key")) if isinstance(item.get("key"), str) else None
        if source is None:
            _bump(counts, "source")
            continue
        counts["same"] += _known(session, item.get("same"), source.item_key)
        counts["clash"] += _known(session, item.get("clash"), source.item_key)
        links = [link for link in item.get("links") or [] if isinstance(link, dict)]
        counts["ai"] += len(links)
        named.setdefault(source.item_key, set()).update(str(link.get("target") or "").strip() for link in links)
        _ai_links(session, source, links, matches.get(source.item_key, {}), evidence[source.item_key], auto=auto,
                  now=now, today=today, counts=counts)
    _glyph_only(session, by_key, matches, named, evidence, auto=auto, now=now, today=today, counts=counts)


def _ai_links(session: Any, source: Any, links: Sequence[dict[str, Any]], found: dict[str, bool], evidence: list[str],
              *, auto: Any, now: datetime.datetime, today: datetime.date, counts: dict[str, Any]) -> None:
    """이을 지식 하나의 AI 잇기 — 꼴 · 겹침 · 근거 글 · 대상 거르기 → 7.2 조건이 다 맞으면 바로, 아니면 제안."""
    for _link in links[MAX_LINKS:]:
        _bump(counts, "cap")
    said: set[tuple[str, str]] = set()
    for link in links[:MAX_LINKS]:
        kind, key = link.get("kind"), str(link.get("target") or "").strip()
        code, reason, target = None, None, None
        if kind not in lp.KINDS or not key:
            code = "form"
        elif (kind, key) in said:
            code = "repeat"
        else:
            said.add((kind, key))
            code, reason = _why(link.get("why"))
        if code is None:
            code, target = _target(session, source, kind, key, today)
        if code is None and counts["auto"] + counts["proposed"] >= MAX_FILED:
            code = "cap"
        if code is None:
            wanted = auto_block(kind, source, target, matched=key in found, unique=found.get(key, False)) is None
            code = _file(session, source, kind, key, reason=str(reason), evidence=evidence, auto=auto, now=now,
                         wanted_auto=wanted)
        _bump(counts, code)


def _glyph_only(session: Any, by_key: dict[str, Any], matches: dict[str, dict[str, bool]], named: dict[str, set[str]],
                evidence: dict[str, list[str]], *, auto: Any, now: datetime.datetime, today: datetime.date,
                counts: dict[str, Any]) -> None:
    """글자 맞춤만 있는 짝(AI 가 그 대상을 말하지 않음) — 이름이 가리키는 지식이 하나뿐이고 종류가 하나로 정해질 때만 제안."""
    for source_key, found in matches.items():
        source = by_key[source_key]
        for key, unique in sorted(found.items()):
            if key in named.get(source_key, set()):
                continue
            target = current_object(session, key)
            kind = _only_kind(source, target) if target is not None else None
            code = "glyph_shared" if not unique else "no_kind" if kind is None else None
            if code is None:
                code, _row = _target(session, source, kind, key, today)
            if code is None and counts["auto"] + counts["proposed"] >= MAX_FILED:
                code = "cap"
            if code is None:  # 글자 맞춤만 있는 것 — AI 가 같은 대상을 말하지 않았으니 늘 사장님께
                code = _file(session, source, kind, key, reason=GLYPH_REASON, evidence=evidence[source_key], auto=auto,
                             now=now, wanted_auto=False)
            _bump(counts, code)


def _evidence(session: Any, rows: Sequence[Any]) -> dict[str, list[str]]:
    """이을 지식마다 그 판을 만든 제안의 근거(사례 · 직원) — 잇기 제안의 근거 관문(서로 다른 사람 둘)이 같은 근거로 지난다."""
    ids = sorted({int(row.change_id) for row in rows if row.change_id is not None})
    found = dict(session.execute(select(BrainChange.id, BrainChange.evidence).where(BrainChange.id.in_(ids))).all()) if ids else {}
    return {row.item_key: [e for e in (found.get(row.change_id) or []) if isinstance(e, str)][:MAX_EVIDENCE]
            for row in rows}


def _attach(session: Any, picked: Sequence[Any], *, cfg: Any, day: str, now: datetime.datetime, client: Any,
            counts: dict[str, Any]) -> None:
    """글자 맞춤 → 두뇌 → 거르기 · 넣기(수는 ``counts`` 에)."""
    from foms.services.cs_agent import handoff_learning as hl  # 돌려 부르기 막기

    today = kst_day(naive_utc(now))
    rows, onto_rows = hp.knowledge_rows(session), onto_prompt.knowledge_rows(session)
    knowledge, ontology = hp.knowledge_lines(rows), onto_prompt.knowledge_lines(onto_rows)
    frozen = night_lists(session, cfg, day, rows, onto_rows)  # 아껴 보내기 켬이면 밤 배우기와 같은 굳힌 목록(같은 캐시 앞부분)
    sources, held = lp.source_lines(picked)
    by_key = {row.item_key: row for row in picked if row.item_key not in held}
    for _key in held:
        _bump(counts, "item_mask")
    counts["items"] = len(by_key)
    if not by_key:
        return
    owners = label_owners(session, today)
    matches = {key: glyph_matches(row.text, key, owners) for key, row in by_key.items()}
    counts["matched"] = sum(len(found) for found in matches.values())
    evidence = _evidence(session, list(by_key.values()))
    model, effort = model_for(EASY)  # 밤 배우기 쉬운 묶음과 같은 모델 · 세기 — 캐시는 모델마다 따로다
    params = lp.build_params(sources, lp.target_lines(lp.target_rows(session, today)), model=model, effort=effort,
                             cfg=cfg, frozen=frozen, knowledge=knowledge, ontology=ontology)
    session.commit()
    called = call_learning(session, params, cfg=cfg, now=now, timeout_s=hl.TIMEOUT_S, client=client)
    counts.update(cache_read=called.tokens.cache_read, cache_write=called.tokens.cache_write)
    if not hp.complete(called.response):  # 출력 상한에 끊김 · 거절 — 넣지 않는다
        counts["halted"] = "incomplete"
        return
    auto = hl.auto_learn(session, cfg)
    session.commit()
    _file_all(session, lp.raw_items(called.response), by_key, matches, evidence, auto=auto, now=now, today=today,
              counts=counts)


def run_link(session: Any, day: str, *, now: datetime.datetime, cfg: Any, client: Any = None) -> dict[str, Any]:
    """붙이기 한 번(모듈 설명). 커밋한다. 숫자 · 코드만 돌려준다 — 안 돌면 ``{"off": 까닭}``."""
    if cfg.get(LINK_FIELD) is not True:
        return {"off": "link_off"}  # 끔 — 표를 읽지도 쓰지도 않는다
    if not reading_done(session, day, now):
        session.rollback()
        return {"off": "reading"}
    cap, doc = _cap(cfg), _doc(session.get(SystemSetting, STORE_KEY, populate_existing=True), day)
    if doc["done"] or doc["calls"] >= cap or _leased(doc, now):
        session.rollback()
        return {"off": "night_done" if not _leased(doc, now) else "busy"}
    picked = night_sources(session, day, frozenset(doc["sent"]))
    if not picked:
        session.rollback()
        return {"off": "no_items"}
    marks = [_mark(row) for row in picked]
    calls = _claim(session, day, now, cap, marks)
    if calls is None:
        return {"off": "busy"}
    counts: dict[str, Any] = {"day": day, "items": 0, "calls": calls, "ai": 0, "matched": 0, "auto": 0, "proposed": 0,
                              "dropped": {}, "same": 0, "clash": 0, "halted": None, "cache_read": 0, "cache_write": 0}
    try:
        _attach(session, picked, cfg=cfg, day=day, now=now, client=client, counts=counts)
    except BrainError as exc:  # 돈 상한 · 부르기 실패 — 넣지 않고 그 밤 붙이기를 닫는다(까닭은 로그에)
        session.rollback()
        counts["halted"] = exc.code
    _finish(session, day, marks if counts["halted"] is None else [], done=counts["halted"] is not None)
    counts["dropped"] = dict(sorted(counts["dropped"].items()))
    logger.info("[CS 붙이기] day=%s items=%d calls=%d ai=%d matched=%d auto=%d proposed=%d dropped=%s same=%d clash=%d "
                "halted=%s cache_read=%d cache_write=%d", day, counts["items"], counts["calls"], counts["ai"],
                counts["matched"], counts["auto"], counts["proposed"], counts["dropped"], counts["same"], counts["clash"],
                counts["halted"], counts["cache_read"], counts["cache_write"])
    return counts


def attach_night(session: Any, day: str, *, now: datetime.datetime, cfg: Any, client: Any = None) -> dict[str, Any]:
    """밤 배우기 바퀴 끝에서 부른다 — 돌았으면 ``{"link": 수}``, 안 돌았으면 빈 dict(밤 배우기 결과 꼴이 예전 그대로)."""
    done = run_link(session, day, now=now, cfg=cfg, client=client)
    return {} if set(done) == {"off"} else {"link": done}
