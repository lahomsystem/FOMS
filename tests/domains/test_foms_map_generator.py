from foms.services.common.map_generator import FOMSMapGenerator


def _render_map_html(order_data):
    map_obj = FOMSMapGenerator().create_map(order_data, title="Order Map")
    assert map_obj is not None
    return map_obj.get_root().render()


def test_duplicate_location_markers_render_pastel_pink():
    html = _render_map_html(
        [
            {
                "id": 1,
                "customer_name": "Alpha",
                "address": "Seoul Same Address 1",
                "product": "Desk",
                "status": "RECEIVED",
                "received_date": "2026-03-31",
                "latitude": 37.5001,
                "longitude": 127.0001,
            },
            {
                "id": 2,
                "customer_name": "Beta",
                "address": "Seoul Same Address 1",
                "product": "Chair",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.5001,
                "longitude": 127.0001,
            },
            {
                "id": 3,
                "customer_name": "Gamma",
                "address": "Seoul Unique Address 2",
                "product": "Cabinet",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.515,
                "longitude": 127.102,
            },
        ]
    )

    assert "background: #f8c8d8" in html
    assert "x2" in html
    assert "background: #28a745" in html


def test_unique_marker_keeps_status_color():
    html = _render_map_html(
        [
            {
                "id": 10,
                "customer_name": "Delta",
                "address": "Unique Address 10",
                "product": "Bed",
                "status": "RECEIVED",
                "received_date": "2026-03-31",
                "latitude": 37.4901,
                "longitude": 127.021,
            }
        ]
    )

    assert "background: #007bff" in html
    assert "x2" not in html


def test_as_status_marker_colors_registered():
    """AS 3종 상태는 회색 fallback이 아닌 전용 색 — JS STATUS_COLORS와 동기 계약."""
    from foms.services.common.map_generator import FOMSMapGenerator

    generator = FOMSMapGenerator()
    assert generator._get_status_color('AS_RECEIVED') == '#dc3545'
    assert generator._get_status_color('AS') == '#fd7e14'
    assert generator._get_status_color('AS_COMPLETED') == '#6c757d'


def test_measurement_marker_prefers_manager_color_theme():
    html = _render_map_html(
        [
            {
                "id": 11,
                "customer_name": "Manager Color",
                "address": "Unique Address 11",
                "product": "Desk",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.4902,
                "longitude": 127.0211,
                "manager_name": "이성민(서서울)",
                "manager_bg_color": "#FADADD",
                "manager_bg_source": "palette",
                "manager_text_color": "#000000",
            }
        ]
    )

    assert "background: #FADADD" in html
    assert "담당자:" in html
    assert "이성민(서서울)" in html


def test_fallback_manager_color_does_not_override_status_theme():
    html = _render_map_html(
        [
            {
                "id": 12,
                "customer_name": "Fallback Manager",
                "address": "Unique Address 12",
                "product": "Desk",
                "status": "RECEIVED",
                "received_date": "2026-03-31",
                "latitude": 37.4903,
                "longitude": 127.0212,
                "manager_name": "",
                "manager_bg_color": "#CCCCCC",
                "manager_bg_source": "fallback",
                "manager_text_color": "#000000",
            }
        ]
    )

    assert "background: #007bff" in html


def test_map_html_includes_visual_overlap_detection_hooks():
    html = _render_map_html(
        [
            {
                "id": 21,
                "customer_name": "Near A",
                "address": "Seoul Nearby Address 1",
                "product": "Desk",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.5001,
                "longitude": 127.0001,
            },
            {
                "id": 22,
                "customer_name": "Near B",
                "address": "Seoul Nearby Address 2",
                "product": "Chair",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.5006,
                "longitude": 127.0006,
            },
        ]
    )

    assert "scheduleVisualOverlapRefresh" in html
    assert "refreshVisualOverlapMarkers" in html
    assert "escapeHtml" in html
    assert "bindMarkerClickDelegation" in html
    assert "event.target.closest('.leaflet-marker-icon .foms-map-marker')" in html
    assert "String(start.orderId) === String(orderId)" in html
    assert "encodeURIComponent(start.lat)" in html
    assert "!response.ok" in html
    assert "getBoundingClientRect()" in html
    assert "data-route-state" in html
    assert "data-overlap-background" in html


