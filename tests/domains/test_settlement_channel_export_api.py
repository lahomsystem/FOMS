"""SETTLE-CHANNEL v1.1 T14: ``GET /api/settlement/channel/export.csv`` **라우트** 계약.

커널(:mod:`foms.services.settlement_channel_export`)의 컬럼표·부호·마스킹·47필드 소진은
``test_settlement_channel_export.py`` 가 덮는다. **이 파일은 그걸 중복하지 않는다.**
여기서 잠그는 것은 파일이 HTTP 로 나가는 길목에서만 깨지는 것들이다:

1. **권한** — CSV 에는 구매자 성명이 실린다. 거부는 **JSON 403** 이어야 한다. 빈 CSV 나
   오류 CSV 를 파일 자리에 주면 회계 담당이 그걸 "그 기간에 정산이 없었다"로 읽는다.
2. **감사(계약 §1.3 C5)** — 다운로드 1회 = ``SecurityLog`` 1행. 성명이 나가는 경로라
   "누가 언제 무엇을 받아 갔는가"가 남지 않으면 이 기능은 열 수 없다.
   ``target_id`` 는 **정수 컬럼**이라 CSV 종류 같은 문자열을 넣으면 PostgreSQL 이 거절하고,
   ``log_access`` 는 fail-open 이라 감사 행이 **조용히 사라진다**(SQLite 로컬만 통과).
   그래서 종류는 ``detail`` 로 남기고 ``target_id`` 는 비운다 — 그 사실을 여기서 못 박는다.
3. **응답 헤더** — ``text/csv; charset=utf-8`` · ASCII 파일명 ``attachment`` ·
   ``nosniff`` · ``no-store``. 한글 파일명은 RFC 5987 함정에 걸리고, 캐시에 남으면 회계
   자료가 공용 PC 브라우저 캐시에 눌러앉는다.
4. **검증 실패 시점** — 종류·구간·조건 오류는 **스트림이 시작되기 전에** 400 JSON 이어야
   한다. 스트림이 시작된 뒤에 터지면 반쪽 파일이 200 으로 내려가고, 사람은 그걸 정상
   파일로 읽는다.
5. **조건 통과** — 화면에서 좁혀 놓고 받은 파일이 전체 기간이면 그 파일은 다른 질문의
   답이다. ``from``/``to``/``q`` 가 실제로 행을 좁힌다.

시드·권한 매트릭스 헬퍼는 ``test_settlement_channel_api.py`` 것을 그대로 쓴다(복제 금지 —
두 파일이 각자 시드를 만들면 한쪽만 갱신된다).
"""

from __future__ import annotations

import datetime

import pytest

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.settlement_channel_export import (
    CSV_COLUMNS,
    EXPORT_KINDS,
    export_filename,
)
from models import SecurityLog

# 권한 매트릭스·시드 SSOT 재사용(복제 금지).
from tests.domains.test_auth_finance import _login, _make_user
from tests.domains.test_settlement_channel_api import (
    _ALLOWED_ACTORS,
    _DENIED_ACTORS,
    _case,
    _daily,
    _seed_basic,
)

EXPORT_URL = "/api/settlement/channel/export.csv"

_AUDIT_ACTION = "NAVER_SETTLE_EXPORT_CSV"
_BOM = b"\xef\xbb\xbf"


# --------------------------------------------------------------------------
# 헬퍼
# --------------------------------------------------------------------------
def _url(**params) -> str:
    """쿼리 문자열을 붙인 내려받기 URL."""
    query = "&".join(f"{key}={value}" for key, value in params.items() if value != "")
    return f"{EXPORT_URL}?{query}" if query else EXPORT_URL


def _body(resp) -> str:
    """200 을 확인하고 본문 전체(BOM 포함)를 문자열로 돌려준다."""
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_data(as_text=True)


def _lines(resp) -> list:
    """CSV 줄 목록(끝의 빈 줄 제외). BOM 은 첫 줄 앞에 그대로 남는다."""
    return [line for line in _body(resp).split("\r\n") if line]


