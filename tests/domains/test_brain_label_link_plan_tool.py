"""다른 이름 · 규칙 잇기 계획 만들기 도구(로컬 — 설계서 2026-11-12 온톨로지 4.2) — 지어낸 말 · 개인정보 · 목록 밖 거르기.

원문에 두 번 미만 · 대표 이름과 같음 · 전화 꼴 · 두 항목이 같은 말 · 목록 밖 키 · 겹친 링크가 빠지고, 출력은 수만. 합성 글만.
"""

from __future__ import annotations

import importlib.util
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PHONE = "01" + "0" + "5550" + "1234"


def load():
    path = os.path.join(ROOT, "scripts", "maintenance", "brain_label_link_plan.py")
    spec = importlib.util.spec_from_file_location("brain_label_link_plan_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KEYS = {"items": [{"key": "product_line/lahom-1", "label": "합성 제품 하나"}, {"key": "option/3-5", "label": "합성 손잡이"}],
        "rules": [{"key": "common/rule-a"}]}
QUESTIONS = ["합성장 문의요", "합성 장 사이즈", "합성장 색", "손잡이 바 있나요", "손잡이바 길이", "한번만 나온말"]


def test_only_names_seen_twice_and_unique_survive():
    tool = load()
    candidates = {"labels": [
        {"key": "product_line/lahom-1", "aliases": ["합성장", "한번만 나온말", "합성 제품하나", f"전화 {PHONE}", "바"]},
        {"key": "option/3-5", "aliases": ["손잡이 바", "바"]},
        {"key": "product_line/lahom-404", "aliases": ["합성장"]}],
        "links": [{"from": "common/rule-a", "to": "option/3-5"}, {"from": "common/rule-a", "to": "option/3-5"},
                  {"from": "common/rule-x", "to": "option/3-5"}, {"from": "common/rule-a", "to": "option/9-9"}]}
    plan, stats = tool.build_plan(candidates, QUESTIONS, KEYS)
    assert plan["labels"] == [{"key": "product_line/lahom-1", "aliases": ["합성장"]},
                              {"key": "option/3-5", "aliases": ["손잡이 바"]}]  # 띄어쓰기 무시 두 번 이상
    assert plan["links"] == [{"from": "common/rule-a", "to": "option/3-5", "kind": "applies_to"}]
    assert stats["label_not_seen_twice"] == 1 and stats["label_same_as_name"] == 1 and stats["label_shape"] == 1
    assert stats["label_two_owners"] == 2 and stats["label_key_unknown"] == 1  # '바' 는 두 항목 — 둘 다 뺀다
    assert stats["link_dup"] == 1 and stats["link_key_unknown"] == 2


def test_cli_writes_the_plan_and_prints_counts_only(tmp_path, capsys):
    tool = load()
    cand, qs, keys, out = (tmp_path / n for n in ("c.json", "q.jsonl", "k.json", "p.json"))
    cand.write_text(json.dumps({"labels": [{"key": "option/3-5", "aliases": ["손잡이 바"]}]}, ensure_ascii=False),
                    encoding="utf-8")
    qs.write_text("\n".join(json.dumps({"question": q}, ensure_ascii=False) for q in QUESTIONS), encoding="utf-8")
    keys.write_text(json.dumps(KEYS, ensure_ascii=False), encoding="utf-8")
    assert tool.run(["--candidates", str(cand), "--questions", str(qs), "--keys", str(keys), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "손잡이" not in printed and json.loads(printed)["stats"]["label_words"] == 1
    assert json.loads(out.read_text(encoding="utf-8"))["schema"] == "label_link_plan/1"
