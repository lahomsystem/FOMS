"""실측 패널·모달 지역 묶음 분류(시/도 생략형 병합·동명 시군구·지역 미상)."""

from __future__ import annotations

from foms.api.measurement.routes import (
    annotate_measurement_case_groups,
    measurement_case_sort_key,
    measurement_region_key,
)


def _case(address: str, name: str = "x", time: str = "", regional: bool = False) -> dict:
    return {"address": address, "customer_name": name, "time": time, "is_regional": regional}


def test_region_key_forms():
    assert measurement_region_key("경기 수원시 권선구 효원로 146") == ("경기", "수원시")
    assert measurement_region_key("수원시 권선구 효원로 146") == ("", "수원시")
    assert measurement_region_key("서울특별시 강동구 아리수로97길 20") == ("서울", "강동구")
    assert measurement_region_key("강동구 아리수로97길 20") == ("", "강동구")
    assert measurement_region_key("경수대로 한일타운아파트 112동1803호") == ("", "")
    assert measurement_region_key("세종특별자치시 한누리대로 2130") == ("세종", "")
    assert measurement_region_key("") == ("", "")


def test_sido_inferred_from_sibling_case():
    cases = [
        _case("수원시 권선구 효원로 146, 매교역펠루시드 107동1004호", "최은혜"),
        _case("경기 수원시 권선구 효원로 146, 매교역펠루시드아파트 115-203", "강미정"),
        _case("안산시 단원구 선부광장남로 113, 주공아파트 1201동 501호", "박혜주"),
    ]
    annotate_measurement_case_groups(cases)
    assert cases[0]["region_label"] == "경기 수원시"
    assert cases[1]["region_label"] == "경기 수원시"
    # 시/도 붙은 형제가 없으면 시군구 단독 라벨 유지
    assert cases[2]["region_label"] == "안산시"


def test_ambiguous_sigungu_not_merged():
    cases = [
        _case("서울 중구 세종대로 110", "a"),
        _case("부산 중구 중앙대로 120", "b", regional=True),
        _case("중구 아무개로 3", "c"),
    ]
    annotate_measurement_case_groups(cases)
    labels = [c["region_label"] for c in cases]
    assert labels == ["서울 중구", "부산 중구", "중구"], labels


def test_unknown_region_goes_last_within_scope():
    cases = [
        _case("경수대로 한일타운아파트 112동1803호", "미상", time="3시 30분"),
        _case("경기 광명시 하안로 172", "광명", time="11시"),
    ]
    annotate_measurement_case_groups(cases)
    cases.sort(key=measurement_case_sort_key)
    assert [c["customer_name"] for c in cases] == ["광명", "미상"]
    assert cases[1]["region_label"] == "지역 미상"


def test_scope_mixed_region_defaults_to_metro():
    cases = [
        _case("경기 광주시 송정동 산 28-4", "a", regional=True),
        _case("경기 광주시 다른로 1", "b", regional=False),
    ]
    annotate_measurement_case_groups(cases)
    assert {c["scope_label"] for c in cases} == {"수도권"}
