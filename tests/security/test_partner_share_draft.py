"""고객 공유 링크 도면 목록에서 협력사 초안 빼기 (SPEC 2026-10-20-share-skip-partner-draft)."""

from db import db_session
from models import Order, OrderAttachment, User
from tests.security.partner_fixtures import _client, _create, _upload, fake_storage, world  # noqa: F401

import foms.api.share as share


def test_share_drawing_list_skips_partner_draft(app, world, fake_storage):
    created = _create(app, world["partner_a"]).get_json()["data"]
    order_id = created.get("order_id") or created["id"]
    partner = _client(app, db_session.get(User, world["partner_a"]))
    assert _upload(partner, order_id, "draft.jpg", "draft").status_code == 200
    assert _upload(partner, order_id, "site.jpg", "photo").status_code == 200
    # 직원(도면팀)이 넘긴 도면 — 음성 대조군.
    db_session.add(OrderAttachment(order_id=order_id, filename="final.pdf", file_type="file",
                                   category="drawing", file_size=1,
                                   storage_key=f"orders/{order_id}/drawing/final.pdf"))
    db_session.commit()

    keys = [f["key"] for f in share._collect_drawing_files(db_session.get(Order, order_id))]

    assert keys == [f"orders/{order_id}/drawing/final.pdf"]
    drafts = db_session.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id, OrderAttachment.storage_key.like("%/partner_draft/%"))
    assert drafts.count() == 1  # 첨부 행은 그대로 남는다