def _audit_rows() -> list:
    """이번 세션의 내보내기 감사 행 전량."""
    return (db_session.query(SecurityLog)
            .filter(SecurityLog.action == _AUDIT_ACTION)
            .order_by(SecurityLog.id.asc()).all())


def _seeded_window(today: datetime.date) -> tuple:
    """시드한 정산 예정일(오늘-1)을 포함하는 좁은 구간."""
    day = today - datetime.timedelta(days=1)
    return day.isoformat(), day.isoformat()


# --------------------------------------------------------------------------
# 1. 권한 매트릭스 — 거부는 파일이 아니라 JSON 이다
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", _ALLOWED_ACTORS)
def test_allowed_actors_receive_a_csv(client, app, role, team):
    """ADMIN·회계팀 MANAGER/STAFF 는 200 + CSV 본문(탭과 같은 게이트)."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role=role, team=team))

    resp = client.get(_url(kind="settle_case"))

    assert resp.status_code == 200, (role, team, resp.get_data(as_text=True))
    assert resp.mimetype == "text/csv", (role, team, resp.mimetype)


@pytest.mark.parametrize("role,team", _DENIED_ACTORS)
def test_denied_actors_get_403_json_not_a_file(client, app, role, team):
    """그 밖의 actor 는 403 **JSON** — **MANAGER+CS 포함**(엔진이라면 통과한다).

    빈 CSV·오류 CSV 를 주면 받는 사람이 "그 기간에 정산이 없었다"로 읽는다.
    """
    _login(client, _make_user(role=role, team=team))

    resp = client.get(_url(kind="settle_case"))

    assert resp.status_code == 403, (role, team, resp.status_code)
    assert resp.mimetype == "application/json", resp.mimetype
    assert "Location" not in resp.headers, "API 거부는 302 가 아니라 403 JSON"
    body = resp.get_json()
    assert body["success"] is False and body["data"] is None and body["error"]


def test_anonymous_is_not_served(client, app):
    """미인증은 로그인 리다이렉트(또는 401) — 절대 200 이 아니다."""
    assert client.get(_url(kind="settle_case")).status_code in (301, 302, 401)


def test_denied_actor_leaves_no_audit_row(client, app):
    """거부된 요청은 감사 행을 남기지 않는다(받아 가지 않았으므로 기록도 없다)."""
    before = len(_audit_rows())
    _login(client, _make_user(role="STAFF", team="CS"))

    client.get(_url(kind="settle_case"))

    assert len(_audit_rows()) == before


# --------------------------------------------------------------------------
# 2. 응답 헤더
# --------------------------------------------------------------------------
def test_content_type_declares_utf8(client, app):
    """``text/csv; charset=utf-8`` — 인코딩을 말하지 않으면 한글이 깨져 열린다."""
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(_url(kind="settle_case"))

    assert resp.headers["Content-Type"] == "text/csv; charset=utf-8", \
        resp.headers["Content-Type"]


@pytest.mark.parametrize("kind", EXPORT_KINDS)
def test_filename_is_ascii_and_attached(client, app, kind):
    """파일명은 커널이 만든 ASCII 이름 그대로다(한글 파일명은 RFC 5987 함정)."""
    today = get_today_kst()
    date_from, date_to = _seeded_window(today)
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(_url(kind=kind, **{"from": date_from, "to": date_to}))

    expected = export_filename(kind, datetime.date.fromisoformat(date_from),
                               datetime.date.fromisoformat(date_to))
    disposition = resp.headers["Content-Disposition"]
    assert disposition == 'attachment; filename="%s"' % expected, disposition
    assert disposition.isascii(), disposition


def test_response_is_not_cached_or_sniffed(client, app):
    """회계 자료가 공용 PC 캐시에 눌러앉지 않고, 브라우저가 타입을 추측하지 않는다."""
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(_url(kind="settle_case"))

    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


# --------------------------------------------------------------------------
# 3. 본문 — 커널이 만든 그대로 나간다
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kind", EXPORT_KINDS)
def test_body_starts_with_bom_and_the_contract_header(client, app, kind):
    """첫 줄은 BOM + 계약 헤더다(순서까지 — 회계 프로그램이 열 순서를 기억한다)."""
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(_url(kind=kind))

    raw = resp.get_data()
    assert raw.startswith(_BOM), raw[:12]
    headers = [header for header, _column, _tag in CSV_COLUMNS[kind]]
    assert _lines(resp)[0] == "﻿" + ",".join(headers)


def test_every_line_ends_with_crlf(client, app):
    """줄바꿈은 CRLF 다 — LF 만이면 일부 표 계산 프로그램이 한 줄로 읽는다."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))

    body = _body(client.get(_url(kind="settle_case")))

    assert body.endswith("\r\n")
    assert body.replace("\r\n", "").count("\n") == 0, "CRLF 아닌 줄바꿈이 있다"


