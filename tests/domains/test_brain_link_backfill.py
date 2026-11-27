"""쌓인 지식 한 번 잇기(되채우기 — 설계 글 ``docs/specs/2026-11-26-brain-ontology-linking_SPEC.md`` 7.3 · 사장님 11-26 '뻔한 것은
AI가 바로' · 11-27 "공정 단계만 여쭙게 하고 켜기").

- 미리 돌려 보기는 아무것도 남기지 않고, 수가 넣을 때와 같다(제안 길 관문 · 바로 반영까지 저장점 안에서 돈다).
- 뻔한 잇기만 바로 들어가 'AI 가 배운 것'에 뜨고 지울 수 있다 · 지운 잇기는 다시 넣지 않는다.
- 음성 대조군 — 조건 하나라도 빠지면 올림(⑥ 규칙 잇기 칸 · 꼭 같이는 ②): 확신 mid · 글자 맞춤 없음(계획이 있다고 거짓말) · 이름이
  둘 · 공정 단계 · 수량 표 · 브랜드 다름 · 기준 답 끝 · 패널 끔. 계획의 글자 맞춤 표시는 믿지 않는다(코드가 바로잡는다).
- 코드가 까닭별로 거른다 · 멱등 · 올림 상한 · 한쪽만 · 앞 N 줄 · 종류 고르기 · 운영은 승인 표시 없이 넣지 않는다 · 수만 낸다.
- 사람 근거 둘이 없는 시작 지식의 줄은 버리지 않고 옮기기 묶음 제안으로 ⑥ 칸에 올린다 — 조건 다섯이 다 맞아도 바로 넣지 않는다.

합성 지식 · 합성 계정만(손님 글 · 직원 이름 · 금액 · 회사 지식 글 없음 · 네트워크 0 · 모델 부르기 0).
"""

from __future__ import annotations

