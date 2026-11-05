"""다시 배운 사진 교훈 카드 → 승인 대기 제안(CS AI 상담팀원 설계서 17.11.3 · 사장님 11-06 D174 '새 카드만 승인 대기로').

저장소 밖에서 만든 카드 파일(JSON 배열 — 17.11.2 의 지난 사진 다시 학습 교훈을 브랜드마다 뜻으로 묶은 것)을 **지금 제안 길로만**
넣는다(:func:`.proposals.propose_create` — 제안한 이 ``agent:cs_photo``, 주간 사진 학습과 같은 이름이라 글 · 숫자 · 가림 ·
부딪침 · 근거 관문이 실제로 돈다). 직접 쓰기는 없다 — 승인 대기 카드가 되고, 승인하면 반영 동작이 같은 저장점에서 그 브랜드
지식 문서를 표로 다시 쓴다(:mod:`.doc_sync`).

카드 꼴: ``{"key": "<lahom|haud>/photo-<슬러그>", "brand", "type": "policy|fact", "title"(40자 안), "text"(400자 안),
"support_chats"(근거 상담 수 — 대략), "overlap": "new|same_as:<id>|conflicts:<id>", "note", "people": ["customer:<16진 10자
지문>", …], "about": "<승인 항목 키>"(고를 것)}``. ``evidence``(학습 폴더 교훈 id)는 읽지도 싣지도 않는다.

- ``same_as`` 카드는 넣지 않는다(이미 승인된 항목과 같은 말).
- **보통 카드** = 지식 문서 유형 항목(층은 :data:`.constants.KIND_TYPES`): 키 = 카드 키, 이름 = 슬러그, 한글 이름
  (``payload.pref_label`` — 카드 제목, 지식 문서로는 안 나감) · 글 = 카드 글 · 상태 반영(승인하면 지식 문서 ``approved``) · 문서 id
  ``photo-<슬러그>`` · 꼬리표 ``photo-relearn`` · 근거 파일 ``photo_relearn`` · 승인 칸(:data:`APPROVED_BY` · 넣은 날 — 실제
  승인은 카드 승인, :mod:`.plan_proposals` 와 같은 꼴) · 근거 = 관찰 한 줄(``photo_relearn:<문서 id>``).
- **``about`` 이 있는 카드**(승인된 규칙과 부딪침) = 그 항목에 대한 에이전트 일 ``conflict`` 항목(키
  ``conflict/<브랜드>-photo-<슬러그>`` · 글 맨 앞 :data:`DIFFERS_LINE` · 실음 칸 ``target`` — 반영되면 그 항목이 '확인 필요',
  :mod:`.conflicts`). 승인된 규칙의 글은 건드리지 않는다. 근거에 ``about:<키>`` 를 더해 ③ 질문 카드가 두 글을 나란히 보인다
  (:func:`.inbox.about_items`).
- 근거 = 카드의 ``people``(이미 지문으로 바꾼 손님 — 서로 다른 둘 이상)뿐이다. 상담 id · 직원 번호는 싣지 않는다. 모자라거나 꼴이
  틀리면 넣지 않고 ``evidence`` 로 센다.
- 제목(한글 이름)과 ``note``(제안 까닭에 붙음)는 제안 길의 글 관문 밖이라 여기서 같은 관문을 먼저 본다(숫자는 지식 항목 제목만 —
  에이전트 일 유형은 숫자를 막지 않는 :func:`.proposals._gates` 규칙 그대로).
- **멱등**: 같은 키(또는 같은 문서 id)의 지금 판이 있거나 같은 키 열린 제안이 있으면 건너뛴다. 같은 제안이 거절됐으면
  :mod:`.proposals` 가 막는다(``rejected_before``).
- 결과에는 키 · 수 · 관문 이름만 싣는다(글 없음 — 꼴이 틀린 키도 싣지 않는다).
- **트랜잭션**: 부딪침 판정자(:func:`.ai_gates.default_judge`)의 모델 부르기가 세션을 커밋하므로 저장점 하나로 묶을 수 없다 —
  카드마다 끝을 맺는다. 넣기는 카드마다 커밋, 미리 보기는 카드마다 되돌린다(brain 쓰기 0 — 판정자 돈 줄만 남는다).
"""

