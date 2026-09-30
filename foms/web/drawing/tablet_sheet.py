"""도면 작업실 태블릿 "관리 시트" fragment 라우트 (목업 v8 프레임 03).

태블릿 가로 코호트에서 도면 갤러리 카드 탭 시 우측 사이드 시트로 로드되는 HTML
fragment 를 반환한다(공용 tablet-side-sheet.js 의 ``data-foms-sheet-url`` 계약).
신규 데이터 스키마는 만들지 않고, 도면 마법사 상태(``structured_data['drawing_wizard']``)와
서버 자동채움 SSOT(``build_wizard_defaults``)를 그대로 재사용한다:

- 시트 썸네일 스트립 = 마법사 시트-PNG 자동 저장물(``drawing_wizard['pending']``, ``_pending_list``).
- 자동 채움(시공일/자수/로고) = ``build_wizard_defaults`` 계산 값.
- 버전 이력 = R2 스냅샷 포인터(``drawing_wizard['versions']``) + 미전달 자동저장.

``erp_drawing_workbench_bp`` 에 부착한다(신규 Blueprint 없음, wizard.py 전례).
"""

from typing import Any

from flask import g, render_template, url_for

from db import get_db
from models import Order
from foms.web.auth import login_required
from foms.services.erp_display import _ensure_dict
from foms.services.erp_policy import (
    can_transfer_drawing,
    has_pending_unchecked_drawing_revision_requests,
)
from foms.services.drawing_wizard_defaults import build_wizard_defaults
from foms.web.drawing.workbench import (
    erp_drawing_workbench_bp,
    _resolve_construction_date_display,
)
from foms.api.drawing.wizard import _pending_list


def _to_month_day(normalized_dates: str) -> str:
    """정규화된 'YYYY-MM-DD[, ...]' 문자열을 'M/D[, ...]' 표기로 변환한다(파싱 실패분 제외)."""
    out: list[str] = []
    for raw in (normalized_dates or '').split(','):
        parts = raw.strip().split('-')
        if len(parts) == 3:
            try:
                out.append(f"{int(parts[1])}/{int(parts[2])}")
            except (TypeError, ValueError):
                continue
    return ', '.join(out)


SHEET_TRANSFER_BLOCKED_TEXT = '작업실에서 반영 체크/교체할 도면을 고른 뒤 전달하세요.'


def _sheet_transfer_block_reason(sd: dict) -> str:
    """'시트 전달'(transfer-pending, 교체 대상 없이 APPEND)이 서버에서 400 이 될 상태면 이유를 돌려준다.

    작업실 상세와 같은 판정이다(원장 M14-d): RETURNED 에서 반영 체크 안 된 수정요청이 남았거나
    (``perform_drawing_transfer`` 반영 체크 게이트), RETURNED 이고 현재본이 2장 이상이면 교체할 도면
    번호가 필요하다(같은 함수의 "교체할 도면 번호" 400). 시트에는 교체 대상을 고르는 칸이 없다.

    Returns:
        막히면 안내 문구, 아니면 빈 문자열.
    """
    drawing_status = ((sd.get('drawing') or {}).get('status') or sd.get('drawing_status') or 'PENDING').upper()
    if drawing_status != 'RETURNED':
        return ''
    current_files = sd.get('drawing_current_files')
    if has_pending_unchecked_drawing_revision_requests(sd) or (
        isinstance(current_files, list) and len(current_files) > 1
    ):
        return SHEET_TRANSFER_BLOCKED_TEXT
    return ''


def _sheet_transfer_replaced_count(sd: dict) -> int:
    """'시트 전달'이 이전 도면을 최신 도면으로 교체하면 교체될 장수를, 아니면 0 을 돌려준다.

    영업 수령 확정 전(TRANSFERRED)에 mode 없이 다시 보내면 ``perform_drawing_transfer`` 가
    REPLACE_ALL 로 처리한다(2026-09-30 주문 5331). 시트에 그 사실을 미리 적어 보인다.
    """
    drawing_status = ((sd.get('drawing') or {}).get('status') or sd.get('drawing_status') or 'PENDING').upper()
    if drawing_status != 'TRANSFERRED':
        return 0
    current_files = sd.get('drawing_current_files')
    return len(current_files) if isinstance(current_files, list) else 0


