"""다시 배운 사진 교훈 카드 → 승인 대기 제안(CS 설계서 17.11.3 · 사장님 D174) — 미리 보기 쓰기 0 · 넣으면 열린 제안(제안한 이 ·
유형 · 층 · 키 · 근거 = 사람 지문만) · 다시 돌리면 0 · 같은 키 지금 판 · 같은 말(``same_as``) 건너뜀 · 금액 · 전화 · 한자 · 근거
모자람은 관문이 막음 · 부딪침 카드는 다루는 항목에 대한 엇갈림 제안(승인 규칙 글은 그대로) · 승인하면 브랜드 지식 문서에 들어감 ·
스크립트 출력에 글 없음 · 운영 막기.

합성 카드 · 합성 항목 · 가짜 부딪침 판정자만(네트워크 0). 실제 회사 지식 · 손님 글 · 직원 이름 없음. 글 표지 :data:`MARK` 는
결과 · 스크립트 출력 어디에도 나오면 안 된다.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest
from sqlalchemy import func, select

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainObject
from foms.services.brain import doc_bridge, photo_cards
from foms.services.brain.apply import apply_change
from foms.services.brain.conflicts import open_conflict_counts
from foms.services.brain.photo_cards import file_cards
from foms.services.brain.store import current_object
from foms.services.cs_agent import knowledge as kn
from foms.services.cs_agent import photo_learning
from tests.domains.test_cs_photo_read import PHONE
from tests.support.brain_support import NOW, agent_judge, create, person

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "maintenance" / "brain_file_photo_cards.py"
MARK = "보라합성표지"
DOC = {"approved_by": "합성", "approved_at": "2026-10-20"}
PEOPLE = ["customer:" + "a" * 10, "customer:" + "b" * 10]
HANJA = chr(0x5BB6)  # 한자 한 글자(글자 범위는 코드 값으로 — 도구 이스케이프 함정)


def card(slug, *, brand="lahom", kind="policy", text=None, **extra):
    """합성 카드 하나(학습 폴더 교훈 id ``evidence`` 도 실어 둔다 — 넣으면 안 된다)."""
    row = {"key": f"{brand}/photo-{slug}", "brand": brand, "type": kind, "title": f"{MARK} 제목",
           "text": text or f"{MARK} 합성 교훈 글", "support_chats": 3, "overlap": "new", "note": f"{MARK} 합성 메모",
           "people": list(PEOPLE), "evidence": ["learn-lesson-a", "learn-lesson-b"]}
    row.update(extra)
    return row


def cards():
    return [
        card("door-sag"),
        card("film-wrap", kind="fact"),
        card("haud-note", brand="haud", kind="fact"),
        card("same-one", overlap="same_as:lahom/synth-rule"),
        card("exists", kind="fact"),
        card("money", text=f"{MARK} 합성 추가 비용은 {'7' * 5}원"),
        card("phone", text=f"{MARK} 합성 연락처 {PHONE}"),
        card("hanja-title", title=f"{MARK} 제목 {HANJA}"),
        card("lonely", people=PEOPLE[:1]),
        card("raw-ids", people=["chat:12345", "customer:" + "c" * 10]),
        card("rule-differs", overlap="conflicts:synth-rule", about="lahom/synth-rule"),
        card("gone-rule", overlap="conflicts:gone", about="lahom/no-such-rule"),
        {"key": MARK, "text": MARK},
    ]


@pytest.fixture
def admin(app):
    admin = person(db_session, "photo_cards_admin")
    create(db_session, admin, "lahom/synth-rule", item_type="policy", brand="LAHOM", text="합성 승인 규칙 글",
           payload={"doc_id": "synth-rule", **DOC})
    create(db_session, admin, "lahom/photo-exists", item_type="fact", brand="LAHOM",
           payload={"doc_id": "photo-exists", **DOC})
    db_session.commit()
    return admin


def run(rows=None, *, apply=True, **kwargs):
    with agent_judge():
        out = file_cards(db_session, rows if rows is not None else cards(), apply=apply, now=NOW, **kwargs)
    assert MARK not in json.dumps(out, ensure_ascii=False)  # 결과에 글 없음
    return out


def written():
    return tuple(db_session.scalar(select(func.count()).select_from(model)) for model in (BrainObject, BrainChange))


def filed():
    db_session.expire_all()
    return {c.item_key: c for c in db_session.scalars(select(BrainChange).where(
        BrainChange.proposed_by == "agent:cs_photo").order_by(BrainChange.id))}


EXPECTED_SKIPPED = {"existing": 1, "same_as": 1}
EXPECTED_BLOCKED = {"about_missing": 1, "evidence": 2, "hanja": 1, "mask": 1, "numbers": 2, "shape": 1}


def test_agent_name_is_the_weekly_photo_learning_agent():
    assert photo_cards.AGENT == photo_learning.AGENT


def test_preview_writes_nothing_and_counts_like_apply(admin):
    before = written()
    dry = run(apply=False)
    assert written() == before and dry["applied"] is False and dry["filed"] == 4
    assert (dry["skipped"], dry["blocked"]) == (EXPECTED_SKIPPED, EXPECTED_BLOCKED)
    real = run()
    assert {k: v for k, v in real.items() if k != "applied"} == {k: v for k, v in dry.items() if k != "applied"}
    assert written()[1] == before[1] + 4


def test_apply_files_open_agent_proposals_with_people_only_evidence(admin):
    out = run()
    by_key = {r["key"]: (r["result"], r["codes"]) for r in out["results"]}
    assert by_key["lahom/photo-money"] == ("blocked", ["numbers"])
    assert by_key["lahom/photo-phone"] == ("blocked", ["mask", "numbers"])
    assert by_key["lahom/photo-lonely"] == ("blocked", ["evidence"])
    assert by_key[None] == ("blocked", ["shape"])  # 꼴이 틀린 카드는 키도 내지 않는다
    rows = filed()
    assert sorted(rows) == ["conflict/lahom-photo-rule-differs", "haud/photo-haud-note", "lahom/photo-door-sag",
                            "lahom/photo-film-wrap"]
    assert all(c.status == "open" and c.op == "create" for c in rows.values())
    door, wrap, haud = rows["lahom/photo-door-sag"], rows["lahom/photo-film-wrap"], rows["haud/photo-haud-note"]
    assert (door.item_type, door.layer, door.brand, door.grade) == ("policy", "common", "LAHOM", "B")
    assert (wrap.item_type, wrap.layer, wrap.grade, haud.brand) == ("fact", "common", "B_LIGHT", "HAUD")
    assert door.evidence == PEOPLE and not any(c.evidence[:2] != PEOPLE for c in rows.values())
    assert not any("learn-lesson" in e for c in rows.values() for e in c.evidence)  # 학습 폴더 id 는 싣지 않는다
    payload = door.fields["payload"]["after"]
    assert payload["doc_id"] == "photo-door-sag" and payload["tags"] == ["photo-relearn"]
    assert (payload["source"], payload["pref_label"]) == ("photo_relearn", f"{MARK} 제목")
    assert (door.fields["name"]["after"], door.fields["status"]["after"]) == ("door-sag", "active")
    assert door.fields["evidence_kind"]["after"] == "observation" and "confidence" not in door.fields
    assert door.reason.startswith("사진 + 상담 전체 대화 다시 학습 · 근거 상담 약 3곳 — ")
    assert door.gates["evidence"] == "pass" and door.gates["conflict"] == "pass"
    assert current_object(db_session, "lahom/photo-door-sag") is None  # 반영 없음 — 승인 대기


def test_rerun_files_nothing_and_existing_key_is_skipped(admin):
    run()
    before = written()
    again = run()
    assert again["filed"] == 0 and written() == before
    assert again["skipped"] == {**EXPECTED_SKIPPED, "open_proposal": 4}
    assert next(r for r in again["results"] if r["key"] == "lahom/photo-exists")["codes"] == ["existing"]


def test_a_doc_id_taken_under_another_key_is_skipped(admin):
    create(db_session, admin, "common/shared-photo", item_type="fact", payload={"doc_id": "photo-shared", **DOC})
    db_session.commit()
    out = run([card("shared", kind="fact")])
    assert (out["filed"], out["skipped"]) == (0, {"existing": 1}) and filed() == {}


def test_conflict_card_becomes_a_conflict_proposal_about_the_rule(admin):
    run()
    change = filed()["conflict/lahom-photo-rule-differs"]
    assert (change.item_type, change.layer, change.brand) == ("conflict", "common", "LAHOM")
    assert change.evidence == [*PEOPLE, "about:lahom/synth-rule"]
    assert change.fields["text"]["after"] == f"승인된 규칙과 다름\n{MARK} 합성 교훈 글"
    assert change.fields["payload"]["after"]["target"] == "lahom/synth-rule"
    assert "승인된 규칙과 다름" in change.reason
    rule = current_object(db_session, "lahom/synth-rule")
    assert (rule.version, rule.text) == (1, "합성 승인 규칙 글")  # 승인된 규칙은 그대로
    apply_change(db_session, change.id, actor=admin, now=NOW)
    db_session.commit()
    assert open_conflict_counts(db_session, ["lahom/synth-rule"]) == {"lahom/synth-rule": 1}  # '확인 필요'
    assert current_object(db_session, "lahom/synth-rule").text == "합성 승인 규칙 글"


def test_approving_a_filed_card_puts_it_into_the_brand_document(admin):
    run()
    rows = filed()
    lahom_before = kn.read_stored(db_session, "LAHOM").version
    apply_change(db_session, rows["lahom/photo-door-sag"].id, actor=admin, now=NOW)
    apply_change(db_session, rows["haud/photo-haud-note"].id, actor=admin, now=NOW)
    db_session.commit()
    item = kn.load_approved(db_session, "LAHOM").get("photo-door-sag")
    assert item is not None and item.text == f"{MARK} 합성 교훈 글" and item.kind == "policy"
    assert item.tags == ("photo-relearn",) and item.source == "photo_relearn"
    assert kn.read_stored(db_session, "LAHOM").version == lahom_before + 1
    assert kn.load_approved(db_session, "HAUD").get("photo-haud-note").kind == "fact"
    assert kn.load_approved(db_session, "LAHOM").get("photo-film-wrap") is None  # 승인 안 한 카드는 재료가 아니다
    assert all(doc_bridge.shadow_compare(db_session, b)["equal"] for b in ("LAHOM", "HAUD"))
    stored = next(i for i in kn.read_stored(db_session, "LAHOM").document["items"] if i["id"] == "photo-door-sag")
    assert MARK not in json.dumps({k: v for k, v in stored.items() if k != "text"}, ensure_ascii=False)  # 제목은 문서 밖


def test_only_key_and_limit_pick_a_subset(admin):
    out = run(only_keys=["lahom/photo-film-wrap", "lahom/photo-nowhere"])
    assert (out["cards"], out["filed"]) == (1, 1) and list(filed()) == ["lahom/photo-film-wrap"]
    preview = run(apply=False, limit=2)
    assert preview["cards"] == 2 and [r["index"] for r in preview["results"]] == [0, 1]


def test_a_judge_that_sees_a_conflict_blocks_the_card(admin, monkeypatch):
    """부딪침 관문(두 순서 판정)이 막으면 넣지 않고 관문 이름으로 센다 — 견줄 승인 지식이 있을 때만 판정자를 부른다."""
    from foms.services.brain import ai_gates
    monkeypatch.setattr(ai_gates, "related_knowledge", lambda *_a, **_k: ["합성 승인 규칙: 합성 승인 규칙 글"])
    with ai_gates.judge_source(lambda _s, _a, _b: True):
        out = file_cards(db_session, [card("door-sag")], apply=True, now=NOW)
    assert (out["filed"], out["blocked"]) == (0, {"conflict": 1}) and filed() == {}


# ── 관리자 스크립트 ──────────────────────────────────────────────────────
def load_script():
    spec = importlib.util.spec_from_file_location("brain_file_photo_cards_ut", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(script, capsys, *argv):
    with agent_judge():
        code = script.run(list(argv))
    printed = capsys.readouterr().out
    assert MARK not in printed and "합성 교훈" not in printed  # 글 · 제목은 화면에 내지 않는다
    return code, json.loads(printed)


def test_script_previews_by_default_then_files_one_key(admin, capsys, tmp_path):
    script = load_script()
    path = tmp_path / "synth_cards.json"
    path.write_text(json.dumps(cards(), ensure_ascii=False), encoding="utf-8")
    before = written()
    code, out = run_script(script, capsys, str(path))
    assert code == 0 and out["applied"] is False and out["filed"] == 4 and written() == before
    code, out = run_script(script, capsys, str(path), "--limit", "1")
    assert code == 0 and out["cards"] == 1
    code, out = run_script(script, capsys, str(path), "--apply", "--only-key", "lahom/photo-door-sag")
    assert code == 0 and out["applied"] is True and (out["cards"], out["filed"]) == (1, 1)
    assert list(filed()) == ["lahom/photo-door-sag"]
    assert run_script(script, capsys, str(tmp_path / "none.json"))[1]["error"] == "CARDS_UNREADABLE"
    (tmp_path / "object.json").write_text(json.dumps({"cards": []}), encoding="utf-8")
    code, out = run_script(script, capsys, str(tmp_path / "object.json"))
    assert (code, out["error"]) == (1, "CARDS_UNREADABLE")


@pytest.mark.parametrize("environment", ["production", "unknown-remote"])
def test_script_refuses_remote_apply_without_owner_approval(admin, capsys, monkeypatch, tmp_path, environment):
    script = load_script()
    monkeypatch.setattr(script, "resolve_environment", lambda: environment)
    path = tmp_path / "synth_cards.json"
    path.write_text(json.dumps(cards(), ensure_ascii=False), encoding="utf-8")
    before = written()
    code, out = run_script(script, capsys, str(path), "--apply")
    assert (code, out["error"]) == (1, "OWNER_APPROVAL_REQUIRED") and written() == before
    code, out = run_script(script, capsys, str(path))  # 미리 보기는 막지 않는다(쓰기 0)
    assert code == 0 and written() == before


def test_photo_cards_skip_the_weekly_cap_and_do_not_expire(admin):
    """D175 '사진 카드만 다 보이기' — 주 상한(층마다 20)을 넘어도 다 보이고, 4주가 지나도 닫히지 않고, 결정해도 그 층 주 자리를
    쓰지 않는다. 다른 AI 제안은 그대로 상한 · 닫힘을 받는다."""
    import datetime

    from foms.services.brain.constants import AI_WEEKLY_CAP
    from foms.services.brain.decide import expire_ai_proposals
    from foms.services.brain.inbox import ai_week, inbox
    from foms.services.brain.scope import viewer_of

    many = [card("bulk-" + chr(97 + n // 26) + chr(97 + n % 26)) for n in range(AI_WEEKLY_CAP + 3)]  # 숫자 없는 슬러그(숫자 관문)
    assert run(many)["filed"] == AI_WEEKLY_CAP + 3
    rows = filed()
    assert {c.action for c in rows.values()} == {"photo_relearn"}
    later = NOW + datetime.timedelta(days=40)
    shown = [c for c in inbox(db_session, viewer_of(admin), now=later)["cards"] if c["key"].startswith("lahom/photo-bulk-")]
    assert len(shown) == AI_WEEKLY_CAP + 3
    assert expire_ai_proposals(db_session, now=later) == 0
    first = rows["lahom/photo-bulk-aa"]
    apply_change(db_session, first.id, actor=admin, now=NOW)
    db_session.commit()
    assert ai_week(db_session, NOW)["layers"]["common"] == {"used": 0, "left": AI_WEEKLY_CAP}
