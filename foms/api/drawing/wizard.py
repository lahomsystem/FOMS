"""도면 작업실 "도면 마법사" API (P1 백엔드).

- GET  ``/api/orders/<id>/drawing-wizard``        상태·자동채움 기본값·저장권한 조회
- PUT  ``/api/orders/<id>/drawing-wizard``         시트 상태 검증·낙관적 충돌 확인 후 저장
- POST ``/api/orders/<id>/drawing-wizard/asset``   이미지 에셋 업로드(R2-only, 참조 key 반환)

상태 JSON은 ``structured_data['drawing_wizard']`` 단일 키에 저장한다
(``copy.deepcopy`` + ``flag_modified`` 패턴). 이미지는 base64 인라인을 금지하고
반드시 ``orders/<id>/drawing_wizard/`` 접두 업로드 참조여야 한다(설계서 §1.3, §5).
"""

import copy
import io
import json
import logging
import os
import re

from flask import Blueprint, Response, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.datastructures import FileStorage

from db import get_db
from models import Order, OrderAttachment
from foms.web.auth import login_required, get_user_by_id
from foms.services.datetime_kst import now_kst, now_utc_naive
from foms.services.erp_permissions import can_edit_erp
from foms.services.erp_policy import is_drawing_workbench_participant
from foms.services.storage import get_storage
from foms.services.drawing_wizard_defaults import build_wizard_defaults, resolve_assignee_drew_en
from foms.services.drawing_wizard_presets import load_wizard_presets, save_wizard_presets
from foms.services.erp_product_items import build_product_items_for_order
from foms.services.erp_display import _erp_coerce_item_price_krw

logger = logging.getLogger(__name__)

erp_orders_drawing_wizard_bp = Blueprint(
    'erp_orders_drawing_wizard',
    __name__,
    url_prefix='/api/orders',
)

_MAX_STATE_BYTES = 64 * 1024
_MAX_SHEETS = 10
_MAX_OBJECTS_PER_SHEET = 200
_MAX_SHEET_NAME_LEN = 50
_MAX_FORM_VALUE_LEN = 500
_MAX_TEXT_LEN = 2000
_MAX_TEXT_RUNS = 60
_MAX_ASSET_BYTES = 10 * 1024 * 1024
# 버전 이력 — 전달 시점 시트 상태 스냅샷 포인터 최대 보관 수(초과 시 오래된 것부터 제거).
_MAX_VERSIONS = 30
_ALLOWED_ASSET_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
_ASSET_RAW_MIMETYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
}
_ALLOWED_TEXT_SIZES = (14, 17, 20, 24, 28)
_ALLOWED_ALIGNS = ('left', 'center')
_ALLOWED_OBJECT_TYPES = ('text', 'image', 'rect', 'ellipse', 'arrow', 'line')
_ALLOWED_STROKE_WIDTHS = (1, 2, 3)
_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')

# 제품별 도면 시트 — 시트 승격 값(제품 리스트 인덱스)
_MAX_PRODUCT_INDEX = 199
# 실측 사진 사이드 참조 — 첨부 category(주문 상세 실측 이미지와 동일 3종)
_MEASURE_PHOTO_CATEGORIES = ('measurement', 'measure_photo', 'photo')

# 표 레이아웃(열/행 경계) 승격 값 — 서버는 타입·범위만 검증(증가순·간격은 클라 책임).
_LAYOUT_X_MIN, _LAYOUT_X_MAX = 41, 1439       # 외곽 40/1440 안쪽
_LAYOUT_Y_MIN, _LAYOUT_Y_MAX = 900, 999       # 외곽 899/1000 안쪽
_LAYOUT_TOP_MIN, _LAYOUT_TOP_MAX = 100, 980   # 표 상단선(top) 이동 허용 범위(optional)
_MAX_LAYOUT_COLS = 12
_MAX_LAYOUT_ROWS = 6
_CELL_FONT_MIN, _CELL_FONT_MAX = 10, 28

_MSG_NOT_FOUND = '주문을 찾을 수 없습니다.'
_MSG_FORBIDDEN = '도면 담당자·도면팀 또는 관리자만 저장할 수 있습니다.'


def _load_order(db, order_id):
    """활성 ERP 주문을 로드한다(soft-delete·draft 제외). 없으면 None."""
    return db.query(Order).filter(
        Order.id == order_id,
        Order.active_filter(),
        Order.is_erp_order.is_(True),
    ).first()


def _load_structured_data(order) -> dict:
    """order.structured_data를 dict로 정규화(deepcopy)한다. 문자열이면 json.loads, 실패 시 {}."""
    raw = order.structured_data
    if isinstance(raw, dict):
        return copy.deepcopy(raw)
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}
    return {}


def _versions_prefix(order_id: int) -> str:
    """주문별 버전 스냅샷 R2 접두사(경로 격리 검증·업로드 폴더 공용, 끝에 ``/``)."""
    return f"orders/{order_id}/drawing_wizard/versions/"


def _can_save_wizard(current_user, order) -> bool:
    """ADMIN 또는 도면 작업실 참여자만 저장할 수 있다."""
    return bool(
        current_user
        and (current_user.role == 'ADMIN' or is_drawing_workbench_participant(current_user, order))
    )


def _can_manage_presets(current_user) -> bool:
    """전역 프리셋(도면팀 공유) 저장·삭제 권한.

    프리셋은 주문 무관 전역 자원이므로 주문 단위 참여 판정을 쓸 수 없다. 대신
    ADMIN·도면팀(DRAWING)·ERP 편집 팀(CS/SALES)에게 관리 권한을 부여한다.
    """
    if not current_user:
        return False
    if current_user.role == 'ADMIN':
        return True
    if (getattr(current_user, 'team', None) or '').strip() == 'DRAWING':
        return True
    return can_edit_erp(current_user)


def _parse_item_index(raw) -> int | None:
    """``?item=N`` 쿼리를 정수 인덱스로 파싱한다. 없거나 음수·비정수면 None(집계 모드)."""
    if raw is None:
        return None
    try:
        idx = int(raw)
    except (TypeError, ValueError):
        return None
    return idx if idx >= 0 else None


def _product_spec(item: dict) -> str:
    """제품 규격 표시값: width×depth×height(셋 다 있을 때), 아니면 ``spec`` 원문."""
    width = item.get('width')
    depth = item.get('depth')
    height = item.get('height')
    if width and depth and height:
        return f"{width}×{depth}×{height}"
    return str(item.get('spec') or '').strip()


def _product_price(item: dict) -> int | None:
    """제품 금액(원) 정수. 값이 없으면 None(가격 미입력)."""
    raw = item.get('price')
    if raw is None or raw == '' or raw is False:
        return None
    return _erp_coerce_item_price_krw(item)