from __future__ import annotations

import datetime
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

from sqlalchemy import select

from foms.persistence.brain.models import BrainChange
from foms.services.brain.ai_gates import MIN_SOURCES, people
from foms.services.brain.constants import (
    CHANGE_OPEN, KEY_RE, KIND_TYPES, MAX_REASON, SCOPE_ALL, STATUS_ACTIVE, TYPE_GRADES, TYPE_KINDS,
)
from foms.services.brain.errors import BrainGateError, BrainRejectedError, BrainShapeError, BrainTargetError
from foms.services.brain.gates import FAIL, text_gates
from foms.services.brain.proposals import Proposer, known_text, propose_create
from foms.services.brain.store import current_object, kst_day
from foms.services.brain.template_fix import doc_row
from foms.services.datetime_kst import now_utc_naive

#: 제안한 이 — 주간 사진 학습(:data:`foms.services.cs_agent.photo_learning.AGENT`)과 같은 이름(시험이 맞춘다).
AGENT = "cs_photo"
APPROVED_BY = "D174 사진 다시 학습"  # 지식 문서 승인 칸(실제 승인은 카드 승인)
TAG, SOURCE, REF_PREFIX, ABOUT_PREFIX = "photo-relearn", "photo_relearn", "photo_relearn:", "about:"
DIFFERS_LINE = "승인된 규칙과 다름"
CARD_TYPES: tuple[str, ...] = ("policy", "fact")
CARD_BRANDS: dict[str, str] = {"lahom": "LAHOM", "haud": "HAUD"}
MAX_TITLE, MAX_CARD_TEXT, MAX_NOTE = 40, 400, 300
FILED, SKIPPED, BLOCKED = "filed", "skipped", "blocked"
#: 카드 키 — 문서 id ``photo-<슬러그>`` 가 지식 문서 id 꼴(64자 안)에 들게 슬러그는 58자까지.
_KEY = re.compile(r"(lahom|haud)/photo-([a-z0-9][a-z0-9_.-]{0,57})")
_PERSON = re.compile(r"customer:[0-9a-f]{10}")
_OVERLAP = re.compile(r"new|(?:same_as|conflicts):\S{1,120}")


@dataclass(frozen=True)
class Card:
    """꼴 검사를 지난 카드 하나(글은 repr 에 싣지 않는다)."""

    key: str
    brand: str
    item_type: str
    slug: str
    title: str = ""
    text: str = ""
    support: int = 0
    overlap: str = "new"
    note: Optional[str] = None
    people: tuple[str, ...] = ()
    about: Optional[str] = None

    def __repr__(self) -> str:
        return f"Card(key={self.key!r})"

    @property
    def doc_id(self) -> str:
        """지식 문서 id."""
        return f"photo-{self.slug}"

    @property
    def target_key(self) -> str:
        """넣을 brain 키 — 부딪침 카드는 엇갈림 항목 키."""
        return f"conflict/{self.brand.lower()}-photo-{self.slug}" if self.about else self.key


def _line(value: Any, limit: int) -> Optional[str]:
    """한 줄 글(앞뒤 빈칸 뺌 · 1 ~ 상한 자) — 아니면 ``None``."""
    text = value.strip() if isinstance(value, str) else ""
    return text if text and len(text) <= limit and "\n" not in text else None