def test_seeded_rows_reach_the_file(client, app):
    """시드한 건별 정산 행이 실제로 파일에 실린다(헤더만 나가는 회귀 방지)."""
    today = get_today_kst()
    _seed_basic(today)
    date_from, date_to = _seeded_window(today)
    _login(client, _make_user(role="ADMIN"))

    lines = _lines(client.get(_url(kind="settle_case",
                                   **{"from": date_from, "to": date_to})))

    assert len(lines) == 3, lines           # 헤더 1 + 시드 2
    assert "2026090100001" in lines[1]


def test_short_kind_alias_reaches_the_same_file(client, app):
    """계약서 초안의 짧은 이름(``case``)도 같은 파일을 낸다."""
    _seed_basic(get_today_kst())
    _login(client, _make_user(role="ADMIN"))

    alias = _lines(client.get(_url(kind="case")))
    canonical = _lines(client.get(_url(kind="settle_case")))

    assert alias == canonical


# --------------------------------------------------------------------------
# 4. 조건 — 화면에서 좁힌 것이 파일에도 그대로 걸린다
# --------------------------------------------------------------------------
def test_range_narrows_the_file(client, app):
    """구간 밖 행은 파일에 없다(헤더만 남는다)."""
    today = get_today_kst()
    _seed_basic(today)
    far = (today - datetime.timedelta(days=200)).isoformat()
    _login(client, _make_user(role="ADMIN"))

    lines = _lines(client.get(_url(kind="settle_case",
                                   **{"from": far, "to": far})))

    assert len(lines) == 1, lines


def test_search_narrows_the_file(client, app):
    """``q`` 가 상품주문번호로 행을 좁힌다."""
    today = get_today_kst()
    _seed_basic(today)
    date_from, date_to = _seeded_window(today)
    _login(client, _make_user(role="ADMIN"))

    lines = _lines(client.get(_url(kind="settle_case", q="2026090100002",
                                   **{"from": date_from, "to": date_to})))

    assert len(lines) == 2 and "2026090100002" in lines[1], lines


def test_filter_on_a_kind_that_takes_none_is_400(client, app):
    """일별 정산은 조건을 받지 않는다 — 조용히 버리지 않고 400 으로 말한다.

    조건을 버리고 200 을 주면 받는 사람은 "좁혀서 받았다"고 믿는데 파일은 전량이다.
    """
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(_url(kind="settle_daily", q="2026090100001"))

    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert resp.mimetype == "application/json"
    assert resp.get_json()["success"] is False


# --------------------------------------------------------------------------
# 5. 검증 실패는 **스트림 전에** 400 JSON
# --------------------------------------------------------------------------
@pytest.mark.parametrize("params,needle", [
    ({}, "kind"),
    ({"kind": "bogus"}, "kind"),
    ({"kind": "settle_case", "from": "2026-13-99"}, "from"),
    ({"kind": "settle_case", "channel": "COUPANG"}, "channel"),
    ({"kind": "settle_case", "basis": "bogus"}, "basis"),
])
def test_bad_parameters_are_400_json_with_a_korean_reason(client, app, params, needle):
    """종류·날짜·채널·기준일 오류는 400 JSON + 사람이 읽는 사유(반쪽 파일 금지)."""
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(_url(**params))

    assert resp.status_code == 400, (params, resp.get_data(as_text=True))
    assert resp.mimetype == "application/json", resp.mimetype
    body = resp.get_json()
    assert body["success"] is False and body["data"] is None
    assert needle in body["error"], body["error"]


