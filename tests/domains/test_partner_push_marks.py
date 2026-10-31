"""협력사 주문 칸의 영발·발주 PUSH 표기.

이름 줄 다음, 결제 앞. 협력사 주문만. 보낸 것만 남긴다.
"""

from __future__ import annotations

from pathlib import Path

from foms.services.orders.partner_push_marks import partner_channel_push_marks

ROOT = Path(__file__).resolve().parents[2]

_SENT_AT = "2026-10-30T01:02:00+00:00"


def test_empty_history_renders_nothing() -> None:
    """안 보낸 종류는 칸이 없다."""
    assert partner_channel_push_marks({}) == []
    assert partner_channel_push_marks(None) == []


def test_only_the_sent_kind_is_kept() -> None:
    """영발만 보냈으면 발주 칸은 없다."""
    marks = partner_channel_push_marks({
        "channeltalk_push": {"pushed": True, "sent_at": _SENT_AT},
    })

    assert [slot["label"] for slot in marks] == ["영발"]


def test_sent_stamp_is_kst_and_resend_shows_ordinal() -> None:
    """보낸 시각은 KST. 다시 보낸 건 라벨에 차례가 붙는다."""
    marks = partner_channel_push_marks({
        "channeltalk_push": {"pushed": True, "sent_at": _SENT_AT},
        "channeltalk_push_drawing": {
            "pushed": True,
            "sent_at": _SENT_AT,
            "is_modified": True,
            "change_log": [{"at": _SENT_AT}, {"at": _SENT_AT}],
        },
    })

    assert marks[0]["label"] == "영발"
    assert marks[0]["state"] == "sent" and marks[0]["mark"] == "check"
    assert "10-30 10:02" in marks[0]["title"]
    assert "10-30 10:02" in marks[0]["aria"]
    assert marks[1]["label"] == "발주 3번째"
    assert marks[1]["state"] == "sent"
    assert "발주 3번째" in marks[1]["aria"]


def test_resend_without_log_is_the_second_send() -> None:
    """예전 기록은 change_log 가 없고 is_modified 만 있다. 그건 2번째다."""
    marks = partner_channel_push_marks({
        "channeltalk_push": {"pushed": True, "sent_at": _SENT_AT, "is_modified": True},
    })

    assert marks[0]["label"] == "영발 2번째"


def test_stale_drawing_keeps_the_send_ordinal() -> None:
    """발주 뒤 도면이 바뀌면 붉은 칸이다. 글자는 보낸 차례이고 '재'가 아니다."""
    marks = partner_channel_push_marks({
        "channeltalk_push_drawing": {
            "pushed": True,
            "sent_at": _SENT_AT,
            "is_modified": True,
            "change_log": [{"at": _SENT_AT}],
            "stale_drawing_at": "2026-10-30T02:00:00+00:00",
        },
    })

    assert len(marks) == 1
    assert marks[0]["label"] == "발주 2번째"
    assert marks[0]["state"] == "stale" and marks[0]["mark"] == "none"
    assert "도면" in marks[0]["title"]


def test_measure_slot_ignores_a_stale_field() -> None:
    """도면 변경 표시는 발주 칸만. 영발 이력에 같은 키가 있어도 보냄이다."""
    marks = partner_channel_push_marks({
        "channeltalk_push": {"pushed": True, "stale_drawing_at": "2026-10-30T02:00:00+00:00"},
    })

    assert marks[0]["state"] == "sent"


