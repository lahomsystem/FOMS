"""AS 타임라인 로그(as_log) 도메인 서비스 테스트."""

import pytest

from foms.services.orders.as_log import (
    append_client_log,
    append_system_log,
    build_as_log_entry,
    build_as_timeline_view,
    coerce_client_log_type,
    migrate_legacy_into_log,
)

_DECORATED_KEYS = {"ts_abs", "ts_rel", "type_label", "is_system", "is_legacy", "is_edited"}


def _entry(idx: int, ts: str, *, log_type: str = "memo") -> dict:
    """고정 ts를 가진 as_log 항목(초 해상도 시드 형식)."""
    return {
        "id": f"al_seed_{idx}",
        "ts": ts,
        "by": "김",
        "by_id": 1,
        "type": log_type,
        "text": f"m{idx}",
        "edited_at": None,
        "edited_by": None,
    }


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


def test_append_system_log_is_server_authored():
    """시스템 항목은 서버 저자(by='시스템', by_id=None)로 append되고 스트림에 노출된다."""
    sd = {"shipment": {}}
    entry = append_system_log(sd, text="AS 비용 확정")
    assert entry["type"] == "system"
    assert entry["by"] == "시스템" and entry["by_id"] is None
    assert sd["shipment"]["as_log"][-1]["id"] == entry["id"]

    decorated = build_as_timeline_view(sd)["stream"][0]
    assert decorated["is_system"] is True
    assert decorated["type_label"] == "시스템"


def test_legacy_entry_ids_are_deterministic():
    """legacy id는 원본 필드에서 파생한 상수 — 렌더 반복·영구화 전후로 불변."""
    sd = {"shipment": {"as_content": "<div>옛 기록</div>", "as_content_2": "<div>탭2</div>"}}
    expected = ["al_legacy_as_content", "al_legacy_as_content_2"]

    first = [e["id"] for e in build_as_timeline_view(sd)["legacy"]]
    second = [e["id"] for e in build_as_timeline_view(sd)["legacy"]]
    assert first == expected and second == expected  # 렌더마다 재생성되지 않는다

    migrate_legacy_into_log(sd)
    assert [e["id"] for e in sd["shipment"]["as_log"]] == expected  # 영구화 후에도 동일


def test_sanitized_injection_skips_reparse():
    """사전 정리값을 주입하면 shipment 원문을 다시 파싱하지 않는다(행 루프 중복 sanitize 제거).

    주입값을 원문과 다르게 주고 주입값이 이겨야 재파싱이 없다는 증거가 된다. 주입을 무시하면 red.
    """
    sd = {"shipment": {"as_content": "<div>원문</div>", "as_content_2": "<div>탭2 원문</div>"}}

    view = build_as_timeline_view(sd, sanitized=("주입 1번", "주입 2번"))
    assert [e["text"] for e in view["legacy"]] == ["주입 1번", "주입 2번"]
    assert [e["id"] for e in view["legacy"]] == ["al_legacy_as_content", "al_legacy_as_content_2"]

    # 빈 주입값은 해당 legacy 항목을 만들지 않는다(as_content_2 없는 행)
    only_first = build_as_timeline_view(sd, sanitized=("주입 1번", ""))
    assert [e["id"] for e in only_first["legacy"]] == ["al_legacy_as_content"]

    # 미주입은 기존 동작(원문 sanitize) 그대로
    assert [e["text"] for e in build_as_timeline_view(sd)["legacy"]] == [
        "<div>원문</div>", "<div>탭2 원문</div>",
    ]


def test_migrate_ignores_sanitized_injection_path():
    """영구화(write) 경로는 주입 없이 shipment를 정본으로 읽는다 — 읽기 최적화가 저장값을 오염시키지 않는다."""
    sd = {"shipment": {"as_content": "<div>옛 기록</div>"}}
    build_as_timeline_view(sd, sanitized=("표시용 위조값", None))  # 읽기 뷰는 주입값 사용
    assert migrate_legacy_into_log(sd) is True
    assert sd["shipment"]["as_log"][0]["text"] == "<div>옛 기록</div>"  # 저장은 원문 기준


def test_equal_ts_truncation_keeps_newest():
    """ts 동률 그룹에서 절단할 때 가장 최신(삽입 순서 뒤) 항목이 살아남는다."""
    sd = {"shipment": {"as_log": [_entry(i, "2026-07-20 10:00:00") for i in range(4)]}}
    view = build_as_timeline_view(sd, recent_limit=2)
    assert [e["text"] for e in view["stream"]] == ["m3", "m2"]
    assert view["stream_total"] == 4 and view["has_more"] is True


def test_mixed_ts_orders_by_time_then_insertion():
    """서로 다른 ts는 시간 역순 우선, 동률 구간만 삽입 역순으로 정렬된다."""
    sd = {"shipment": {"as_log": [
        _entry(0, "2026-07-20 09:00:00"),
        _entry(1, "2026-07-20 11:00:00"),
        _entry(2, "2026-07-20 11:00:00"),
        _entry(3, "2026-07-20 10:00:00"),
    ]}}
    view = build_as_timeline_view(sd)
    assert [e["text"] for e in view["stream"]] == ["m2", "m1", "m3", "m0"]


def test_view_shape_stable_after_decorate_moved_post_slice():
    """절단 후 decorate로 바뀌어도 반환 shape과 항목 파생 필드는 동일하다."""
    sd = {"shipment": {"as_log": [_entry(i, f"2026-07-20 10:0{i}:00") for i in range(5)]}}
    sd["shipment"]["as_log"].append(_entry(9, "2026-07-20 08:00:00", log_type="reception"))
    view = build_as_timeline_view(sd, recent_limit=2)

    assert set(view) == {"reception", "legacy", "stream", "stream_total", "has_more", "count"}
    assert len(view["stream"]) == 2
    for decorated in view["stream"]:
        assert _DECORATED_KEYS <= set(decorated)
    assert _DECORATED_KEYS <= set(view["reception"])
    assert view["count"] == view["stream_total"] + 1  # 절단분이 아닌 전체 기준


def test_decorate_does_not_mutate_source_entries():
    """decorate는 얕은 복사 — 원본 as_log 항목에 파생 필드가 새지 않는다."""
    sd = {"shipment": {"as_log": [_entry(0, "2026-07-20 10:00:00")]}}
    build_as_timeline_view(sd)
    assert _DECORATED_KEYS.isdisjoint(sd["shipment"]["as_log"][0])