def _build_products(db, order) -> list[dict]:
    """마법사 좌측 제품 리스트 소스 [{index, name, spec, price}] 를 구성한다.

    ``build_product_items_for_order`` 정규화 결과(이름/규격/가격)를 재사용한다.
    """
    products = []
    for idx, item in enumerate(build_product_items_for_order(db, order)):
        products.append({
            'index': idx,
            'name': str(item.get('product_name') or '').strip(),
            'spec': _product_spec(item),
            'price': _product_price(item),
        })
    return products


def _build_measure_photos(db, order) -> list[dict]:
    """실측 사진 사이드 참조 소스 [{key, filename, item_index, thumb_url}] 를 구성한다.

    주문 실측 첨부(``measurement``/``measure_photo``/``photo``)를 최신순으로 모아,
    ``item_index`` 가 제품 범위를 벗어나거나 음수·None 이면 공통(``item_index=None``)으로
    정규화한다(주문 상세의 common_measure_photos 규칙과 동일). ``thumb_url`` 은
    ``thumbnail_key`` 우선(없으면 ``storage_key``)으로 ``/api/files/view/`` 경로를 만든다.
    실측 원본은 읽기만 하며 변경하지 않는다.
    """
    order_id = getattr(order, 'id', None)
    if not order_id:
        return []
    product_count = len(build_product_items_for_order(db, order))
    photos = []
    for att in db.query(OrderAttachment).filter(
        OrderAttachment.order_id == order_id,
        OrderAttachment.category.in_(list(_MEASURE_PHOTO_CATEGORIES)),
    ).order_by(OrderAttachment.created_at.desc()).all():
        raw_index = getattr(att, 'item_index', None)
        try:
            item_index = int(raw_index) if raw_index is not None else None
        except (TypeError, ValueError):
            item_index = None
        if item_index is not None and not (0 <= item_index < product_count):
            item_index = None
        thumb_source = att.thumbnail_key or att.storage_key
        photos.append({
            'key': att.storage_key,
            'filename': att.filename,
            'item_index': item_index,
            'thumb_url': f'/api/files/view/{thumb_source}',
        })
    return photos


def _is_number(value) -> bool:
    """bool이 아닌 int/float이면 True."""
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _is_number_in_range(value, low: float, high: float) -> bool:
    """value가 숫자이고 [low, high] 범위에 있으면 True."""
    return _is_number(value) and low <= value <= high


def _validate_text_runs(obj: dict) -> str | None:
    """optional ``runs``(글자 단위 스타일 런) 검증. 없으면 통과(하위호환 단색 텍스트).

    각 런은 ``{t: str, c: '#rrggbb', b: bool}``. 런 개수 ≤ 60, t 길이 합계 ≤ _MAX_TEXT_LEN,
    런 t 를 순서대로 이은 문자열이 플레인 합본 ``text`` 와 정확히 일치해야 한다(SSOT).
    """
    if 'runs' not in obj:
        return None
    runs = obj.get('runs')
    if not isinstance(runs, list) or len(runs) > _MAX_TEXT_RUNS:
        return f'텍스트 스타일 런은 최대 {_MAX_TEXT_RUNS}개까지 허용됩니다.'
    total_len = 0
    joined = []
    for run in runs:
        if not isinstance(run, dict):
            return '텍스트 스타일 런 형식이 올바르지 않습니다.'
        run_text = run.get('t')
        if not isinstance(run_text, str):
            return '텍스트 스타일 런 내용이 올바르지 않습니다.'
        total_len += len(run_text)
        if total_len > _MAX_TEXT_LEN:
            return f'텍스트 내용이 올바르지 않습니다(최대 {_MAX_TEXT_LEN}자).'
        run_color = run.get('c')
        if not isinstance(run_color, str) or not _COLOR_RE.match(run_color):
            return '텍스트 스타일 런 색상 값이 올바르지 않습니다.'
        if not isinstance(run.get('b'), bool):
            return '텍스트 스타일 런 굵기 값이 올바르지 않습니다.'
        joined.append(run_text)
    if ''.join(joined) != obj.get('text'):
        return '텍스트 스타일 런과 본문이 일치하지 않습니다.'
    return None


def _validate_text_object(obj: dict) -> str | None:
    """텍스트 객체 필드 검증. 정상이면 None, 오류면 메시지.

    ``text``(플레인 합본)·``size``·``color``·``bold``·``align`` 는 필수이며,
    optional ``runs`` 가 있으면 글자 단위 스타일을 추가 검증한다(하위호환).
    """
    text = obj.get('text')
    if not isinstance(text, str) or len(text) > _MAX_TEXT_LEN:
        return f'텍스트 내용이 올바르지 않습니다(최대 {_MAX_TEXT_LEN}자).'
    if obj.get('size') not in _ALLOWED_TEXT_SIZES:
        return '텍스트 크기 값이 올바르지 않습니다.'
    color = obj.get('color')
    if not isinstance(color, str) or not _COLOR_RE.match(color):
        return '텍스트 색상 값이 올바르지 않습니다.'
    if not isinstance(obj.get('bold'), bool):
        return '텍스트 굵기 값이 올바르지 않습니다.'
    if obj.get('align') not in _ALLOWED_ALIGNS:
        return '텍스트 정렬 값이 올바르지 않습니다.'
    return _validate_text_runs(obj)


def _validate_image_object(obj: dict, order_id: int) -> str | None:
    """이미지 객체 필드 검증(경로 격리·base64 인라인 차단 포함)."""
    if not _is_number_in_range(obj.get('h'), 1, 3000):
        return '이미지 높이가 범위를 벗어났습니다.'
    key = obj.get('key')
    if not isinstance(key, str) or not key:
        return '이미지 참조 키가 올바르지 않습니다.'
    if key.startswith('data:'):
        return '이미지는 base64 인라인이 아닌 업로드 참조여야 합니다.'
    if not key.startswith(f'orders/{order_id}/drawing_wizard/'):
        return '이미지 참조 키 경로가 올바르지 않습니다.'
    for dim_key in ('natural_w', 'natural_h'):
        if dim_key in obj and not _is_number(obj.get(dim_key)):
            return '이미지 원본 치수 값이 올바르지 않습니다.'
    return None


def _validate_rotation(obj: dict) -> str | None:
    """공통 optional ``rotation``(있으면 -360~360 숫자). 없으면 통과."""
    if 'rotation' in obj and not _is_number_in_range(obj.get('rotation'), -360, 360):
        return '객체 회전 값이 올바르지 않습니다.'
    return None


def _validate_stroke(obj: dict) -> str | None:
    """도형 공통 선 속성: ``stroke`` ``#rrggbb`` + ``strokeWidth`` in (1,2,3)."""
    stroke = obj.get('stroke')
    if not isinstance(stroke, str) or not _COLOR_RE.match(stroke):
        return '도형 선 색상 값이 올바르지 않습니다.'
    stroke_width = obj.get('strokeWidth')
    if isinstance(stroke_width, bool) or stroke_width not in _ALLOWED_STROKE_WIDTHS:
        return '도형 선 굵기 값이 올바르지 않습니다.'
    return None


