"""다른 이름 · 규칙 → 제품 잇기 계획 만들기(로컬 전용 — 설계서 2026-11-12 온톨로지 4.2 · 사장님 D193 · D194).

AI 가 가린 상담 · 회사 지식을 읽고 낸 **후보**(저장소 밖 JSON)를 코드로 거르고 자료 계획 꼴(``labels[]`` · ``links[]`` —
:mod:`foms.services.brain.plan_labels`)로 쓴다. 넣기는 운영 스크립트 ``brain_plan_proposals.py --plan`` 이 한다(모의 실행 기본).

거르기(지어낸 말 · 개인정보 · 목록 밖 막기):

- 다른 이름: 키가 허용 목록(``--keys`` 의 ``items``)에 있고, 한 줄 40자 이하, 가림 검사 0, 그 항목의 대표 이름과 다르고, **가린
  질문 원문(``--questions`` JSONL 의 ``question``)에 띄어쓰기를 맞춰 두 번 이상 그대로** 나온 말만. 두 항목이 같은 말을 원하면
  그 말은 둘 다 뺀다(어느 쪽인지 모른다).
- 링크: 시작 키가 규칙 목록(``rules``), 끝 키가 항목 목록(``items``)에 있는 ``applies_to`` 만. 겹침은 하나로.

출력은 계획 파일과 수(까닭별)만 — 낱말 · 글은 화면에 내지 않는다. 사용 예::

    python scripts/maintenance/brain_label_link_plan.py --candidates <후보.json> --questions <qa.jsonl> \\
        --keys <키 목록.json> --out <계획.json>
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from typing import Any, Iterable, Mapping, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)

from foms.services.cs_agent.masking import leak_counts  # noqa: E402

SCHEMA = "label_link_plan/1"
MIN_SEEN, MAX_ALIAS = 2, 40
_SPACE = re.compile(r"\s+")


def squash(text: Any) -> str:
    """띄어쓰기를 모두 지운 글(견주기용)."""
    return _SPACE.sub("", str(text or ""))


def seen_counts(questions: Iterable[str], words: Iterable[str]) -> dict[str, int]:
    """말마다 원문에 나온 질문 수(띄어쓰기 무시 · 한 질문에 여러 번이어도 1)."""
    keys = {word: squash(word) for word in words}
    counts: dict[str, int] = dict.fromkeys(keys, 0)
    for question in questions:
        body = squash(question)
        for word, key in keys.items():
            if key and key in body:
                counts[word] += 1
    return counts


def build_plan(candidates: Mapping[str, Any], questions: list[str], keys: Mapping[str, Any]) -> tuple[dict, dict]:
    """후보 → (계획, 까닭별 수). 글 · 낱말은 수에 싣지 않는다."""
    items = {str(i["key"]): str(i.get("label") or "") for i in keys.get("items") or [] if isinstance(i, Mapping)}
    rules = {str(r["key"]) for r in keys.get("rules") or [] if isinstance(r, Mapping)}
    stats: collections.Counter = collections.Counter()
    wanted: dict[str, list[str]] = collections.defaultdict(list)
    for row in candidates.get("labels") or []:
        key = str((row or {}).get("key") or "")
        if key not in items:
            stats["label_key_unknown"] += 1
            continue
        for raw in (row or {}).get("aliases") or []:
            word = " ".join(str(raw).split())
            if not word or len(word) > MAX_ALIAS or any(leak_counts(word).values()):
                stats["label_shape"] += 1
            elif squash(word) == squash(items[key]):
                stats["label_same_as_name"] += 1
            elif word not in wanted[key]:
                wanted[key].append(word)
    owners = collections.Counter(squash(w) for words in wanted.values() for w in set(words))
    seen = seen_counts(questions, {w for words in wanted.values() for w in words})
    labels = []
    for key, words in wanted.items():
        keep = []
        for word in words:
            if owners[squash(word)] > 1:
                stats["label_two_owners"] += 1
            elif seen[word] < MIN_SEEN:
                stats["label_not_seen_twice"] += 1
            else:
                keep.append(word)
        if keep:
            labels.append({"key": key, "aliases": keep})
            stats["label_words"] += len(keep)
    links, pairs = [], set()
    for row in candidates.get("links") or []:
        start, end = str((row or {}).get("from") or ""), str((row or {}).get("to") or "")
        if start not in rules or end not in items:
            stats["link_key_unknown"] += 1
        elif (start, end) in pairs:
            stats["link_dup"] += 1
        else:
            pairs.add((start, end))
            links.append({"from": start, "to": end, "kind": "applies_to"})
    stats.update(label_items=len(labels), links=len(links))
    return {"schema": SCHEMA, "items": [], "new_items": [], "conflicts": [], "labels": labels, "links": links}, dict(stats)


def _questions(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as handle:
        return [str(json.loads(line).get("question") or "") for line in handle if line.strip()]


def run(argv: Optional[list] = None) -> int:
    """CLI — 계획 파일을 쓰고 수만 낸다."""
    parser = argparse.ArgumentParser(description="build label/link plan from AI candidates (local only)")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--keys", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.candidates, "r", encoding="utf-8") as handle:
        candidates = json.load(handle)
    with open(args.keys, "r", encoding="utf-8") as handle:
        keys = json.load(handle)
    plan, stats = build_plan(candidates, _questions(args.questions), keys)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(plan, handle, ensure_ascii=False, indent=1)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    print(json.dumps({"ok": True, "stats": stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(run())
