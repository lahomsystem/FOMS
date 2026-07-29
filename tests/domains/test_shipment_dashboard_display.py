"""enrich_shipment_rows as_material_text 파생 필드 단위 테스트 (DB 불필요)."""

from types import SimpleNamespace

from foms.services.shipment_dashboard_display import enrich_shipment_rows


def test_enrich_as_row_converts_material_log_html_to_plain_text():
    """AS 행은 as_log material 최신 항목 HTML을 개행 보존 plain text로 변환한다."""
    row = SimpleNamespace(
        id=1,
        status="AS",
        structured_data={
            "shipment": {
                "as_log": [
                    {
                        "type": "material",
                        "ts": "2026-07-20T10:00:00",
                        "text": "<div>자재 A</div><div>자재 B</div>",
                    }
                ]
            }
        },
    )

    enrich_shipment_rows([row])

    assert row.as_material_text == "자재 A\n자재 B"


def test_enrich_non_as_row_has_empty_material_text():
    """비AS 행은 as_material_text가 빈 문자열이다."""
    row = SimpleNamespace(id=2, status="RECEIVED", structured_data={})

    enrich_shipment_rows([row])

    assert row.as_material_text == ""