def parse_card(raw: Any) -> Optional[Card]:
    """카드 꼴 검사 — 틀리면 ``None``. ``people`` 은 꼴(``customer:`` + 16진 10자)이 모두 맞을 때만 싣는다(아니면 빈 묶음 —
    근거 관문 앞에서 막힌다)."""
    if not isinstance(raw, Mapping):
        return None
    match = _KEY.fullmatch(raw.get("key") or "") if isinstance(raw.get("key"), str) else None
    text = raw.get("text").strip() if isinstance(raw.get("text"), str) else ""
    support, note, about = raw.get("support_chats"), raw.get("note"), raw.get("about")
    if (match is None or raw.get("brand") != match.group(1) or raw.get("type") not in CARD_TYPES
            or _line(raw.get("title"), MAX_TITLE) is None or not text or len(text) > MAX_CARD_TEXT
            or isinstance(support, bool) or not isinstance(support, int) or support < 0
            or not isinstance(raw.get("overlap"), str) or not _OVERLAP.fullmatch(raw["overlap"])
            or not (note is None or (isinstance(note, str) and len(note) <= MAX_NOTE))
            or not (about is None or (isinstance(about, str) and KEY_RE.fullmatch(about)))):
        return None
    given = raw.get("people")
    valid = isinstance(given, list) and all(isinstance(p, str) and _PERSON.fullmatch(p) for p in given)
    return Card(key=match.group(0), brand=CARD_BRANDS[match.group(1)], item_type=raw["type"], slug=match.group(2),
                title=raw["title"].strip(), text=text, support=support, overlap=raw["overlap"],
                note=(" ".join(note.split()) or None) if isinstance(note, str) else None,
                people=tuple(dict.fromkeys(given)) if valid else (), about=about)


def reason_of(card: Card) -> str:
    """제안 까닭 — 사진 + 상담 전체 대화 다시 학습 · 근거 상담 수(대략) · 부딪침이면 그 표시 · 메모(상한 안)."""
    head = f"사진 + 상담 전체 대화 다시 학습 · 근거 상담 약 {card.support}곳"
    line = f"{head} · {DIFFERS_LINE}" if card.about else head
    line = f"{line} — {card.note}" if card.note else line
    return line if len(line) <= MAX_REASON else line[:MAX_REASON - 1] + "…"


def side_gates(card: Card, known: str) -> list[str]:
    """제안 길 관문 밖 글(제목 · 메모)의 떨어진 관문 이름 — 가림 · 한자, 숫자는 지식 항목 제목만."""
    title = text_gates([card.title], known)
    note = text_gates([card.note], "") if card.note else {}
    failed = [name for name, value in title.items() if value == FAIL and not (name == "numbers" and card.about)]
    failed += [name for name, value in note.items() if value == FAIL and name != "numbers"]
    return sorted(set(failed))


def _open_change(session: Any, key: str) -> bool:
    """그 키의 열린 제안이 있나(동작 상관없이)."""
    return session.execute(select(BrainChange.id).where(BrainChange.status == CHANGE_OPEN,
                                                        BrainChange.item_key == key).limit(1)).first() is not None


def _doc_values(card: Card, today: str) -> dict[str, Any]:
    """보통 카드 → 지식 문서 유형 값 칸(:func:`.doc_bridge.doc_item_of` 가 문서 항목으로 바꾼다)."""
    return {"name": card.slug, "text": card.text, "status": STATUS_ACTIVE, "risk_grade": TYPE_GRADES[card.item_type],
            "checked_at": today, "evidence_kind": "observation", "evidence_ref": f"{REF_PREFIX}{card.doc_id}",
            "visibility": SCOPE_ALL,
            "payload": {"doc_id": card.doc_id, "intents": [], "tags": [TAG], "source": SOURCE,
                        "approved_by": APPROVED_BY, "approved_at": today, "pref_label": card.title}}


def _propose(session: Any, card: Card, *, known: str, now: datetime.datetime) -> Optional[str]:
    """제안 하나를 넣는다(flush 만). 부딪침 카드의 다루는 항목이 없으면 그 까닭 코드, 넣었으면 ``None``."""
    common = dict(reason=reason_of(card), proposer=Proposer.agent_named(AGENT), now=now, known=known)
    if card.about is None:
        item_type, layer = KIND_TYPES[TYPE_KINDS[card.item_type]]
        propose_create(session, key=card.key, brand=card.brand, layer=layer, item_type=item_type,
                       values=_doc_values(card, kst_day(now).isoformat()), evidence=list(card.people), **common)
        return None
    target = current_object(session, card.about)
    if target is None:
        return "about_missing"
    values = {"name": card.slug, "text": f"{DIFFERS_LINE}\n{card.text}", "status": STATUS_ACTIVE,
              "visibility": target.visibility, "evidence_kind": "observation",
              "evidence_ref": f"{REF_PREFIX}{card.doc_id}",
              "payload": {"target": target.item_key, "target_version": target.version, "pref_label": card.title}}
    propose_create(session, key=card.target_key, brand=card.brand, layer=target.layer, item_type="conflict",
                   values=values, evidence=[*card.people, f"{ABOUT_PREFIX}{target.item_key}"], **common)
    return None


