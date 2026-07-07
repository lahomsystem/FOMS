"""도면 작업실 "도면 마법사" API (P1 백엔드).

- GET  ``/api/orders/<id>/drawing-wizard``        상태·자동채움 기본값·저장권한 조회
- PUT  ``/api/orders/<id>/drawing-wizard``         시트 상태 검증·낙관적 충돌 확인 후 저장
- POST ``/api/orders/<id>/drawing-wizard/asset``   이미지 에셋 업로드(R2-only, 참조 key 반환)

상태 JSON은 ``structured_data['drawing_wizard']`` 단일 키에 저장한다
(``copy.deepcopy`` + ``flag_modified`` 패턴). 이미지는 base64 인라인을 금지하고
반드시 ``orders/<id>/drawing_wizard/`` 접두 업로드 참조여야 한다(설계서 §1.3, §5).
"""

import copy
import json
import logging
import os
import re

from flask import Blueprint, Response, jsonify, request, session
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order
from foms.web.auth import login_required, get_user_by_id
from foms.services.datetime_kst import now_utc_naive
from foms.services.erp_policy import is_drawing_workbench_participant
from foms.services.storage import get_storage
from foms.services.drawing_wizard_defaults import build_wizard_defaults, resolve_assignee_drew_en

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


def _can_save_wizard(current_user, order) -> bool:
    """ADMIN 또는 도면 작업실 참여자만 저장할 수 있다."""
    return bool(
        current_user
        and (current_user.role == 'ADMIN' or is_drawing_workbench_participant(current_user, order))
    )


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
    """개별 시트의 id/name/form/objects 구조를 검증한다."""
    if not isinstance(sheet, dict):
        return '시트 형식이 올바르지 않습니다.'
    if not isinstance(sheet.get('id'), str) or not isinstance(sheet.get('name'), str):
        return '시트 id/이름 형식이 올바르지 않습니다.'
    if len(sheet['name']) > _MAX_SHEET_NAME_LEN:
        return f'시트 이름은 {_MAX_SHEET_NAME_LEN}자를 넘을 수 없습니다.'
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

    return jsonify({
        'success': True,
        'data': {
            'order_id': order_id,
            'customer_name': customer_name,
            'state': sd.get('drawing_wizard') or None,
            'defaults': build_wizard_defaults(order, sd, current_user),
            'drew_assignee_en': resolve_assignee_drew_en(sd),
            'can_save': _can_save_wizard(current_user, order),
            'drew_default': current_user.name if current_user else '',
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
