from foms_map_generator import FOMSMapGenerator


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
    assert "clearMarkerVisualOffset" in html
    assert "applyDuplicateMarkerLayout();" in html
    assert "style.transform = 'translate(" in html
    assert "data-duplicate-group-size" in html
    assert html.count("data-duplicate-group-index") >= 2
    assert "data-duplicate-group-key" in html
