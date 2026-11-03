"""제안함 · 다시 확인 순수 함수 node 시험(static/js/brain/brain-review-view.js — 설계서 7.5 화면 4 · 5 · 6 · D103).

- 칸별 전 → 후 글 · 한 줄 요약 · 관문 줄.
- 휴대폰은 칸 하나 고침의 넣기 + 'PC 에서 볼게요'만, 기준 판이 바뀐 제안은 넣기 없음(PC 도).
- 넣기 본문: 기준 판 · 결정 시간 · 등급 B 확인 글(서버 글 그대로, 고쳐 넣은 칸이면 고친 글) · 고친 값(처음 값과 다른 칸만).
- 등급 A 한꺼번에 대상 · 기준 판 경고 · 사진 근거 주소(사진만) · 다시 확인 날 글 · 되돌림 표시.
표시 표는 서버 :func:`foms.services.brain.display.display_table` 그대로 싣는다.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from foms.services.brain.display import display_table

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "static/js/brain/brain-review-view.js"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def _node(expr: str, data: object = None):
    script = (f"const r = require({json.dumps(str(REVIEW))});"
              f"const data = {json.dumps(data, ensure_ascii=False)};"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60,
                         check=True).stdout
    return json.loads(out)


def _prop(**extra):
    base = {"id": 7, "op": "update", "grade": "A", "ai": False, "base_version": 2, "base": {"changed": False, "current": 2},
            "fields": [{"field": "name", "before": "옛 이름", "after": "새 이름"}], "phone_ok": True, "bulk_ok": True,
            "confirm": None, "gates": [{"name": "form", "value": "pass"}, {"name": "numbers", "value": "fail"},
                                       {"name": "conflict", "value": "not_run"}]}
    base.update(extra)
    return base


@NODE
def test_diff_rows_summary_and_gates():
    display = display_table()
    two = [{"field": "text", "before": None, "after": "글", "proposed": "처음 글"},
           {"field": "status", "before": "active", "after": "retired"}, {"field": "copies", "before": ["가", "나"], "after": []}]
    card = {"type": "lesson", "name": "사진 먼저", "main": _prop(fields=two)}
    got = _node("[r.diffRows(data.f, data.d), r.summary(data.c, data.d), r.gateRows(data.g, data.d),"
                " r.summary({type:'lesson', name:'x', main:{op:'link_add', fields:[], link:{kind:'applies_to', from:'a', to:'b'}}}, data.d)]",
                {"f": two, "d": display, "c": card, "g": _prop()["gates"]})
    assert got[0] == [
        {"field": "text", "label": "글", "before": "(없음)", "after": "글", "proposed": "처음 글"},
        {"field": "status", "label": "상태", "before": "반영", "after": "은퇴", "proposed": None},
        {"field": "copies", "label": "사본 목록", "before": "가 · 나", "after": "(빈 목록)", "proposed": None}]
    assert got[1] == "고침 · 배운 점 · 사진 먼저 — 글 · 상태 · 사본 목록"
    assert got[2] == [{"label": "꼴", "text": "통과", "cls": "is-pass"}, {"label": "숫자 출처", "text": "안 됨", "cls": "is-fail"},
                      {"label": "승인 지식과 부딪침", "text": "아직 안 돌림", "cls": "is-wait"}]
    assert got[3] == "링크 더함 · 적용: a → b"


@NODE
def test_phone_shows_only_one_field_apply_and_stale_proposals_cannot_be_applied():
    many = _prop(phone_ok=False, fields=[{"field": "name", "after": "a"}, {"field": "text", "after": "b"}])
    stale = _prop(base={"changed": True, "current": 3})
    got = _node("[r.actionsFor(data.one, true), r.actionsFor(data.many, true), r.actionsFor(data.one, false),"
                " r.actionsFor(data.stale, false), r.actionsFor(data.stale, true),"
                " r.actionsFor(Object.assign({}, data.one, {op:'retire', fields:[{field:'status'}]}), false)]",
                {"one": _prop(), "many": many, "stale": stale})
    assert got[0] == {"apply": True, "edit": False, "reject": False, "later": True, "hint": False}
    assert got[1] == {"apply": False, "edit": False, "reject": False, "later": True, "hint": True}
    assert got[2] == {"apply": True, "edit": True, "reject": True, "later": True, "hint": False}
    assert got[3] == {"apply": False, "edit": False, "reject": True, "later": True, "hint": False}
    assert got[4]["apply"] is False
    assert got[5]["edit"] is False  # 은퇴는 고쳐 넣기 없음


@NODE
def test_apply_body_echoes_the_confirm_value_and_sends_only_changed_edits():
    grade_b = _prop(grade="B", confirm={"field": "text", "value": "새 글"},
                    fields=[{"field": "text", "before": "옛 글", "after": "새 글"},
                            {"field": "valid_to", "before": None, "after": "2026-12-31"}])
    got = _node("[r.applyBody(data.p, {viewMs: 1234.4}), r.applyBody(data.p, {viewMs: 10, confirmed: true}),"
                " r.editsFrom(data.p, {text: '고친 글', valid_to: ''}), r.editsFrom(data.p, {text: '새 글'}),"
                " r.applyBody(data.p, {confirmed: true, edits: {text: '고친 글'}}),"
                " r.applyBody(Object.assign({}, data.p, {base_version: null}), {})]", {"p": grade_b})
    assert got[0] == {"base_version": 2, "view_ms": 1234}
    assert got[1] == {"base_version": 2, "view_ms": 10, "confirm": {"field": "text", "value": "새 글"}}
    assert got[2] == {"text": "고친 글", "valid_to": None}
    assert got[3] is None  # 처음 값과 같으면 고친 것이 없다
    assert got[4]["confirm"] == {"field": "text", "value": "고친 글"} and got[4]["edits"] == {"text": "고친 글"}
    assert got[5] == {"base_version": None, "view_ms": 0}


@NODE
def test_bulk_ids_warnings_links_and_lines():
    cards = [{"main": _prop(id=1)}, {"main": _prop(id=2, bulk_ok=False)},
             {"main": _prop(id=3, base={"changed": True, "current": 4})}]
    got = _node("[r.bulkIds(data.cards), r.conflictText(data.cards[2].main), r.conflictText(data.cards[0].main),"
                " r.evidenceHref('photo:12/3'), r.evidenceHref('turn:12'), r.evidenceHref('photo:../x'),"
                " r.similarText({count: 2, first: '2026-10-01', last: '2026-10-20'}), r.similarText({count: 0}),"
                " r.recheckWhen({days: -3}), r.recheckWhen({days: 0}), r.recheckWhen({days: 5}),"
                " r.rollbackText({into: 4, at: '2026-11-03'}), r.elapsed(100, 350.6),"
                " r.touchText({total: 3, items: [{name: '가'}, {name: '나'}]}, 2, {})]", {"cards": cards})
    assert got[0] == [1]
    assert got[1].startswith("제안을 만든 뒤 이 지식이 바뀌었어요(기준 판 2 → 지금 판 4)") and got[2] == ""
    assert got[3:6] == ["/cs-agent/turns/12/photos/3", None, None]
    assert got[6] == "비슷한 사례 2건 (2026-10-01 ~ 2026-10-20)" and got[7].startswith("비슷한 사례 없음")
    assert got[8:11] == ["확인 날 3일 지남", "오늘이 확인 날", "5일 뒤 확인"]
    assert got[11] == "되돌림 — 판 4에서(2026-11-03)" and got[12] == 251
    assert got[13].startswith("이어진 항목 3개: 가, 나 그 밖 1개 · 사본 2곳")


@NODE
def test_typed_fields_changed_after_and_registry_labels():
    from foms.services.brain.actions import specs
    got = _node("[r.fieldValue('number', ' 650 '), r.fieldValue('int', ''), r.fieldValue('list', 'hinged, sliding ,'),"
                " r.fieldValue('enum', 'mm'), r.fieldValue('number', 'abc'),"
                " r.changedAfter({name: 'a', 'payload.value': 600, 'payload.door_kinds': ['hinged']},"
                "                {name: 'a', 'payload.value': 650, 'payload.door_kinds': ['hinged']}),"
                " r.changedAfter({name: 'a'}, {name: 'a'}),"
                " r.actionLabel(data.a, 'recheck'), r.actionLabel(data.a, 'nope'),"
                " r.actionChoices(data.a, 'reject', 'code').map(function (c) { return c.label; }),"
                " r.diffRows([{field: 'payload.value', before: 600, after: 650, label: '값', unit: 'mm'}], {})]",
                {"a": specs()})
    assert got[0:5] == [650, None, ["hinged", "sliding"], "mm", "abc"]
    assert got[5] == {"payload.value": 650} and got[6] is None
    assert got[7] == "아직 맞음" and got[8] == "nope"
    assert got[9][:4] == ["숫자 틀림", "한 손님 일", "정책 아님", "사진 필요"]
    assert got[10] == [{"field": "payload.value", "label": "값", "before": "600mm", "after": "650mm", "proposed": None}]


@NODE
def test_edits_use_the_schema_datatype_and_editable_flag():
    prop = _prop(fields=[{"field": "payload.value", "before": 600, "after": 650, "editable": True, "datatype": "number"},
                         {"field": "checked_at", "before": None, "after": "2026-11-02", "editable": False}])
    got = _node("[r.editableFields(data.p), r.editsFrom(data.p, {'payload.value': '640', checked_at: '2026-11-03'}),"
                " r.editsFrom(data.p, {'payload.value': '650'})]", {"p": prop})
    assert got[0] == ["payload.value"]
    assert got[1] == {"payload.value": 640}  # 고칠 수 없는 칸은 빠지고 수는 수로
    assert got[2] is None
