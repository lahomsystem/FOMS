"""자료 계획의 '다른 이름' · '규칙 → 제품 잇기' 칸(설계서 2026-11-12 온톨로지 4.2 · 사장님 D193 · D194).

계획(저장소 밖 파일 — 낱말 · 키만, 손님 글 없음)을 한 번 뽑아 사장님 승인 뒤 옮기기 묶음(:data:`.proposals.IMPORT_PROPOSER`)
제안으로 넣는다(AI 주 상한 밖 — D130 과 같은 길). 반영하지 않는다.

- ``labels[]`` = ``{"key": 항목 키, "aliases": [다른 이름 …], "why"?}`` → 그 항목 실음 칸의 ``aliases`` 에 **더하기**만 하는
  고침 제안(이름표만 바뀜 → 제안함 ① 표). 이미 있는 이름 · 대표 이름 · 이름과 같은 말은 뺀다. 이름 하나는 한 줄 :data:`MAX_ALIAS`
  자까지, 가림 검사(:func:`foms.services.cs_agent.masking.leak_counts`)가 0 이 아닌 말(이름 · 전화 꼴)은 뺀다. 항목이 아직 없고
  만들기 제안이 열려 있으면 다음 차례(``awaiting_create``).
- ``links[]`` = ``{"from": 규칙 키, "to": 제품 라인 · 옵션 키, "kind"?: "applies_to", "why"?}`` → ``applies_to`` 링크 더하기 제안만
  (그 밖 종류는 ``not_allowed``). 허용 짝 · 양 끝 · 이미 있음 · 열린 제안은 :func:`.plan_links.file_link` 가 본다(끝이 승인
  대기면 다음 차례). 제안함 ⑥ 규칙 · 제품 잇기 표에 든다(:mod:`.inbox_bins`).

'원문에 두 번 이상 그대로 나온 말만'(지어낸 말 막기)은 계획을 만드는 로컬 도구가 원문을 가진 자리에서 본다 — 서버는 원문이 없다.
세는 까닭은 영어 짧은 코드, 글 · 이름은 세지도 싣지도 않는다.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from foms.services.brain.constants import KEY_RE, OP_UPDATE
from foms.services.brain.plan_links import Link, Run, decisions_in, file_one, held, missing_end, open_changes, reason
from foms.services.brain.proposals import IMPORT_PROPOSER, propose_update
from foms.services.brain.store import current_object
from foms.services.cs_agent.masking import leak_counts

__all__ = ["LINK_KINDS", "MAX_ALIAS", "MAX_ALIASES", "TO_TYPES", "file_labels", "file_rule_links"]

LINK_KINDS: tuple[str, ...] = ("applies_to",)
#: 끝 키 머리 → 유형(계산기에서 만든 제품 라인 · 옵션 키 — :mod:`.catalog_plan`).
TO_TYPES: dict[str, str] = {"product_line/": "product_line", "option/": "option"}
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


def _to_type(key: str) -> Any:
    return next((kind for head, kind in TO_TYPES.items() if key.startswith(head)), None)


def file_rule_links(run: Run, rows: Iterable[Any]) -> None:
    """``links[]`` — 규칙 → 제품 라인 · 옵션 ``applies_to`` 를 링크 목록에 모은다(넣기는 :func:`.plan_links.file_link`)."""
    for row in rows:
        if not isinstance(row, Mapping) or held(run, row):
            continue
        kind = str(row.get("kind") or "applies_to")
        from_key, to_key = str(row.get("from") or ""), str(row.get("to") or "")
        if kind not in LINK_KINDS:
            run.skipped["not_allowed"] += 1
            continue
        if not KEY_RE.fullmatch(from_key) or not KEY_RE.fullmatch(to_key):
            run.skipped["shape"] += 1
            continue
        source = current_object(run.session, from_key)
        if source is None:
            missing_end(run, from_key)
            continue
        run.links.append(Link(kind, from_key, source.item_type, to_key, _to_type(to_key),
                              ref_id=f"links/{from_key}>{to_key}", decisions=decisions_in(row.get("why"))))