def _build_version_timeline(pending: list[dict], versions: list) -> list[dict]:
    """버전 이력 타임라인을 구성한다: 미전달 자동저장(최신) → 전달 스냅샷(최신 먼저).

    Args:
        pending: ``_pending_list`` 결과(자동 저장된 미전달 시트 PNG 목록).
        versions: ``drawing_wizard['versions']`` R2 스냅샷 포인터 리스트.

    Returns:
        타임라인 항목 dict 리스트 [{kind, label, sheet_name, at, by}].
    """
    timeline: list[dict] = []
    for entry in pending:
        timeline.append({
            'kind': 'autosave',
            'label': '자동 저장 (미전달)',
            'sheet_name': entry.get('sheet_name') or '도면',
            'at': entry.get('at') or '',
            'by': '',
        })
    for ver in reversed(versions if isinstance(versions, list) else []):
        if not isinstance(ver, dict):
            continue
        timeline.append({
            'kind': 'snapshot',
            'label': f"전달 스냅샷 v{ver.get('v') or '?'}",
            'sheet_name': ver.get('sheet_name') or '도면',
            'at': ver.get('at') or '',
            'by': ver.get('by_name') or '',
        })
    return timeline


@erp_drawing_workbench_bp.route('/drawing-workbench/tablet-sheet/<int:order_id>')
@login_required
def erp_drawing_workbench_tablet_sheet(order_id: int) -> Any:
    """도면 관리 시트 fragment(태블릿 사이드 시트용, HTML). 로그인 필수.

    카드 탭 → 사이드 시트가 이 fragment 를 fetch 로 로드한다. 마법사 상태·자동채움·
    버전 이력을 읽기 전용으로 렌더하고, m-foot 에 '시트 전달'(전달 대기 → transfer-pending)과
    '마법사 열기 ↗'(마법사 전체화면) 액션 링크를 노출한다.
    """
    db = get_db()
    current_user = getattr(g, 'current_user', None)
    order = db.query(Order).filter(
        Order.id == order_id, Order.active_filter(), Order.is_erp_order.is_(True)
    ).first()

    if not order:
        return render_template('drawing/partials/tablet_sheet_body.html', sheet_not_found=True, order_id=order_id)

    sd = _ensure_dict(order.structured_data)
    customer_name = (((sd.get('parties') or {}).get('customer') or {}).get('name')) or '-'
    construction_md = _to_month_day(_resolve_construction_date_display(order, sd))

    wizard = sd.get('drawing_wizard') if isinstance(sd.get('drawing_wizard'), dict) else {}
    sheets = wizard.get('sheets') if isinstance(wizard.get('sheets'), list) else []
    pending = _pending_list(sd)
    versions = wizard.get('versions') if isinstance(wizard.get('versions'), list) else []
    # 썸네일 스트립: 자동 저장된 시트 PNG(same-origin view URL). 신규 쿼리 없음(이미 로드된 sd).
    sheet_strip = [
        {
            'sheet_name': entry.get('sheet_name') or '도면',
            'thumb_url': f"/api/files/view/{entry['key']}",
            'at': entry.get('at') or '',
        }
        for entry in pending
    ]
    sheet_count = len(sheets) or len(sheet_strip)

    defaults = build_wizard_defaults(order, sd, current_user)
    autofill = {
        'construction_date': defaults.get('construction_date') or '-',
        'spec_w300': defaults.get('spec_w300') or '-',
        'logo': (defaults.get('logo') or '').upper() or '-',
    }

    # '시트 전달'(마법사 transfer-pending → perform_drawing_transfer)은 서버 전달 권한과 같은
    # 술어를 쓴다(관리자 · 지정 도면 담당, M14-a 화면 == 서버). 담당 아닌 도면팀은 이유 한 줄.
    can_transfer = can_transfer_drawing(current_user, order)
    show_transfer_assignee_only_hint = bool(
        current_user
        and not can_transfer
        and current_user.role != 'ADMIN'
        and (getattr(current_user, 'team', None) or '').strip() == 'DRAWING'
    )

    return render_template(
        'drawing/partials/tablet_sheet_body.html',
        sheet_not_found=False,
        order_id=order.id,
        customer_name=customer_name,
        construction_md=construction_md,
        sheet_count=sheet_count,
        sheet_strip=sheet_strip,
        autofill=autofill,
        timeline=_build_version_timeline(pending, versions),
        has_pending=bool(pending),
        can_transfer=can_transfer,
        show_transfer_assignee_only_hint=show_transfer_assignee_only_hint,
        transfer_block_reason=_sheet_transfer_block_reason(sd),
        transfer_replaced_count=_sheet_transfer_replaced_count(sd),
        wizard_url=url_for('erp_drawing_workbench.erp_drawing_workbench_wizard', order_id=order.id),
        detail_url=url_for('erp_drawing_workbench.erp_drawing_workbench_detail', order_id=order.id) + '?tab=timeline',
    )
