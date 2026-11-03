"""답 길이 5단계(사장님 11-03 — '간결하게 ~ 자세하게') — 관리 화면 '답 길이' 칸이 지시문의 길이 문장 하나만 바꾼다.

3(처음 값)은 예전 문장 그대로라 줄이 없으면 요청이 예전과 같다(음성 대조). 출력 토큰 칸은 잘림을 막는 상한이라 그대로 둔다.
가짜 클라이언트만(네트워크 · 키 없음) — 픽스처는 ``test_cs_brain_settings`` · ``test_cs_admin_panel_api`` 것을 쓴다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.cs_agent import brain_instructions as bi
from foms.services.cs_agent import brain_prompt as bp
from foms.services.cs_agent import settings as st
from tests.domains.test_cs_admin_panel_api import API, env, login  # noqa: F401 — env 는 픽스처
from tests.domains.test_cs_brain import request
from tests.domains.test_cs_brain_settings import actor, call, configure  # noqa: F401 — actor 는 픽스처

OLD_SENTENCE = "답은 직원 말투처럼 짧고 공손한 한국어로, 빈 줄로 나눈 덩어리마다 120자 안쪽으로 쓴다."


def test_default_level_keeps_the_old_sentence():
    assert bi.LENGTH_DEFAULT == 3 and bi.LENGTH_RULES[3] == OLD_SENTENCE
    text = bp.instructions("LAHOM")
    assert text == bp.instructions("LAHOM", 3)
    assert f"판단 칸을 낸다. {OLD_SENTENCE}\n\n꼭 지킬 것" in text


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5])
def test_each_level_changes_only_the_length_sentence(level):
    text = bp.instructions("LAHOM", level)
    assert text.count(bi.LENGTH_RULES[level]) == 1
    assert not any(rule in text for key, rule in bi.LENGTH_RULES.items() if key != level)
    assert text.replace(bi.LENGTH_RULES[level], OLD_SENTENCE) == bp.instructions("LAHOM")  # 다른 줄은 그대로


def test_unknown_level_is_refused_by_the_prompt():
    with pytest.raises(KeyError):
        bp.instructions("LAHOM", 6)


def test_panel_field_is_five_steps_from_short_to_detailed(app):
    field = st.FIELD_BY_NAME["draft_length"]
    assert (field.kind, field.default, field.locked, field.group) == (st.KIND_CHOICE, 3, False, st.FIELDS[0].group)
    assert [value for value, _label in field.choices] == [1, 2, 3, 4, 5] == sorted(bi.LENGTH_RULES)
    assert st.value_label("draft_length", 1) == "1 · 아주 간결하게" and st.value_label("draft_length", 5) == "5 · 아주 자세하게"
    for bad in (0, 6, "3", 3.5, True, None):
        assert st.check_value(field, bad) == (False, None), bad


def test_the_brain_sends_the_chosen_length(actor):
    _, fake = call()
    assert fake.calls[0]["system"][0]["text"] == bp.instructions("LAHOM")  # 줄 없음 = 예전 그대로
    configure(actor, draft_length=1)
    _, fake = call()
    assert bi.LENGTH_RULES[1] in fake.calls[0]["system"][0]["text"]
    configure(actor, draft_length=5)
    _, fake = call(request(purpose="intent"))  # 의도 고르기도 같은 앞부분을 쓴다(캐시를 함께 쓴다)
    assert fake.calls[0]["system"][0]["text"] == bp.instructions("LAHOM", 5)


def test_the_panel_shows_five_steps_and_saves_a_number(client, env):
    login(client)
    html = client.get("/admin/cs-agent").get_data(as_text=True)
    start = html.index('data-setting="draft_length"')
    select = html[start:html.index("</select>", start)]
    assert 'data-kind="choice-number"' in select  # 화면 JS 가 숫자로 보낸다
    assert [select.count(f'value="{level}"') for level in range(1, 6)] == [1] * 5
    assert "3 · 보통" in select and "아주 간결하게" in select and "아주 자세하게" in select
    saved = client.post(f"{API}/settings", json={"values": {"draft_length": 4}, "expected_version": 0})
    assert saved.status_code == 200 and st.read_settings(db_session).get("draft_length") == 4
    refused = client.post(f"{API}/settings", json={"values": {"draft_length": 9}, "expected_version": 1})
    assert refused.status_code == 400
