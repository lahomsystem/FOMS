"""담당자 여러 명(MULTI-MGR-01) 저장·읽기 규칙 계약.

정본: ``parties.manager.name`` = 대표(첫 뱃지) · ``names`` = 전체 명단. ``name`` 이 늘
정본이라 ``name`` 만 바꾸는 옛 경로가 남긴 낡은 명단은 버린다. 옛 한 칸 여러 이름
(``"김의종, 백재현"``)은 읽을 때 나누고 다음 저장 때 정리된다.
"""
from __future__ import annotations

from types import SimpleNamespace

from foms.services import erp_permissions
from foms.services.orders.manager_names import (
    manager_label_filter,
    normalize_manager_party,
    order_manager_label,
    order_manager_names,
)


def _sd(name, names=None):
    manager = {"name": name}
    if names is not None:
        manager["names"] = names
    return {"parties": {"manager": manager}}


def test_names_list_with_primary_first() -> None:
    assert order_manager_names(_sd("한용희", ["김의종", "한용희"])) == ["한용희", "김의종"]
    assert order_manager_label(_sd("김의종", ["김의종", "한용희"])) == "김의종, 한용희"


def test_stale_names_are_dropped_when_primary_changed_elsewhere() -> None:
    """옛 경로가 name 만 바꾸면 명단은 낡은 것이다 — name 만 남는다."""
    assert order_manager_names(_sd("박영수", ["김의종", "한용희"])) == ["박영수"]


def test_legacy_single_cell_multi_names_are_split() -> None:
    assert order_manager_names(_sd("김의종, 백재현")) == ["김의종", "백재현"]
    assert order_manager_names(_sd("최진호/한용희")) == ["최진호", "한용희"]


def test_column_fallback_and_scalar_shapes() -> None:
    assert order_manager_names({}, "한용희") == ["한용희"]
    assert order_manager_names({"parties": {"manager": "김철수"}}) == ["김철수"]
    assert order_manager_names(None) == []


def test_normalize_sets_primary_and_drops_single_list() -> None:
    sd = _sd("김의종", ["김의종", "한용희", "김의종", " "])
    normalize_manager_party(sd)
    assert sd["parties"]["manager"] == {"name": "김의종", "names": ["김의종", "한용희"]}

    single = _sd("김의종", ["김의종"])
    normalize_manager_party(single)
    assert single["parties"]["manager"] == {"name": "김의종"}

    legacy = _sd("김의종, 백재현")
    normalize_manager_party(legacy)
    assert legacy["parties"]["manager"] == {"name": "김의종", "names": ["김의종", "백재현"]}


def test_clearing_primary_clears_list() -> None:
    sd = _sd("", ["김의종", "한용희"])
    normalize_manager_party(sd)
    assert sd["parties"]["manager"] == {"name": ""}


def test_template_filter_reads_rows_and_dtos() -> None:
    order = SimpleNamespace(manager_name="김의종", structured_data=_sd("김의종", ["김의종", "한용희"]))
    assert manager_label_filter(order) == "김의종, 한용희"
    assert manager_label_filter({"manager_name": "한용희"}) == "한용희"
    assert manager_label_filter(None) == ""


def test_second_manager_counts_as_mine() -> None:
    """대표가 아닌 담당자에게도 '내 주문'이다(영업 범위)."""
    user = SimpleNamespace(id=None, name="한용희", username="hanyh", team="SALES", role="STAFF")
    order = SimpleNamespace(manager_name="김의종", structured_data=_sd("김의종", ["김의종", "한용희"]))
    assert erp_permissions.is_order_related_to_user(order, user, scope="sales")
    other = SimpleNamespace(manager_name="김의종", structured_data=_sd("김의종"))
    assert not erp_permissions.is_order_related_to_user(other, user, scope="sales")


def test_inline_manager_field_accepts_comma_list(client) -> None:
    """실측 대시보드 담당자 칸(인라인 저장)에 "김의종, 한용희" 를 적으면 대표+명단으로 저장된다."""
    from werkzeug.security import generate_password_hash

    from db import db_session
    from models import Order, User

    user = User(username="inline-mgr", password=generate_password_hash("pw"), role="ADMIN",
                team="CS", name="inline-mgr", is_active=True)
    db_session.add(user)
    order = Order(received_date="2026-10-30", customer_name="담당여럿", phone="010-0000-0000",
                  address="Seoul", product="붙박이장", status="RECEIVED", manager_name="김의종",
                  is_erp_order=True,
                  structured_data={"workflow": {"stage": "RECEIVED"},
                                   "parties": {"manager": {"name": "김의종"}}})
    db_session.add(order)
    db_session.commit()
    order_id = int(order.id)
    with client.session_transaction() as sess:
        sess["user_id"] = int(user.id)
        sess["username"] = user.username
        sess["role"] = user.role

    response = client.post("/api/update_order_field",
                           json={"order_id": order_id, "field": "manager_name", "value": "한용희, 김의종"})
    assert response.status_code == 200, response.get_data(as_text=True)

    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.manager_name == "한용희"
    assert saved.structured_data["parties"]["manager"] == {"name": "한용희", "names": ["한용희", "김의종"]}