def _validate_shape_object(obj: dict) -> str | None:
    """rect/ellipse 필드 검증(높이 범위 + 선 속성). x/y/w 는 공통에서 검증됨."""
    if not _is_number_in_range(obj.get('h'), 1, 3000):
        return '도형 높이가 범위를 벗어났습니다.'
    return _validate_stroke(obj)


def _validate_line_object(obj: dict) -> str | None:
    """arrow/line 필드 검증. ``points`` 숫자 4개(각 -2000~4000) + 선 속성.

    x/y/w 는 요구하지 않으며, 존재하면 숫자인지만 확인한다.
    """
    points = obj.get('points')
    if not isinstance(points, list) or len(points) != 4:
        return '도형 점 좌표(points)는 숫자 4개여야 합니다.'
    for coord in points:
        if not _is_number_in_range(coord, -2000, 4000):
            return '도형 점 좌표가 범위를 벗어났습니다.'
    for opt_key in ('x', 'y', 'w'):
        if opt_key in obj and not _is_number(obj.get(opt_key)):
            return '도형 좌표 값이 올바르지 않습니다.'
    return _validate_stroke(obj)


def _validate_object(obj, order_id: int) -> str | None:
    """객체 공통 필드(type/rotation)를 검증한 뒤 유형별 검증에 위임한다.

    허용 유형은 6종(text/image/rect/ellipse/arrow/line). text/image/rect/ellipse 는
    공통 x/y/w 범위를 요구하고, arrow/line 은 ``points`` 기반이라 x/y/w 를 요구하지 않는다.
    ``rotation`` 은 모든 유형 공통 optional(-360~360).
    """
    if not isinstance(obj, dict):
        return '객체 형식이 올바르지 않습니다.'
    obj_type = obj.get('type')
    if obj_type not in _ALLOWED_OBJECT_TYPES:
        return '지원하지 않는 객체 유형입니다.'
    rotation_error = _validate_rotation(obj)
    if rotation_error:
        return rotation_error
    if obj_type in ('arrow', 'line'):
        return _validate_line_object(obj)
    if not _is_number_in_range(obj.get('x'), -2000, 4000):
        return '객체 x 좌표가 범위를 벗어났습니다.'
    if not _is_number_in_range(obj.get('y'), -2000, 4000):
        return '객체 y 좌표가 범위를 벗어났습니다.'
    if not _is_number_in_range(obj.get('w'), 1, 3000):
        return '객체 너비가 범위를 벗어났습니다.'
    if obj_type == 'text':
        return _validate_text_object(obj)
    if obj_type == 'image':
        return _validate_image_object(obj, order_id)
    return _validate_shape_object(obj)


def _validate_layout(layout) -> str | None:
    """폼 ``layout``(표 열/행 경계) 구조 검증.

    ``cols``/``rows`` 는 숫자 리스트(각 길이 캡·좌표 범위), ``addr``/``top`` 은 optional 숫자.
    증가순·최소간격은 클라이언트 책임이며 서버는 타입·범위만 확인한다(설계서 I-5).
    ``top`` 은 하단 표 상단선(y) 위치로, 없으면(구 저장분) 통과한다.
    """
    if not isinstance(layout, dict):
        return '폼 layout 형식이 올바르지 않습니다.'
    cols = layout.get('cols')
    if not isinstance(cols, list) or len(cols) > _MAX_LAYOUT_COLS:
        return '폼 layout cols 형식이 올바르지 않습니다.'
    for col in cols:
        if not _is_number_in_range(col, _LAYOUT_X_MIN, _LAYOUT_X_MAX):
            return '폼 layout cols 값이 범위를 벗어났습니다.'
    if 'addr' in layout and not _is_number_in_range(layout.get('addr'), _LAYOUT_X_MIN, _LAYOUT_X_MAX):
        return '폼 layout addr 값이 범위를 벗어났습니다.'
    if 'top' in layout and not _is_number_in_range(layout.get('top'), _LAYOUT_TOP_MIN, _LAYOUT_TOP_MAX):
        return '폼 layout top 값이 범위를 벗어났습니다.'
    rows = layout.get('rows')
    if not isinstance(rows, list) or len(rows) > _MAX_LAYOUT_ROWS:
        return '폼 layout rows 형식이 올바르지 않습니다.'
    for row in rows:
        if not _is_number_in_range(row, _LAYOUT_Y_MIN, _LAYOUT_Y_MAX):
            return '폼 layout rows 값이 범위를 벗어났습니다.'
    return None


def _validate_form(form: dict) -> str | None:
    """폼 값은 문자열(≤500자). 예외: ``checks``=dict[str,bool], ``layout``=경계 dict,
    ``cell_font``=10~28 숫자."""
    for key, value in form.items():
        if key == 'checks':
            if not isinstance(value, dict):
                return '폼 checks 형식이 올바르지 않습니다.'
            for check_value in value.values():
                if not isinstance(check_value, bool):
                    return '폼 checks 값은 참/거짓이어야 합니다.'
            continue
        if key == 'layout':
            layout_error = _validate_layout(value)
            if layout_error:
                return layout_error
            continue
        if key == 'cell_font':
            if not _is_number_in_range(value, _CELL_FONT_MIN, _CELL_FONT_MAX):
                return '폼 글자 크기 값이 올바르지 않습니다.'
            continue
        if not isinstance(value, str):
            return '폼 값 형식이 올바르지 않습니다.'
        if len(value) > _MAX_FORM_VALUE_LEN:
            return f'폼 값은 {_MAX_FORM_VALUE_LEN}자를 넘을 수 없습니다.'
    return None


def _validate_sheet(sheet, order_id: int) -> str | None:
    """개별 시트의 id/name/form/objects 구조를 검증한다.

    제품별 도면 시트 승격 값(optional): ``product_index``(제품 리스트 인덱스,
    0~199)와 ``attachment_id``(도면 탭 첨부 식별자, 양의 정수)를 허용한다. 둘 다
    없거나 ``None`` 이면 통과(구 저장분·비-제품 시트).
    """
    if not isinstance(sheet, dict):
        return '시트 형식이 올바르지 않습니다.'
    if not isinstance(sheet.get('id'), str) or not isinstance(sheet.get('name'), str):
        return '시트 id/이름 형식이 올바르지 않습니다.'
    if len(sheet['name']) > _MAX_SHEET_NAME_LEN:
        return f'시트 이름은 {_MAX_SHEET_NAME_LEN}자를 넘을 수 없습니다.'
    product_index = sheet.get('product_index')
    if product_index is not None and (
        isinstance(product_index, bool)
        or not isinstance(product_index, int)
        or not (0 <= product_index <= _MAX_PRODUCT_INDEX)
    ):
        return '시트 제품 인덱스 값이 올바르지 않습니다.'
    attachment_id = sheet.get('attachment_id')
    if attachment_id is not None and (
        isinstance(attachment_id, bool)
        or not isinstance(attachment_id, int)
        or attachment_id < 0
    ):
        return '시트 첨부 식별자 값이 올바르지 않습니다.'
    form = sheet.get('form')
    if not isinstance(form, dict):
        return '시트 폼 형식이 올바르지 않습니다.'
    form_error = _validate_form(form)
    if form_error:
        return form_error
    objects = sheet.get('objects')
    if not isinstance(objects, list) or len(objects) > _MAX_OBJECTS_PER_SHEET:
        return f'시트 객체는 최대 {_MAX_OBJECTS_PER_SHEET}개까지 허용됩니다.'
    for obj in objects:
        obj_error = _validate_object(obj, order_id)
        if obj_error:
            return obj_error
    return None


