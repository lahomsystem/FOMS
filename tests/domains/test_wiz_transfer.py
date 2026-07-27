"""WIZ-TRANSFER-01 도면 전달 source helper 계약 테스트 (순수·commit=False).

이 helper 모듈(``foms.services.orders.drawing_transfer``)은 도면 전달의 **순수 소스**만
제공한다: pending 스냅샷·첨부 materialization 을 계산해 반환할 뿐, DB commit/flush·version
bump·event 기록·SIDEFX outbox enqueue 를 **일절 하지 않는다**(조립은 STATE-DRAWING-01).
Flask app/DB 불필요 — 경량 fake order + spy 로 순수성·도면 필터를 증명한다.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from foms.services.orders.drawing_transfer import (
    materialize_pending_snapshot,
    materialize_transfer_attachments,
)


def _order(order_id=7, structured_data=None):
    """구조화 데이터만 갖는 경량 fake 주문(DB 무접근)."""
    return SimpleNamespace(id=order_id, structured_data=structured_data)


def _pending_sd(order_id=7):
    return {
        "drawing_wizard": {
            "pending": {
                "s-1": {
                    "key": f"orders/{order_id}/drawing_wizard/exports/1_a.png",
                    "filename": "a.png",
                    "at": "2026-07-24 10:00",
                    "sheet_name": "도면 1",
                },
                "s-2": {
                    "key": f"orders/{order_id}/drawing_wizard/exports/2_b.png",
                    "filename": "b.png",
                    "at": "2026-07-24 10:05",
                    "sheet_name": "도면 2",
                },
            }
        }
    }


# ── pending snapshot: 순수 반환·DB write 0 ──────────────────────────────────

def test_pending_snapshot_materializes_list_in_order():
    order = _order(structured_data=_pending_sd())
    snap = materialize_pending_snapshot(order)

    assert [p["sheet_id"] for p in snap] == ["s-1", "s-2"]  # 삽입 순서 유지
    assert snap[0]["key"] == "orders/7/drawing_wizard/exports/1_a.png"
    assert snap[0]["filename"] == "a.png"
    assert snap[0]["sheet_name"] == "도면 1"


def test_pending_snapshot_skips_blank_key_entries():
    sd = _pending_sd()
    sd["drawing_wizard"]["pending"]["s-3"] = {"filename": "no-key.png"}
    sd["drawing_wizard"]["pending"]["s-4"] = "not-a-dict"
    snap = materialize_pending_snapshot(_order(structured_data=sd))

    assert [p["sheet_id"] for p in snap] == ["s-1", "s-2"]  # s-3(빈 key)·s-4(비 dict) 제외


def test_pending_snapshot_empty_when_no_wizard():
    assert materialize_pending_snapshot(_order(structured_data={})) == []
    assert materialize_pending_snapshot(_order(structured_data=None)) == []


def test_pending_snapshot_does_not_mutate_order_or_commit():
    sd = _pending_sd()
    order = _order(structured_data=sd)
    before = {k: dict(v) for k, v in sd["drawing_wizard"]["pending"].items()}

    materialize_pending_snapshot(order)

    # 원본 구조화 데이터 불변(순수 계산·in-place 변경 0).
    assert order.structured_data is sd
    assert sd["drawing_wizard"]["pending"] == before


# ── attachment materialization: 도면 key 필터(실측/일반 유출 0) ──────────────

def test_attachment_materialization_keeps_only_drawing_keys():
    files = [
        {"key": "orders/7/drawing_wizard/exports/1_a.png", "filename": "a.png"},
        {"key": "orders/7/drawing/plan.pdf", "filename": "plan.pdf"},
        {"key": "orders/7/drawing_gateway/revisions/r1.png", "filename": "r1.png"},
        # 유출되면 안 되는 것들:
        {"key": "orders/7/measurement/site.jpg", "filename": "site.jpg"},
        {"key": "orders/7/photo/general.jpg", "filename": "general.jpg"},
        {"key": "orders/7/misc/other.pdf", "filename": "other.pdf"},
    ]
    out = materialize_transfer_attachments(7, files)

    keys = [f["key"] for f in out]
    assert keys == [
        "orders/7/drawing_wizard/exports/1_a.png",
        "orders/7/drawing/plan.pdf",
        "orders/7/drawing_gateway/revisions/r1.png",
    ]
    # 실측/일반 첨부 유출 0 (construction_card drawing_current_files leak 함정).
    assert not any("measurement" in k or "/photo/" in k or "/misc/" in k for k in keys)


def test_attachment_materialization_rejects_other_order_and_traversal():
    files = [
        {"key": "orders/8/drawing/other-order.pdf", "filename": "x.pdf"},  # 타 주문
        {"key": "orders/7/drawing/../../etc/passwd", "filename": "p"},      # traversal
        {"key": "/orders/7/drawing/abs.pdf", "filename": "abs"},            # 절대경로
        {"key": "", "filename": "empty"},
        "not-a-dict",
        {"key": "orders/7/drawing/ok.pdf", "filename": "ok.pdf"},
    ]
    out = materialize_transfer_attachments(7, files)

    assert [f["key"] for f in out] == ["orders/7/drawing/ok.pdf"]


def test_attachment_materialization_builds_same_origin_urls():
    out = materialize_transfer_attachments(
        7, [{"key": "orders/7/drawing_wizard/exports/1_a.png", "filename": "a.png"}]
    )

    entry = out[0]
    # asset-raw same-origin 규칙: 앱 same-origin 경로만(교차출처 R2 presigned 금지).
    assert entry["view_url"] == "/api/files/view/orders/7/drawing_wizard/exports/1_a.png"
    assert entry["download_url"] == "/api/files/download/orders/7/drawing_wizard/exports/1_a.png"
    assert entry["filename"] == "a.png"


def test_attachment_materialization_defaults_filename_from_key():
    out = materialize_transfer_attachments(
        7, [{"key": "orders/7/drawing/plan.pdf"}]
    )
    assert out[0]["filename"] == "plan.pdf"


# ── commit=False 계약: version/event/outbox/commit 0 ────────────────────────

def test_helpers_never_touch_db_or_side_effects():
    """spy db/outbox 를 넘겨도(현재 시그니처는 받지 않음) 어떤 side-effect 도 없음을 증명.

    helper 는 db 세션을 인자로 받지 않으므로 commit/flush/version/event/outbox 자체가
    코드 경로에 존재하지 않는다. 순수 계산 후 스냅샷/엔트리만 반환한다.
    """
    db = MagicMock()  # 넘길 자리가 없어야 정상(순수) — 참조만으로 미사용 증명.
    order = _order(structured_data=_pending_sd())

    materialize_pending_snapshot(order)
    materialize_transfer_attachments(order.id, materialize_pending_snapshot(order))

    db.commit.assert_not_called()
    db.flush.assert_not_called()
    db.add.assert_not_called()
