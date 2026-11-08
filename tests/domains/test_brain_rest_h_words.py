"""회사 지식 남은 후보 3차 일꾼 H — 오류 글 · 어려운 낱말(점검 후보 15 · F19).

- H1 지식 카드 '고칠 말 제안'이 꼴 오류로 막히면 서버 문제 글('칸 자리: 까닭' — 칸 코드 · 반말 · 결정 번호)을 화면이 칸
  이름표 · 해요체로 바꿔 붙인다(``static/js/brain/brain-view.js`` ``problemText`` · ``problemLine``). **서버 글 꼴은 그대로**다 —
  시험 · 옮기기 도구 · 지식 문서 다시 만들기가 칸 자리로 읽는다(음성 대조군). 실제 카드 화면 HTML · 실제 API 답 · 실제
  스크립트(brain-item-actions.js)로 화면에 붙는 글을 본다.
- H2 지식 표 거르기 · 머리 '층' → '쓰는 팀', '확신' → '확실한 정도'(칸 이름만 — 저장 값 · 고르기 값 그대로), 카드 배지는 값만,
  물어보기 답 줄 '근거: … · 답이 맞을 가능성: …'(test_brain_chat_js), 수정 기록 '바뀐 칸' 이름표.
합성 계정 · 합성 항목만.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import subprocess

from db import db_session
from foms.services.brain import actions
from foms.services.brain.constants import CONFIDENCES, LAYERS
from foms.services.brain.display import CONFIDENCE_LABELS, FIELD_LABELS, LAYER_LABELS, display_table
from foms.services.brain.errors import BrainShapeError
from foms.services.brain.gates import object_problems
from foms.services.brain.schemas import TYPE_SCHEMAS, schema_problems
from tests.domains.test_brain_fix_inbox_js import HARNESS, NODE, ROOT
from tests.support.brain_review_support import DOC, review_world
from tests.support.brain_support import create

JS = ROOT / "static/js/brain"
CARD_SCRIPTS = [str(JS / n) for n in ("brain-view.js", "brain-dom.js", "brain-review-view.js", "brain-item-actions.js")]
SHAPE = actions.FAILURES["BRAIN_SHAPE"]
OK_REPLY = "  return { status: 200, json: async () => ({ success: true, data: data }) };"
# 가짜 fetch 가 POST 마다 input.replies 의 실제 서버 답(상태 · JSON)을 차례로 돌려주게
REPLY_HARNESS = HARNESS.replace(OK_REPLY, (
    "  if (method !== 'GET' && (input.replies || []).length) {\n"
    "    const r = input.replies.shift();\n"
    "    return { status: r.status, json: async () => r.json };\n"
    "  }\n" + OK_REPLY))
CARD_TAG = re.compile(r'<div class="[^"]*\bbrain-card\b[^"]*"([^>]*\sdata-brain-card[\s>][^>]*)>')
ATTR = re.compile(r'([\w-]+)(?:="([^"]*)")?')
# 화면 글에 남으면 안 되는 것 — 칸 코드(뱀 꼴 · 실음 칸 자리 · 값 칸 이름) · 결정 번호 · 반말 끝 · '항목'
CODE = re.compile(r"[a-z]+_[a-z_]+|payload|\b(?:name|text|key|reason|after|valid|status)\b|\(D\d|항목")


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _node_view(expr: str, data: object):
    script = (f"const v = require({json.dumps(str(JS / 'brain-view.js'))});"
              "const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], input=json.dumps(data, ensure_ascii=False), capture_output=True,
                         text=True, encoding="utf-8", timeout=60, check=True).stdout
    return json.loads(out)


def _card_page(client, key: str) -> tuple[dict, str]:
    """실제 카드 화면 — 뿌리 칸(data-*)과 '고치기' 칸 HTML."""
    page = client.get(f"/brain/items/{key}").get_data(as_text=True)
    tag = CARD_TAG.search(page)
    assert tag, "카드 뿌리(data-brain-card)를 못 찾음"
    attrs = {k: html_lib.unescape(v or "") for k, v in ATTR.findall(tag.group(1))}
    start = page.index('<section class="brain-section brain-propose"')
    return attrs, page[start:page.index("</section>", start) + len("</section>")]


def _drive_card(attrs: dict, html: str, cases: list[dict], replies: list[dict]) -> dict:
    """카드 스크립트로 '고칠 말 제안'을 칸 값만 바꿔 보내고(가짜 fetch 가 실제 서버 답을 돌려줌) 알림 줄 글을 읽는다."""
    body = f"const cases = {json.dumps(cases, ensure_ascii=False)};" + """
      const out = [];
      for (const c of cases) {
        await api.click(api.q('[data-brain-propose-open="propose_edit"]'));
        Object.keys(c).forEach(name => { api.q('[data-brain-field="' + name + '"]').value = c[name]; });
        api.q('[name="reason"]').value = '합성 시험 까닭';
        api.q('[data-brain-propose-form]').dispatchEvent({ type: 'submit', preventDefault() {} });
        for (let i = 0; i < 10; i += 1) await new Promise(r => setTimeout(r, 0));
        const box = api.q('[data-brain-propose-status]');
        out.push({ text: api.text(box), error: box.classList.contains('is-error') });
      }
      return { out: out, posts: api.posts.map(p => p.body) };"""
    payload = {"scripts": CARD_SCRIPTS, "html": html, "attrs": attrs, "cards": [], "replies": replies, "body": body}
    out = subprocess.run(["node", "-e", REPLY_HARNESS], input=json.dumps(payload, ensure_ascii=False),
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def _post(client, attrs: dict, after: dict) -> tuple[dict, dict]:
    """화면이 보낼 본문 그대로 실제 API 로 — (본문, {status, json})."""
    body = {"action": "propose_edit", "key": attrs["data-brain-key"], "base_version": int(attrs["data-brain-version"]),
            "reason": "합성 시험 까닭", "after": after}
    res = client.post("/api/brain/proposals", json=body)
    return body, {"status": res.status_code, "json": res.get_json()}


# ── H1 실제 카드 화면에 붙는 글 ──────────────────────────────────────────
@NODE
def test_card_propose_failure_line_uses_field_names_and_polite_endings(app):
    assert REPLY_HARNESS != HARNESS  # 가짜 fetch 답 꼴이 바뀌면 여기서 먼저 알린다
    world = review_world(db_session)
    admin = world["people"]["admin"]
    create(db_session, admin, "common/policy/sale", item_type="policy", name="합성 판촉 정책", text="합성 판촉 정책 글",
           checked_at="2026-10-20", payload={"doc_id": "sale", **DOC})
    db_session.commit()
    client = _client(app, admin.id)

    door_attrs, door_html = _card_page(client, "common/door")
    door_cases = [{"payload.lead_days": "500"}, {"valid_from": "2026-12-31", "valid_to": "2026-12-01"},
                  {"payload.lead_days": "30"}]  # 마지막은 대조군(맞는 값 — 올라감)
    door = [_post(client, door_attrs, after) for after in (
        {"payload.lead_days": 500}, {"valid_from": "2026-12-31", "valid_to": "2026-12-01"}, {"payload.lead_days": 30})]
    got = _drive_card(door_attrs, door_html, door_cases, [reply for _body, reply in door])
    assert got["posts"] == [body for body, _reply in door]  # 화면이 보낸 본문 = 서버에 보낸 본문(답이 그 본문의 답)
    # 서버 글 꼴은 그대로(칸 자리: 까닭 — 시험 · 도구가 칸 자리로 읽는다)
    assert door[0][1]["json"]["data"]["problems"] == ["payload.lead_days: 제작 기간 — 1 ~ 180일 안이어야 한다"]
    assert door[1][1]["json"]["data"]["problems"] == ["valid_from: valid_to 보다 늦다"]
    assert got["out"][0] == {"text": f"{SHAPE} (제작 기간 — 1 ~ 180일 안이어야 해요)", "error": True}
    assert got["out"][1] == {"text": f"{SHAPE} (유효 시작 — 유효 끝보다 늦어요)", "error": True}
    assert door[2][1]["status"] == 200 and got["out"][2] == {"text": "'승인 대기'에 올렸어요. 승인 대기에서 보기",
                                                             "error": False}

    sale_attrs, sale_html = _card_page(client, "common/policy/sale")
    sale = _post(client, sale_attrs, {"payload.policy_kind": "promotion"})
    got = _drive_card(sale_attrs, sale_html, [{"payload.policy_kind": "promotion"}], [sale[1]])
    assert got["posts"] == [sale[0]]
    assert sale[1]["json"]["data"]["problems"] == ["valid_to: 판촉 정책은 유효 끝이 꼭 있어야 한다(D124)"]
    assert got["out"] == [{"text": f"{SHAPE} (판촉 정책은 유효 끝이 꼭 있어야 해요)", "error": True}]  # 결정 번호 뺌


# ── H1 서버가 만드는 문제 글 모두(카드 칸으로 닿는 것) ─────────────────────
def _bad_values(prop) -> list:
    """틀 칸 하나에 넣어 볼 틀린 값들(자료형 · 범위 · 길이 · 꼴 · 고른 값)."""
    kind = prop.datatype
    if kind in ("int", "number"):
        return ["열", 10 ** 12] + ([1.5] if kind == "int" else [])
    if kind == "date":
        return ["2026-13-40"]
    if kind == "datetime":
        return ["어제 저녁"]
    if kind == "enum":
        return ["nope"]
    if kind == "list":
        return [["nope"] if prop.choices else ["x"] * 30]
    return ["x" * ((prop.max_len or 2000) + 1)] + (["X12"] if prop.pattern else [])


def _server_problems() -> list[str]:
    """실제 검사 함수가 내는 문제 글 — 틀 칸마다 틀린 값 · 빈 꼭 칸 · 짝 칸 · 날짜 차례 · 이름 · 글 · 액션 매개변수."""
    seen: list[str] = []
    for item_type, props in TYPE_SCHEMAS.items():
        for prop in props:
            for bad in _bad_values(prop):
                values = {"status": "active", "text": "합성"}
                if prop.path.startswith("payload."):
                    values["payload"] = {prop.path[len("payload."):]: bad}
                else:
                    values[prop.path] = bad
                seen += schema_problems(values, item_type)
        seen += schema_problems({"status": "active"}, item_type)  # 꼭 있어야 하는 칸
    seen += schema_problems({"status": "active", "text": "합성", "payload": {"value": 5, "low": 9, "high": 1}}, "spec")
    seen += schema_problems({"status": "active", "text": "합성", "payload": {"policy_kind": "promotion"}}, "policy")
    base = {"name": "합성", "text": "합성", "status": "active", "confidence": "confirmed", "visibility": "all"}
    for extra in ({"valid_from": "2026-12-31", "valid_to": "2026-12-01"}, {"valid_from": "내일"}, {"name": ""},
                  {"text": "x" * 2001}):
        seen += object_problems({**base, **extra}, brand="COMMON", layer="common", item_type="term")
    for body in ({"key": "Common/Door", "base_version": 1, "after": {"text": "x"}, "reason": "합성"},
                 {"key": "common/door", "base_version": "1", "after": {"text": "x"}},
                 {"key": "common/door", "base_version": 1, "after": [], "reason": "합성"}):
        try:
            actions.parse("propose_edit", body)
        except BrainShapeError as exc:
            seen += exc.problems
    return sorted(set(seen))


@NODE
def test_every_server_problem_reads_as_people_words_on_the_card():
    problems = _server_problems()
    assert len(problems) > 60  # 틀 칸 · 날짜 · 이름 · 액션 매개변수를 다 돌았다
    raw = [p for p in problems if CODE.search(p)]
    assert len(raw) == len(problems)  # 음성 대조군 — 서버 글에는 칸 코드가 다 있다(화면이 바꿔야 할 것)
    shown = _node_view("data.p.map(p => v.problemText(p, data.d))", {"p": problems, "d": display_table()})
    bad = [(p, s) for p, s in zip(problems, shown) if CODE.search(s) or not s.endswith("요") or "1e+" in s or "ISO" in s]
    assert bad == []
    picked = dict(zip(problems, shown))
    assert picked["valid_from: valid_to 보다 늦다"] == "유효 시작 — 유효 끝보다 늦어요"
    assert picked["key: 항목 키 꼴이 맞지 않는다"] == "지식 키 꼴이 맞지 않아요"
    assert picked["reason: 꼭 있어야 한다"] == "까닭 — 꼭 있어야 해요"
    assert picked["text: 2000자 이하 글이어야 한다"] == "글 — 2000자 이하 글이어야 해요"  # 한 글자 이름표도 붙는다
    assert picked["text: 설명 칸이 꼭 있어야 한다"] == "설명 칸이 꼭 있어야 해요"  # 틀 글은 이름표가 이미 있다
    assert picked["payload.quote_kind: 견적 규칙 종류 — hinge / slide / linear / none 가운데 하나여야 한다"] == (
        "견적 규칙 종류 — 여닫이 / 슬라이딩 / cm 비례 / 최소 없음 가운데 하나여야 해요")  # 고르기 값도 이름표로
    assert picked["payload.decision_no: 결정 번호 — 꼴(D\\d{1,5})이 맞지 않는다"] == "결정 번호 — 꼴이 맞지 않아요"
    assert picked["payload.low: 아래 끝이 위 끝보다 크다"] == "아래 끝이 위 끝보다 커요"
    assert picked["payload.band_high: 값 위 끝 — 0 ~ 100,000,000원 안이어야 한다"] == (
        "값 위 끝 — 0 ~ 100,000,000원 안이어야 해요")  # 범위 끝은 쉼표 꼴(옛 1e+08 아님)
    assert picked["payload.occurred_at: 일어난 때 — 시각(YYYY-MM-DD HH:MM)이어야 한다"] == (
        "일어난 때 — 시각(YYYY-MM-DD HH:MM)이어야 해요")  # 옛 '— ISO' 꼴 아님
    assert schema_problems({"payload": {"occurred_at": "2026-11-08 14:30"}}, "case") == []  # 글이 알려 준 꼴은 받는다
    assert picked["payload.value: 값이 아래 끝 ~ 위 끝 밖이다"] == "값이 아래 끝 ~ 위 끝 밖이에요"


@NODE
def test_failure_line_keeps_the_fixed_message_and_param_names_follow_the_action_list():
    params = {p.name: p.label for a in actions.ACTIONS.values() if a.stage == "propose" for p in a.params}
    names = sorted(n for n in params if n not in FIELD_LABELS)
    problems = [f"{name}: 꼭 있어야 한다" for name in names]
    got = _node_view("[data.p.map(p => v.problemText(p, data.d)), v.problemLine('막혔어요.', null, data.d),"
                     " v.problemLine('막혔어요.', [], data.d), v.problemLine('막혔어요.', data.p.slice(0, 2), data.d)]",
                     {"p": problems, "d": display_table()})
    assert names == ["after", "base_version", "key", "reason", "to_version"]
    assert got[0] == [f"{params[n]} — 꼭 있어야 해요".replace("항목", "지식") for n in names]  # 액션 목록 이름표와 같다
    assert got[1] == got[2] == "막혔어요."  # 문제 글이 없으면 정한 말만
    assert got[3] == "막혔어요. (고칠 칸 — 꼭 있어야 해요 · 기준 판 — 꼭 있어야 해요)"


# ── H2 어려운 낱말 ───────────────────────────────────────────────────────
def test_table_filters_and_head_say_team_and_certainty_with_values_untouched(app):
    world = review_world(db_session)
    page = _client(app, world["people"]["admin"].id).get("/brain?tab=table").get_data(as_text=True)
    start = page.index("data-brain-table-form")
    pane = page[start:page.index("data-brain-table-pager", start)]
    assert re.search(r">쓰는 팀\s*<select [^>]*name=\"layer\"", pane)
    assert re.search(r">확실한 정도\s*<select [^>]*name=\"confidence\"", pane)
    assert '<th scope="col">쓰는 팀</th>' in pane and '<th scope="col">확실한 정도</th>' in pane
    assert not re.search(r">\s*(?:층|확신)\s*<", pane)  # 옛 칸 이름 없음
    for value in LAYERS:  # 고르기 값 · 이름은 그대로
        assert f'<option value="{value}"' in pane
        assert f'data-label="{LAYER_LABELS[value]}">{LAYER_LABELS[value]}</option>' in pane
    for value in CONFIDENCES:
        assert f'data-label="{CONFIDENCE_LABELS[value]}">{CONFIDENCE_LABELS[value]}</option>' in pane
    assert [LAYER_LABELS[v] for v in LAYERS] == ["공통 바탕", "상담", "도면", "생산"]
    assert [CONFIDENCE_LABELS[v] for v in CONFIDENCES] == ["확정", "근거 있음", "관찰"]


def test_card_certainty_badge_shows_only_the_value_and_history_field_name(app):
    world = review_world(db_session)
    page = _client(app, world["people"]["admin"].id).get("/brain/items/common/door").get_data(as_text=True)
    more = page[page.index("data-brain-card-more"):]
    assert '<span class="brain-badge brain-badge--confirmed">확정</span>' in more
    assert "확신 확정" not in page and ">확신 " not in page
    assert FIELD_LABELS["confidence"] == "확실한 정도"  # 수정 기록 '바뀐 칸' · 승인 대기 칸 이름
    assert display_table()["fields"]["confidence"] == "확실한 정도"