def test_map_html_includes_duplicate_group_layout_hooks():
    html = _render_map_html(
        [
            {
                "id": 31,
                "customer_name": "Overlap A",
                "address": "Seoul Same Address 31",
                "product": "Desk",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.5001,
                "longitude": 127.0001,
            },
            {
                "id": 32,
                "customer_name": "Overlap B",
                "address": "Seoul Same Address 31",
                "product": "Chair",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.5003,
                "longitude": 127.0003,
            },
        ]
    )

    assert "applyDuplicateMarkerLayout" in html
    assert "window.duplicateMarkerZoomThreshold = 14" in html
    assert "setRenderedMarkerVisibility" in html
    assert "window.mapObject.getZoom() >= window.duplicateMarkerZoomThreshold" in html
    assert "wrapper.style.display = visible ? '' : 'none'" in html
    assert "clearMarkerVisualOffset" in html
    assert "applyDuplicateMarkerLayout();" in html
    assert "style.transform = 'translate(" in html
    assert "data-duplicate-group-size" in html
    assert html.count("data-duplicate-group-index") >= 2
    assert "data-duplicate-group-key" in html


def test_prepare_marker_data_promotes_snapshot_duplicate_location_metadata():
    generator = FOMSMapGenerator()
    prepared = generator._prepare_marker_data(
        [
            {
                "id": 41,
                "customer_name": "Snapshot A",
                "address": "서로 다른 원본 주소 A",
                "product": "Desk",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.5001,
                "longitude": 127.0001,
                "is_duplicate_location": True,
                "duplicate_location_group_size": 2,
                "duplicate_location_group_index": 1,
                "duplicate_location_group_key": "37.50010000,127.00010000",
            },
            {
                "id": 42,
                "customer_name": "Snapshot B",
                "address": "서로 다른 원본 주소 B",
                "product": "Chair",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.5002,
                "longitude": 127.0002,
                "is_duplicate_location": True,
                "duplicate_location_group_size": 2,
                "duplicate_location_group_index": 2,
                "duplicate_location_group_key": "37.50010000,127.00010000",
            },
        ]
    )

    assert prepared[0]["duplicate_group_size"] == 2
    assert prepared[1]["duplicate_group_size"] == 2
    assert prepared[0]["duplicate_group_index"] == 1
    assert prepared[1]["duplicate_group_index"] == 2
    assert prepared[0]["duplicate_group_key"] == "meta:37.50010000,127.00010000"
    assert prepared[1]["duplicate_group_key"] == "meta:37.50010000,127.00010000"


def test_prepare_marker_data_falls_back_to_duplicate_address_metadata():
    generator = FOMSMapGenerator()
    prepared = generator._prepare_marker_data(
        [
            {
                "id": 51,
                "customer_name": "Address A",
                "address": "서울시 강동구 고덕로 130",
                "product": "Desk",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.5001,
                "longitude": 127.0001,
                "is_duplicate_location": True,
                "duplicate_address_group_size": 2,
                "duplicate_address_group_index": 1,
                "duplicate_address_group_key": "addr:seoul-godeok",
            },
            {
                "id": 52,
                "customer_name": "Address B",
                "address": "서울시 강동구 고덕로 130",
                "product": "Chair",
                "status": "MEASURE",
                "received_date": "2026-03-31",
                "latitude": 37.5003,
                "longitude": 127.0003,
                "is_duplicate_location": True,
                "duplicate_address_group_size": 2,
                "duplicate_address_group_index": 2,
                "duplicate_address_group_key": "addr:seoul-godeok",
            },
        ]
    )

    assert prepared[0]["duplicate_group_size"] == 2
    assert prepared[1]["duplicate_group_size"] == 2
    assert prepared[0]["duplicate_group_index"] == 1
    assert prepared[1]["duplicate_group_index"] == 2
    assert prepared[0]["duplicate_group_key"] == "meta:addr:seoul-godeok"
    assert prepared[1]["duplicate_group_key"] == "meta:addr:seoul-godeok"
