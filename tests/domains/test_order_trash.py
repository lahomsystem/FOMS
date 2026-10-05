import copy

from sqlalchemy import inspect as sa_inspect
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.context_processors import parse_json_string
from foms.services.erp_display import _ensure_dict, apply_erp_display_fields
from foms.services.erp_order_flags import is_erp_order_record
from foms.services.order_display_utils import format_options_for_display
from foms.services.orders.status_constants import STATUS
from foms.web.orders import trash as trash_view
from models import Order, User


def _login_admin_session(client):
    user = User(
        username="trash_admin",
        password=generate_password_hash("admin"),
        role="ADMIN",
        name="Trash Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.id

    return user


def _create_deleted_erp_order():
    order = Order(
        received_date="2026-03-31",
        customer_name="ERP Order",
        phone="000-0000-0000",
        address="-",
        product="ERP Order",
        options="''",
        notes="",
        status="DELETED",
        original_status="MEASURE",
        deleted_at="2026-03-31 09:00:00",
        is_erp_order=True,
        structured_data={
            "parties": {
                "customer": {
                    "name": "윤인선",
                    "phone": "010-2562-9522",
                },
                "manager": {
                    "name": "이시영",
                },
                "orderer": {
                    "name": "라홈",
                },
            },
            "site": {
                "address_full": "경기 용인시 처인구 포곡읍 영문리 52-4 영문중학교 앞",
            },
            "items": [
                {
                    "product_name": "주방 외5조",
                    "standard": "붙박이 3조",
                    "color": "화이트",
                    "option_detail": "신발장 1조",
                }
            ],
            "schedule": {
                "measurement": {
                    "date": "2026-03-28",
                    "time": "오전",
                }
            },
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def test_trash_displays_erp_order_structured_fields(client):
    _login_admin_session(client)
    order_id = _create_deleted_erp_order()

    response = client.get("/trash")

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "윤인선" in html
    assert "010-2562-9522" in html
    assert "경기 용인시 처인구 포곡읍 영문리 52-4 영문중학교 앞" in html
    assert "주방 외5조" in html
    assert "붙박이 3조" in html
    assert "신발장 1조" in html
    assert f">{order_id}<" in html
    assert ">ERP Order<" not in html
    assert "000-0000-0000" not in html


def test_trash_search_matches_erp_order_structured_fields(client):
    _login_admin_session(client)
    order_id = _create_deleted_erp_order()

    response = client.get("/trash", query_string={"search": "윤인선"})

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert str(order_id) in html
    assert "윤인선" in html


# --- 표시 행 = 옛 표시 사본(ORM deepcopy) 동치 (성능 원장 P3-6) ---------------------------
#
# 휴지통은 ORM 주문을 행마다 ``copy.deepcopy`` 해서 표시 속성을 덧입혔다(스테이징 343행에
# 표시 준비 약 120ms). 이제는 컬럼 행을 분리된 표시 행(`TrashDisplayRow`)으로 옮겨 담는다.
# 화면이 그대로인지 — 같은 시드에서 옛 방식으로 만든 HTML 과 **글자 그대로** 같은지 — 를 잰다.

def _deepcopy_reference(orders):
    """옛 표시 사본(ORM 인스턴스 ``deepcopy``) — 이 동치 테스트의 기준선(2026-10-05 이전 코드)."""
    display_orders = []
    for order in orders:
        order_display = copy.deepcopy(order)
        order_display.display_options = format_options_for_display(order.options)
        if is_erp_order_record(order) and getattr(order, "structured_data", None):
            order_display.structured_data = _ensure_dict(order.structured_data)
            apply_erp_display_fields(order_display)
            summary = trash_view._build_erp_order_options_summary(order_display.structured_data)
            if summary:
                order_display.display_options = summary
                order_display.options = summary
            elif str(getattr(order_display, "options", "") or "").strip() in {"''", '""', "-", "ERP Order"}:
                order_display.options = ""
        elif getattr(order_display, "display_options", None):
            order_display.options = order_display.display_options
        display_orders.append(order_display)
    return display_orders


def _seed_trash_shapes():
    """휴지통 표시 갈래를 한 번씩 거는 삭제 주문들(레거시 옵션 JSON·긴 옵션 글·ERP 품목 옵션·
    ERP 옵션 자리표시·문서 없는 ERP·숫자 담당자·AS 방문일)."""
    _create_deleted_erp_order()
    manager = User(username="trash_mgr", password=generate_password_hash("x"), role="STAFF",
                   name="숫자담당", is_active=True)
    db_session.add(manager)
    db_session.flush()
    base = dict(received_date="2026-03-01", phone="010-1111-2222", address="서울 마포구",
                product="붙박이장", status="COMPLETED", original_status="COMPLETED")
    rows = [
        Order(**base, customer_name="레거시JSON", notes="메모",
              options='{"option_type": "direct", "details": {"color": "화이트", "handle": "없음"}}',
              deleted_at="2026-03-02 10:00:00"),
        Order(**base, customer_name="레거시긴글", options="가" * 45, deleted_at="2026-03-03 11:00:00"),
        Order(**base, customer_name="ERP자리표시", options="ERP Order", is_erp_order=True,
              deleted_at="2026-03-04 12:00:00",
              structured_data={"parties": {"manager": str(manager.id),
                                           "customer": {"name": "숫자담당고객"}},
                               "items": [{"product_name": "식탁"}],
                               "schedule": {"as_visit": {"date": "2026-03-10"},
                                            "construction": {"date": "2026-03-09"}},
                               "payment": {"deposit": "100,000"}}),
        Order(**base, customer_name="ERP문서없음", options="-", is_erp_order=True,
              deleted_at="2026-03-05 13:00:00", structured_data=None),
    ]
    db_session.add_all(rows)
    db_session.commit()


def _render(app, orders):
    parent = app.jinja_env.from_string(
        "{% block head %}{% endblock %}{% block content %}{% endblock %}{% block scripts %}{% endblock %}")
    with app.test_request_context("/trash"):
        return app.jinja_env.get_template("orders/trash.html").render(
            orders=orders, search_term="", parent_template=parent, ALL_STATUS=STATUS,
            parse_json_string=parse_json_string)


def _trash_query(*entities):
    return (db_session.query(*entities).filter(Order.deleted_at.isnot(None))
            .order_by(Order.deleted_at.desc()))


def test_trash_display_rows_render_exactly_like_the_deepcopy_copies(app):
    """같은 시드 — 표시 행으로 그린 HTML == 옛 ORM 사본으로 그린 HTML(글자 그대로)."""
    _seed_trash_shapes()

    reference = _deepcopy_reference(_trash_query(Order).all())
    rows = trash_view._build_trash_display_orders(_trash_query(*trash_view._TRASH_COLUMNS).all())

    assert len(rows) == len(reference) == 5
    assert not any(isinstance(row, Order) for row in rows), "표시 행이 ORM 인스턴스다"
    html = _render(app, rows)
    assert "숫자담당고객" in html and "화이트" in html, "빈 화면끼리 같다는 거짓 통과"
    assert html == _render(app, reference)


def test_trash_display_rows_negative_control_drops_a_column(app):
    """음성 대조군 — 표시 행에서 칸 하나(비고)를 빼면 같은 비교가 갈린다."""
    _seed_trash_shapes()

    reference = _deepcopy_reference(_trash_query(Order).all())
    rows = trash_view._build_trash_display_orders(_trash_query(*trash_view._TRASH_COLUMNS).all())
    for row in rows:
        row.__dict__.pop("notes", None)

    assert _render(app, rows) != _render(app, reference)


def test_trash_display_row_carries_every_mapped_column():
    """표시 행은 Order 매핑 컬럼을 **전부** 싣는다 — 고르면 Jinja 가 빠진 칸을 빈칸으로 그린다."""
    assert set(trash_view._TRASH_ROW_KEYS) == {a.key for a in sa_inspect(Order).column_attrs}
