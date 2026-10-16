"""수정 대상 도면 칩 — 번호와 함께 파일 이름·썸네일을 보여 준다(2026-10-12 #5600).

도면 장 안의 페이지 번호(마법사 시트 번호)와 ERP 전달 순번이 달라 "2번 대상" 만으로는
도면팀이 다른 도면을 고쳤다. 대상은 저장된 번호가 아니라 key 로 찾아 이름을 붙인다.
"""
from pathlib import Path

from foms.web.drawing.workbench import _event_target_files

FILES = [
    {'key': 'orders/5600/drawing_wizard/exports/a.png', 'filename': '도면_장익중_5600_몰딩 여닫이.png'},
    {'key': 'orders/5600/drawing_wizard/exports/b.png', 'filename': '도면_장익중_5600_보테가 슬라이딩.png'},
]


def test_target_resolved_by_key_with_name_and_thumbnail():
    event = {'action': 'REQUEST_REVISION', 'target_drawing_keys': [FILES[1]['key']], 'target_drawing_number': 2}
    rows = _event_target_files(5600, event, FILES)
    assert rows == [{
        'no': 2,
        'name': '도면_장익중_5600_보테가 슬라이딩',
        'view_url': '/api/files/view/orders/5600/drawing_wizard/exports/b.png',
    }]


def test_key_wins_over_stale_number():
    event = {'target_drawing_key': FILES[0]['key'], 'target_drawing_number': 2}
    assert _event_target_files(5600, event, FILES)[0]['no'] == 1


def test_unknown_key_falls_back_to_number_only():
    event = {'target_drawing_keys': ['orders/5600/gone.png'], 'target_drawing_numbers': [2]}
    assert _event_target_files(5600, event, FILES) == [{'no': 2, 'name': '', 'view_url': ''}]


def test_foreign_order_key_gets_no_link():
    files = [{'key': 'orders/9999/drawing_wizard/exports/x.png', 'filename': 'x.png'}]
    event = {'target_drawing_keys': [files[0]['key']]}
    assert _event_target_files(5600, event, files)[0]['view_url'] == ''


def test_template_uses_chip_in_timeline_and_request_card():
    src = Path('templates/drawing/partials/workbench_detail_body.html').read_text(encoding='utf-8')
    assert "dw_target_chips(h.target_files, 'target-history-' ~ loop.index0)" in src
    assert "dw_target_chips(r.target_files, 'target-request-' ~ loop.index0)" in src


def test_replaced_target_uses_history_name_and_stored_number():
    """수정본으로 교체되어 지금 목록에 없는 옛 판도 이름·그림을 보여 준다(운영 #5600 실측)."""
    from foms.web.drawing.workbench import _history_file_names
    old_key = 'orders/5600/drawing_wizard/exports/old_bottega.png'
    history = [
        {'action': 'TRANSFER', 'files': [FILES[0], {'key': old_key, 'filename': '도면_장익중_5600_보테가 슬라이딩.png'}]},
        {'action': 'REQUEST_REVISION', 'target_drawing_keys': [old_key], 'target_drawing_numbers': [2]},
    ]
    rows = _event_target_files(5600, history[1], FILES, _history_file_names(history))
    assert rows == [{
        'no': 2,
        'name': '도면_장익중_5600_보테가 슬라이딩',
        'view_url': f'/api/files/view/{old_key}',
    }]


def test_mobile_thread_and_dashboard_show_target_name():
    from foms.web.drawing.workbench import _target_files_text
    event = {'target_files': [{'no': 2, 'name': '보테가 슬라이딩', 'view_url': ''}]}
    assert _target_files_text(event, [2]) == '2번 · 보테가 슬라이딩'
    assert _target_files_text({}, [2]) == '2번 대상'
    js = Path('static/js/orders/dashboard/erp-dashboard-gateway.js').read_text(encoding='utf-8')
    assert 'drawingTargetLabel(h, names)' in js
