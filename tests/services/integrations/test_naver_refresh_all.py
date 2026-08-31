"""**전체 다시 읽기** 계약 테스트 (NVREPAY-03).

**왜 필요한가**: 자동 스윕은 네이버가 변경 이벤트를 준 집만 다시 읽는다
(`claim_watch.refresh_claims`). 이벤트가 안 오는 집은 자동 경로로 **영영** 안 갱신되고,
화면의 상태·금액·클레임이 낡은 채로 남는다. 단건 `다시 읽기` 는 그 집 pane 에 서 있어야
눌러서, "지금 이 목록 전체가 진짜인가"를 확인할 방법이 없었다.

이 파일이 무는 것: 대상이 **수집된 집 전부**라는 것, 집 하나당 대표 링크 **하나만** 큐에
간다는 것(형제 상품주문마다 중복 호출하지 않는다), 그리고 이 조작이 **ADMIN 전용**이라는 것.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.claim_watch import (
    STATE_KEY,
    refreshable_household_link_ids,
)
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink, User

TRIAGE_PATH = "/admin/naver-ingest/triage"
REFRESH_ALL_PATH = "/admin/naver-ingest/refresh-all"
REPO_ROOT = Path(__file__).resolve().parents[3]

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"nvall_{role.lower()}_{_uid()}",
                password=generate_password_hash("pw"), role=role, team="CS",
                name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _link(*, order_no: str, order_status: str = "PAYED",
          claim_status: str | None = None,
          refreshed_at: object = None) -> ExternalOrderLink:
    """수집 링크 1건(붙지 않은 상태). 같은 ``order_no`` 를 주면 같은 집이 된다.

    ``order_status``·``claim_status`` 는 종결 판정을, ``refreshed_at`` 은 쿨다운 판정을
    태우는 자리다(둘 다 NVREPAY-03 후속).
    """
    external_id = f"PO-ALL-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no, "ordererName": "김주문",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {"productOrderId": external_id, "productName": "붙박이장",
                         "productOrderStatus": order_status,
                         "totalPaymentAmount": 100000},
    }
    sync = {}
    if claim_status is not None:
        sync["last_status"] = claim_status
    if refreshed_at is not None:
        sync["refreshed_at"] = (refreshed_at.isoformat()
                                if hasattr(refreshed_at, "isoformat") else refreshed_at)
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="COLLECTED", external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             triage_state={STATE_KEY: sync} if sync else None)
    db_session.add(link)
    db_session.commit()
    return link


# --------------------------------------------------------------------------- #
# 대상 — 집 단위로 한 번씩
# --------------------------------------------------------------------------- #

def test_one_link_per_household(app):
    """상품주문이 여러 건인 집도 **대표 하나**만 큐에 간다.

    `refresh_household` 가 그 링크의 집 전체를 다시 읽으므로, 형제마다 넣으면 같은 집을
    건수만큼 중복 호출한다.
    """
    order_no = f"N-ALL-A-{_uid()}"
    first = _link(order_no=order_no)
    _link(order_no=order_no)
    _link(order_no=order_no)

    link_ids, total, _skipped = refreshable_household_link_ids(db_session)

    assert link_ids.count(int(first.id)) == 1
    assert total >= 1


def test_counts_every_collected_household(app):
    """붙은 집·안 붙은 집을 가리지 않는다 — 목록 전체가 대상이다."""
    _link(order_no=f"N-ALL-B-{_uid()}")
    _link(order_no=f"N-ALL-C-{_uid()}")

    link_ids, total, _skipped = refreshable_household_link_ids(db_session)

    assert total == len(set(link_ids)) == len(link_ids)
    assert total >= 2


def test_limit_truncates_but_reports_total(app):
    """캡이 걸려도 **전체 수**는 그대로 돌려준다(조용한 절단 금지)."""
    _link(order_no=f"N-ALL-D-{_uid()}")
    _link(order_no=f"N-ALL-E-{_uid()}")

    link_ids, total, _skipped = refreshable_household_link_ids(db_session, limit=1)

    assert len(link_ids) == 1
    assert total >= 2


# --------------------------------------------------------------------------- #
# 라우트 — ADMIN 전용, 큐 장애를 숨기지 않는다
# --------------------------------------------------------------------------- #

def test_admin_enqueues_every_household(client, workbench_on, monkeypatch):
    """ADMIN 이 누르면 수집된 집마다 하나씩 큐에 들어간다."""
    _login(client, role="ADMIN")
    a = _link(order_no=f"N-ALL-F-{_uid()}")
    b = _link(order_no=f"N-ALL-G-{_uid()}")
    a_id, b_id = int(a.id), int(b.id)

    seen: list[int] = []
    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_refresh",
                        lambda link_id, user_id=None: seen.append(int(link_id)) or True)

    response = client.post(REFRESH_ALL_PATH, json={})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["queued"] == len(seen)
    assert a_id in seen and b_id in seen


def test_staff_cannot_refresh_everything(client, workbench_on):
    """STAFF 는 못 누른다 — 한 번에 수십 집 호출은 '지금 수집'과 같은 급이다.

    STAFF 에게는 각 집의 단건 `다시 읽기` 가 그대로 남아 있다.
    """
    _login(client, role="STAFF")
    _link(order_no=f"N-ALL-H-{_uid()}")

    response = client.post(REFRESH_ALL_PATH, json={})

    assert response.status_code in (302, 403)


def test_queue_outage_is_not_reported_as_success(client, workbench_on, monkeypatch):
    """큐가 막혀 하나도 못 넣으면 503 — 성공한 척하지 않는다."""
    _login(client, role="ADMIN")
    _link(order_no=f"N-ALL-I-{_uid()}")

    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_refresh",
                        lambda link_id, user_id=None: False)

    response = client.post(REFRESH_ALL_PATH, json={})

    assert response.status_code == 503
    assert response.get_json()["success"] is False


# --------------------------------------------------------------------------- #
# 화면 — 버튼은 ADMIN 에게만
# --------------------------------------------------------------------------- #

def test_button_shows_for_admin_with_count(client, workbench_on):
    """머리줄에 집 수를 달고 뜬다 — 몇 개를 읽는지 누르기 전에 안다."""
    _login(client, role="ADMIN")
    _link(order_no=f"N-ALL-J-{_uid()}")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'id="wb-refresh-all"' in body
    assert "다시 읽기" in body


def test_button_hidden_for_staff(client, workbench_on):
    """STAFF 화면에는 버튼이 아예 없다(라우트도 막혀 있다 — 화면만 숨기지 않는다)."""
    _login(client, role="STAFF")
    _link(order_no=f"N-ALL-K-{_uid()}")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'id="wb-refresh-all"' not in body


# --------------------------------------------------------------------------- #
# 계약 등재
# --------------------------------------------------------------------------- #

def test_route_is_registered_in_both_manifests():
    """write guard·mutation policy 매니페스트 둘 다 등재(별개 파일)."""
    endpoint = "admin.naver_ingest_refresh_all"
    guard = (REPO_ROOT / "docs" / "harness" / "foms_write_guard_manifest.json").read_text(encoding="utf-8")
    policy = (REPO_ROOT / "docs" / "harness" / "foms_order_mutation_policy_manifest.json").read_text(encoding="utf-8")

    assert endpoint in guard
    assert endpoint in policy
    assert json.loads(policy)["routes"][endpoint]["policy_id"] == "ADMIN_OPS"


def test_audit_action_has_a_korean_label():
    """새 감사 action 은 한글 업무 라벨이 있어야 한다."""
    from foms.services.audit_message_display import ACTION_LABELS

    assert ACTION_LABELS.get("NAVER_INGEST_REFRESH_ALL_ENQUEUE")


# --------------------------------------------------------------------------- #
# 대상 축소 — 종결·쿨다운 (NVREPAY-03 후속, 2026-08-30)
# --------------------------------------------------------------------------- #

def test_terminal_household_is_skipped(app):
    """취소·반품 완료, 구매확정된 집은 대상에서 빠진다 — 다시 읽어도 안 바뀐다."""
    order_no = f"N-ALL-T1-{_uid()}"
    _link(order_no=order_no, order_status="CANCELED")
    _link(order_no=order_no, order_status="RETURNED")

    link_ids, total, skipped = refreshable_household_link_ids(db_session)

    assert not any(link.external_order_no == order_no
                   for link in db_session.query(ExternalOrderLink)
                   .filter(ExternalOrderLink.id.in_(link_ids or [0])).all())
    assert skipped["done"] >= 1
    assert total == len(link_ids) or total >= len(link_ids)


def test_purchase_decided_is_terminal(app):
    """구매확정은 클레임 창이 닫혔다는 네이버 쪽 사실이라 종결로 본다."""
    order_no = f"N-ALL-T2-{_uid()}"
    _link(order_no=order_no, order_status="PURCHASE_DECIDED")

    _ids, _total, skipped = refreshable_household_link_ids(db_session)

    assert skipped["done"] >= 1


def test_claim_done_status_is_terminal_even_when_order_status_lives(app):
    """``productOrderStatus`` 가 살아 있어도 클레임이 확정이면 종결이다(두 축 OR)."""
    order_no = f"N-ALL-T3-{_uid()}"
    _link(order_no=order_no, order_status="DELIVERING", claim_status="RETURN_DONE")

    _ids, _total, skipped = refreshable_household_link_ids(db_session)

    assert skipped["done"] >= 1


def test_partly_terminal_household_is_still_read(app):
    """한 건이라도 살아 있으면 **읽는다** — 분할 취소된 집의 남은 취소를 놓치지 않는다."""
    order_no = f"N-ALL-T4-{_uid()}"
    first = _link(order_no=order_no, order_status="CANCELED")
    _link(order_no=order_no, order_status="PAYED")

    link_ids, _total, _skipped = refreshable_household_link_ids(db_session)

    assert int(first.id) in link_ids


def test_unknown_status_is_not_terminal(app):
    """모르는 상태는 종결이 아니다 — 모르면 읽는 쪽으로 기운다."""
    order_no = f"N-ALL-T5-{_uid()}"
    live = _link(order_no=order_no, order_status="SOMETHING_NEW")

    link_ids, _total, _skipped = refreshable_household_link_ids(db_session)

    assert int(live.id) in link_ids


def test_recently_refreshed_household_is_skipped(app):
    """쿨다운 안에 이미 읽은 집은 건너뛴다 — 연타가 같은 조회를 곱하지 않는다."""
    from foms.services.datetime_kst import now_utc_naive

    order_no = f"N-ALL-T6-{_uid()}"
    _link(order_no=order_no, refreshed_at=now_utc_naive())

    link_ids, _total, skipped = refreshable_household_link_ids(db_session)

    assert skipped["recent"] >= 1
    assert not any(link.external_order_no == order_no
                   for link in db_session.query(ExternalOrderLink)
                   .filter(ExternalOrderLink.id.in_(link_ids or [0])).all())


def test_cooldown_expires(app):
    """쿨다운이 지난 집은 다시 대상이 된다."""
    from datetime import timedelta

    from foms.services.datetime_kst import now_utc_naive
    from foms.services.integrations.naver_commerce.claim_watch import (
        REFRESH_ALL_COOLDOWN_SECONDS,
    )

    order_no = f"N-ALL-T7-{_uid()}"
    stale = now_utc_naive() - timedelta(seconds=REFRESH_ALL_COOLDOWN_SECONDS + 60)
    link = _link(order_no=order_no, refreshed_at=stale)

    link_ids, _total, _skipped = refreshable_household_link_ids(db_session)

    assert int(link.id) in link_ids


def test_never_refreshed_is_never_recent(app):
    """한 번도 안 읽은 집은 쿨다운에 걸리지 않는다."""
    link = _link(order_no=f"N-ALL-T8-{_uid()}")

    link_ids, _total, _skipped = refreshable_household_link_ids(db_session)

    assert int(link.id) in link_ids


def test_response_says_what_it_skipped(client, workbench_on, monkeypatch):
    """조용히 줄이지 않는다 — 응답이 뺀 수를 말한다."""
    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_refresh",
                        lambda *a, **k: True)
    _login(client, role="ADMIN")
    done_no = f"N-ALL-T9-{_uid()}"
    _link(order_no=done_no, order_status="CANCELED")
    _link(order_no=f"N-ALL-TA-{_uid()}")

    payload = client.post(REFRESH_ALL_PATH, json={}).get_json()

    assert payload["success"] is True
    assert payload["data"]["skipped_done"] >= 1
    assert "since" in payload["data"]
    assert payload["data"]["link_ids"]


# --------------------------------------------------------------------------- #
# 진행 조회 — 화면이 '끝났다'를 스스로 말한다
# --------------------------------------------------------------------------- #

PROGRESS_PATH = "/admin/naver-ingest/triage/refresh-progress"


def test_progress_counts_household_as_done_only_when_all_links_refreshed(client, workbench_on):
    """집은 **형제 전부**가 다시 읽혔을 때만 끝난 것이다(대표 하나만 보면 거짓말)."""
    from datetime import timedelta

    from foms.services.datetime_kst import now_utc_naive

    since = now_utc_naive()
    order_no = f"N-ALL-P1-{_uid()}"
    first = _link(order_no=order_no, refreshed_at=since + timedelta(seconds=5))
    _link(order_no=order_no)
    _login(client, role="ADMIN")

    payload = client.get(PROGRESS_PATH, query_string={
        "link_ids": str(first.id), "since": since.isoformat()}).get_json()

    assert payload["data"]["total"] == 1
    assert payload["data"]["done"] == 0
    assert payload["data"]["pending"] == 1


def test_progress_reports_done_when_every_link_is_newer(client, workbench_on):
    """형제 전부가 ``since`` 뒤에 읽히면 끝났다고 말한다."""
    from datetime import timedelta

    from foms.services.datetime_kst import now_utc_naive

    since = now_utc_naive()
    order_no = f"N-ALL-P2-{_uid()}"
    first = _link(order_no=order_no, refreshed_at=since + timedelta(seconds=5))
    _link(order_no=order_no, refreshed_at=since + timedelta(seconds=7))
    _login(client, role="ADMIN")

    payload = client.get(PROGRESS_PATH, query_string={
        "link_ids": str(first.id), "since": since.isoformat()}).get_json()

    assert payload["data"]["done"] == 1
    assert payload["data"]["pending"] == 0


def test_progress_is_admin_only(client, workbench_on):
    """진행 조회도 버튼과 같은 급이다 — STAFF 는 못 본다."""
    link = _link(order_no=f"N-ALL-P3-{_uid()}")
    _login(client, role="STAFF")

    response = client.get(PROGRESS_PATH, query_string={
        "link_ids": str(link.id), "since": "2026-08-30T00:00:00"})

    assert response.status_code in (302, 403)


def test_progress_rejects_missing_arguments(client, workbench_on):
    """인자가 없으면 400 — 조용히 0 을 주면 화면이 '끝났다'로 읽는다."""
    _login(client, role="ADMIN")

    assert client.get(PROGRESS_PATH).status_code == 400
    assert client.get(PROGRESS_PATH, query_string={"link_ids": "1"}).status_code == 400
    assert client.get(PROGRESS_PATH, query_string={
        "link_ids": "1", "since": "어제"}).status_code == 400


def test_idle_state_says_why_the_button_is_gone(client, workbench_on, monkeypatch):
    """쿨다운으로 대상이 0 이면 **말은 한다** — 버튼이 그냥 사라지면 기능이 없어진 걸로 읽는다.

    술어가 아니라 **화면 분기**를 보는 테스트다. 공유 세션의 다른 링크를 건드려 0 을
    만들면 같은 파일의 다른 테스트가 깨진다(실제로 깨뜨려 봤다) — 대상 계산만 갈아 끼운다.
    """
    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.claim_watch"
        ".refreshable_household_link_ids",
        lambda *a, **k: ([], 0, {"done": 0, "recent": 3}))
    _login(client, role="ADMIN")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'id="wb-refresh-all-idle"' in body
    assert "방금 다 읽었습니다" in body
    assert 'id="wb-refresh-all"' not in body


# --------------------------------------------------------------------------- #
# 감사 행위자 — 누가 눌렀는지 없는 감사는 절반짜리다
# --------------------------------------------------------------------------- #

def test_every_naver_audit_call_records_the_actor():
    """`naver_ingest.py` 의 모든 `log_access` 는 **행위자**를 넘긴다.

    ``log_access`` 는 ``user_id`` 를 생략하면 NULL 로 남긴다. 이 파일만 19곳 전부가
    생략해서 네이버 감사 행에 행위자가 없었다(운영 실측 2026-08-30: `NAVER_*` 액션
    전량 ``user_id IS NULL``). 저장소 전체로는 127곳 중 90곳이 넘기고 있었으니 관행이
    아니라 **이 파일의 누락**이었다.

    되돌아가는 것을 막는 게이트다 — 새 라우트를 붙일 때 빠뜨리면 여기서 빨개진다.
    """
    import re

    source = (REPO_ROOT / "foms" / "web" / "admin" / "naver_ingest.py").read_text(
        encoding="utf-8")
    missing = []
    for match in re.finditer(r"log_access\(", source):
        depth = 0
        for offset, char in enumerate(source[match.start():match.start() + 900]):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    call = source[match.start():match.start() + offset]
                    break
        else:  # pragma: no cover - 900자 안에 닫히지 않는 호출은 없다
            call = ""
        if 'session.get("user_id")' not in call:
            missing.append(source[:match.start()].count("\n") + 1)

    assert not missing, f"행위자 없는 log_access 라인: {missing}"


def test_audit_row_actually_carries_the_actor(client, workbench_on, monkeypatch):
    """소스가 아니라 **실제로 남은 감사 행**에 행위자가 있는지 본다.

    앞의 소스 스캔은 모양만 본다 — `log_access` 의 인자 순서가 바뀌면 스캔은 통과하고
    행은 여전히 비게 된다. 라우트를 실제로 눌러 ``SecurityLog`` 행을 읽는다.
    """
    from models import SecurityLog

    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_refresh",
                        lambda *a, **k: True)
    user_id = _login(client, role="ADMIN").id   # 요청 뒤에는 detach 된다 — id 를 먼저 뜬다
    _link(order_no=f"N-ALL-AC-{_uid()}")

    assert client.post(REFRESH_ALL_PATH, json={}).get_json()["success"] is True

    row = (db_session.query(SecurityLog)
           .filter(SecurityLog.action == "NAVER_INGEST_REFRESH_ALL_ENQUEUE")
           .order_by(SecurityLog.id.desc()).first())
    assert row is not None
    assert row.user_id == user_id


# --------------------------------------------------------------------------- #
# 걸리는 시간 — 침묵은 "곧 끝난다"로 읽힌다 (NVREPAY-05 T2)
# --------------------------------------------------------------------------- #

def test_eta_speaks_a_range_not_one_number():
    """실측 두 벌(운영 45집 42.3초·스테이징 85집 81.7초)을 범위로 말한다.

    한 값으로 말하면 워커가 밀린 날 화면이 거짓말한 것이 된다 — 워커는 하나뿐이라
    앞선 작업이 있으면 시작이 통째로 밀린다(운영 실측 첫 스탬프 +40.5초·+69.0초).
    """
    from foms.services.integrations.naver_commerce.claim_watch import refresh_all_eta_text

    assert refresh_all_eta_text(45) == "약 1~2분"
    assert refresh_all_eta_text(85) == "약 2~3분"


def test_eta_for_a_small_batch_says_under_a_minute():
    """느린 쪽으로 재도 1분이 안 되면 분 단위로 말하지 않는다."""
    from foms.services.integrations.naver_commerce.claim_watch import refresh_all_eta_text

    assert refresh_all_eta_text(20) == "약 1분 안"


def test_eta_is_silent_when_there_is_nothing_to_read():
    """대상이 0 이면 아무 말도 안 한다 — 없는 일에 시간을 붙이지 않는다."""
    from foms.services.integrations.naver_commerce.claim_watch import refresh_all_eta_text

    assert refresh_all_eta_text(0) == ""


def test_tooltip_and_modal_say_the_same_eta(client, workbench_on, monkeypatch):
    """툴팁·모달·라벨이 **서버가 만든 같은 값**을 말한다.

    화면이 세 자리에서 따로 계산하면 같은 버튼이 세 말을 한다. 서버가 한 번 만들고
    (``refresh_all.eta``) 툴팁은 그대로 쓰며 모달은 ``data-eta`` 로 읽는다.
    """
    monkeypatch.setattr(
        "foms.services.integrations.naver_commerce.claim_watch"
        ".refreshable_household_link_ids",
        lambda *a, **k: ([1], 45, {"done": 0, "recent": 0}))
    _login(client, role="ADMIN")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'data-eta="약 1~2분"' in body
    assert "약 1~2분 걸립니다" in body
    source = (REPO_ROOT / "static" / "js" / "admin" / "naver-workbench.js").read_text(
        encoding="utf-8")
    assert "button.dataset.eta" in source, "모달은 서버가 만든 값을 읽는다(재계산 금지)"


# --------------------------------------------------------------------------- #
# 남이 눌러도 보인다 — 진행이 누른 브라우저 안에만 있던 자리 (NVREPAY-05 T1)
# --------------------------------------------------------------------------- #

RUNNING_PATH = "/admin/naver-ingest/triage/refresh-running"


def _enqueue_log(*, user_id, queued: int, age_seconds: int = 10):
    """전체 다시 읽기 요청 감사 행 1건을 심는다(진행 표시의 유일한 원천)."""
    from datetime import timedelta

    from foms.services.datetime_kst import now_utc_naive
    from foms.services.integrations.naver_commerce.claim_watch import (
        REFRESH_ALL_AUDIT_ACTION,
    )
    from models import SecurityLog

    row = SecurityLog(user_id=user_id, message="네이버 전체 다시 읽기 요청(계약 테스트)",
                      action=REFRESH_ALL_AUDIT_ACTION,
                      timestamp=now_utc_naive() - timedelta(seconds=age_seconds),
                      detail={"queued": queued, "total": queued})
    db_session.add(row)
    db_session.commit()
    return row


def test_other_admin_sees_that_someone_is_reading(client, workbench_on):
    """다른 관리자의 화면도 **돌고 있다**고 말한다 — 그리고 버튼을 잠근다.

    진행 표시가 누른 브라우저 안에만 있어서, 남의 화면에는 돌고 있는 중에도
    `다시 읽기 45주문` 이라 적혀 있었다. 그래서 또 누른다 — 한 사람이 28초 만에 두 번
    눌러 낭비된 것과 **같은 낭비를 두 사람이** 낸다.
    """
    presser = _login(client, role="ADMIN")
    presser_name = presser.name
    _link(order_no=f"N-ALL-R1-{_uid()}")
    _enqueue_log(user_id=presser.id, queued=50)
    _login(client, role="ADMIN")   # 다른 브라우저에서 보는 다른 관리자

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'id="wb-refresh-all-running"' in body
    assert "다시 읽는 중" in body
    assert presser_name in body, "누가 눌렀는지까지 말한다(감사 행위자가 남으므로)"
    assert 'id="wb-refresh-all"' not in body, "돌고 있는 동안 같은 조회를 또 걸지 않는다"


def test_running_strip_names_the_unknown_presser(client, workbench_on):
    """행위자가 없던 시절(2026-08-31 이전) 행도 그대로 읽는다 — 이름만 모른다."""
    _link(order_no=f"N-ALL-R2-{_uid()}")
    _enqueue_log(user_id=None, queued=50)
    _login(client, role="ADMIN")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'id="wb-refresh-all-running"' in body
    assert "다른 관리자 시작" in body


def test_running_strip_ignores_a_request_that_is_too_old(app):
    """창(5분) 밖 요청은 돌고 있는 게 아니다 — 화면 폴링 마감과 같은 값이다."""
    from foms.services.integrations.naver_commerce.claim_watch import running_refresh_all

    _link(order_no=f"N-ALL-R3-{_uid()}")
    _enqueue_log(user_id=None, queued=50, age_seconds=600)

    assert running_refresh_all(db_session) is None


def test_running_strip_folds_when_every_household_is_read(app):
    """다 읽으면 띠가 접힌다 — 그 순간이 버튼이 돌아오는 순간이다."""
    from datetime import timedelta

    from foms.services.datetime_kst import now_utc_naive
    from foms.services.integrations.naver_commerce.claim_watch import running_refresh_all

    started = now_utc_naive()
    _enqueue_log(user_id=None, queued=1, age_seconds=0)
    _link(order_no=f"N-ALL-R4-{_uid()}", refreshed_at=started + timedelta(seconds=5))

    assert running_refresh_all(db_session) is None


def test_running_progress_never_passes_what_was_queued(app):
    """센 집이 넣은 집보다 많아도 100%를 넘지 않는다.

    어떤 집을 넣었는지는 감사 행에 없어서 수집된 집 전부를 센다 — 그 사이 단건
    `다시 읽기` 나 자동 스윕이 찍은 스탬프가 섞이면 진행이 넘칠 수 있다.
    """
    from datetime import timedelta

    from foms.services.datetime_kst import now_utc_naive
    from foms.services.integrations.naver_commerce.claim_watch import running_refresh_all

    started = now_utc_naive()
    _enqueue_log(user_id=None, queued=2, age_seconds=0)
    for _ in range(3):
        _link(order_no=f"N-ALL-R5-{_uid()}", refreshed_at=started + timedelta(seconds=5))

    assert running_refresh_all(db_session) is None


def test_running_counts_a_household_only_when_all_siblings_are_read(app):
    """집 판정은 누른 사람 화면과 **같은 함수**다 — 형제 하나가 남으면 안 끝났다."""
    from datetime import timedelta

    from foms.services.datetime_kst import now_utc_naive
    from foms.services.integrations.naver_commerce.claim_watch import (
        refreshed_household_counts,
    )

    since = now_utc_naive()
    order_no = f"N-ALL-R6-{_uid()}"
    _link(order_no=order_no, refreshed_at=since + timedelta(seconds=5))
    _link(order_no=order_no)

    assert refreshed_household_counts(db_session, since, order_nos=[order_no]) == (0, 1)


def test_progress_and_running_share_one_predicate():
    """세는 규칙이 라우트에 두 벌로 남지 않는다(조용히 갈리는 자리)."""
    source = (REPO_ROOT / "foms" / "web" / "admin" / "naver_ingest.py").read_text(
        encoding="utf-8")

    assert "done_by_house" not in source, "집 세기는 claim_watch 한 곳에서만 한다"
    assert source.count("refreshed_household_counts") >= 1


def test_running_endpoint_answers_without_arguments(client, workbench_on):
    """남의 요청은 링크 id 를 모른다 — 인자 없이 물어도 답해야 한다."""
    _login(client, role="ADMIN")

    payload = client.get(RUNNING_PATH).get_json()

    assert payload["success"] is True
    assert "running" in payload["data"]


def test_running_endpoint_is_admin_only(client, workbench_on):
    """진행 조회도 버튼과 같은 급이다 — STAFF 는 못 본다."""
    _login(client, role="STAFF")

    assert client.get(RUNNING_PATH).status_code in (302, 403)


def test_running_endpoint_is_closed_when_the_gate_is_off(client, monkeypatch):
    """워크벤치 게이트 밖에서는 없는 화면이다(404)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "0")
    _login(client, role="ADMIN")

    assert client.get(RUNNING_PATH).status_code == 404


def test_screen_follows_a_running_refresh_from_any_browser():
    """첫 화면과 교체 뒤 화면 **둘 다** 남의 진행을 따라간다.

    `softRefresh` 는 워크벤치 루트를 통째로 갈아 끼운다 — 거기서 다시 걸지 않으면
    폴링이 한 번 돌고 죽어 띠가 영원히 멈춘 채로 남는다.
    """
    source = (REPO_ROOT / "static" / "js" / "admin" / "naver-workbench.js").read_text(
        encoding="utf-8")

    assert "/admin/naver-ingest/triage/refresh-running" in source
    assert source.count("syncRefreshRunning();") >= 2
