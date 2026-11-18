"""문장으로 고치기 — 화면 값에 지식 주소 · 코드 이름 · 영어 상태 코드가 나오지 않는다(설계서 2026-11-18 12절 '화면에 남은 흠').

1. 연결 줄의 끝이 없는 지식 · 볼 수 없는 지식이면 줄 이름은 '없거나 볼 수 없는 지식'(둘을 가르지 않는다 — 볼 수 없는 키가
   있는지 알리지 않는다). 주소는 ``key`` · ``after.to`` 에만 남는다. 바깥 자리 끝은 그 자리 이름, 모르는 연결 종류는 '모르는 연결'.
2. '같이 볼 것'의 없는 키는 주소 대신 이름 · 링크 없음(``key`` 빈 값), 키 꼴이 아닌 글은 그대로.
3. AI 글(요약 · 줄 까닭 · 코드가 필요한 것 · 물음 · 같이 볼 것 까닭) 속 주소는 이번 묶음 재료의 이름으로(새 항목 ``new:<n>`` ·
   설정 칸 이름 포함), 재료에 없는 주소는 그대로. AI 답 원본(``raw``)은 그대로 남긴다.
4. 은퇴 줄의 상태 · 설정 줄의 수준은 화면 말(값 칸은 저장 값 그대로).
합성 지식 · 합성 계정만.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.persistence.brain.models import BrainChange, BrainChangeRequest
from foms.services.brain import change_request as cr
from foms.services.brain.change_request_words import UNKNOWN_LABEL, external_label, tidy
from tests.domains.test_brain_change_request import APPLY_AT, _start, answer_text, fake_queue, flags_on, lvl, world
from tests.support.brain_chat_support import fixed

#: 재료에 문짝 둘 · 도면 담당 규칙이 들게 하는 합성 문장.
DOOR_SENTENCE = "여닫이 문짝 미닫이 문짝 도면 담당 바뀜"
SETTING = "운영 AI · 도면 담당 맡기기"


@pytest.fixture
def who(app, monkeypatch):
    flags_on(monkeypatch)
    fake_queue(monkeypatch)
    return world(db_session)


def _link(start, end, kind="requires"):
    return {"op": "add", "kind": kind, "from": start, "to": end, "why": "합성 연결"}


def _upd(key, why="합성", text="도면 담당은 도면팀이 스스로 정한다."):
    return {"key": key, "after": {"name": "", "text": text, "valid_from": "", "valid_to": ""}, "why": why}


def _has_address(text):
    return any(head in (text or "") for head in ("common/", "cs/", "drawing/", "new:", "ops.", "calc:", "erp:"))


def test_missing_and_unseen_link_ends_show_one_plain_name(who):
    """상담팀장 — 도면팀만 보는 배운 점은 볼 수 없다(없는 것과 같은 이름). 공통 층 줄은 같이 볼 것으로 간다."""
    view = _start(who["cs_mgr"], client=fixed(answer_text(links=[
        _link("common/rule/assign", "common/nothing"), _link("common/rule/assign", "cs/lesson/hidden"),
        _link("common/nothing", "common/door"), _link("new:7", "common/door", kind="applies_to")])))
    assert [l["label"] for l in view["lines"]] == [f"{UNKNOWN_LABEL} → 여닫이 문짝 (필요)",
                                                   f"{UNKNOWN_LABEL} → 여닫이 문짝 (적용)"]
    assert [(l["key"], l["after"]["from"]) for l in view["lines"]] == [("common/nothing",) * 2, ("new:7",) * 2]
    assert [a["label"] for a in view["also_look"]] == [f"도면 담당 정하기 → {UNKNOWN_LABEL} (필요)"] * 2
    assert not any(_has_address(t["label"]) for t in [*view["lines"], *view["also_look"], *view["not_done"]])


def test_lines_and_also_look_never_show_an_address_or_code_name(who):
    view = _start(who["admin"], DOOR_SENTENCE, client=fixed(answer_text(
        updates=[_upd("common/nope")], retires=[{"key": "common/gone", "why": "합성"}],
        links=[_link("common/door", "calc:product/1", "value_from"), _link("common/door", "common/slide", "made_up")],
        also_look=["common/zzz — 없는 키", "common/door — 같은 문짝", "ops.assign_draftsman — 수준 표도",
                   "common/never", "도면팀 규칙도 같이 봐요"])))
    labels = [l["label"] for l in view["lines"]]
    assert labels[:2] == [UNKNOWN_LABEL, UNKNOWN_LABEL]
    assert labels[2].startswith("여닫이 문짝 → 견적 계산기 (") and labels[3] == "여닫이 문짝 → 미닫이 문짝 (모르는 연결)"
    assert [l["key"] for l in view["lines"][:2]] == ["common/nope", "common/gone"]  # 주소는 key 칸에 남는다
    assert view["lines"][2]["after"]["to"] == "calc:product/1"
    assert view["also_look"] == [
        {"key": None, "label": UNKNOWN_LABEL, "why": "없는 키"},
        {"key": "common/door", "label": "여닫이 문짝", "why": "같은 문짝"},
        {"key": None, "label": SETTING, "why": "수준 표도"},
        {"key": None, "label": UNKNOWN_LABEL, "why": None},
        {"key": None, "label": "도면팀 규칙도 같이 봐요", "why": None}]
    assert not any(_has_address(t["label"]) for t in [*view["lines"], *view["also_look"], *view["not_done"]])


def test_addresses_in_the_ai_text_become_names_from_this_bundle(who):
    admin = who["admin"]
    view = _start(admin, DOOR_SENTENCE, client=fixed(answer_text(
        summary="common/rule/assign 를 고치고 new:1 을 만든다",
        updates=[_upd("common/rule/assign", why="common/door 에 맞춘다. ops.assign_draftsman 도 0 으로")],
        creates=[{"type": "fact", "brand": "COMMON", "values": {"name": "합성 새 사실", "text": "합성 사실 글."},
                  "why": "common/slide 와 같이 본다"}],
        needs_code=["밤 훑기 규칙(common/zzz-rule)은 코드 상수라 사람이 끈다 — calc:product/1 은 그대로"],
        questions=["common/slide 도 같이 바꿀까요?", "erp:stage/drawing 단계도 바뀌나요?"],
        also_look=["common/door — common/slide 와 같은 문짝"])))
    assert view["summary"] == "도면 담당 정하기 를 고치고 합성 새 사실 을 만든다"
    assert view["lines"][0]["why"] == f"여닫이 문짝 에 맞춘다. {SETTING} 도 0 으로"
    assert view["lines"][1]["why"] == "미닫이 문짝 와 같이 본다"
    assert view["needs_code"] == ["밤 훑기 규칙(common/zzz-rule)은 코드 상수라 사람이 끈다 — 견적 계산기 은 그대로"]  # 모르는 주소는 그대로
    assert view["questions"][0] == "미닫이 문짝 도 같이 바꿀까요?" and view["questions"][1] == "ERP 단계 · 도면 단계도 바뀌나요?"
    assert view["also_look"] == [{"key": "common/door", "label": "여닫이 문짝", "why": "미닫이 문짝 와 같은 문짝"}]
    row = db_session.get(BrainChangeRequest, view["id"])
    assert row.bundle["raw"]["summary"].startswith("common/rule/assign")  # AI 답 원본은 그대로
    done = cr.apply(db_session, admin, view["id"], now=APPLY_AT)
    db_session.commit()
    assert done["status"] == "applied"
    made = db_session.get(BrainChangeRequest, view["id"]).bundle["lines"][0]["change_id"]
    assert "common/door" not in db_session.get(BrainChange, made).reason  # 승인 대기 · 수정 기록의 까닭도 이름으로


def test_retire_status_and_setting_levels_are_screen_words(who):
    view = _start(who["admin"], client=fixed(answer_text(
        retires=[{"key": "common/rule/old", "why": "옛 규칙"}],
        settings=[lvl("ops.assign_draftsman", 0), lvl("enabled", 0, area="cs_agent"), lvl("ops.nothing", 0)])))
    retire, setting, cs_cell, unknown = view["lines"]
    assert retire["fields"] == [{"name": "status", "label": "상태", "before": "사용 중", "after": "은퇴"}]
    assert retire["before"] == {"status": "active"}  # 값 칸은 저장 값 그대로
    assert setting["fields"] == [{"name": "level", "label": "수준", "before": "2 제안", "after": "0 읽기만"}]
    assert setting["before"] == {"level": 2} and setting["after"] == {"level": 0}
    assert (setting["label"], cs_cell["label"], unknown["label"]) == (SETTING, "상담 AI 관리 칸", "없는 설정 칸")


def test_tidy_and_external_labels_alone():
    names = {"common/door": "여닫이 문짝", "new:2": "새 조건"}
    assert tidy("common/door. new:2, common/doors", names) == "여닫이 문짝. 새 조건, common/doors"
    assert tidy("xcommon/door 와 (common/door)", names) == "xcommon/door 와 (여닫이 문짝)"
    assert tidy(None, names) is None and tidy("", names) == ""
    assert external_label("erp:stage/drawing") == "ERP 단계 · 도면" and external_label("calc:product/1") == "견적 계산기"
    assert external_label("common/door") is None
