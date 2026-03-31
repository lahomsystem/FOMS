from werkzeug.security import generate_password_hash

from db import db_session
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


def _create_deleted_erp_beta_order():
    order = Order(
        received_date="2026-03-31",
        customer_name="ERP Beta",
        phone="000-0000-0000",
        address="-",
        product="ERP Beta",
        options="''",
        notes="",
        status="DELETED",
        original_status="MEASURE",
        deleted_at="2026-03-31 09:00:00",
        is_erp_beta=True,
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


def test_trash_displays_erp_beta_structured_fields(client):
    _login_admin_session(client)
    order_id = _create_deleted_erp_beta_order()

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
    assert ">ERP Beta<" not in html
    assert "000-0000-0000" not in html


def test_trash_search_matches_erp_beta_structured_fields(client):
    _login_admin_session(client)
    order_id = _create_deleted_erp_beta_order()

    response = client.get("/trash", query_string={"search": "윤인선"})

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert str(order_id) in html
    assert "윤인선" in html
