"""AS 타임라인 로그(as_log) 도메인 서비스 테스트."""

import pytest

from foms.services.orders.as_log import (
    append_client_log,
    build_as_log_entry,
    build_as_timeline_view,
    coerce_client_log_type,
    migrate_legacy_into_log,
)


def test_client_type_rejects_system():
    with pytest.raises(ValueError):
        coerce_client_log_type("system")


def test_client_type_defaults_memo():
    assert coerce_client_log_type("bogus") == "memo"
    assert coerce_client_log_type("call") == "call"


def test_migrate_legacy_seeds_from_as_content():
    sd = {"shipment": {"as_content": "<div>옛 기록</div>", "as_content_2": "<div>탭2</div>"}}
    assert migrate_legacy_into_log(sd) is True
    log = sd["shipment"]["as_log"]
    assert len(log) == 2 and all(e["legacy"] is True for e in log)
    # 재호출은 no-op
    assert migrate_legacy_into_log(sd) is False


def test_append_creates_reception_anchor_and_stream():
    sd = {"shipment": {}}
    append_client_log(sd, log_type="reception", text="접수", by="김", by_id=1)
    append_client_log(sd, log_type="call", text="통화함", by="김", by_id=1)
    view = build_as_timeline_view(sd)
    assert view["reception"]["text"] == "접수"
    assert view["stream"][0]["text"] == "통화함"  # 역시간순
    assert view["stream_total"] == 1


def test_build_as_log_entry_shape():
    entry = build_as_log_entry(log_type="memo", text="내용", by="김", by_id=7)
    assert entry["id"].startswith("al_")
    assert entry["type"] == "memo"
    assert entry["by"] == "김" and entry["by_id"] == 7
    assert entry["edited_at"] is None and entry["edited_by"] is None
    assert entry["ts"]  # UTC naive ISO


def test_timeline_view_lazy_legacy_is_non_destructive():
    """as_log 미생성 상태에서 뷰 구성은 sd를 변경하지 않는다(표시 시점 비파괴)."""
    sd = {"shipment": {"as_content": "<div>옛 기록</div>"}}
    view = build_as_timeline_view(sd)
    assert len(view["legacy"]) == 1
    assert view["legacy"][0]["is_legacy"] is True
    assert "as_log" not in sd["shipment"]  # 영구화는 최초 append 시점


def test_first_append_persists_legacy_entries():
    sd = {"shipment": {"as_content": "<div>옛 기록</div>"}}
    append_client_log(sd, log_type="memo", text="새 메모", by="김", by_id=1)
    log = sd["shipment"]["as_log"]
    assert len(log) == 2
    assert log[0]["legacy"] is True and log[1]["text"] == "새 메모"


def test_stream_respects_recent_limit():
    sd = {"shipment": {}}
    for i in range(5):
        append_client_log(sd, log_type="memo", text=f"m{i}", by="김", by_id=1)
    view = build_as_timeline_view(sd, recent_limit=2)
    assert len(view["stream"]) == 2
    assert view["stream_total"] == 5
    assert view["has_more"] is True
