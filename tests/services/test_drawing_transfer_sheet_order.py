"""전달 파일을 마법사 시트 순서(도면 장 번호)로 줄 세운다(2026-10-12 주문 5600).

[저장] 순서로 전달되어 1장 보테가 슬라이딩이 ERP 2번이 되었다.
"""
from foms.services.orders.drawing_transfer import order_by_wizard_sheets

SD = {'drawing_wizard': {'sheets': [{'id': 's-rru2cwcgh'}, {'id': 's-acbgwq0zi'}]}}


def _f(key, sheet_id=None):
    out = {'key': key}
    if sheet_id:
        out['sheet_id'] = sheet_id
    return out


def test_order_5600_saved_order_follows_sheet_order():
    files = [_f('molding.png', 's-acbgwq0zi'), _f('bottega.png', 's-rru2cwcgh')]
    assert [f['key'] for f in order_by_wizard_sheets(files, SD)] == ['bottega.png', 'molding.png']


def test_manual_upload_keeps_its_slot():
    files = [_f('molding.png', 's-acbgwq0zi'), _f('manual.pdf'), _f('bottega.png', 's-rru2cwcgh')]
    assert [f['key'] for f in order_by_wizard_sheets(files, SD)] == ['bottega.png', 'manual.pdf', 'molding.png']


def test_unknown_sheet_and_no_wizard_untouched():
    files = [_f('b.png', 's-zzzzzzzzz'), _f('a.png', 's-acbgwq0zi')]
    assert order_by_wizard_sheets(files, SD) == files
    assert order_by_wizard_sheets(files, {}) == files


def test_input_not_mutated():
    files = [_f('molding.png', 's-acbgwq0zi'), _f('bottega.png', 's-rru2cwcgh')]
    order_by_wizard_sheets(files, SD)
    assert files[0]['key'] == 'molding.png'