def test_macro_renders_ordinal_and_stale_without_inline_style(app) -> None:
    """매크로가 차례·체크·붉은 칸을 그린다. '재'와 style 속성은 없다."""
    render = app.jinja_env.get_template(
        "partials/shared/channel_mark.html"
    ).module.partner_push_marks
    html = str(render({
        "channeltalk_push": {
            "pushed": True,
            "sent_at": _SENT_AT,
            "change_log": [{"at": _SENT_AT}],
        },
        "channeltalk_push_drawing": {
            "pushed": True,
            "sent_at": _SENT_AT,
            "stale_drawing_at": "2026-10-30T02:00:00+00:00",
        },
    }))

    assert "영발 2번째" in html
    assert "foms-partner-push__item--sent" in html
    assert "foms-partner-push__item--stale" in html
    assert "foms-partner-push__check" in html
    assert "foms-partner-push__again" not in html
    assert ">재<" not in html
    assert 'role="img"' in html
    assert "10-30 10:02" in html
    assert "foms-partner-push__item--wait" not in html
    assert 'style="' not in html
    assert str(render({})) == ""


def test_workqueue_places_marks_only_on_partner_rows() -> None:
    """작업 큐 세 표면: 협력사 이름 다음, 결제·제품보다 앞. 이름 게이트 안."""
    grid = (ROOT / "templates/orders/partials/dashboard_grid.html").read_text(encoding="utf-8")
    name = grid.index("partner_mark(o.partner_name")
    push = grid.index("partner_push_marks(o.structured_data)")
    pay = grid.index("erp-payment-badge-row", name)
    assert name < push < pay
    assert "{%- if o.partner_name -%}" in grid[name:push]

    card = (ROOT / "templates/partials/shared/erp_mobile_queue_card_v2.html").read_text(encoding="utf-8")
    card_push = card.index("partner_push_marks(order.structured_data)")
    assert card.index("partner_mark(order.partner_name") < card_push
    assert card_push < card.index("foms-queue-card-v2__subtitle")
    assert "{%- if order.partner_name -%}" in card[card.index("partner_mark(order.partner_name"):card_push]

    tablet = (ROOT / "templates/orders/partials/tablet_workqueue_grid.html").read_text(encoding="utf-8")
    tablet_push = tablet.index("partner_push_marks(o.structured_data)")
    assert tablet.index("foms-tqchip-urgent") < tablet_push
    assert "{%- if o.partner_name -%}" in tablet[tablet.index("partner_mark(o.partner_name"):tablet_push]


def test_requested_construction_mark_until_confirmed() -> None:
    """희망 시공일은 우리 시공일이 정해지기 전만 칸이 된다. 날짜는 월-일로 줄인다."""
    from foms.services.orders.partner_push_marks import partner_requested_construction_mark

    wish = {"partner_intake": {"requested_construction": {"date": "2026-11-06", "time": "오후"}}}
    mark = partner_requested_construction_mark(wish)
    assert mark["label"] == "희망 시공 11-06 오후"
    assert "2026-11-06 오후" in mark["aria"]

    confirmed = dict(wish, schedule={"construction": {"date": "2026-11-07"}})
    assert partner_requested_construction_mark(confirmed) is None
    assert partner_requested_construction_mark({}) is None
    assert partner_requested_construction_mark(None) is None
    assert partner_requested_construction_mark(
        {"partner_intake": {"requested_construction": {"date": "", "time": ""}}}
    ) is None
    assert partner_requested_construction_mark(
        {"partner_intake": {"requested_construction": {"date": "", "time": "종일"}}}
    )["label"] == "희망 시공 종일"


def test_macro_renders_wish_alone_and_after_push(app) -> None:
    """PUSH 가 없어도 희망 시공일만으로 줄이 생기고, 있으면 PUSH 칸 뒤에 붙는다."""
    render = app.jinja_env.get_template(
        "partials/shared/channel_mark.html"
    ).module.partner_push_marks
    wish = {"partner_intake": {"requested_construction": {"date": "2026-11-06", "time": "오전"}}}

    alone = str(render(wish))
    assert "foms-partner-push__item--wish" in alone
    assert "희망 시공 11-06 오전" in alone
    assert 'style="' not in alone

    both = str(render(dict(wish, channeltalk_push={"pushed": True, "sent_at": _SENT_AT})))
    assert both.index("foms-partner-push__item--sent") < both.index("foms-partner-push__item--wish")
