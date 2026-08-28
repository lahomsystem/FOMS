"""커머스API 인증 만료일 **등록면** (2026-08-28).

왜 필요했나
-----------
만료일은 API 로 못 읽는다 — 커머스API센터 화면의 `인증 기한` 을 사람이 보고 옮겨 적는
값이다. 저장 함수(`app_expiry.set_expiry_date`)와 D-7 알림(`check_and_notify`)은 처음부터
있었는데 **값을 넣을 자리가 화면에 없었다.** 그래서 운영 카드는 늘 `미등록` 이었고,
만료되면 앱이 자동 휴면돼 수집이 전면 중단되는데도 경고가 한 번도 뜰 수 없었다.

이 파일이 무는 규율
-------------------
* 권한은 `지금 수집` 과 같은 **ADMIN 전용**(ADMIN_OPS).
* 형식이 깨진 값·상식 밖 연도는 저장하지 않는다 — 오타 한 자리가 경고를 영구히 끈다.
* 저장하면 카드가 그 값을 말한다(등록면과 표시면이 같은 값을 본다).
* 감사에 남는다.
"""

from __future__ import annotations

import datetime
import pathlib

from db import db_session
from models import SecurityLog

from tests.services.integrations.test_naver_workbench import (  # noqa: F401 - fixture 재사용
    _login,
    _uid,
    workbench_on,
)

EXPIRY_PATH = "/admin/naver-ingest/app-expiry"
TRIAGE_PATH = "/admin/naver-ingest/triage"


def _read(client):
    from foms.services.integrations.naver_commerce import app_expiry

    return app_expiry.read_expiry_date(db_session)


def test_admin_can_register_the_expiry_date(client, workbench_on):
    """ADMIN 이 날짜를 적으면 저장되고, 남은 일수까지 돌려준다."""
    _login(client)
    target = datetime.date.today() + datetime.timedelta(days=40)

    response = client.post(EXPIRY_PATH, json={"expires_on": target.isoformat()})
    body = response.get_json()

    assert response.status_code == 200, body
    assert body["success"] is True
    assert body["data"]["expires_on"] == target.isoformat()
    assert body["data"]["days_left"] == 40
    assert _read(client) == target


def test_the_card_says_the_registered_date(client, workbench_on):
    """등록면과 표시면이 같은 값을 본다 — 저장했는데 카드가 `미등록` 이면 안 된다."""
    _login(client)
    target = datetime.date.today() + datetime.timedelta(days=200)
    client.post(EXPIRY_PATH, json={"expires_on": target.isoformat()})

    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)

    assert target.isoformat() in body
    assert "미등록" not in body.split('id="wb-ingest-status"')[1].split("</section>")[0]


def test_history_card_offers_the_input_even_when_unset(client, workbench_on):
    """`미등록` 상태에서도 적을 칸이 있다 — 없으면 영원히 미등록이다."""
    _login(client)

    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)
    card = body.split('id="wb-ingest-status"')[1].split("</section>")[0]

    assert "미등록" in card
    assert 'id="wb-expiry-input"' in card and 'id="wb-expiry-save"' in card
    assert 'type="date"' in card, "달력 칸이라야 형식 오타가 애초에 안 난다"


def test_broken_format_is_refused(client, workbench_on):
    """형식이 깨진 값은 저장하지 않는다(조용히 무시하지도 않는다)."""
    _login(client)

    response = client.post(EXPIRY_PATH, json={"expires_on": "2027/02/23"})

    assert response.status_code == 400
    assert response.get_json()["success"] is False
    assert _read(client) is None


def test_year_typo_far_outside_is_refused(client, workbench_on):
    """연도 한 자리 오타(2207)는 막는다 — 통과하면 경고가 영원히 안 뜬다."""
    _login(client)

    response = client.post(EXPIRY_PATH, json={"expires_on": "2207-02-23"})

    assert response.status_code == 400
    assert "5년" in response.get_json()["error"]
    assert _read(client) is None


def test_non_admin_cannot_register(client, workbench_on):
    """STAFF 는 못 적는다 — `지금 수집` 과 같은 ADMIN 전용 축이다."""
    _login(client, role="STAFF")
    target = datetime.date.today() + datetime.timedelta(days=10)

    response = client.post(EXPIRY_PATH, json={"expires_on": target.isoformat()})

    assert response.status_code in (302, 403)
    assert _read(client) is None


def test_registering_is_audited(client, workbench_on):
    """수집이 멈춘 뒤 '누가 언제 무엇으로 바꿨나'를 묻게 되는 값이라 기록에 남긴다."""
    _login(client)
    target = datetime.date.today() + datetime.timedelta(days=15)

    client.post(EXPIRY_PATH, json={"expires_on": target.isoformat()})

    rows = (db_session.query(SecurityLog)
            .filter(SecurityLog.action == "NAVER_INGEST_SET_APP_EXPIRY").all())
    assert rows, "감사 기록이 없다"


def test_changing_the_date_rearms_the_warning(client, workbench_on):
    """날짜를 바꾸면 임계값 알림 이력이 지워진다 — 갱신했으면 다시 알려야 한다."""
    from foms.services.integrations.naver_commerce import app_expiry

    _login(client)
    first = datetime.date.today() + datetime.timedelta(days=3)
    client.post(EXPIRY_PATH, json={"expires_on": first.isoformat()})
    app_expiry.check_and_notify(db_session)
    db_session.commit()

    second = datetime.date.today() + datetime.timedelta(days=365)
    client.post(EXPIRY_PATH, json={"expires_on": second.isoformat()})

    row = db_session.get(__import__("models").SystemSetting, app_expiry.SETTING_KEY)
    assert list(row.setting_value.get("notified") or []) == []


def test_js_wires_the_save_button_to_the_route() -> None:
    """저장 버튼이 그 라우트를 문다 — 화면에 칸만 있고 배선이 없으면 아무 일도 안 난다."""
    js = pathlib.Path("static/js/admin/naver-workbench.js").read_text(encoding="utf-8")

    assert "'wb-expiry-save': submitExpiry" in js, "버튼 id 가 핸들러에 안 걸렸다"
    tail = js.split("async function submitExpiry")[1]
    body = tail.split("    /**")[0]
    assert "'/admin/naver-ingest/app-expiry'" in body
    assert "await softRefresh()" in body, (
        "저장 뒤 카드가 남은 일수·D-7 경고를 다시 그려야 한다(통째 이동은 하지 않는다)")