def test_oversized_range_is_400_with_the_shared_ceiling(client, app):
    """구간 폭 상한은 탭과 **같은 상수**(400일)다 — 새 상한을 발명하지 않는다."""
    today = get_today_kst()
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(_url(kind="settle_case",
                           **{"from": (today - datetime.timedelta(days=500)).isoformat(),
                              "to": today.isoformat()}))

    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert "400" in resp.get_json()["error"]


def test_failed_request_leaves_no_audit_row(client, app):
    """400 은 감사 행을 남기지 않는다 — 받아 가지 않은 파일을 받아 갔다고 적지 않는다."""
    before = len(_audit_rows())
    _login(client, _make_user(role="ADMIN"))

    client.get(_url(kind="bogus"))

    assert len(_audit_rows()) == before


# --------------------------------------------------------------------------
# 6. 감사 — 다운로드 1회 = 1행 (계약 §1.3 C5)
# --------------------------------------------------------------------------
def test_one_download_writes_exactly_one_audit_row(client, app):
    """다운로드 1회 → ``NAVER_SETTLE_EXPORT_CSV`` 1행(행위자·종류·구간 포함)."""
    today = get_today_kst()
    _seed_basic(today)
    date_from, date_to = _seeded_window(today)
    user = _make_user(role="ADMIN")
    user_id = user.id
    _login(client, user)
    before = len(_audit_rows())

    _body(client.get(_url(kind="settle_case",
                          **{"from": date_from, "to": date_to})))

    rows = _audit_rows()
    assert len(rows) == before + 1
    row = rows[-1]
    assert row.user_id == user_id, "행위자가 없다(log_access 두 번째 위치 인자)"
    assert row.detail["kind"] == "settle_case"
    assert row.detail["from"] == date_from and row.detail["to"] == date_to
    assert row.detail["channel"] == "NAVER"
    assert row.message


def test_audit_row_leaves_the_integer_target_id_empty(client, app):
    """``target_id`` 는 비운다 — 정수 컬럼이라 CSV 종류 문자열을 넣으면 PG 가 거절한다.

    ``log_access`` 는 fail-open 이라 그 실패가 예외로 드러나지 않고 **감사 행이 조용히
    사라진다**. SQLite 로컬에서는 통과해 보이므로 여기서 못 박는다.
    """
    _login(client, _make_user(role="ADMIN"))

    _body(client.get(_url(kind="settle_case")))

    row = _audit_rows()[-1]
    assert row.target_id is None, row.target_id
    assert row.target_type and row.target_type.isascii()


def test_two_downloads_write_two_audit_rows(client, app):
    """두 번 받으면 두 행이다(요약·중복 제거로 사람의 행위를 지우지 않는다)."""
    _login(client, _make_user(role="ADMIN"))
    before = len(_audit_rows())

    _body(client.get(_url(kind="settle_case")))
    _body(client.get(_url(kind="vat_daily")))

    rows = _audit_rows()
    assert len(rows) == before + 2
    assert [row.detail["kind"] for row in rows[-2:]] == ["settle_case", "vat_daily"]


def test_audit_row_does_not_claim_a_row_count(client, app):
    """행수를 적지 않는다 — 응답을 만드는 시점에는 아직 모른다(모르는 것을 적지 않는다)."""
    _login(client, _make_user(role="ADMIN"))

    _body(client.get(_url(kind="settle_case")))

    assert "rows" not in _audit_rows()[-1].detail


# --------------------------------------------------------------------------
# 7. 5종 전부가 실제로 열린다
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kind", EXPORT_KINDS)
def test_every_kind_is_downloadable(client, app, kind):
    """커널이 아는 5종이 전부 라우트로도 나간다(화면에서만 감춘 종류가 없다)."""
    today = get_today_kst()
    _seed_basic(today)
    _case(today - datetime.timedelta(days=1), product_order_id="2026090100003")
    _daily(today - datetime.timedelta(days=1))
    db_session.commit()
    _login(client, _make_user(role="ADMIN"))

    resp = client.get(_url(kind=kind))

    assert resp.status_code == 200, (kind, resp.get_data(as_text=True))
    assert resp.get_data().startswith(_BOM)
