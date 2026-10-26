"""도면 마법사 자재표 계산 칸(2단계, 그림자 판) 계약 테스트.

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.3 · §3.6
- 시트 ``calc``(입력값·계산 글자·규칙 판·모드)는 닫힌 칸·범위·크기 상한으로 검증된다.
- 계산 규칙 숫자는 전역 SystemSetting(``drawing_wizard_bom_rules``)에 version 잠금 + 감사로 저장된다.
- 브라우저 계산식(bom-calc.js)은 서버 기본 숫자로 설계서 견본과 같은 줄을 내고,
  저장 직전 정리(sanitize) 결과는 서버 검증을 늘 통과한다.
- 계산 칸 배치 안 A(사용성 평가 2026-10-25): 근거 숫자에 규칙 이름, 한 치수만 다른 줄은 한 줄
  '높이 +100(시트 2260)'(차이는 여유·짧음처럼 시트 − 계산, 한도 ±100 · 문 높이 ±200), 시트에서 아직 안 친 칸은
  회색 '아직 안 침'. 칸 그리기 자체는 test_drawing_bom_panel_ui.py 가 가짜 DOM 으로 본다.
- 실화면 QA(2026-10-25): 짝짓기는 같은 수량 짝을 먼저(수량이 다른 ±20 짝은 맨 나중), 칸을 열 때 시트가 칸에
  가리면 화면 폭과 상관없이 폭 맞춤(roomPlan), 규칙을 마지막으로 고친 사람·시각(감사 행), 칸 배치 CSS.
"""

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.drawing import wizard as wizard_api
from foms.services.drawing_wizard_bom_rules import (
    BOM_RULES_KEY,
    DEFAULT_RULES,
    BomRulesConflictError,
    BomRulesPreconditionError,
    BomRulesSchemaError,
    load_bom_rules,
    update_bom_rules,
    validate_bom_rules,
)
from models import Order, SecurityLog, SystemSetting, User

ROOT = Path(__file__).resolve().parents[2]
BOM_SCRIPTS = ("bom-calc", "bom-rules", "bom-rules-dialog", "bom-results", "bom-form", "bom-panel")   # 실행 순서
JS = {name: ROOT / f"static/js/drawing/{name}.js" for name in BOM_SCRIPTS}
TEMPLATE = ROOT / "templates/drawing/wizard.html"
WIZARD_JS = ROOT / "static/js/drawing/wizard.js"
RULES_URL = "/api/orders/drawing-wizard/bom-rules"
_SEQ = [0]


