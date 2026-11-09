"""[수정하기] 화면 고침(플랜 C10-7) — 운영에서 직원이 [보내기]를 눌렀는데 안 보내졌다.

원인: '고친 까닭' 첫 값이 빈 '고르기'였고, 화면은 빈 까닭이면 맨 위 알림 칸에만 '골라 주세요'를 띄우고 보내지 않았다 — 맨 아래
[보내기] 근처에선 그 알림이 안 보였다. 고친 것: ① 까닭은 안 골라도 보낸다(서버 · 화면 둘 다, 빈 까닭은 ``None`` 으로 저장, 목록
밖 값은 계속 400) ② 알림 칸을 [보내기] 바로 위로 옮기고 알림이 뜨면 보이게 스크롤 ③ '고칠 말'은 여러 줄 textarea, 두 글 칸은
글에 맞춰 높이가 는다.

채널톡 · 두뇌는 가짜(네트워크 없음), 손으로 꾸민 합성 글만. 시각은 2026-11 KST(11-02 월).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from db import db_session
from foms.services.cs_agent import send_flow
from foms.services.cs_agent.brain_cases import QUOTE, rewrite_lines
from tests.domains.test_cs_drafting import DRAFT, channel  # noqa: F401 — channel 은 fixture
from tests.domains.test_cs_send import FakeSender, fresh, posted, press, token, user
from tests.domains.test_cs_send_parts import login, ready  # noqa: F401 — ready 는 fixture(화면 읽기도 가짜)
from tests.support.cs_agent_fakes import at, keys  # noqa: F401 — keys 는 fixture

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "static/js/cs-agent/send-screen.js"
TEMPLATE = ROOT / "templates/cs/cs_agent_send.html"
EDITED = "합성 고친 답입니다."
NOTE_LINES = "더 짧게 써 주세요\n실측 안내를 먼저"


# ── ① 까닭은 안 골라도 보낸다(서버) ───────────────────────────────────────
@pytest.mark.parametrize("reason", [None, ""])
def test_an_edit_without_a_reason_is_sent_and_the_reason_is_left_empty(app, ready, reason):
    staff = user()
    turn_id = posted(ready)
    sender = FakeSender(ready)
    result = press(app, ready, turn_id, staff.id, sender, mode="edited", text=EDITED, edit_reason=reason)
    assert result.code == "sent" and [c.text for c in sender.calls] == [EDITED]
    row = fresh(turn_id)
    assert (row.outcome, row.edit_reason) == ("edited", None) and 0 < row.edit_ratio <= 1


def test_a_chosen_reason_is_still_kept(app, ready):
    staff = user()
    turn_id = posted(ready)
    assert press(app, ready, turn_id, staff.id, FakeSender(ready), mode="edited", text=EDITED,
                 edit_reason="tone").code == "sent"
    assert fresh(turn_id).edit_reason == "tone"


@pytest.mark.parametrize("reason", ["wat", " ", "TONE", 0, False, ["tone"]])
def test_a_reason_outside_the_list_is_still_refused(app, ready, reason):
    staff = user()
    turn_id = posted(ready)
    sender = FakeSender(ready)
    result = press(app, ready, turn_id, staff.id, sender, mode="edited", text=EDITED, edit_reason=reason)
    assert (result.code, result.status, result.data) == ("bad_request", 400, {"field": "edit_reason"})
    assert sender.calls == [] and fresh(turn_id).send_state is None


def test_the_empty_reason_rule_in_one_place():
    assert [send_flow.edit_reason_or_none(v) for v in (None, "", "tone", " ", 0)] == [None, None, "tone", " ", 0]


# ── ③ '고칠 말'은 여러 줄(서버는 줄 바꿈을 받고 두뇌 재료도 줄마다 앞표) ──────────
def test_a_multi_line_note_is_accepted_and_quoted_line_by_line(app, ready):
    staff = user()
    turn_id = posted(ready)
    asked = send_flow.request_rewrite(db_session, turn_id=turn_id, user_id=staff.id, token=token(app, turn_id, staff.id),
                                      note=NOTE_LINES, secret_key=app.secret_key, now=at(2, 9))
    row = fresh(turn_id)
    assert asked.code == "rewrite_requested" and row.rewrite_note_masked == NOTE_LINES
    lines = rewrite_lines((DRAFT, row.rewrite_note_masked))
    assert lines[-2:] == [f"{QUOTE}더 짧게 써 주세요", f"{QUOTE}실측 안내를 먼저"]


def test_a_note_over_the_cap_counts_line_breaks_and_is_refused(app, ready):
    staff = user()
    turn_id = posted(ready)
    note = "가\n" * (send_flow.MAX_NOTE // 2) + "가"
    asked = send_flow.request_rewrite(db_session, turn_id=turn_id, user_id=staff.id, token=token(app, turn_id, staff.id),
                                      note=note, secret_key=app.secret_key, now=at(2, 9))
    assert (asked.code, asked.data) == ("bad_request", {"field": "note"}) and fresh(turn_id).rewrite_state is None


# ── ② · ③ 화면(알림 칸은 [보내기] 바로 위 · 글 칸 두 개는 높이가 는다) ──────────
def test_the_edit_screen_puts_the_notice_right_above_send_and_grows_both_boxes(client, ready):
    turn_id = posted(ready)
    login(client, user())
    html = client.get(f"/cs-agent/turns/{turn_id}/edit?c=uc-1").get_data(as_text=True)
    order = [html.index(n) for n in ("data-cs-send-text", "data-cs-send-reason", "data-cs-rewrite-note",
                                     "data-cs-send-notice", "data-cs-send-msg", "data-cs-send-warnings", "data-cs-send-go")]
    assert order == sorted(order)
    assert '<input type="text"' not in html and 'id="cs-send-note" data-cs-rewrite-note data-cs-autosize' in html
    assert html.count("data-cs-autosize") == 2 and html.count("data-cs-send-msg") == 1
    assert '<option value="">고르지 않음</option>' in html and "안 골라도 보내져요" in html


def test_the_as_is_screen_also_puts_the_notice_right_above_send(client, ready):
    turn_id = posted(ready)
    login(client, user())
    html = client.get(f"/cs-agent/turns/{turn_id}/send?c=uc-1").get_data(as_text=True)
    assert html.index("data-cs-send-draft") < html.index("data-cs-send-notice") < html.index("data-cs-send-go")
    assert "data-cs-autosize" not in html and html.count("data-cs-send-msg") == 1


def test_a_fresh_customer_message_still_shows_at_the_top_on_open(client, ready):
    from tests.support.cs_agent_fakes import api_message
    turn_id = posted(ready)
    ready.messages["uc-1"].append(api_message("m-new", at(2, 8, 55), "user", "합성 손님 새 글"))
    login(client, user())
    html = client.get(f"/cs-agent/turns/{turn_id}/edit?c=uc-1").get_data(as_text=True)
    note = send_flow.MESSAGES["new_message"]
    assert note in html and html.index(note) < html.index("data-cs-send-text")


def test_the_screen_script_no_longer_demands_a_reason_and_reveals_the_notice():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "고친 까닭을 골라" not in script and "!body.edit_reason" not in script
    assert "scrollIntoView" in script and "[data-cs-send-notice]" in script
    assert "[data-cs-autosize]" in script and "addEventListener('input'" in script and "'paste'" in script
    css = (ROOT / "static/css/foundation/erp-pro.css").read_text(encoding="utf-8")
    for rule in (".cs-send__grow {", ".cs-send__grow.is-fit {", ".cs-send__note {", ".cs-send__notice {"):
        assert rule in css, rule
    html = TEMPLATE.read_text(encoding="utf-8")
    assert "send-screen.js') }}?v=20261104a" in html and "erp-pro.css') }}?v=20261109a" in html  # 17.6.1 에서 올림


# ── JS 순수 함수(node) ──────────────────────────────────────────────────
def _node(expr: str):
    script = ("global.window={};global.document={querySelector(){return null}};"
              f"require({json.dumps(str(SCRIPT))});"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60,
                         check=True).stdout
    return json.loads(out)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_the_send_body_needs_text_but_not_a_reason():
    m = "window.FOMS_CS_SEND"
    no_reason, empty, as_is = _node(
        f"[{m}.sendBody({{mode:'edit',token:'t',text:'가\\n나',reason:'',confirm:null,shownMs:1200}}),"
        f"{m}.sendBody({{mode:'edit',token:'t',text:'  \\n ',reason:'tone'}}),"
        f"{m}.sendBody({{mode:'send',token:'t',confirm:'c',shownMs:-5}})]")
    assert no_reason == {"error": "", "body": {"token": "t", "mode": "edited", "confirm": None, "shown_ms": 1200,
                                               "text": "가\n나", "edit_reason": None}}
    assert empty["error"] == "보낼 글이 비었어요."
    assert as_is == {"error": "", "body": {"token": "t", "mode": "as_is", "confirm": "c", "shown_ms": 0}}


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_the_box_grows_with_the_text_up_to_its_max_height():
    m = "window.FOMS_CS_SEND.fitSize"
    sizes = _node(f"[{m}(120,2,NaN),{m}(120.4,2,400),{m}(900,2,400),{m}(0,2,400)]")
    assert sizes == [{"height": 122, "capped": False}, {"height": 123, "capped": False},
                     {"height": 400, "capped": True}, {"height": 2, "capped": False}]
