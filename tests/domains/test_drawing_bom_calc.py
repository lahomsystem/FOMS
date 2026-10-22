"""도면 마법사 자재표 계산 칸(2단계, 그림자 판) 계약 테스트.

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.3 · §3.6
- 시트 ``calc``(입력값·계산 글자·규칙 판·모드)는 닫힌 칸·범위·크기 상한으로 검증된다.
- 계산 규칙 숫자는 전역 SystemSetting(``drawing_wizard_bom_rules``)에 version 잠금 + 감사로 저장된다.
- 브라우저 계산식(bom-calc.js)은 서버 기본 숫자로 설계서 견본과 같은 줄을 내고,
  저장 직전 정리(sanitize) 결과는 서버 검증을 늘 통과한다.
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
JS = {name: ROOT / f"static/js/drawing/{name}.js" for name in ("bom-calc", "bom-rules", "bom-panel")}
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


def test_rules_create_bump_conflict_and_audit(app):
    assert load_bom_rules(db_session) == {"rules": DEFAULT_RULES, "label": "d1", "version": 0}
    with pytest.raises(BomRulesPreconditionError):
        update_bom_rules(db_session, actor_user_id=None, payload={}, if_match_version=None)
    db_session.rollback()

    first = update_bom_rules(db_session, actor_user_id=None, payload={"rod_cut": 40}, if_match_version=0)
    db_session.commit()
    assert first["version"] == 1 and first["label"] == "s1" and first["rules"]["rod_cut"] == 40
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
    denied = client.post(RULES_URL, json={"rules": {"rod_cut": 40}, "settings_version": 0})
    assert denied.status_code == 403

    _login(client, role="STAFF", team="DRAWING")
    assert client.get(RULES_URL).get_json()["data"]["can_edit"] is True
    missing = client.post(RULES_URL, json={"rules": {"rod_cut": 40}})
    assert missing.status_code == 428
    bad = client.post(RULES_URL, json={"rules": {"rod_cut": "많이"}, "settings_version": 0})
    assert bad.status_code == 400 and bad.get_json()["code"] == "BOM_RULES_SCHEMA"
    ok = client.post(RULES_URL, json={"rules": {"rod_cut": 40}, "settings_version": 0})
    assert ok.status_code == 200, ok.get_json()
    assert ok.get_json()["data"]["label"] == "s1"
    stale = client.post(RULES_URL, json={"rules": {"rod_cut": 41}, "settings_version": 0})
    assert stale.status_code == 409 and stale.get_json()["current_version"] == 1
    after = client.get(RULES_URL).get_json()["data"]
    assert after["rules"]["rod_cut"] == 40 and after["version"] == 1


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
process.stdout.write(JSON.stringify(out));
"""


def _run_calc(job):
    proc = subprocess.run([_node(), "-e", RUNNER, str(JS["bom-calc"]), json.dumps(job)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_calc_matches_spec_samples_and_sanitize_passes_server():
    s11 = {"line": "mold", "handle": "phoenix", "W": 3660, "D": 570, "H": 2300, "zone": 753,
           "mods": [{"w": 1000, "doors": 2, "drawers": 3, "rods": 1}, {"w": 1000, "doors": 2, "rods": 2},
                    {"w": 1000, "doors": 2, "rods": 2}, {"w": 500, "doors": 1, "rods": 2}]}
    s12 = {"line": "mold", "handle": "phoenix", "W": 3500, "D": 620, "H": 2305, "zone": 753,
           "mods": [{"w": 950, "doors": 2, "drawers": 3, "rods": 1}, {"w": 950, "doors": 2, "rods": 2},
                    {"w": 950, "rods": 1}, {"w": 488, "doors": 1}]}
    nomold = {"line": "nomold", "nomold": "ceiling", "handle": "other", "W": 2400, "D": 600, "H": 2400,
              "ep": 1, "mods": [{"w": 800, "doors": 2}]}
    res = _run_calc({
        "rules": DEFAULT_RULES, "specs": {"s11": s11, "s12": s12, "nomold": nomold},
        "messy": {"in": {"line": "kitchen", "W": "3500.4", "ep": 9, "mods": [{"w": -3, "doors": 9, "glass": 1}]},
                  "out": "a", "rules": "d1", "mode": "auto", "junk": 1},
        "huge": _calc(out="[옷봉]" * 500),
        "sheet": ["[SR] 120*2440=2\n보조목=4", "[DOOR]\n458*2160=3\n458*1407=2\n[옷봉]\n925=4\n[마이다]\n945*236=3"],
        "orphan_texts": ["483*2160=4\nㄴ피닉스바 2EA\n975=5", "[SR]\n60*2440=1"],
    })
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
    order = [html.index(f"js/drawing/{n}.js") for n in ("bom-calc", "bom-rules", "bom-panel", "wizard")]
    assert order == sorted(order)   # 계산 → 규칙 → 칸 → 마법사 순서로 실행(defer)
    for name in ("bom-calc", "bom-rules", "bom-panel"):
        tag = re.search(r'<script src="[^"]*' + name + r'\.js[^"]*"[^>]*>', html).group(0)
        assert "?v=" in tag and " defer" in tag
    assert 'id="dws-btn-calc"' in html and 'id="dws-calc"' in html
    wjs = WIZARD_JS.read_text(encoding="utf-8")
    assert "window.FomsBomCalc.sanitize(s.calc)" in wjs        # 저장에 calc 를 싣는다
    assert "if (s.calc && typeof s.calc === 'object') { sheet.calc = s.calc; }" in wjs   # 불러올 때 받는다
    assert "window.FomsBomPanel.sync()" in wjs
