"""
ERP Blueprint 허브 (erp_bp)
- 모든 대시보드 페이지는 개별 Blueprint로 분리 완료
- erp_bp는 공통 템플릿 필터 등록 + display 헬퍼 re-export 역할만 수행
"""
from flask import Blueprint
import os
import unicodedata

from services.erp_permissions import can_edit_erp, erp_edit_required  # noqa: F401
from services.erp_template_filters import register_erp_template_filters, spec_w300_value  # noqa: F401
from services.erp_display import (  # noqa: F401
    _ensure_dict,
    _erp_get_urgent_flag,
    _erp_get_stage,
    _erp_has_media,
    _erp_alerts,
    _sales_domain_fallback_match,
    _can_modify_sales_domain,
    _drawing_status_label,
    _drawing_next_action_text,
    apply_erp_display_fields,
    apply_erp_display_fields_to_orders,
)

def _normalize_for_search(s):
    """검색 매칭용 문자열 정규화 (유니코드 NFC, 공백 정리)"""
    if s is None:
        return ''
    s = str(s).strip()
    if not s:
        return ''
    return unicodedata.normalize('NFC', s)


erp_bp = Blueprint('erp', __name__)
ERP_BETA_DEBUG = os.environ.get('ERP_BETA_DEBUG', '').lower() in ('1', 'true', 'yes', 'on')

register_erp_template_filters(erp_bp)