import datetime
import importlib.util
import io
import json
import pathlib
import types

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainLink
from foms.services.brain import constants as c
from foms.services.brain import learned
from foms.services.brain.apply import apply_change
from foms.services.brain.inbox import inbox
from foms.services.brain.inbox_bins import card_bin, change_ends
from foms.services.brain.proposals import Proposer, propose_create
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_link, current_object
from foms.services.cs_agent import settings as st
from foms.services.cs_agent.handoff_learn_settings import AUTO_FIELD
from foms.services.cs_agent.handoff_learning_backfill import REASON_HEAD, run_backfill
from foms.services.cs_agent.handoff_learning_gates import AGENT
from models import SystemSetting
from tests.support.brain_support import NOW, create, link as tie, person, values

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "brain_link_backfill.py"
WHEN = datetime.datetime(2026, 11, 27, 9, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
LATER = datetime.datetime(2026, 11, 28, 1, 0)  # 승인 대기 화면을 여는 때(UTC naive)
EVIDENCE = ["case:1", "staff:mgr-1"]  # 서로 다른 사람 둘 — 잇기 제안 근거 관문이 지난다
DOC = {"approved_by": "합성", "approved_at": "2026-10-20"}
DOOR, STEP, TERM, TABLE = "common/bf-door", "process_step/bf-measure", "common/bf-term", "common/bf-table"
FACT, OTHER = "lahom/bf-fact", "lahom/bf-other"
WHY = "합성 글이 그 이름을 그대로 말한다"
MARK = "합성 되채우기 표지"  # 지식 글에만 넣는 표지 — 화면 · 결과에 새지 않는지 본다


def made(admin, key, item_type, name, *, text=None, brand="COMMON", layer="common", evidence=EVIDENCE, **vals):
    """사람이 넣은 지식(근거 — 사람 둘) — 제안 → 반영. 지금 줄."""
    extra = vals.pop("payload", {})
    payload = {"doc_id": key.rsplit("/", 1)[-1].replace("-", "_"), **DOC, **extra} if item_type in c.DOC_TYPES else extra
    change = propose_create(db_session, key=key, brand=brand, layer=layer, item_type=item_type,
                            values=values(name, text=f"{MARK} {text or name}", payload=payload, **vals), reason="합성",
                            proposer=Proposer.user(admin.id), evidence=list(evidence), now=NOW, known="")
    apply_change(db_session, change.id, actor=admin, now=NOW)
    return current_object(db_session, key)


def panel(auto=True):
    db_session.merge(SystemSetting(setting_key=st.SETTINGS_KEY, setting_value={**st.DEFAULTS, AUTO_FIELD: auto}))
    db_session.commit()


def ln(start, kind, to, *, sure="high", glyph=True, why=WHY):
    return {"from": start, "kind": kind, "to": to, "glyph": glyph, "sure": sure, "why": why}


def backfill(*links, apply=True, **kwargs):
    out = run_backfill(db_session, [{"links": list(links)}], now=WHEN, apply=apply, **kwargs)
    db_session.commit()
    assert MARK not in json.dumps(out, ensure_ascii=False) and "합성 여닫이문" not in json.dumps(out, ensure_ascii=False)
    return out


def filed():
    db_session.expire_all()
    return list(db_session.scalars(select(BrainChange).where(
        BrainChange.proposed_by == f"agent:{AGENT}", BrainChange.op == "link_add").order_by(BrainChange.id)))


def links():
    return db_session.scalar(select(func.count()).select_from(BrainLink))


def bin_of(change):
    return card_bin(change.op, change.item_type, change.fields, change.link_kind, **change_ends(change))


@pytest.fixture
def world(app):
    """잇기 대상(제품 · 공정 단계 · 용어 · 규격)과 그 이름을 글에 그대로 말하는 라홈 사실 — 패널 '배운 것 바로 반영' 켬."""
    admin = person(db_session, "bf-admin")
    made(admin, DOOR, "product_line", "합성 여닫이문")
    made(admin, STEP, "process_step", "합성 실측 방문", payload={"erp_stage": "MEASURE"})
    made(admin, TERM, "term", "합성 통 단위")
    made(admin, TABLE, "spec", "합성 통 수 표")
    made(admin, FACT, "fact", "합성 배운 사실", brand="LAHOM", text="합성 여닫이문은 합성 실측 방문 때 합성 통 단위로 잰다")
    db_session.commit()
    panel()
    return admin


# ── 미리 돌려 보기 · 바로 · 'AI 가 배운 것' ─────────────────────────────────
def test_dry_run_leaves_nothing_and_counts_like_apply(world):
    plan = (ln(FACT, "applies_to", DOOR), ln(FACT, "at_step", STEP), ln(FACT, "applies_to", "common/none"))
    before = links()
    dry = backfill(*plan, apply=False)
    assert filed() == [] and links() == before and dry["applied"] is False
    assert (dry["auto_total"], dry["ask_total"], dry["dropped"]) == (1, 1, {"unknown": 1})
    real = backfill(*plan)
    assert {k: v for k, v in real.items() if k != "applied"} == {k: v for k, v in dry.items() if k != "applied"}
    assert real["by_kind"] == {"applies_to": {"auto": 1, "ask": 0}, "at_step": {"auto": 0, "ask": 1}}
    assert (real["by_source_type"], real["ask_why"], real["ask_bins"]) == (
        {"fact": {"auto": 1, "ask": 1}}, {"kind": 1}, {"rules": 1, "content": 0})
    assert real["most_on_one"] == {"from": 2, "to": 1} and real["plan"] == {"files": 1, "links": 3, "same": 0, "clash": 0}
    auto, ask = filed()
    assert (auto.link_kind, auto.status, auto.decided_action, auto.decided_by) == ("applies_to", "applied", "auto_learn", None)
    assert (ask.link_kind, ask.status, bin_of(ask)) == ("at_step", "open", "rules")
    assert ask.reason == f"{REASON_HEAD} — {WHY}" and auto.evidence == EVIDENCE  # 밤 붙이기와 구별되는 까닭 글 · 시작 항목 근거
    assert current_link(db_session, "applies_to", FACT, DOOR).created_by == f"agent:{AGENT}"


def test_an_obvious_link_shows_in_learned_and_undo_keeps_it_out(world):
    backfill(ln(FACT, "applies_to", DOOR))
    (change,) = filed()
    rows = learned.learned_list(db_session, viewer_of(world))["items"]
    assert [(r["kind"], r["state"]) for r in rows if r["id"] == change.id] == [("잇기", "live")]
    learned.undo(db_session, change.id, actor=world, now=NOW)
    db_session.commit()
    assert current_link(db_session, "applies_to", FACT, DOOR) is None
    again = backfill(ln(FACT, "applies_to", DOOR))
    assert (again["auto_total"], again["ask_total"], again["dropped"]) == (0, 0, {"refused_before": 1})


# ── 음성 대조군 — 조건 하나씩 빠뜨리면 바로 넣지 않고 올림 ─────────────────────
def _mid(admin):
    return ln(FACT, "applies_to", DOOR, sure="mid"), "mid", "rules"


def _no_glyph(admin):
    made(admin, OTHER, "fact", "합성 다른 사실", brand="LAHOM", text="합성 문짝은 경첩으로 단다")  # 상대 이름이 글에 없다
    return ln(OTHER, "applies_to", DOOR, glyph=True), "no_match", "rules"  # 계획은 있다고 했다(거짓말)


def _twin(admin):
    made(admin, "common/bf-door-twin", "product_line", "합성 여닫이문")  # 같은 이름이 둘
    return ln(FACT, "applies_to", DOOR), "not_unique", "rules"


def _step(admin):
    return ln(FACT, "at_step", STEP), "kind", "rules"  # 공정 단계는 늘 사장님께(11-27)


def _quantity(admin):
    made(admin, "lahom/bf-price", "price_rule", "합성 통 값 규칙", brand="LAHOM", text="합성 통 수 표를 따른다",
         checked_at="2026-10-20")
    return ln("lahom/bf-price", "quantity_from", TABLE), "kind", "rules"  # 수량 정본


def _requires(admin):
    made(admin, "lahom/bf-rule", "build_rule", "합성 제작 조건", brand="LAHOM", text="합성 여닫이문과 꼭 같이 만든다")
    return ln("lahom/bf-rule", "requires", DOOR), "kind", "content"  # 꼭 같이 — ② 한 장씩


def _brand(admin):
    made(admin, "haud/bf-door", "product_line", "합성 하우드 문짝", brand="HAUD")
    made(admin, OTHER, "fact", "합성 다른 사실", brand="LAHOM", text="합성 하우드 문짝은 경첩으로 단다")
    return ln(OTHER, "applies_to", "haud/bf-door"), "brand", "rules"


def _owner_end(admin):
    made(admin, "lahom/bf-tpl", "template", "합성 기준 답", brand="LAHOM", layer="cs", text="합성 통 단위로 안내한다",
         payload={"intents": ["hours"]})
    return ln("lahom/bf-tpl", "uses", TERM), "owner_item", "rules"  # 기준 답 끝


def _panel_off(admin):
    panel(auto=False)
    return ln(FACT, "applies_to", DOOR), "auto_off", "rules"


@pytest.mark.parametrize("setup", [_mid, _no_glyph, _twin, _step, _quantity, _requires, _brand, _owner_end, _panel_off])
def test_each_missing_condition_asks_instead(world, setup):
    line, why, bin_name = setup(world)
    db_session.commit()
    out = backfill(line)
    assert (out["auto_total"], out["ask_total"], out["ask_why"], out["dropped"]) == (0, 1, {why: 1}, {})
    (change,) = filed()
    assert (change.status, change.link_kind, change.link_to, bin_of(change)) == ("open", line["kind"], line["to"], bin_name)
    assert current_link(db_session, line["kind"], line["from"], line["to"]) is None


def test_the_code_measures_the_glyph_itself(world):
    made(world, OTHER, "fact", "합성 다른 사실", brand="LAHOM", text="합성 문짝은 경첩으로 단다")
    db_session.commit()
    out = backfill(ln(FACT, "applies_to", DOOR, glyph=False), ln(OTHER, "applies_to", DOOR, glyph=True))
    assert out["glyph_fixed"] == {"plan_yes_code_no": 1, "plan_no_code_yes": 1}
    assert (out["auto_total"], out["ask_total"], out["ask_why"]) == (1, 1, {"no_match": 1})  # 코드가 잰 대로 가른다
    assert current_link(db_session, "applies_to", FACT, DOOR) is not None
    assert current_link(db_session, "applies_to", OTHER, DOOR) is None


# ── 코드가 거른다 ─────────────────────────────────────────────────────────
def test_the_code_drops_bad_lines_and_counts_each_reason(world):
    create(db_session, world, "common/bf-old", name="합성 옛 문", status="retired")
    made(world, "lahom/bf-rule", "build_rule", "합성 제작 조건", brand="LAHOM", text="합성 규칙 글")
    tie(db_session, world, "excludes", "lahom/bf-rule", DOOR)
    tie(db_session, world, "uses", FACT, TERM)
    db_session.commit()
    phone = "010-" + "1234-" + "5678"
    out = backfill(
        {"from": FACT, "kind": "broader", "to": DOOR, "sure": "high", "why": WHY}, ln(FACT, "applies_to", DOOR, sure="low"),
        "합성 꼴 아닌 줄", ln(FACT, "applies_to", DOOR, why=f"합성 연락처 {phone}"), ln("lahom/none", "applies_to", DOOR),
        ln(FACT, "applies_to", FACT), ln(FACT, "applies_to", "common/none"), ln(FACT, "applies_to", "common/bf-old"),
        ln(FACT, "applies_to", TERM), ln(FACT, "uses", TERM), ln("lahom/bf-rule", "requires", DOOR),
        ln(FACT, "applies_to", DOOR), ln(FACT, "applies_to", DOOR), show_dropped=True)
    assert out["dropped"] == {"exists": 1, "form": 3, "mask": 1, "not_allowed": 1, "repeat": 1, "retired": 1, "rule": 1,
                              "self": 1, "source": 1, "unknown": 1}
    assert (out["auto_total"], out["ask_total"]) == (1, 0)
    assert [d["code"] for d in out["dropped_keys"]][:3] == ["form", "form", "form"] and "from" not in out["dropped_keys"][2]
    assert {"n": 11, "code": "rule", "from": "lahom/bf-rule", "kind": "requires", "to": DOOR} in out["dropped_keys"]
    assert "dropped_keys" not in backfill(ln(FACT, "applies_to", DOOR), apply=False)  # 키는 물을 때만


# ── 사람 근거 없는 시작 지식 — 버리지 않고 옮기기 묶음으로 사장님께 ─────────────
BARE = "lahom/bf-bare"


def bare(admin):
    """사람이 바로 만든 사실(근거 없음 — 옮기기 · 사장님 승인 · 직접 고침으로 생긴 판과 같다)."""
    create(db_session, admin, BARE, item_type="fact", brand="LAHOM", name="합성 근거 없는 사실",
           text=f"{MARK} 합성 여닫이문은 합성 실측 방문 때 잰다", payload={"doc_id": "bf_bare", **DOC})
    db_session.commit()


def imported():
    db_session.expire_all()
    return list(db_session.scalars(select(BrainChange).where(
        BrainChange.proposed_by == "import", BrainChange.op == "link_add").order_by(BrainChange.id)))


def test_a_source_without_people_evidence_goes_to_the_owner_and_never_in_at_once(world):
    bare(world)
    plan = (ln(BARE, "applies_to", DOOR), ln(BARE, "at_step", STEP))  # 앞 줄은 바로 넣는 조건 다섯이 다 맞는다
    dry = backfill(*plan, apply=False)
    assert imported() == [] and filed() == []
    assert (dry["auto_total"], dry["ask_total"], dry["ask_why"], dry["ask_bins"], dry["dropped"]) == (
        0, 2, {"no_evidence": 2}, {"rules": 2, "content": 0}, {})
    real = backfill(*plan)
    assert {k: v for k, v in real.items() if k != "applied"} == {k: v for k, v in dry.items() if k != "applied"}
    rows = imported()
    assert [(r.link_kind, r.status, r.proposed_by, bin_of(r)) for r in rows] == [
        ("applies_to", "open", "import", "rules"), ("at_step", "open", "import", "rules")]
    assert all(r.reason == f"{REASON_HEAD} — {WHY}" for r in rows) and filed() == []  # 에이전트 제안이 아니다
    assert current_link(db_session, "applies_to", BARE, DOOR) is None  # 조건 다섯이 맞아도 바로 들어가지 않는다
    cards = {card["main"]["id"]: card for card in inbox(db_session, viewer_of(world), now=LATER)["cards"]}
    assert [(cards[r.id]["bin"], cards[r.id]["main"]["bulk_ok"]) for r in rows] == [("rules", True), ("rules", True)]
    again = backfill(*plan)
    assert (again["ask_total"], again["dropped"], len(imported())) == (0, {"open": 2}, 2)  # 멱등


def test_owner_proposals_follow_only_and_max_ask(world):
    bare(world)
    plan = (ln(BARE, "applies_to", DOOR), ln(BARE, "at_step", STEP), ln(FACT, "applies_to", DOOR))
    held = backfill(*plan, only="auto")
    assert (held["auto_total"], held["only_held"], imported()) == (1, {"auto": 0, "ask": 2}, [])
    capped = backfill(*plan, max_ask=1)
    assert (capped["ask_total"], capped["ask_left"], capped["ask_why"], len(imported())) == (1, 1, {"no_evidence": 1}, 1)


# ── 멱등 · 올림 상한 · 한쪽만 · 앞 N 줄 · 종류 ──────────────────────────────
def _three_facts(admin):
    for n in range(3):
        made(admin, f"lahom/bf-step-{n}", "fact", f"합성 단계 사실 {n}", brand="LAHOM", text="합성 실측 방문 때 잰다")
    db_session.commit()
    return [ln(f"lahom/bf-step-{n}", "at_step", STEP) for n in range(3)]


def test_rerun_files_nothing_twice(world):
    plan = (ln(FACT, "applies_to", DOOR), ln(FACT, "at_step", STEP))
    first = backfill(*plan)
    count, made_links = len(filed()), links()
    again = backfill(*plan)
    assert (first["auto_total"], first["ask_total"]) == (1, 1)
    assert (again["auto_total"], again["ask_total"], again["dropped"]) == (0, 0, {"exists": 1, "open": 1})
    assert len(filed()) == count and links() == made_links


def test_max_ask_leaves_the_rest_for_the_next_run(world):
    plan = _three_facts(world)
    out = backfill(*plan, max_ask=2)
    assert (out["ask_total"], out["ask_left"], len(filed())) == (2, 1, 2)
    nxt = backfill(*plan, max_ask=2)
    assert (nxt["ask_total"], nxt["ask_left"], nxt["dropped"], len(filed())) == (1, 0, {"open": 2}, 3)


def test_only_limit_and_kinds_pick_a_small_start(world):
    plan = [ln(FACT, "applies_to", DOOR), *_three_facts(world)]
    only_auto = backfill(*plan, only="auto")
    assert (only_auto["auto_total"], only_auto["ask_total"], only_auto["only_held"]) == (1, 0, {"auto": 0, "ask": 3})
    limited = backfill(*plan, only="ask", limit=2)
    assert (limited["picked"], limited["ask_total"], limited["dropped"]) == (2, 1, {"exists": 1})
    kinds = backfill(*plan, kinds={"at_step"})
    assert (kinds["kinds_skipped"], kinds["picked"], kinds["ask_total"], kinds["dropped"]) == (1, 3, 2, {"open": 1})


# ── 관리자 스크립트 ──────────────────────────────────────────────────────
def load_script():
    spec = importlib.util.spec_from_file_location("brain_link_backfill_ut", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(script, capsys, *argv):
    code = script.run(list(argv))
    printed = capsys.readouterr().out
    assert MARK not in printed and "합성 여닫이문" not in printed and WHY not in printed  # 글 · 이름은 내지 않는다
    return code, json.loads(printed)


def write(tmp_path, name, document):
    path = tmp_path / name
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_script_dry_run_then_apply_with_two_plan_files(world, capsys, monkeypatch, tmp_path):
    script = load_script()
    monkeypatch.setattr(script, "resolve_environment", lambda: "local")
    first = write(tmp_path, "synth_a.json", {"links": [ln(FACT, "applies_to", DOOR)], "same": [["a", "b"]], "clash": []})
    second = write(tmp_path, "synth_b.json", {"links": [ln(FACT, "at_step", STEP)], "clash": [["c", "d"], ["e", "f"]]})
    code, out = run_script(script, capsys, "--plan", first, "--plan", second)
    assert code == 0 and out["applied"] is False and (out["auto_total"], out["ask_total"]) == (1, 1) and filed() == []
    assert out["plan"] == {"files": 2, "links": 2, "same": 1, "clash": 2} and out["environment"] == "local"
    code, out = run_script(script, capsys, "--plan", first, "--plan", second, "--apply", "--only", "auto")
    assert code == 0 and out["applied"] is True and [c.link_kind for c in filed()] == ["applies_to"]
    code, out = run_script(script, capsys, "--plan", str(tmp_path / "none.json"))
    assert (code, out["error"]) == (1, "PLAN_UNREADABLE")
    code, out = run_script(script, capsys, "--plan", first, "--kinds", "applies_to,made_up")
    assert (code, out["error"]) == (1, "KINDS_UNKNOWN")


def test_script_reads_the_plan_from_stdin(world, capsys, monkeypatch):
    script = load_script()
    monkeypatch.setattr(script, "resolve_environment", lambda: "local")
    raw = json.dumps({"links": [ln(FACT, "applies_to", DOOR)]}, ensure_ascii=False).encode("utf-8-sig")
    monkeypatch.setattr(script.sys, "stdin", types.SimpleNamespace(buffer=io.BytesIO(raw)))
    code, out = run_script(script, capsys, "--plan", "-")
    assert code == 0 and out["auto_total"] == 1 and filed() == []
    code, out = run_script(script, capsys, "--plan", "-", "--plan", "-")
    assert (code, out["error"]) == (1, "PLAN_UNREADABLE")


@pytest.mark.parametrize("environment", ["production", "unknown-remote"])
def test_script_refuses_remote_apply_without_owner_approval(world, capsys, monkeypatch, tmp_path, environment):
    script = load_script()
    monkeypatch.setattr(script, "resolve_environment", lambda: environment)
    path = write(tmp_path, "synth_a.json", {"links": [ln(FACT, "applies_to", DOOR)]})
    code, out = run_script(script, capsys, "--plan", path, "--apply")
    assert (code, out["error"], out["environment"]) == (1, "OWNER_APPROVAL_REQUIRED", environment) and filed() == []
    code, out = run_script(script, capsys, "--plan", path)  # 미리 돌려 보기는 막지 않는다(쓰기 0)
    assert code == 0 and out["auto_total"] == 1 and filed() == []
    code, out = run_script(script, capsys, "--plan", path, "--apply", "--i-have-owner-approval")
    assert code == 0 and out["applied"] is True and len(filed()) == 1