def _validate_wizard_state(state, order_id: int) -> str | None:
    """도면 마법사 상태 스키마·크기 캡을 검증한다(설계서 §5). 정상이면 None."""
    if not isinstance(state, dict):
        return '저장 데이터 형식이 올바르지 않습니다.'
    if state.get('v') != 1:
        return '지원하지 않는 저장 버전입니다.'
    sheets = state.get('sheets')
    if not isinstance(sheets, list):
        return '시트 목록 형식이 올바르지 않습니다.'
    if len(sheets) > _MAX_SHEETS:
        return f'시트는 최대 {_MAX_SHEETS}장까지 저장할 수 있습니다.'
    for sheet in sheets:
        sheet_error = _validate_sheet(sheet, order_id)
        if sheet_error:
            return sheet_error
    try:
        serialized = json.dumps(state, ensure_ascii=False).encode('utf-8')
    except (TypeError, ValueError):
        return '저장 데이터를 직렬화할 수 없습니다.'
    if len(serialized) > _MAX_STATE_BYTES:
        return '저장 데이터가 너무 큽니다(64KB 초과). 이미지는 반드시 업로드 참조여야 합니다.'
    return None


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard', methods=['GET'])
@login_required
def api_get_drawing_wizard(order_id):
    """도면 마법사 상태·자동채움 기본값·저장권한을 반환한다."""
    db = get_db()
    order = _load_order(db, order_id)
    if not order:
        return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404

    sd = _load_structured_data(order)
    current_user = get_user_by_id(session.get('user_id'))
    customer_name = (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-'
    item_index = _parse_item_index(request.args.get('item'))

    return jsonify({
        'success': True,
        'data': {
            'order_id': order_id,
            'customer_name': customer_name,
            'state': sd.get('drawing_wizard') or None,
            'defaults': build_wizard_defaults(order, sd, current_user, item_index=item_index),
            'products': _build_products(db, order),
            'measure_photos': _build_measure_photos(db, order),
            'drew_assignee_en': resolve_assignee_drew_en(sd),
            'can_save': _can_save_wizard(current_user, order),
            'drew_default': current_user.name if current_user else '',
            'pending_count': len(_pending_list(sd)),
        },
    })


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard', methods=['PUT'])
@login_required
def api_put_drawing_wizard(order_id):
    """도면 마법사 시트 상태를 검증·낙관적 충돌 확인 후 저장한다."""
    db = None
    try:
        db = get_db()
        order = _load_order(db, order_id)
        if not order:
            return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404

        current_user = get_user_by_id(session.get('user_id'))
        if not _can_save_wizard(current_user, order):
            return jsonify({'success': False, 'message': _MSG_FORBIDDEN}), 403

        data = request.get_json(silent=True) or {}
        state = data.get('state')
        base_updated_at = data.get('base_updated_at')

        error = _validate_wizard_state(state, order_id)
        if error:
            return jsonify({'success': False, 'message': error}), 400

        sd = _load_structured_data(order)
        saved = sd.get('drawing_wizard')
        if isinstance(saved, dict) and saved.get('updated_at') != (base_updated_at or None):
            return jsonify({
                'success': False,
                'error': 'conflict',
                'message': '다른 사용자가 먼저 저장했습니다.',
                'server_updated_at': saved.get('updated_at'),
                'server_updated_by_name': saved.get('updated_by_name'),
            }), 409

        # 버전 이력(versions)은 별도 스냅샷 경로가 관리하는 서버 소유 필드다. 클라이언트가
        # 보낸 state 의 versions 는 신뢰하지 않고 서버 보존값으로 덮어써(없으면 제거) 클라가
        # 실수로 versions 를 비우는 사고를 차단한다(설계 §4).
        if isinstance(saved, dict) and isinstance(saved.get('versions'), list):
            state['versions'] = saved['versions']
        else:
            state.pop('versions', None)

        state['updated_at'] = now_utc_naive().strftime('%Y-%m-%d %H:%M:%S')
        state['updated_by'] = session.get('user_id')
        state['updated_by_name'] = current_user.name
        sd['drawing_wizard'] = state
        order.structured_data = sd
        flag_modified(order, 'structured_data')
        db.commit()

        return jsonify({'success': True, 'data': {'updated_at': state['updated_at']}})
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception as rb_err:
                logger.warning("drawing-wizard PUT rollback failed: %s", rb_err, exc_info=True)
        logger.error("drawing-wizard PUT failed: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard/asset', methods=['POST'])
@login_required
def api_post_drawing_wizard_asset(order_id):
    """도면 마법사 이미지 에셋을 업로드하고 참조 key를 반환한다(OrderAttachment 미생성)."""
    try:
        db = get_db()
        order = _load_order(db, order_id)
        if not order:
            return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404

        current_user = get_user_by_id(session.get('user_id'))
        if not _can_save_wizard(current_user, order):
            return jsonify({'success': False, 'message': _MSG_FORBIDDEN}), 403

        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '파일이 없습니다.'}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in _ALLOWED_ASSET_EXTENSIONS:
            return jsonify({'success': False, 'message': '이미지 파일만 업로드할 수 있습니다.'}), 400

        # content_length는 신뢰 불가 → seek/tell로 실제 크기 확인.
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > _MAX_ASSET_BYTES:
            return jsonify({'success': False, 'message': '이미지 용량이 너무 큽니다(최대 10MB).'}), 400

        storage = get_storage()
        result = storage.upload_file(file, file.filename, f"orders/{order_id}/drawing_wizard/assets")
        if not result.get('success'):
            return jsonify({'success': False, 'message': '파일 업로드에 실패했습니다.'}), 500

        key = result.get('key')
        return jsonify({
            'success': True,
            'data': {
                'key': key,
                'view_url': f"/api/files/view/{key}",
                'filename': file.filename,
            },
        })
    except Exception as e:
        logger.error("drawing-wizard asset upload failed: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard/import-attachment', methods=['POST'])
@login_required
def api_post_drawing_wizard_import_attachment(order_id):
    """실측 첨부를 마법사 에셋 폴더로 복사하고 참조 key를 반환한다(실측 원본 불변).

    실측 사진 키(``orders/<id>/...`` 접두)는 위저드 이미지 격리(``orders/<id>/drawing_wizard/``)
    규칙에 맞지 않으므로 인라인 참조가 불가능하다. 대신 요청 ``key`` 가 해당 주문의 실측
    첨부(``measurement``/``measure_photo``/``photo``)에 존재하는지 검증한 뒤, 원본 바이트를
    읽어 ``orders/<id>/drawing_wizard/assets/`` 로 새로 업로드한다(파일명 유지). OrderAttachment
    행은 만들지 않으며(위저드 에셋 관행), 실측 원본은 읽기만 하고 변경하지 않는다.
    """
    db = None
    try:
        db = get_db()
        order = _load_order(db, order_id)
        if not order:
            return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404

        current_user = get_user_by_id(session.get('user_id'))
        if not _can_save_wizard(current_user, order):
            return jsonify({'success': False, 'message': _MSG_FORBIDDEN}), 403

        data = request.get_json(silent=True) or {}
        key = data.get('key')
        if not isinstance(key, str) or not key:
            return jsonify({'success': False, 'message': '실측 사진 키가 없습니다.'}), 400

        # 해당 주문의 실측 첨부(3종)에 존재하는 key만 허용(타 주문·비실측 category 차단).
        attachment = db.query(OrderAttachment).filter(
            OrderAttachment.order_id == order_id,
            OrderAttachment.storage_key == key,
            OrderAttachment.category.in_(list(_MEASURE_PHOTO_CATEGORIES)),
        ).first()
        if attachment is None:
            return jsonify({'success': False, 'message': '해당 주문의 실측 사진이 아닙니다.'}), 400

        storage = get_storage()
        raw = storage.read_file_bytes(key)
        if raw is None:
            return jsonify({'success': False, 'message': '실측 사진 원본을 찾을 수 없습니다.'}), 404

        filename = attachment.filename or (key.rsplit('/', 1)[-1] if key else 'measure.png')
        file_obj = FileStorage(stream=io.BytesIO(raw), filename=filename)
        result = storage.upload_file(file_obj, filename, f"orders/{order_id}/drawing_wizard/assets")
        if not result.get('success'):
            return jsonify({'success': False, 'message': '실측 사진 복사에 실패했습니다.'}), 500

        new_key = result.get('key')
        return jsonify({
            'success': True,
            'data': {
                'key': new_key,
                'view_url': f"/api/files/view/{new_key}",
                'filename': filename,
            },
        })
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception as rb_err:
                logger.warning("import-attachment rollback failed: %s", rb_err, exc_info=True)
        logger.error("drawing-wizard import-attachment failed: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard/sheet-png', methods=['POST'])
@login_required
def api_post_drawing_wizard_sheet_png(order_id):
    """현재 시트 PNG를 '전달 대기'(``structured_data['drawing_wizard']['pending']``)로 보관한다.

    multipart ``file``(PNG) + form ``sheet_id`` + optional ``sheet_name``. PNG는
    ``orders/<id>/drawing_wizard/exports/`` 로 업로드하고, sheet_id 별 pending 항목에
    ``{key, filename, at(KST), sheet_name}`` 을 기록한다. 저장/전달 분리 원칙에 따라
    OrderAttachment(주문 '도면' 탭)은 만들지 않으며(전달은 작업실 일괄 전송이 담당),
    같은 sheet_id 재저장 시 구 R2 파일을 삭제하고 덮어쓴다. ``updated_at`` 을 건드리지
    않으므로 PUT 낙관적 잠금과 충돌하지 않는다(별도 필드).
    """
    db = None
    try:
        db = get_db()
        order = _load_order(db, order_id)
        if not order:
            return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404

        current_user = get_user_by_id(session.get('user_id'))
        if not _can_save_wizard(current_user, order):
            return jsonify({'success': False, 'message': _MSG_FORBIDDEN}), 403

        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({'success': False, 'message': '파일이 없습니다.'}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        if ext != '.png':
            return jsonify({'success': False, 'message': 'PNG 파일만 저장할 수 있습니다.'}), 400

        # content_length는 신뢰 불가 → seek/tell로 실제 크기 확인.
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)
        if size > _MAX_ASSET_BYTES:
            return jsonify({'success': False, 'message': '이미지 용량이 너무 큽니다(최대 10MB).'}), 400

        raw_sheet_id = request.form.get('sheet_id') or ''
        sheet_id = re.sub(r'[^A-Za-z0-9_-]', '', str(raw_sheet_id))[:40] or 'sheet'
        sheet_name = str(request.form.get('sheet_name') or sheet_id)[:_MAX_SHEET_NAME_LEN]

        storage = get_storage()
        result = storage.upload_file(
            file, file.filename, f"orders/{order_id}/drawing_wizard/exports"
        )
        if not result.get('success'):
            return jsonify({'success': False, 'message': '파일 업로드에 실패했습니다.'}), 500
        key = result.get('key')

        # 전달 대기함(pending)에 기록 — deepcopy(_load_structured_data) + flag_modified.
        sd = _load_structured_data(order)
        wiz = sd.get('drawing_wizard')
        if not isinstance(wiz, dict):
            wiz = {}
            sd['drawing_wizard'] = wiz
        pending = wiz.get('pending')
        if not isinstance(pending, dict):
            pending = {}
            wiz['pending'] = pending

        # 같은 시트 재저장 → 구 R2 파일 삭제 대상 확보(교체). 커밋 후 정리(삭제 실패는 로그만).
        old_entry = pending.get(sheet_id)
        old_key = old_entry.get('key') if isinstance(old_entry, dict) else None

        pending[sheet_id] = {
            'key': key,
            'filename': file.filename,
            'at': now_kst().strftime('%Y-%m-%d %H:%M'),
            'sheet_name': sheet_name,
        }
        order.structured_data = sd
        flag_modified(order, 'structured_data')
        db.commit()

        if old_key and old_key != key:
            try:
                storage.delete_file(old_key)
            except Exception as del_err:
                logger.warning("sheet-png pending stale delete failed (%s): %s", old_key, del_err)

        return jsonify({'success': True, 'data': {'key': key}})
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception as rb_err:
                logger.warning("sheet-png rollback failed: %s", rb_err, exc_info=True)
        logger.error("drawing-wizard sheet-png failed: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500


def _pending_list(sd: dict) -> list[dict]:
    """``sd['drawing_wizard']['pending']`` (dict) → 목록 [{sheet_id, key, filename, at, sheet_name}].

    key 가 비어있거나 항목이 dict 가 아니면 건너뛴다(방어). 삽입 순서를 그대로 유지한다.
    """
    dw = sd.get('drawing_wizard') if isinstance(sd, dict) else None
    pending = dw.get('pending') if isinstance(dw, dict) else None
    out = []
    if isinstance(pending, dict):
        for sheet_id, entry in pending.items():
            if not isinstance(entry, dict):
                continue
            key = (entry.get('key') or '').strip()
            if not key:
                continue
            out.append({
                'sheet_id': sheet_id,
                'key': key,
                'filename': entry.get('filename') or key.rsplit('/', 1)[-1],
                'at': entry.get('at') or '',
                'sheet_name': entry.get('sheet_name') or sheet_id,
            })
    return out


def _append_sheet_version(storage, order_id: int, sheet: dict, sheet_id: str,
                          sheet_name: str, versions: list, current_user) -> int | None:
    """검증된 시트 1장을 버전 스냅샷 파일로 업로드하고 ``versions`` 포인터 리스트에 append한다.

    ``versions`` 를 in-place 로 갱신하며(30개 초과분은 오래된 것부터 R2 삭제), 새 버전
    번호를 반환한다. 업로드 실패 시 ``versions`` 를 건드리지 않고 ``None`` 을 반환한다.
    """
    next_v = max([p.get('v', 0) for p in versions if isinstance(p, dict)], default=0) + 1
    payload = json.dumps(sheet, ensure_ascii=False).encode('utf-8')
    filename = f"v{next_v}_{sheet_id}.json"
    file_obj = FileStorage(stream=io.BytesIO(payload), filename=filename)
    result = storage.upload_file(file_obj, filename, _versions_prefix(order_id).rstrip('/'))
    if not result.get('success'):
        return None
    versions.append({
        'v': next_v,
        'sheet_id': sheet_id,
        'sheet_name': sheet_name,
        'key': result.get('key'),
        'at': now_kst().strftime('%Y-%m-%d %H:%M'),
        'by_name': current_user.name if current_user else '',
    })
    # 30개 초과분(가장 오래된 것부터) 포인터 제거 + R2 파일 삭제(삭제 실패는 로그만).
    while len(versions) > _MAX_VERSIONS:
        stale = versions.pop(0)
        stale_key = stale.get('key') if isinstance(stale, dict) else None
        if stale_key:
            try:
                storage.delete_file(stale_key)
            except Exception as del_err:
                logger.warning("version-snapshot stale delete failed (%s): %s", stale_key, del_err)
    return next_v


def snapshot_and_clear_pending(db, order, order_id, current_user, sheet_ids=None):
    """전달 성공 후 대기(pending) 시트를 버전 스냅샷으로 저장하고 pending 에서 제거한다(공용).

    ``perform_drawing_transfer`` 가 이미 커밋한 뒤 호출되며, 이 함수가 별도 커밋한다.
    대상 각 대기 시트의 현재 상태를 ``_append_sheet_version`` 으로 버전 스냅샷하고 pending
    에서 비운다. ``structured_data`` 는 ``copy.deepcopy`` + ``flag_modified`` 로 갱신한다.

    :param sheet_ids: ``None`` 이면 전체 pending 을 스냅샷+초기화(작업실 일괄 transfer-pending
        동작 그대로). 리스트면 해당 ``sheet_id`` 들만 스냅샷하고 pending 에서 제거(부분 전달).
    :returns: 스냅샷한 대기 시트 수(int).
    """
    sd_after = copy.deepcopy(order.structured_data or {})
    dw = sd_after.get('drawing_wizard')
    if not isinstance(dw, dict):
        dw = {}
        sd_after['drawing_wizard'] = dw

    sheets_by_id = {}
    for s in (dw.get('sheets') or []):
        if isinstance(s, dict) and isinstance(s.get('id'), str):
            sheets_by_id[s['id']] = s
    versions = dw.get('versions')
    if not isinstance(versions, list):
        versions = []

    # 스냅샷 대상 = pending 유효 목록(_pending_list) 중 sheet_ids 필터.
    pending_items = _pending_list(sd_after)
    if sheet_ids is not None:
        wanted = {str(sid) for sid in sheet_ids}
        pending_items = [p for p in pending_items if p['sheet_id'] in wanted]

    storage = get_storage()
    for item in pending_items:
        sheet = sheets_by_id.get(item['sheet_id'])
        if isinstance(sheet, dict):
            _append_sheet_version(
                storage, order_id, sheet, item['sheet_id'], item['sheet_name'],
                versions, current_user,
            )
    dw['versions'] = versions

    # pending 비움: None=전체 초기화, 리스트=해당 sheet_id 만 제거.
    if sheet_ids is None:
        dw['pending'] = {}
    else:
        pending_map = dw.get('pending')
        if isinstance(pending_map, dict):
            for sid in sheet_ids:
                pending_map.pop(str(sid), None)
                pending_map.pop(sid, None)
            dw['pending'] = pending_map
        else:
            dw['pending'] = {}

    sd_after['drawing_wizard'] = dw
    order.structured_data = sd_after
    flag_modified(order, 'structured_data')
    db.commit()
    return len(pending_items)


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard/pending', methods=['GET'])
@login_required
def api_get_drawing_wizard_pending(order_id):
    """전달 대기 도면 목록 [{sheet_id, key, filename, at, sheet_name}] 을 반환한다(로그인 필요)."""
    db = get_db()
    order = _load_order(db, order_id)
    if not order:
        return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404
    return jsonify({'success': True, 'data': {'pending': _pending_list(_load_structured_data(order))}})


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard/pending/<sheet_id>', methods=['DELETE'])
@login_required
def api_delete_drawing_wizard_pending(order_id: int, sheet_id: str):
    """전달 대기(pending) 저장 도면 1건을 삭제한다(R2 export 파일 + 연결 도면탭 첨부 정리).

    ``sd['drawing_wizard']['pending'][sheet_id]`` 항목을 제거하고 그 항목의 export PNG
    (``entry['key']``)를 R2에서 삭제한다. 해당 시트에 도면 탭 첨부(``attachment_id``)가
    연결돼 있으면 그 ``OrderAttachment`` 행과 R2 파일도 함께 삭제하고 시트에서
    ``attachment_id`` 를 떼어낸다. **시트의 ``objects``(편집 중 캔버스)는 절대 건드리지 않는다**
    (저장 도면만 취소하고 편집 상태는 보존). ``structured_data`` 는 ``copy.deepcopy`` +
    ``flag_modified`` 로 갱신한다.

    :param order_id: ERP 주문 id.
    :param sheet_id: 삭제할 pending 시트 식별자.
    :returns: Flask ``(response, status)`` 튜플. 성공 시 ``{success, data:{sheet_id, deleted_key}}``.
    """
    db = None
    try:
        db = get_db()
        order = _load_order(db, order_id)
        if not order:
            return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404

        current_user = get_user_by_id(session.get('user_id'))
        if not _can_save_wizard(current_user, order):
            return jsonify({'success': False, 'message': _MSG_FORBIDDEN}), 403

        sd = copy.deepcopy(order.structured_data or {})
        dw = sd.get('drawing_wizard') if isinstance(sd, dict) else None
        pending = dw.get('pending') if isinstance(dw, dict) else None
        entry = pending.get(sheet_id) if isinstance(pending, dict) else None
        if not isinstance(entry, dict):
            return jsonify({'success': False, 'message': '삭제할 저장 도면이 없습니다.'}), 404

        storage = get_storage()

        # 1) export PNG(R2) 삭제 — 파일이 이미 없을 수 있으니 실패는 로그만 남기고 계속.
        deleted_key = (entry.get('key') or '').strip()
        if deleted_key:
            try:
                storage.delete_file(deleted_key)
            except Exception as del_err:
                logger.warning("pending export delete failed (%s): %s", deleted_key, del_err)

        # 2) 연결된 도면 탭 첨부(OrderAttachment) 정리 — 시트의 attachment_id 로 추적.
        sheet = None
        for s in (dw.get('sheets') or []):
            if isinstance(s, dict) and s.get('id') == sheet_id:
                sheet = s
                break
        if isinstance(sheet, dict):
            attachment_id = sheet.get('attachment_id')
            if isinstance(attachment_id, int) and not isinstance(attachment_id, bool) and attachment_id > 0:
                att = db.query(OrderAttachment).filter(
                    OrderAttachment.id == attachment_id,
                    OrderAttachment.order_id == order_id,
                ).first()
                if att is not None:
                    att_key = (att.storage_key or '').strip()
                    if att_key:
                        try:
                            storage.delete_file(att_key)
                        except Exception as att_del_err:
                            logger.warning(
                                "pending attachment file delete failed (%s): %s", att_key, att_del_err
                            )
                    db.delete(att)
                    sheet.pop('attachment_id', None)

        # 3) pending 항목 제거 — sheet.objects(편집 캔버스)는 보존한다.
        pending.pop(sheet_id, None)

        sd['drawing_wizard'] = dw
        order.structured_data = sd
        flag_modified(order, 'structured_data')
        db.commit()

        return jsonify({'success': True, 'data': {'sheet_id': sheet_id, 'deleted_key': deleted_key}})
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception as rb_err:
                logger.warning("pending delete rollback failed: %s", rb_err, exc_info=True)
        logger.exception("drawing-wizard pending delete failed: %s", e)
        return jsonify({
            'success': False,
            'error': 'internal_error',
            'message': f'오류 발생: {str(e)}',
        }), 500


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard/transfer-pending', methods=['POST'])
@login_required
def api_post_drawing_wizard_transfer_pending(order_id):
    """전달 대기 도면을 담당자에게 전달한다(transfer-drawing 과 동일 효과 + 스냅샷 + pending 비움).

    body ``{note, mode}`` (mode in APPEND/REPLACE_ALL, 기본 APPEND). pending 각 항목을
    ``files=[{key, filename}]`` 로 조립해 공용 전달 처리(``perform_drawing_transfer``)를
    호출한다(알림·drawing_current_files·status·히스토리 SSOT 재사용). 전달 성공 후 각 대기
    시트 상태를 버전 스냅샷으로 저장하고 pending 을 비운다. 응답 ``{success, data:{count, message}}``.
    """
    from foms.api.drawing.erp_orders_drawing import perform_drawing_transfer

    db = None
    try:
        db = get_db()
        order = _load_order(db, order_id)
        if not order:
            return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404

        current_user = get_user_by_id(session.get('user_id'))
        if not _can_save_wizard(current_user, order):
            return jsonify({'success': False, 'message': _MSG_FORBIDDEN}), 403

        data = request.get_json(silent=True) or {}
        note = data.get('note') or ''
        mode = (data.get('mode') or 'APPEND').upper()
        if mode not in ('APPEND', 'REPLACE_ALL'):
            mode = 'APPEND'

        pending_items = _pending_list(_load_structured_data(order))
        if not pending_items:
            return jsonify({'success': False, 'message': '전달할 대기 도면이 없습니다.'}), 400

        files = [{'key': p['key'], 'filename': p['filename']} for p in pending_items]
        payload, status = perform_drawing_transfer(
            db, order, order_id, current_user, session.get('user_id'),
            note=note, mode=mode, files=files,
        )
        if not payload.get('success'):
            return jsonify(payload), status

        # 전달 성공(perform_drawing_transfer 가 커밋함) → 대기 시트 전체를 버전 스냅샷 저장 + pending 비움.
        snapshot_and_clear_pending(db, order, order_id, current_user, sheet_ids=None)

        count = len(files)
        return jsonify({
            'success': True,
            'data': {'count': count, 'message': payload.get('message') or f'{count}장 전달됨'},
        })
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception as rb_err:
                logger.warning("transfer-pending rollback failed: %s", rb_err, exc_info=True)
        logger.error("drawing-wizard transfer-pending failed: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard/version-snapshot', methods=['POST'])
@login_required
def api_post_drawing_wizard_version_snapshot(order_id):
    """전달된 시트 상태를 버전 스냅샷으로 R2에 저장하고 포인터를 sd에 append한다.

    도면 전달(runBatchTransfer) 성공 직후 각 시트에 대해 호출된다. 스냅샷 본문(시트 1장
    JSON)은 ``orders/<id>/drawing_wizard/versions/v<n>_<sheet_id>.json`` 으로 업로드하고,
    ``sd['drawing_wizard']['versions']`` 에는 경량 포인터만 append한다(structured_data 비대
    방지). 30개를 초과하면 가장 오래된 포인터와 R2 파일을 함께 제거한다. ``state.sheets``·
    ``updated_at`` 는 건드리지 않고 ``versions`` 필드만 갱신하므로 PUT 낙관적 잠금과
    충돌하지 않는다(설계 §1).
    """
    db = None
    try:
        db = get_db()
        order = _load_order(db, order_id)
        if not order:
            return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404

        current_user = get_user_by_id(session.get('user_id'))
        if not _can_save_wizard(current_user, order):
            return jsonify({'success': False, 'message': _MSG_FORBIDDEN}), 403

        data = request.get_json(silent=True) or {}
        sheet = data.get('sheet')
        if not isinstance(sheet, dict):
            return jsonify({'success': False, 'message': '시트 데이터가 없습니다.'}), 400

        sheet_error = _validate_sheet(sheet, order_id)
        if sheet_error:
            return jsonify({'success': False, 'message': sheet_error}), 400

        raw_sheet_id = data.get('sheet_id') if isinstance(data.get('sheet_id'), str) else sheet.get('id')
        sheet_id = re.sub(r'[^A-Za-z0-9_-]', '', str(raw_sheet_id or ''))[:40] or 'sheet'
        sheet_name = str(data.get('sheet_name') or sheet.get('name') or '도면')[:_MAX_SHEET_NAME_LEN]

        sd = _load_structured_data(order)
        dw = sd.get('drawing_wizard')
        if not isinstance(dw, dict):
            dw = {}
        versions = dw.get('versions')
        if not isinstance(versions, list):
            versions = []

        storage = get_storage()
        next_v = _append_sheet_version(
            storage, order_id, sheet, sheet_id, sheet_name, versions, current_user
        )
        if next_v is None:
            return jsonify({'success': False, 'message': '버전 저장에 실패했습니다.'}), 500

        dw['versions'] = versions
        sd['drawing_wizard'] = dw
        order.structured_data = sd
        flag_modified(order, 'structured_data')
        db.commit()

        return jsonify({'success': True, 'data': {'v': next_v}})
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception as rb_err:
                logger.warning("version-snapshot rollback failed: %s", rb_err, exc_info=True)
        logger.error("drawing-wizard version-snapshot failed: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard/versions', methods=['GET'])
@login_required
def api_get_drawing_wizard_versions(order_id):
    """저장된 버전 스냅샷 포인터 목록을 반환한다(로그인 필요, 열람 전용도 조회 가능)."""
    db = get_db()
    order = _load_order(db, order_id)
    if not order:
        return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404
    sd = _load_structured_data(order)
    dw = sd.get('drawing_wizard')
    versions = dw.get('versions') if isinstance(dw, dict) else None
    if not isinstance(versions, list):
        versions = []
    return jsonify({'success': True, 'data': {'versions': versions}})


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard/version-content', methods=['GET'])
@login_required
def api_get_drawing_wizard_version_content(order_id):
    """버전 스냅샷 파일(시트 1장 JSON)의 내용을 반환한다(접두사·경로 격리 검증).

    ``key`` 는 해당 주문의 버전 접두사(``orders/<id>/drawing_wizard/versions/``)만 허용해
    경로 traversal·타 주문 참조를 차단한다. 저장 권한은 요구하지 않는다(GET 조회 정책).
    """
    key = request.args.get('key') or ''
    if not key:
        return jsonify({'success': False, 'message': '버전 키가 없습니다.'}), 400
    if '..' in key or key.startswith('/'):
        return jsonify({'success': False, 'message': '비정상적인 경로입니다.'}), 400
    if not key.startswith(_versions_prefix(order_id)):
        return jsonify({'success': False, 'message': '버전 키 경로가 올바르지 않습니다.'}), 400

    db = get_db()
    order = _load_order(db, order_id)
    if not order:
        return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404

    storage = get_storage()
    raw = storage.read_file_bytes(key)
    if raw is None:
        return jsonify({'success': False, 'message': '버전 파일을 찾을 수 없습니다.'}), 404
    try:
        sheet = json.loads(raw.decode('utf-8'))
    except (ValueError, TypeError, UnicodeDecodeError):
        return jsonify({'success': False, 'message': '버전 파일을 해석할 수 없습니다.'}), 500
    return jsonify({'success': True, 'data': {'sheet': sheet}})


@erp_orders_drawing_wizard_bp.route('/<int:order_id>/drawing-wizard/asset-raw', methods=['GET'])
@login_required
def api_get_drawing_wizard_asset_raw(order_id):
    """도면 마법사 에셋 원본 바이트를 same-origin으로 스트리밍한다(내보내기 canvas 오염 방지).

    운영(R2)에서 ``/api/files/view/<key>`` 는 presigned URL로 redirect되어 cross-origin이
    되므로 html2canvas 캡처 시 이미지가 누락된다. 본 엔드포인트는 앱이 바이트를 직접
    반환해 same-origin을 보장한다. key는 해당 주문의 drawing_wizard 접두사만 허용해
    경로 traversal·타 주문 참조를 차단한다. 열람 전용 사용자도 이미지를 봐야 하므로
    저장 권한(``_can_save_wizard``)은 요구하지 않는다(GET 조회와 동일 정책).
    """
    key = request.args.get('key') or ''
    if not key:
        return jsonify({'success': False, 'message': '이미지 참조 키가 없습니다.'}), 400
    if '..' in key or key.startswith('/'):
        return jsonify({'success': False, 'message': '비정상적인 경로입니다.'}), 400
    if not key.startswith(f'orders/{order_id}/drawing_wizard/'):
        return jsonify({'success': False, 'message': '이미지 참조 키 경로가 올바르지 않습니다.'}), 400

    db = get_db()
    order = _load_order(db, order_id)
    if not order:
        return jsonify({'success': False, 'message': _MSG_NOT_FOUND}), 404

    storage = get_storage()
    data = storage.read_file_bytes(key)
    if data is None:
        return jsonify({'success': False, 'message': '파일을 찾을 수 없습니다.'}), 404

    ext = os.path.splitext(key)[1].lower()
    mimetype = _ASSET_RAW_MIMETYPES.get(ext, 'application/octet-stream')
    response = Response(data, mimetype=mimetype)
    response.headers['Cache-Control'] = 'private, max-age=3600'
    return response


@erp_orders_drawing_wizard_bp.route('/drawing-wizard/presets', methods=['GET'])
@login_required
def api_get_drawing_wizard_presets():
    """도면팀 공유 사용자 프리셋 목록을 반환한다(주문 무관 전역)."""
    try:
        presets = load_wizard_presets()
        return jsonify({'success': True, 'data': {'presets': presets}})
    except Exception as e:
        logger.error("drawing-wizard presets GET failed: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500


@erp_orders_drawing_wizard_bp.route('/drawing-wizard/presets', methods=['POST'])
@login_required
def api_post_drawing_wizard_presets():
    """도면팀 공유 사용자 프리셋 목록을 검증·저장한다(전역 SystemSetting)."""
    db = None
    try:
        db = get_db()
        current_user = get_user_by_id(session.get('user_id'))
        if not _can_manage_presets(current_user):
            return jsonify({
                'success': False,
                'message': '관리자·도면팀 또는 ERP 편집 권한자만 프리셋을 관리할 수 있습니다.',
            }), 403

        data = request.get_json(silent=True) or {}
        presets = data.get('presets')
        if not isinstance(presets, list):
            return jsonify({'success': False, 'message': '프리셋 목록 형식이 올바르지 않습니다.'}), 400

        saved = save_wizard_presets(presets)
        return jsonify({'success': True, 'data': {'presets': saved}})
    except Exception as e:
        if db is not None:
            try:
                db.rollback()
            except Exception as rb_err:
                logger.warning("drawing-wizard presets POST rollback failed: %s", rb_err, exc_info=True)
        logger.error("drawing-wizard presets POST failed: %s", e, exc_info=True)
        return jsonify({'success': False, 'message': f'오류 발생: {str(e)}'}), 500
