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


def _link(*, order_no: str) -> ExternalOrderLink:
    """수집 링크 1건(붙지 않은 상태). 같은 ``order_no`` 를 주면 같은 집이 된다."""
    external_id = f"PO-ALL-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no, "ordererName": "김주문",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {"productOrderId": external_id, "productName": "붙박이장",
                         "totalPaymentAmount": 100000},
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="COLLECTED", external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot))
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

    link_ids, total = refreshable_household_link_ids(db_session)

    assert link_ids.count(int(first.id)) == 1
    assert total >= 1


def test_counts_every_collected_household(app):
    """붙은 집·안 붙은 집을 가리지 않는다 — 목록 전체가 대상이다."""
    _link(order_no=f"N-ALL-B-{_uid()}")
    _link(order_no=f"N-ALL-C-{_uid()}")

    link_ids, total = refreshable_household_link_ids(db_session)

    assert total == len(set(link_ids)) == len(link_ids)
    assert total >= 2


def test_limit_truncates_but_reports_total(app):
    """캡이 걸려도 **전체 수**는 그대로 돌려준다(조용한 절단 금지)."""
    _link(order_no=f"N-ALL-D-{_uid()}")
    _link(order_no=f"N-ALL-E-{_uid()}")

    link_ids, total = refreshable_household_link_ids(db_session, limit=1)

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
    assert "전체 다시 읽기" in body


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
