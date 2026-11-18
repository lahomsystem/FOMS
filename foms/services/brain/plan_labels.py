"""자료 계획의 '다른 이름' · '규칙 → 제품 잇기' · '꼭 같이 · 같이 못 함' 칸(설계서 2026-11-12 온톨로지 4.2 · 사장님 D193 ·
D194, 2026-11-13 빈 재료 채우기 B · D203).

계획(저장소 밖 파일 — 낱말 · 키만, 손님 글 없음)을 한 번 뽑아 사장님 승인 뒤 옮기기 묶음(:data:`.proposals.IMPORT_PROPOSER`)
제안으로 넣는다(AI 주 상한 밖 — D130 과 같은 길). 반영하지 않는다.

- ``labels[]`` = ``{"key": 항목 키, "aliases": [다른 이름 …], "why"?}`` → 그 항목 실음 칸의 ``aliases`` 에 **더하기**만 하는
  고침 제안(이름표만 바뀜 → 제안함 ① 표). 이미 있는 이름 · 대표 이름 · 이름과 같은 말은 뺀다. 이름 하나는 한 줄 :data:`MAX_ALIAS`
  자까지, 가림 검사(:func:`foms.services.cs_agent.masking.leak_counts`)가 0 이 아닌 말(이름 · 전화 꼴)은 뺀다. 항목이 아직 없고
  만들기 제안이 열려 있으면 다음 차례(``awaiting_create``).
- ``links[]`` = ``{"from": 시작 키, "to": 끝 키, "kind"?: "applies_to" | "requires" | "excludes", "why"?}`` → 링크 더하기 제안
  (그 밖 종류는 ``not_allowed``). 허용 짝 · 양 끝 · 이미 있음 · 열린 제안 · 맞섬은 :func:`.plan_links.file_link` 가 본다(끝이 승인
  대기면 다음 차례). 끝 유형은 지금 항목(없으면 열린 만들기 제안 · 키 머리)에서 안다.

  - ``applies_to``(규칙 → 제품 라인 · 옵션 — D194)는 제안함 ⑥ 규칙 잇기 표에 든다(:mod:`.inbox_bins`).
  - ``requires`` · ``excludes``(꼭 같이 · 같이 못 함 — 빈 재료 채우기 B · D203: 제작 조건 · 제품 라인 · 옵션 → 제품 라인 · 옵션 ·
    규격)는 상담 AI 가 "그 조합은 안 돼요"라고 말하게 하는 재료라 **② 한 장씩**이다(한꺼번에 승인 안 됨). 같은 계획 안에 같은 두
    항목(어느 방향이든)의 ``requires`` 와 ``excludes`` 가 함께 있으면 어느 쪽이 맞는지 모르니 둘 다 넣지 않는다(``opposed_in_plan``).

'원문에 두 번 이상 그대로 나온 말만'(지어낸 말 막기)은 계획을 만드는 로컬 도구가 원문을 가진 자리에서 본다 — 서버는 원문이 없다.
세는 까닭은 영어 짧은 코드, 글 · 이름은 세지도 싣지도 않는다.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from foms.services.brain.constants import KEY_RE, OP_UPDATE
from foms.services.brain.constants import OPPOSED_KINDS
from foms.services.brain.plan_links import (
    TO_TYPES, Link, Run, decisions_in, end_type, file_one, held, missing_end, open_changes, reason,
)
from foms.services.brain.proposals import IMPORT_PROPOSER, propose_update
from foms.services.brain.store import current_object
from foms.services.cs_agent.masking import leak_counts

__all__ = ["LINK_KINDS", "MAX_ALIAS", "MAX_ALIASES", "TO_TYPES", "file_labels", "file_rule_links"]

LINK_KINDS: tuple[str, ...] = ("applies_to", "requires", "excludes")
MAX_ALIAS, MAX_ALIASES = 40, 12


def _words(value: Any) -> list[str]:
    """다른 이름 목록 — 한 줄 · 상한 · 가림 검사 0 · 겹침 빼고(처음 나온 순서)."""
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for word in value:
        text = " ".join(word.split()) if isinstance(word, str) else ""
        if text and len(text) <= MAX_ALIAS and not any(leak_counts(text).values()) and text not in out:
            out.append(text)
    return out


def file_labels(run: Run, rows: Iterable[Any]) -> None:
    """``labels[]`` — 항목마다 다른 이름 더하기 고침 하나."""
    for row in rows:
        if not isinstance(row, Mapping) or held(run, row):
            continue
        key, words = str(row.get("key") or ""), _words(row.get("aliases"))
        if not KEY_RE.fullmatch(key) or not words:
            run.skipped["shape"] += 1
            continue
        cur = current_object(run.session, key)
        if cur is None:
            missing_end(run, key)
            continue
        payload = dict(cur.payload or {})
        old = [w for w in payload.get("aliases") or [] if isinstance(w, str)]
        taken = {cur.name, payload.get("pref_label"), *old}
        add = [w for w in words if w not in taken]
        if not add:
            run.skipped["same"] += 1
            continue
        after = {"payload": {**payload, "aliases": [*old, *add][:MAX_ALIASES]}}
        if any((c.fields or {}).get("payload", {}).get("after") == after["payload"]
               for c in open_changes(run.session, OP_UPDATE, key)):
            run.skipped["open_proposal"] += 1
            continue
        file_one(run, "update:labels", lambda: propose_update(
            run.session, key=key, base_version=cur.version, after=after,
            reason=reason("손님이 부르는 다른 이름을 붙여요", decisions_in(row.get("why"))), proposer=IMPORT_PROPOSER,
            evidence=[run.ref(f"labels/{key}")], now=run.now, known=run.known))


def _row_ends(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """링크 줄 → (종류, 시작 키, 끝 키)."""
    return str(row.get("kind") or "applies_to"), str(row.get("from") or ""), str(row.get("to") or "")


def _clashing_pairs(rows: list[Any]) -> set[frozenset[str]]:
    """같은 계획 안에서 맞서는 종류(필요 ↔ 제외)가 함께 걸린 두 항목(방향 없음)."""
    kinds: dict[frozenset[str], set[str]] = {}
    for row in rows:
        if isinstance(row, Mapping):
            kind, from_key, to_key = _row_ends(row)
            if kind in OPPOSED_KINDS:
                kinds.setdefault(frozenset((from_key, to_key)), set()).add(kind)
    return {pair for pair, found in kinds.items() if len(found) > 1}


def file_rule_links(run: Run, rows: Iterable[Any]) -> None:
    """``links[]`` — 규칙 → 제품 ``applies_to`` · 꼭 같이 · 같이 못 함을 링크 목록에 모은다(넣기는 :func:`.plan_links.file_link`)."""
    rows = list(rows)
    clashing = _clashing_pairs(rows)
    for row in rows:
        if not isinstance(row, Mapping) or held(run, row):
            continue
        kind, from_key, to_key = _row_ends(row)
        if kind not in LINK_KINDS:
            run.skipped["not_allowed"] += 1
            continue
        if not KEY_RE.fullmatch(from_key) or not KEY_RE.fullmatch(to_key):
            run.skipped["shape"] += 1
            continue
        if kind in OPPOSED_KINDS and frozenset((from_key, to_key)) in clashing:
            run.skipped["opposed_in_plan"] += 1
            continue
        source = current_object(run.session, from_key)
        if source is None:
            missing_end(run, from_key)
            continue
        decisions = decisions_in(row.get("why"), "D203" if kind in OPPOSED_KINDS else "")
        run.links.append(Link(kind, from_key, source.item_type, to_key, end_type(run, to_key),
                              ref_id=f"links/{from_key}>{to_key}", decisions=decisions))