def _login(client, *, role, team):
    _SEQ[0] += 1
    user = User(username=f"bomcalc-{_SEQ[0]}", password=generate_password_hash("x"),
                role=role, team=team, name=f"bomcalc-{_SEQ[0]}", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order_id():
    order = Order(
        received_date=date.today().strftime("%Y-%m-%d"), customer_name="시험", phone="010-0000-0000",
        address="대구", product="붙박이장", status="DRAWING", is_erp_order=True,
        structured_data={"parties": {"customer": {"name": "시험"}}, "items": [{"product_name": "몰딩 여닫이장"}]},
    )
    db_session.add(order)
    db_session.commit()
    return order.id   # 요청이 끝나면 세션이 닫혀 객체가 떨어지므로 id 만 들고 간다


def _calc(**over):
    calc = {
        "in": {"line": "mold", "handle": "phoenix", "nomold": "ceiling", "W": 3500, "D": 620, "H": 2305,
               "zone": 753, "door_h": 0, "ep": 0, "sr_l": 0, "sr_r": 0,
               "mods": [{"w": 950, "doors": 2, "drawers": 3, "rods": 1}, {"w": 488, "doors": 1, "drawers": 0, "rods": 0}]},
        "out": "[SR]\n120*2440=2", "rules": "d1", "mode": "shadow",
    }
    calc.update(over)
    return calc


def _state(calc):
    return {"v": 1, "sheets": [{"id": "s-1", "name": "도면 1", "form": {}, "objects": [], "calc": calc}]}


# --------------------------------------------------------------------------- #
# 1. 시트 calc 저장·검증
# --------------------------------------------------------------------------- #
def test_put_keeps_sheet_calc(client):
    _login(client, role="ADMIN", team="DRAWING")
    order_id = _order_id()
    calc = _calc()
    resp = client.put(f"/api/orders/{order_id}/drawing-wizard", json={"state": _state(calc), "base_updated_at": None})
    assert resp.status_code == 200, resp.get_json()
    saved = client.get(f"/api/orders/{order_id}/drawing-wizard").get_json()["data"]["state"]
    assert saved["sheets"][0]["calc"] == calc


@pytest.mark.parametrize("calc", [
    "그림자",
    {"in": {}, "extra": 1},
    {"in": {}, "mode": "auto"},
    {"in": {}, "rules": "s 1"},
    {"in": {}, "out": "x" * 2001},
    {"in": {"line": "kitchen"}},
    {"in": {"W": -1}},
    {"in": {"W": "3500"}},
    {"in": {"ep": True}},
    {"in": {"color": "white"}},
    {"in": {"mods": [{"w": 900, "glass": 1}]}},
    {"in": {"mods": [{"w": 900, "doors": 5}]}},
    {"in": {"mods": [{"w": 900}] * 25}},
    {"in": {"mods": "900"}},
])
def test_put_rejects_bad_sheet_calc(client, calc):
    _login(client, role="ADMIN", team="DRAWING")
    order_id = _order_id()
    resp = client.put(f"/api/orders/{order_id}/drawing-wizard", json={"state": _state(calc), "base_updated_at": None})
    assert resp.status_code == 400, resp.get_json()


def test_calc_byte_cap():
    big = _calc(out="[옷봉]" * 500)   # 2000자 이하지만 UTF-8 로 4KB 를 넘는다
    assert wizard_api._validate_calc(big) == "자재표 계산 데이터가 너무 큽니다."
    assert wizard_api._validate_calc(_calc()) is None
    assert wizard_api._validate_calc({}) is None   # 빈 calc(옛 저장분·입력 전)도 통과


# --------------------------------------------------------------------------- #
# 2. 계산 규칙 숫자 — 형식·잠금·감사
# --------------------------------------------------------------------------- #
def test_validate_rules_fills_defaults_and_rejects_bad_values():
    assert validate_bom_rules({}) == DEFAULT_RULES
    assert validate_bom_rules({"rod_cut": 40})["rod_cut"] == 40
    for bad in ({"rod_cut": "35"}, {"rod_cut": 999}, {"rod_cut": True}, {"unknown": 1},
                {"door_std_heights": [2160, 2060]}, {"door_std_heights": []}, {"door_std_heights": [100]}):
        with pytest.raises(BomRulesSchemaError):
            validate_bom_rules(bad)
    with pytest.raises(BomRulesSchemaError):
        validate_bom_rules([DEFAULT_RULES])


CHANGED_AT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")   # 한국 시간 'YYYY-MM-DD HH:MM'


def test_rules_create_bump_conflict_and_audit(app):
    assert load_bom_rules(db_session) == {"rules": DEFAULT_RULES, "label": "d1", "version": 0,
                                          "changed_at": None, "changed_by": None}
    with pytest.raises(BomRulesPreconditionError):
        update_bom_rules(db_session, actor_user_id=None, payload={}, if_match_version=None)
    db_session.rollback()

    first = update_bom_rules(db_session, actor_user_id=None, payload={"rod_cut": 40}, if_match_version=0)
    db_session.commit()
    assert first["version"] == 1 and first["label"] == "s1" and first["rules"]["rod_cut"] == 40
    # 마지막 고침 시각은 방금 남긴 감사 행에서 읽는다(시스템 저장이라 이름은 없음 — 보통-4)
    assert CHANGED_AT.match(first["changed_at"]) and first["changed_by"] is None
    assert load_bom_rules(db_session)["changed_at"] == first["changed_at"]
    log = db_session.query(SecurityLog).filter(SecurityLog.action == "DRAWING_WIZARD_BOM_RULES_UPDATE").one()
    assert log.detail["changed"] == {"rod_cut": [35, 40]}

    with pytest.raises(BomRulesConflictError) as err:
        update_bom_rules(db_session, actor_user_id=None, payload={"rod_cut": 30}, if_match_version=0)
    assert err.value.current_version == 1 and err.value.status_code == 409
    db_session.rollback()
    assert load_bom_rules(db_session)["rules"]["rod_cut"] == 40


def test_load_tolerates_broken_stored_values(app):
    db_session.add(SystemSetting(setting_key=BOM_RULES_KEY, version=3,
                                 setting_value={"rod_cut": "bad", "sr_step": 20, "junk": 1}))
    db_session.commit()
    got = load_bom_rules(db_session)
    assert got["label"] == "s3" and got["rules"]["rod_cut"] == 35 and got["rules"]["sr_step"] == 20
    assert set(got["rules"]) == set(DEFAULT_RULES)


def test_rules_api_permission_and_round_trip(client):
    _login(client, role="STAFF", team="CS")
    data = client.get(RULES_URL).get_json()["data"]
    assert data["can_edit"] is False and data["label"] == "d1" and data["defaults"] == DEFAULT_RULES
    assert data["changed_at"] is None and data["changed_by"] is None   # 아직 아무도 안 고침
    denied = client.post(RULES_URL, json={"rules": {"rod_cut": 40}, "settings_version": 0})
    assert denied.status_code == 403

    editor = _login(client, role="STAFF", team="DRAWING").name   # 요청이 끝나면 객체가 세션에서 떨어지니 이름만
    assert client.get(RULES_URL).get_json()["data"]["can_edit"] is True
    missing = client.post(RULES_URL, json={"rules": {"rod_cut": 40}})
    assert missing.status_code == 428
    bad = client.post(RULES_URL, json={"rules": {"rod_cut": "많이"}, "settings_version": 0})
    assert bad.status_code == 400 and bad.get_json()["code"] == "BOM_RULES_SCHEMA"
    ok = client.post(RULES_URL, json={"rules": {"rod_cut": 40}, "settings_version": 0})
    assert ok.status_code == 200, ok.get_json()
    saved = ok.get_json()["data"]
    assert saved["label"] == "s1" and saved["changed_by"] == editor and CHANGED_AT.match(saved["changed_at"])
    stale = client.post(RULES_URL, json={"rules": {"rod_cut": 41}, "settings_version": 0})
    assert stale.status_code == 409 and stale.get_json()["current_version"] == 1
    _login(client, role="STAFF", team="CS")   # 보기만 하는 사람도 누가 언제 고쳤는지 본다(보통-4)
    after = client.get(RULES_URL).get_json()["data"]
    assert after["rules"]["rod_cut"] == 40 and after["version"] == 1
    assert after["changed_by"] == editor and after["changed_at"] == saved["changed_at"]


# --------------------------------------------------------------------------- #
# 3. 브라우저 계산식(node) — 견본·정리·서버 검증 정합
# --------------------------------------------------------------------------- #
def _node():
    node = shutil.which("node")
    assert node, "node must be on PATH for JS checks"
    return node


@pytest.mark.parametrize("name", sorted(JS))
def test_node_check(name):
    proc = subprocess.run([_node(), "--check", str(JS[name])], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr


RUNNER = r"""
global.window = {};
require(process.argv[1]);
const C = window.FomsBomCalc, job = JSON.parse(process.argv[2]);
const out = {};
for (const [k, s] of Object.entries(job.specs)) out[k] = C.toText(C.calc(s, job.rules));
out.sanitized = C.sanitize(job.messy);
out.huge = C.sanitize(job.huge);
out.cmp = C.compare(C.calc(job.specs.s12, job.rules), C.parseBom(job.sheet)).map(r => r.kind + ' ' + r.text);
out.guess = ['로라 몰딩 여닫이', '무몰딩 붙박이장', '3연동 슬라이딩', '냉장고장', '붙박이장'].map(C.guessLine);
out.orphans = C.parseBom(job.orphan_texts).orphans;
const s11 = C.calc(job.specs.s11, job.rules);
out.why = s11.filter(l => !l.head).map(l => l.text + ' | ' + l.why);
const show = res => res.map(r => r.kind + ' ' + r.text + ' ' + r.note);
out.grouped = show(C.compare(s11, C.parseBom(job.sheet11)));
const line = (sec, a, b, q, ea) => ({ sec, a, b, q, ea, text: (b == null ? a : a + '*' + b) + '=' + q });
out.order = show(C.compare([line('DOOR', 471, 2260, 4), line('DOOR', 471, 2160, 4)], C.parseBom(['[DOOR]\n471*2160=4'])));
out.width = show(C.compare([line('DOOR', 476, 2160, 2), line('옷봉', 965, null, 3)], C.parseBom(['[DOOR]\n446*2160=2\n[옷봉]\n925=3'])));
out.todo_ea = show(C.compare([line('DOOR', 483, 2160, 4, 2)], C.parseBom(['[SR]\n60*2440=1'])));
// 실화면 QA 2026-10-25: 폭이 비슷한 다른 문(496*2160=1)이 있어도 높이만 다른 같은 문 줄끼리 묶는다
out.qa_height = show(C.compare([line('DOOR', 483, 2160, 6, 3), line('DOOR', 470, 2160, 1, 1)],
  C.parseBom(['[DOOR]\n483*2260=6\nㄴ피닉스바 3EA\n496*2160=1\nㄴ피닉스바 1EA\n471*1400=2'])));
out.qa_pair = show(C.compare([line('DOOR', 483, 2160, 6)], C.parseBom(['[DOOR]\n483*2260=6\n496*2160=1'])));
out.other_qty = show(C.compare([line('DOOR', 483, 2160, 6)], C.parseBom(['[DOOR]\n496*2160=1'])));
out.closest = show(C.compare([line('DOOR', 500, 2160, 2), line('DOOR', 488, 2160, 2)], C.parseBom(['[DOOR]\n489*2160=2'])));
out.same_dims = show(C.compare([line('DOOR', 483, 2160, 4)], C.parseBom(['[DOOR]\n483*2160=2', '[DOOR]\n483*2160=4'])));
process.stdout.write(JSON.stringify(out));
"""


def _run_calc(job):
    proc = subprocess.run([_node(), "-e", RUNNER, str(JS["bom-calc"]), json.dumps(job)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _job():
    s11 = {"line": "mold", "handle": "phoenix", "W": 3660, "D": 570, "H": 2300, "zone": 753,
           "mods": [{"w": 1000, "doors": 2, "drawers": 3, "rods": 1}, {"w": 1000, "doors": 2, "rods": 2},
                    {"w": 1000, "doors": 2, "rods": 2}, {"w": 500, "doors": 1, "rods": 2}]}
    s12 = {"line": "mold", "handle": "phoenix", "W": 3500, "D": 620, "H": 2305, "zone": 753,
           "mods": [{"w": 950, "doors": 2, "drawers": 3, "rods": 1}, {"w": 950, "doors": 2, "rods": 2},
                    {"w": 950, "rods": 1}, {"w": 488, "doors": 1}]}
    nomold = {"line": "nomold", "nomold": "ceiling", "handle": "other", "W": 2400, "D": 600, "H": 2400,
              "ep": 1, "mods": [{"w": 800, "doors": 2}]}
    return {
        "rules": DEFAULT_RULES, "specs": {"s11": s11, "s12": s12, "nomold": nomold},
        "messy": {"in": {"line": "kitchen", "W": "3500.4", "ep": 9, "mods": [{"w": -3, "doors": 9, "glass": 1}]},
                  "out": "a", "rules": "d1", "mode": "auto", "junk": 1},
        "huge": _calc(out="[옷봉]" * 500),
        "sheet": ["[SR] 120*2440=2\n보조목=4", "[DOOR]\n458*2160=3\n458*1407=2\n[옷봉]\n925=4\n[마이다]\n945*236=3"],
        "orphan_texts": ["483*2160=4\nㄴ피닉스바 2EA\n975=5", "[SR]\n60*2440=1"],
        # 11번 견본을 반쯤 친 시트: 문 높이를 2060 으로 잘못 침 · 옷봉은 자리표만 · 마이다는 아직 없음
        "sheet11": ["[SR]\n110*2440=3", "[DOOR]\n483*2060=4\nㄴ피닉스바 2EA\n483*1407=2", "[옷봉]"],
    }


def test_calc_matches_spec_samples_and_sanitize_passes_server():
    res = _run_calc(_job())
    # 설계서 §3.3 견본 대조: 11번 7줄 중 6줄(SR 수량만 다름), 12번 5줄 모두 같음
    for line in ("483*2160=4", "483*1407=2", "470*2160=1", "965=5", "465=2", "995*236=3", "110*2440=2"):
        assert line in res["s11"].split("\n")
    for line in ("458*1407=2", "458*2160=3", "915=4", "945*236=3", "120*2440=2"):
        assert line in res["s12"].split("\n")
    # 무몰딩: 문 높이 천장−45(2355), 위 틈 45 → SR 60, 여닫이 EP 깊이+10, 그 밖 손잡이 쌍문 (800−8)÷2
    assert res["nomold"].split("\n") == ["[SR]", "60*2440=1", "[EP]", "610*2440=1", "[DOOR]", "396*2355=2"]

    for cleaned in (res["sanitized"], res["huge"]):
        assert wizard_api._validate_calc(cleaned) is None, cleaned
    assert res["sanitized"]["in"]["line"] == "mold" and res["sanitized"]["mode"] == "shadow"
    assert res["sanitized"]["in"]["W"] == 3500 and res["sanitized"]["in"]["ep"] == 4
    assert res["sanitized"]["in"]["mods"] == [{"w": 0, "doors": 4, "drawers": 0, "rods": 0}]
    assert "out" not in res["huge"]   # 크기 상한을 넘으면 계산 글자를 버린다(입력값으로 다시 만든다)

    assert "ok 120*2440=2" in res["cmp"] and "warn 915=4" in res["cmp"] and "extra 보조목=4" in res["cmp"]
    assert res["guess"] == ["mold", "nomold", "slide", "other", "mold"]
    assert res["orphans"] == 2   # 머리글 없이 친 크기 줄(피닉스바 줄은 세지 않음)


def test_reasons_name_each_rule_number():
    """근거 글의 숫자에 규칙 이름을 붙인다 — '(1000 − 34) ÷ 2' 만으로는 34 가 무슨 규칙인지 모른다(보통-3)."""
    why = _run_calc(_job())["why"]
    for expected in ("483*2160=4 | (1000 − 쌍문 틈 34) ÷ 2 내림 · 높이: 표준 문 중 천장 2300 − 띄울 높이 90 이하에서 가장 큰 것",
                     "470*2160=1 | 500 − 외짝 틈 30 · 높이:",
                     "483*1407=2 | (1000 − 쌍문 틈 34) ÷ 2 내림 · 높이 2160 − 서랍 칸 753",
                     "965=5 | 1000 − 옷봉 빼기 35",
                     "995*236=3 | (1000 − 폭 빼기 5) × (753 ÷ 3 − 높이 빼기 15)",
                     "110*2440=2 | 위 틈 140 − 틈 빼기 30 → 10 단위 올림 · 폭 3660 ÷ 판 길이 2440 올림 2장"):
        assert any(w.startswith(expected) for w in why), (expected, why)


def test_compare_groups_one_dimension_and_marks_untyped_sections():
    """한 치수만 다른 줄은 '높이 -100(시트 2060)' 한 줄로 묶고(보통-7), 아직 안 친 칸은 빨강 대신 회색 '아직 안 침'."""
    res = _run_calc(_job())
    grouped = res["grouped"]
    assert "bad 483*2160=4 높이 -100(시트 2060)" in grouped              # 두 줄(시트에 없음·계산에 없음)로 가르지 않는다
    assert not any(g.startswith("extra ") for g in grouped), grouped    # 시트 줄은 모두 짝을 찾았다
    assert "ok ㄴ피닉스바 2EA 같음" in grouped                             # 묶인 문 줄에 딸린 피닉스바도 맞춰 본다
    assert "bad 110*2440=2 수량 다름(시트 3)" in grouped
    assert "bad 470*2160=1 시트에 없음" in grouped                         # 친 칸(DOOR)에서 빠진 줄은 진짜 빨강
    assert "todo 965=5 아직 안 침" in grouped and "todo 465=2 아직 안 침" in grouped   # 자리표만 있는 칸
    assert "todo 995*236=3 아직 안 침" in grouped                          # 아직 안 친 칸
    assert "todo 580*2440=1 아직 안 침" not in grouped                     # EP 는 입력이 없어 계산 자체가 없다
    # 꼭 맞는 짝을 먼저 찾는다 — 앞 줄(2260)이 뒤 줄(2160)의 짝을 가져가지 않는다
    assert res["order"] == ["bad 471*2260=4 시트에 없음", "ok 471*2160=4 같음"]
    # 너비만 다른 줄 · 길이 하나뿐인 옷봉도 같은 방식(시트가 작으면 −)
    assert res["width"] == ["bad 476*2160=2 너비 -30(시트 446)", "bad 965=3 길이 -40(시트 925)"]
    # 안 친 칸의 문 줄에 딸린 피닉스바 줄도 회색(시트에 있는 줄은 '계산에 없음')
    assert res["todo_ea"] == ["todo 483*2160=4 아직 안 침", "todo ㄴ피닉스바 2EA 아직 안 침", "extra 60*2440=1 계산에 없음"]


def test_compare_prefers_same_quantity_then_closest_pair():
    """짝짓는 차례(실화면 QA 2026-10-25 새 문제): 수량을 안 보는 ±20 짝이 '같은 수량, 한 치수만 다름' 짝보다 먼저라
    계산 483*2160=6 이 다른 문 496*2160=1 과 '여유 +13'으로 묶이고 483*2260=6 은 '계산에 없음'으로 갈렸다."""
    res = _run_calc(_job())
    assert res["qa_pair"] == ["bad 483*2160=6 높이 +100(시트 2260)", "extra 496*2160=1 계산에 없음"]
    assert res["qa_height"] == ["bad 483*2160=6 높이 +100(시트 2260)", "ok ㄴ피닉스바 3EA 같음",
                                "bad 470*2160=1 너비 +26(시트 496)", "ok ㄴ피닉스바 1EA 같음",
                                "extra 471*1400=2 계산에 없음"]
    # 수량이 다른 ±20 짝은 맨 나중에, 빨강으로 '수량 다름'까지 적는다
    assert res["other_qty"] == ["bad 483*2160=6 여유 +13 · 수량 다름(시트 496*2160=1)"]
    # 같은 차례 안에서는 계산 줄 차례가 아니라 차이가 작은 짝부터(489 는 500 보다 488 에 가깝다)
    assert res["closest"] == ["bad 500*2160=2 시트에 없음", "warn 488*2160=2 여유 +1(시트 489*2160=2)"]
    # 크기가 같은 줄이 둘이면 수량까지 같은 줄과 짝짓는다
    assert res["same_dims"] == ["ok 483*2160=4 같음", "extra 483*2160=2 계산에 없음"]
    # 한 치수 차이 한도·같은 칸 안 부호 방향(실화면 QA V2)은 test_drawing_bom_compare_and_keys.py


SUMMARY_RUNNER = r"""
global.window = {};
require(process.argv[1]);
require(process.argv[2]);
const S = window.FomsBomResults.summary, L = window.FomsBomRules.labelName;
const rows = ['ok', 'ok', 'ok', 'bad', 'todo', 'extra'].map(kind => ({ kind }));
process.stdout.write(JSON.stringify({
  mixed: S(rows, true), clean: S([{ kind: 'ok' }, { kind: 'ok' }], true), warn: S([{ kind: 'ok' }, { kind: 'warn' }], true),
  none: S([{ kind: 'todo' }, { kind: 'todo' }], false), labels: ['d1', 's2', 's13', ''].map(L),
}));
"""


def test_summary_chip_and_rule_label_words():
    """요약 칩 'N줄 중 M줄 같음 · 다름 K', 판 이름은 개발 말('판 s2') 대신 '규칙 2판'·'기본 규칙'(작음·보통-4)."""
    proc = subprocess.run([_node(), "-e", SUMMARY_RUNNER, str(JS["bom-results"]), str(JS["bom-rules"])],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    assert got["mixed"]["text"] == "5줄 중 3줄 같음 · 다름 1 · 아직 안 침 1 · 시트에만 1" and got["mixed"]["tone"] == "bad"
    assert got["clean"] == {"text": "2줄 중 2줄 같음", "tone": "ok",
                            "counts": {"ok": 2, "warn": 0, "bad": 0, "todo": 0, "extra": 0}}
    assert got["warn"]["text"] == "2줄 중 1줄 같음 · 여유 1" and got["warn"]["tone"] == "warn"
    assert got["none"]["text"] == "계산 2줄 · 시트에 아직 안 침" and got["none"]["tone"] == "todo"
    assert got["labels"] == ["기본 규칙", "규칙 2판", "규칙 13판", ""]


def test_bom_scripts_stay_small():
    """새 JS 300줄 래칫(tests/harness/test_file_size_ratchet.py) — 계산 칸은 파일을 나눠 지킨다."""
    for name, path in JS.items():
        assert len(path.read_text(encoding="utf-8").splitlines()) < 300, name


def _js_object_keys(text, var_name):
    m = re.search(r"var " + var_name + r" = \{([^}]*)\}", text)
    assert m, var_name
    return dict(re.findall(r"(\w+): (\d+)", m.group(1)))


def test_js_contract_matches_server_lists():
    calc_js = JS["bom-calc"].read_text(encoding="utf-8")
    numbers = {k: int(v) for k, v in _js_object_keys(calc_js, "NUMBERS").items()}
    assert numbers == {k: hi for k, (lo, hi) in wizard_api._CALC_NUMBERS.items()}
    mod_numbers = {k: int(v) for k, v in _js_object_keys(calc_js, "MOD_NUMBERS").items()}
    assert mod_numbers == {k: hi for k, (lo, hi) in wizard_api._CALC_MOD_NUMBERS.items()}
    for js_var, key in (("LINES", "line"), ("HANDLES", "handle"), ("NOMOLD", "nomold")):
        m = re.search(r"var " + js_var + r" = \[([^\]]*)\]", calc_js)
        assert re.findall(r"'([^']+)'", m.group(1)) == list(wizard_api._CALC_CHOICES[key])
    rules_js = JS["bom-rules"].read_text(encoding="utf-8")
    field_keys = re.findall(r"\['([a-z_]+)', '", rules_js) + (["door_std_heights"] if "[HEIGHTS, '" in rules_js else [])
    assert sorted(field_keys) == sorted(DEFAULT_RULES)


def test_template_and_wizard_wiring():
    html = TEMPLATE.read_text(encoding="utf-8")
    order = [html.index(f"js/drawing/{n}.js") for n in BOM_SCRIPTS + ("wizard",)]
    assert order == sorted(order)   # 계산 → 규칙 → 규칙 창 → 결과 → 입력 → 칸 → 마법사 순서로 실행(defer)
    for name in BOM_SCRIPTS:
        tag = re.search(r'<script src="[^"]*/' + name + r'\.js[^"]*"[^>]*>', html).group(0)
        assert "?v=" in tag and " defer" in tag
    assert 'id="dws-btn-calc"' in html and 'id="dws-calc"' in html
    wjs = WIZARD_JS.read_text(encoding="utf-8")
    assert "window.FomsBomCalc.sanitize(s.calc)" in wjs        # 저장에 calc 를 싣는다
    assert "if (s.calc && typeof s.calc === 'object') { sheet.calc = s.calc; }" in wjs   # 불러올 때 받는다
    assert "window.FomsBomPanel.sync()" in wjs


def test_open_hook_folds_products_and_fits_width():
    """칸을 열면 화면 폭(1600)이 아니라 '시트 오른쪽이 칸에 가리는가'로 폭을 맞추고, 맞춤만으로 80% 아래면 제품
    목록도 접고, 닫으면 되돌린다(큼-2 · 실화면 QA 2026-10-25: 1920 배율 100% 에서 [마이다]가 '[마'로 가렸다)."""
    wjs = WIZARD_JS.read_text(encoding="utf-8")
    assert "onOpenChange: onBomPanelOpenChange" in wjs
    body = wjs.split("function onBomPanelOpenChange(open) {", 1)[1].split("\n  }\n", 1)[0]
    assert "window.innerWidth > 1600" not in body and "window.innerWidth <= 900" in body
    assert "window.FomsBomPanel.roomPlan({ zoom: zoom, avail: els.canvas.clientWidth - 48, stageW: STAGE_W," in body
    assert "toggleProducts();" in body and "fitZoom();" in body and "setZoom(prev.zoom);" in body
    assert "if (ctx.onOpenChange) { ctx.onOpenChange(on); }" in JS["bom-panel"].read_text(encoding="utf-8")
    # '가림' 판단(roomPlan)과 맞춤(fitZoom)이 같은 여백 48·같은 식을 써야 맞춘 뒤에도 가리지 않는다
    fit = wjs.split("function fitZoom() {", 1)[1].split("\n  }\n", 1)[0]
    assert "els.canvas.clientWidth - 48" in fit and "Math.min(1, avail / STAGE_W)" in fit


ROOM_RUNNER = r"""
global.window = {};
require(process.argv[1]);
const plan = window.FomsBomPanel.roomPlan;
process.stdout.write(JSON.stringify(JSON.parse(process.argv[2]).map(o => plan(o))));
"""


def test_room_plan_fits_by_cover_not_screen_width():
    """시트 폭 1478 · 제품 목록 220(접으면 32) · 계산 칸 340 · 좌우 여백 48 로 실화면 QA 의 폭들을 재현한다."""
    def case(screen, zoom, products=220):
        return {"zoom": zoom, "avail": screen - products - 340 - 48, "stageW": 1478, "productsOpen": products == 220}
    cases = [case(1920, 1), case(1680, 0.955), case(1600, 0.9), case(1366, 0.743), case(1600, 1, products=32),
             case(2560, 1), case(1920, 0.5), case(1920, 1.5), {"zoom": 1, "avail": 0, "stageW": 1478}]
    proc = subprocess.run([_node(), "-e", ROOM_RUNNER, str(JS["bom-panel"]), json.dumps(cases)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    rounded = [p and {"zoom": round(p["zoom"], 3), "fold": p["fold"]} for p in got]
    assert rounded[0] == {"zoom": 0.888, "fold": False}   # 1920: 목록은 두고 맞춤만 89%
    assert rounded[1] == {"zoom": 0.725, "fold": True}    # 1680: 맞춤만이면 73% → 목록도 접는다(접으면 85%)
    assert rounded[2]["fold"] is True and rounded[3]["fold"] is True   # 1600 · 1366
    assert rounded[4] == {"zoom": 0.798, "fold": False}   # 목록이 이미 접혀 있으면 맞춤만
    assert rounded[5] is None and rounded[6] is None      # 넓은 화면 · 이미 작게 본 시트는 가리지 않아 그대로
    assert rounded[7] == {"zoom": 0.888, "fold": False}   # 크게 본 시트도 칸이 가리면 맞춘다(닫으면 되돌림)
    assert rounded[8] is None


def test_calc_panel_css_readability():
    """글자·대비(보고서 글자 표): 근거 13px 진한 회색, 입력 테두리 대비 3 이상, 칩 굵게·줄바꿈 없음·폭 상한 없음."""
    css = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")
    calc = css.split("/* ---- 오른쪽 자재표 계산 칸", 1)[1]
    assert ".dws-calc-why { font-size: 13px; line-height: 1.45; color: #6e6e73; }" in calc
    assert "border: 1px solid #8e8e93;" in calc
    chip = calc.split("\n.dws-calc-chip {", 1)[1].split("}", 1)[0]
    assert "font-weight: 700;" in chip and "white-space: nowrap;" in chip and "max-width" not in chip
    assert "word-break: keep-all;" in calc.split(".dws-calc {", 1)[1].split("}", 1)[0]
    assert ".dws-calc-rule-wide { grid-column: 1 / -1; }" in calc
    assert "@media (pointer: coarse) {" not in calc   # 터치 시험이 마지막 이 덩어리를 앱바 규칙으로 읽는다


def test_calc_panel_layout_css_after_live_qa():
    """실화면 QA 2026-10-25 에서 잰 칸 배치 문제의 CSS 계약."""
    css = (ROOT / "static/css/contexts/drawing/wizard.css").read_text(encoding="utf-8")
    calc = css.split("/* ---- 오른쪽 자재표 계산 칸", 1)[1]
    # 줄어드는 몫은 아래 스크롤 구역이 진다 — 근거·기본을 펴도 위 결과 칸(268px)이 130·109px 로 줄지 않는다
    assert ".dws-calc-body { flex: 1 1 0; min-height: 120px;" in calc
    assert "flex: 0 1 auto;\n  max-height: 45vh;" in calc.split(".dws-calc-top {", 1)[1].split("}", 1)[0]
    # 요약 칩은 칸 폭 안에서 줄을 바꾼다(1366 에서 6px 넘쳐 '시트에만 4'가 잘렸다)
    score = calc.split(".dws-calc-chip.dws-calc-score {", 1)[1].split("}", 1)[0]
    assert "white-space: normal;" in score and "max-width: 100%;" in score and "box-sizing: border-box;" in score
    # 모듈 폭 열 62px 고정 · 숫자 칸 화살표 숨김 · 여백 4px — '1000'이 '100'으로 잘리지 않게
    assert ".dws-calc-mods th:nth-child(2), .dws-calc-mods td:nth-child(2) { width: 62px; }" in calc
    assert ".dws-calc-mods select { padding-left: 4px; padding-right: 4px; font-variant-numeric: tabular-nums; }" in calc
    assert '.dws-calc-mods input[type="number"] { -moz-appearance: textfield; appearance: textfield; }' in calc
    assert '.dws-calc-mods input[type="number"]::-webkit-inner-spin-button' in calc
    # 규칙 창: 세로 flex — 낮은 화면에서도 단추 줄은 늘 보이고 18칸 묶음만 스크롤
    assert ".dws-calc-rules-dialog[open] { display: flex; flex-direction: column; }" in calc
    grid = calc.split(".dws-calc-rules-grid {", 1)[1].split("}", 1)[0]
    assert "overflow-y: auto;" in grid and "min-height: 0;" in grid
    assert ".dws-calc-rules-body { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }" in calc
    assert ".dws-calc-rules-actions { flex: 0 0 auto;" in calc
