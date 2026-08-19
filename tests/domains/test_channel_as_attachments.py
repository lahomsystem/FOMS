"""AS PUSH 첨부 선정 규칙(AS-FRESH-01 T6) 계약.

전량 발사 → "이번 건의 최신 첨부"로 좁히는 변경이라, **덜 보내는 방향의 회귀**가 가장 큰
위험이다. 3단 판정(현재 회차 → 미발송분 → 최신 N)의 하한을 여기서 고정한다.
"""

from __future__ import annotations

from types import SimpleNamespace

from foms.services.channel_as_attachments import (
    last_pushed_max_attachment_id,
    select_as_push_attachments,
)


def _att(
    att_id: int,
    *,
    as_log_id: str | None = None,
    storage_key: str | None = None,
    sort_order: int | None = None,
):
    return SimpleNamespace(
        id=att_id,
        as_log_id=as_log_id,
        sort_order=sort_order,
        storage_key=f"orders/1/f{att_id}.jpg" if storage_key is None else storage_key,
        filename=f"f{att_id}.jpg",
        file_type="image",
    )


def _sd(*entries: dict) -> dict:
    return {"shipment": {"as_log": list(entries)}}


def _log(log_id: str, log_type: str = "memo", round_no: int = 1, **extra) -> dict:
    entry = {"id": log_id, "type": log_type, "round": round_no, "ts": "2026-08-13T01:00:00"}
    entry.update(extra)
    return entry


def test_selects_current_round_attachments_only() -> None:
    """1단: 기록에 결합된 첨부는 현재 회차 몫만 나간다."""
    sd = _sd(
        _log("al_1", round_no=1),
        _log("al_v", "verdict", 1, verdict="unresolved"),  # 미결 = 2회차 개시
        _log("al_2", round_no=2),
    )
    attachments = [_att(1, as_log_id="al_1"), _att(2, as_log_id="al_2")]

    picked = select_as_push_attachments(sd, attachments, None)

    assert [a.id for a in picked] == [2]


def test_falls_back_to_unsent_delta_when_no_round_link() -> None:
    """2단: 결합이 없으면(T1 이전 첨부) 마지막 발송 id 이후만."""
    picked = select_as_push_attachments(
        {}, [_att(1), _att(2), _att(3)], {"max_attachment_id": 2}
    )

    assert [a.id for a in picked] == [3]


def test_falls_back_to_newest_when_nothing_new() -> None:
    """3단: 회차 결합도 신규분도 없으면 최신 N장(구주문 최초/재전송)."""
    picked = select_as_push_attachments(
        {}, [_att(1), _att(2)], {"max_attachment_id": 99}, limit=1
    )

    assert [a.id for a in picked] == [2]


def test_cap_drops_oldest_not_newest() -> None:
    """상한 절단이 **최신**을 버리면 안 된다 — 이 버그가 AS-FRESH-01 의 발단이다."""
    attachments = [_att(i) for i in range(1, 22)]  # 21장

    picked = select_as_push_attachments({}, attachments, None, limit=20)

    assert len(picked) == 20
    assert picked[-1].id == 21  # 최신 보존
    assert picked[0].id == 2  # 가장 오래된 1장만 탈락
    assert [a.id for a in picked] == sorted(a.id for a in picked)  # 업로드 순 전송


def test_skips_attachments_without_storage_key() -> None:
    picked = select_as_push_attachments({}, [_att(1, storage_key=""), _att(2)], None)

    assert [a.id for a in picked] == [2]


def test_deleted_log_entry_does_not_bind_round() -> None:
    """소프트 삭제된 기록에 걸린 첨부는 회차 결합을 잃고 델타 판정으로 내려간다."""
    sd = _sd(_log("al_1", deleted=True))

    picked = select_as_push_attachments(
        sd, [_att(5, as_log_id="al_1")], {"max_attachment_id": 9}
    )

    assert [a.id for a in picked] == [5]  # 3단 폴백으로 살아남는다(빈손 전송 금지)


def test_last_pushed_max_attachment_id_reads_history() -> None:
    assert last_pushed_max_attachment_id(None) == 0
    assert last_pushed_max_attachment_id({}) == 0
    assert last_pushed_max_attachment_id({"max_attachment_id": 7}) == 7
    # max_attachment_id 없는 구이력은 목록 최대값으로 폴백.
    assert last_pushed_max_attachment_id({"attachment_ids": [3, 11, 5]}) == 11


def test_send_order_follows_sort_order_not_id() -> None:
    """지정한 sort_order 가 id 보다 앞선다 (AS-SORT-01)."""
    attachments = [
        _att(10, sort_order=2),
        _att(11, sort_order=0),
        _att(12, sort_order=1),
    ]

    picked = select_as_push_attachments({}, attachments, None)

    assert [a.id for a in picked] == [11, 12, 10]


def test_cap_keeps_end_of_sort_order_sequence() -> None:
    """상한 절단은 시퀀스 끝(큰 sort_order)을 남긴다."""
    attachments = [_att(i, sort_order=i - 1) for i in range(1, 22)]

    picked = select_as_push_attachments({}, attachments, None, limit=20)

    assert [a.id for a in picked] == list(range(2, 22))