def file_card(session: Any, raw: Any, *, known: str, now: datetime.datetime,
              seen: set[str]) -> tuple[str, tuple[str, ...]]:
    """카드 하나 → (``filed`` · ``skipped`` · ``blocked``, 까닭 코드 · 관문 이름). 넣으면 flush 만(끝맺음은 부르는 쪽)."""
    card = parse_card(raw)
    if card is None:
        return BLOCKED, ("shape",)
    if card.overlap.startswith("same_as:"):
        return SKIPPED, ("same_as",)
    if card.target_key in seen:
        return SKIPPED, ("duplicate",)
    seen.add(card.target_key)
    if len(people(card.people)) < MIN_SOURCES:
        return BLOCKED, ("evidence",)
    failed = side_gates(card, known)
    if failed:
        return BLOCKED, tuple(failed)
    if current_object(session, card.target_key) is not None or (
            card.about is None and doc_row(session, card.brand, card.doc_id) is not None):
        return SKIPPED, ("existing",)
    if _open_change(session, card.target_key):
        return SKIPPED, ("open_proposal",)
    try:
        missing = _propose(session, card, known=known, now=now)
    except BrainGateError as exc:
        return BLOCKED, tuple(sorted(set(exc.failed)))
    except BrainRejectedError:
        return SKIPPED, ("rejected_before",)
    except BrainShapeError:
        return BLOCKED, ("shape",)
    except BrainTargetError:
        return SKIPPED, ("existing",)
    return (BLOCKED, (missing,)) if missing else (FILED, ())


def _shown_key(raw: Any) -> Optional[str]:
    """결과에 싣는 키 — 카드 키 꼴일 때만(꼴이 틀린 칸에 글이 들어 있어도 내지 않게)."""
    key = raw.get("key") if isinstance(raw, Mapping) else None
    return key if isinstance(key, str) and _KEY.fullmatch(key) else None


def file_cards(session: Any, cards: Sequence[Any], *, apply: bool, now: Optional[datetime.datetime] = None,
               only_keys: Iterable[str] = (), limit: Optional[int] = None) -> dict[str, Any]:
    """카드 파일을 열린 제안으로 넣는다(반영 없음). ``apply`` 가 아니면 카드마다 되돌린다(brain 쓰기 0 — 수는 넣을 때와 같다).

    Args:
        only_keys: 이 카드 키만(스테이징 시험 — 비우면 모두).
        limit: 앞에서부터 이 수만(미리 보기 — 부딪침 판정자 돈을 아낀다).

    Returns:
        ``{"applied", "cards", "filed", "skipped", "blocked", "results": [{"index", "key", "result", "codes"}]}`` —
        글 없음. ``blocked`` 는 관문 이름 · 까닭 코드 → 카드 수.
    """
    now = now or now_utc_naive()
    wanted = set(only_keys)
    chosen = [(i, raw) for i, raw in enumerate(cards) if not wanted or _shown_key(raw) in wanted]
    chosen = chosen[:limit] if limit is not None else chosen
    known = known_text(session)
    seen: set[str] = set()
    counts: dict[str, Counter[str]] = {SKIPPED: Counter(), BLOCKED: Counter()}
    results, filed = [], 0
    for index, raw in chosen:
        committed = False
        try:
            result, codes = file_card(session, raw, known=known, now=now, seen=seen)
            if apply and result == FILED:
                session.commit()
                committed = True
        finally:
            if not committed:  # 미리 보기 · 넘김 · 막힘 · 오류 — 이 카드의 쓰기를 남기지 않는다
                session.rollback()
        filed += result == FILED
        if result != FILED:
            counts[result].update(codes)
        results.append({"index": index, "key": _shown_key(raw), "result": result, "codes": list(codes)})
    return {"applied": bool(apply), "cards": len(chosen), "filed": filed, "skipped": dict(sorted(counts[SKIPPED].items())),
            "blocked": dict(sorted(counts[BLOCKED].items())), "results": results}
