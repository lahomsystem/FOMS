from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import html
import folium
from folium import plugins
from map_config import DEFAULT_CENTER

# 지도 마커 이름 최대 표시 글자 수 (모바일 시인성 고려)
MAP_MARKER_NAME_MAX_LEN = 8
OVERLAP_MARKER_COLOR = "#f8c8d8"


class FOMSMapGenerator:
    """FOMS 시스템용 지도 생성 클래스"""
    
    def __init__(self):
        """지도 생성기 초기화"""
        pass
    
    def _calculate_center(self, order_data):
        """유효한 좌표들의 중심점 계산"""
        valid_coords = [
            (order['latitude'], order['longitude']) 
            for order in order_data 
            if order['latitude'] is not None and order['longitude'] is not None
        ]
        
        if not valid_coords:
            return DEFAULT_CENTER
        
        avg_lat = sum(coord[0] for coord in valid_coords) / len(valid_coords)
        avg_lng = sum(coord[1] for coord in valid_coords) / len(valid_coords)
        
        return [avg_lat, avg_lng]
    
    def _calculate_zoom_level(self, order_data):
        """좌표 분포에 따른 적절한 줌 레벨 계산"""
        valid_coords = [
            (order['latitude'], order['longitude']) 
            for order in order_data 
            if order['latitude'] is not None and order['longitude'] is not None
        ]
        
        if len(valid_coords) <= 1:
            return 10
        
        # 좌표 범위 계산
        lats = [coord[0] for coord in valid_coords]
        lngs = [coord[1] for coord in valid_coords]
        
        lat_range = max(lats) - min(lats)
        lng_range = max(lngs) - min(lngs)
        
        # 범위에 따른 줌 레벨 결정
        max_range = max(lat_range, lng_range)
        
        if max_range > 2:
            return 6
        elif max_range > 1:
            return 7
        elif max_range > 0.5:
            return 8
        elif max_range > 0.1:
            return 9
        elif max_range > 0.05:
            return 10
        else:
            return 11
    
    def _get_status_color(self, status):
        """주문 상태에 따른 마커 색상 반환"""
        status_colors = {
            'RECEIVED': '#007bff',      # 파란색 - 접수
            'MEASURE': '#28a745',       # 초록색 - 실측
            'MEASURED': '#28a745',      # 레거시 - 실측
            'DRAWING': '#6f42c1',       # 보라색 - 도면
            'CONFIRM': '#0d6efd',       # 파란색 - 고객컨펌
            'PRODUCTION': '#fd7e14',    # 주황색 - 생산
            'CONSTRUCTION': '#20c997',  # 민트색 - 시공
            'CS': '#dc3545',            # 빨간색 - CS
            'CONFIRMED': '#28a745',     # 초록색 - 확인
            'IN_PRODUCTION': '#ffc107', # 노란색 - 제작중
            'COMPLETED': '#6c757d',     # 회색 - 완료
            'SHIPPED': '#17a2b8',       # 청록색 - 배송
            'DELIVERED': '#20c997',     # 민트색 - 배송완료
            'CANCELLED': '#dc3545',     # 빨간색 - 취소
            'ON_HOLD': '#fd7e14'        # 주황색 - 보류
        }
        return status_colors.get(status, '#6c757d')

    def _duplicate_group_key(self, order):
        """중복 위치를 묶기 위한 안정적인 키를 만든다."""
        if not isinstance(order, dict):
            return None

        explicit_key = order.get('duplicate_group_key')
        if explicit_key:
            return f"meta:{explicit_key}"

        address = str(order.get('address') or '').strip()
        if address and address not in {'-', '주소없음'}:
            normalized_address = ' '.join(address.split()).lower()
            return f"addr:{normalized_address}"

        lat = order.get('latitude')
        lng = order.get('longitude')
        if lat is None or lng is None:
            return None

        try:
            return f"coord:{round(float(lat), 6):.6f}:{round(float(lng), 6):.6f}"
        except (TypeError, ValueError):
            return None

    def _prepare_marker_data(self, order_data):
        """입력 마커를 복사하고 중복 위치 메타데이터를 부여한다."""
        prepared = []
        groups = {}

        for order in order_data:
            if not isinstance(order, dict):
                continue
            item = dict(order)
            duplicate_location_size = int(item.get('duplicate_location_group_size') or 0)
            duplicate_address_size = int(item.get('duplicate_address_group_size') or 0)
            item['is_duplicate_location'] = bool(
                item.get('is_duplicate_location')
                or duplicate_location_size > 1
                or duplicate_address_size > 1
            )
            item['duplicate_group_size'] = int(
                item.get('duplicate_group_size')
                or duplicate_location_size
                or duplicate_address_size
                or 0
            )
            item['duplicate_group_index'] = int(
                item.get('duplicate_group_index')
                or item.get('duplicate_location_group_index')
                or item.get('duplicate_address_group_index')
                or 0
            )
            existing_group_key = (
                item.get('duplicate_group_key')
                or item.get('duplicate_location_group_key')
                or item.get('duplicate_address_group_key')
                or ''
            )
            if existing_group_key:
                item['duplicate_group_key'] = existing_group_key
            key = self._duplicate_group_key(item)
            if key:
                groups.setdefault(key, []).append(item)
                item['duplicate_group_key'] = key
            prepared.append(item)

        for group_items in groups.values():
            if len(group_items) <= 1:
                continue
            group_size = len(group_items)
            for index, item in enumerate(group_items, 1):
                item['is_duplicate_location'] = True
                item['duplicate_group_size'] = group_size
                item['duplicate_group_index'] = index

        return prepared

    def _get_marker_theme(self, order):
        """실측 담당자색 또는 상태색 기반 마커 테마를 반환한다."""
        manager_bg = str(order.get('manager_bg_color') or '').strip()
        manager_bg_source = str(order.get('manager_bg_source') or '').strip()
        manager_text = str(order.get('manager_text_color') or '#000000').strip() or '#000000'
        if manager_bg and manager_bg_source == 'palette':
            return {
                'background': manager_bg,
                'border': '#ffffff',
                'text': manager_text,
                'shadow': 'rgba(0, 0, 0, 0.18)',
                'badge_bg': '#ffffff',
                'badge_text': '#0f172a',
                'label_prefix': '담당',
            }

        if order.get('is_duplicate_location') or int(order.get('duplicate_group_size') or 0) > 1:
            return {
                'background': OVERLAP_MARKER_COLOR,
                'border': '#e29ab7',
                'text': '#6c2845',
                'shadow': 'rgba(232, 160, 186, 0.35)',
                'badge_bg': '#f5b7cd',
                'badge_text': '#5a1f38',
                'label_prefix': '중복',
            }

        return {
            'background': self._get_status_color(order.get('status')),
            'border': '#ffffff',
            'text': '#ffffff',
            'shadow': 'rgba(0,0,0,0.25)',
            'badge_bg': '#ffffff',
            'badge_text': '#0d6efd',
            'label_prefix': '',
        }
    
    def create_map(self, order_data, title="주문 지도"):
        """
        주문 데이터로 Folium 지도 생성
        Args: 
            order_data - List[Dict] with order information including coordinates
            title - 지도 제목
        Returns: folium.Map object or None
        """
        if not order_data:
            return None
        
        # 성공한 좌표만 필터링
        valid_data = []
        for order in order_data:
            if not isinstance(order, dict):
                continue
            if order.get('latitude') is not None and order.get('longitude') is not None:
                valid_data.append(dict(order))
        
        if not valid_data:
            return None
        
        # 지도 중심점과 줌 레벨 계산
        render_data = self._prepare_marker_data(valid_data)
        center = self._calculate_center(render_data)
        zoom_level = self._calculate_zoom_level(render_data)
        
        # 지도 생성 - OpenStreetMap 기본
        m = folium.Map(
            location=center,
            zoom_start=zoom_level,
            width="100%",
            height="100vh",
            tiles='OpenStreetMap'
        )
        
        # OpenStreetMap만 사용 (레이어 컨트롤 불필요)
        
        # 전체화면 플러그인 추가
        plugins.Fullscreen(
            position='topright',
            title='전체화면',
            title_cancel='전체화면 해제',
            force_separate_button=True
        ).add_to(m)
        
        # 미니맵 추가
        minimap = plugins.MiniMap(toggle_display=True)
        m.add_child(minimap)
        
        # 마커 추가 (지도에는 주문 ID로 표기, 클릭/경로 계산은 idx로 DOM 참조)
        for idx, order in enumerate(render_data, 1):
            lat = order['latitude']
            lng = order['longitude']
            order_id = order.get('id', idx)  # 지도 마커에 표시할 주문 ID
            order_id_text = str(order_id)
            order_id_attr = html.escape(order_id_text, quote=True)
            order_id_display = html.escape(order_id_text, quote=False)

            # 주문 정보
            customer_name = order.get('customer_name', '정보없음')
            address = order.get('address', '주소없음')
            product = order.get('product', '제품없음')
            status = order.get('status', 'UNKNOWN')
            received_date = order.get('received_date', '날짜없음')
            phone = order.get('phone', '연락처없음')
            manager_name = order.get('manager_name') or '-'
            customer_name_escaped = html.escape(str(customer_name), quote=True)
            address_escaped = html.escape(str(address), quote=True)
            product_escaped = html.escape(str(product), quote=True)
            status_escaped = html.escape(str(status), quote=True)
            received_date_escaped = html.escape(str(received_date), quote=True)
            phone_escaped = html.escape(str(phone), quote=True)
            manager_name_escaped = html.escape(str(manager_name), quote=True)
            
            # 상태별 색상
            status_color = self._get_status_color(status)
            marker_theme = self._get_marker_theme(order)
            marker_bg = marker_theme['background']
            marker_border = marker_theme['border']
            marker_text = marker_theme['text']
            marker_shadow = marker_theme['shadow']
            duplicate_group_size = int(order.get('duplicate_group_size') or 0)
            duplicate_group_index = int(order.get('duplicate_group_index') or 0)
            duplicate_group_key_attr = html.escape(str(order.get('duplicate_group_key') or ''), quote=True)
            is_duplicate = bool(order.get('is_duplicate_location') or duplicate_group_size > 1)
            duplicate_badge_html = ''
            if is_duplicate:
                duplicate_badge_html = (
                    f'<span style="display:inline-block;margin-left:8px;padding:2px 8px;'
                    f'border-radius:9999px;background:{marker_theme["badge_bg"]};'
                    f'color:{marker_theme["badge_text"]};font-size:12px;font-weight:700;">'
                    f'중복 위치 x{duplicate_group_size}'
                    f'</span>'
                )
            
            # 팝업 텍스트 구성
            duplicate_row = ''
            if is_duplicate:
                duplicate_marker_badge_html = (
                    f'<span style="display:inline-flex;align-items:center;justify-content:center;'
                    f'min-width:22px;height:22px;margin-left:8px;padding:0 7px;border-radius:9999px;'
                    f'background:{marker_theme["badge_bg"]};color:{marker_theme["badge_text"]};'
                    f'font-size:12px;font-weight:700;border:1px solid rgba(0,0,0,0.08);">'
                    f'{duplicate_group_size}</span>'
                )
                duplicate_row = (
                    f'<tr><td style="padding: 3px; font-weight: bold;">중복:</td>'
                    f'<td style="padding: 3px; color: {marker_text};">{duplicate_group_size}건 같은 주소</td></tr>'
                )
            else:
                duplicate_marker_badge_html = ''

            popup_html = f"""
            <div style="width: 300px; font-family: 'Malgun Gothic', sans-serif;">
                <h4 style="margin: 0 0 10px 0; color: {marker_text};">주문 #{order_id_display}{duplicate_badge_html}</h4>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 3px; font-weight: bold;">고객명:</td><td style="padding: 3px;">{customer_name_escaped}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">담당자:</td><td style="padding: 3px;">{manager_name_escaped}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">연락처:</td><td style="padding: 3px;">{phone_escaped}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">주소:</td><td style="padding: 3px;">{address_escaped}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">제품:</td><td style="padding: 3px;">{product_escaped}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">상태:</td><td style="padding: 3px; color: {status_color};">{status_escaped}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">접수일:</td><td style="padding: 3px;">{received_date_escaped}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">좌표:</td><td style="padding: 3px;">{lat:.6f}, {lng:.6f}</td></tr>
                    {duplicate_row}
                </table>
            </div>
            """
            
            # 지도 마커: 고객명 표기 (Pro 스타일 · 모바일 시인성)
            name_display = (customer_name[:MAP_MARKER_NAME_MAX_LEN] + "…") if len(customer_name) > MAP_MARKER_NAME_MAX_LEN else customer_name
            name_display_escaped = html.escape(name_display)

            # Pro 디자인: pill 배지, 넉넉한 패딩/폰트, 그림자로 시인성 확보 (모바일 시인성)
            icon_html = f"""
            <div class="foms-map-marker"
                data-marker-index="{idx}"
                data-order-id="{order_id_attr}"
                data-customer-name="{customer_name_escaped}"
                data-lat="{lat}"
                data-lng="{lng}"
                data-base-background="{marker_bg}"
                data-base-border="{marker_border}"
                data-base-border-width="2px"
                data-base-text="{marker_text}"
                data-base-shadow="{marker_shadow}"
                data-overlap-background="{OVERLAP_MARKER_COLOR}"
                data-overlap-border="#e29ab7"
                data-overlap-border-width="2px"
                data-overlap-text="#6c2845"
                data-overlap-shadow="rgba(232, 160, 186, 0.35)"
                data-duplicate-group-key="{duplicate_group_key_attr}"
                data-duplicate-group-size="{duplicate_group_size}"
                data-duplicate-group-index="{duplicate_group_index}"
                data-route-state="none"
                data-visual-overlap="false"
                style="
                background: {marker_bg};
                color: {marker_text};
                border-radius: 9999px;
                padding: 6px 12px;
                font-weight: 600;
                font-size: 14px;
                line-height: 1.2;
                display: inline-flex;
                align-items: center;
                white-space: nowrap;
                max-width: 160px;
                overflow: hidden;
                text-overflow: ellipsis;
                border: 2px solid {marker_border};
                box-shadow: 0 2px 8px {marker_shadow};
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif;
                transition: transform 0.12s ease-out;
            "><span>{name_display_escaped}</span>{duplicate_marker_badge_html}</div>
            """
            icon_w = max(80, min(184, len(name_display) * 14 + 24 + (32 if is_duplicate else 0)))
            icon_h = 36
            
            # DivIcon: 고객명 pill 배지 (Pro · 모바일 시인성)
            marker = folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(popup_html, max_width=350),
                tooltip=html.escape(
                    f"{customer_name} · {('중복 위치 x' + str(duplicate_group_size) + ' · ' if is_duplicate else '')}{status}",
                    quote=True,
                ),
                icon=folium.DivIcon(
                    html=icon_html,
                    icon_size=(icon_w, icon_h),
                    icon_anchor=(icon_w // 2, icon_h)
                )
            )
            
            marker.add_to(m)
        
        # 범례 추가
        title_escaped = html.escape(str(title), quote=False)
        legend_html = f"""
        <div style="position: fixed; 
                    bottom: 50px; left: 50px; width: 200px; height: auto; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px; font-family: 'Malgun Gothic', sans-serif;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.3); border-radius: 5px;">
        <h4 style="margin-top: 0;">{title_escaped}</h4>
        <p><strong>총 {len(valid_data)}개 주문</strong></p>
        <div style="margin-top: 10px;">
            <div style="margin: 3px 0;"><span style="color: #007bff;">●</span> 접수</div>
            <div style="margin: 3px 0;"><span style="color: #28a745;">●</span> 확인</div>
            <div style="margin: 3px 0;"><span style="color: #ffc107;">●</span> 제작중</div>
            <div style="margin: 3px 0;"><span style="color: #17a2b8;">●</span> 배송</div>
            <div style="margin: 3px 0;"><span style="color: #20c997;">●</span> 배송완료</div>
            <div style="margin: 3px 0;"><span style="color: #6c757d;">●</span> 완료</div>
            <div style="margin: 3px 0;"><span style="color: #dc3545;">●</span> 취소</div>
            <div style="margin: 3px 0;"><span style="color: #fd7e14;">●</span> 보류</div>
            <div style="margin: 3px 0;"><span style="color: {OVERLAP_MARKER_COLOR};">●</span> 동일 주소 중첩</div>
        </div>
        </div>
        """
        
        getattr(m.get_root(), "html").add_child(folium.Element(legend_html))

        # Pro 스타일: 지도 마커 모바일 시인성 (터치 영역·가독성)
        marker_style = """
        <style>
        .foms-map-marker { -webkit-tap-highlight-color: transparent; }
        @media (max-width: 768px) {
            .leaflet-marker-icon .foms-map-marker,
            .foms-map-marker {
                font-size: 16px !important;
                padding: 8px 14px !important;
                min-height: 44px;
                box-sizing: border-box;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
        }
        </style>
        """
        getattr(m.get_root(), "html").add_child(folium.Element(marker_style))
        
        # 경로 계산을 위한 JavaScript 함수들 추가
        route_js = """
        <script>
        // 전역 변수
        window.selectedMarkers = [];
        window.currentRouteLine = null;
        window.routeStatus = null;
        window.mapObject = null;
        window.visualOverlapFrame = null;
        window.duplicateMarkerZoomThreshold = 14;
        
        // 지도 객체 참조 설정 (DOM 로드 후)
        document.addEventListener('DOMContentLoaded', function() {
            // Folium 지도 객체 찾기
            var mapKeys = Object.keys(window).filter(key => key.startsWith('map_'));
            if (mapKeys.length > 0) {
                window.mapObject = window[mapKeys[0]];
                if (window.mapObject) {
                    window.mapObject.whenReady(function() {
                        scheduleVisualOverlapRefresh();
                    });
                    window.mapObject.on('zoomend moveend resize', scheduleVisualOverlapRefresh);
                    setTimeout(scheduleVisualOverlapRefresh, 300);
                }
            }
        });

        function getRenderedMarkerPills() {
            return Array.from(document.querySelectorAll('.leaflet-marker-icon .foms-map-marker'));
        }

        function getMarkerPillByIndex(markerIndex) {
            var markerPills = getRenderedMarkerPills();
            return markerPills[markerIndex - 1] || null;
        }

        function clearMarkerVisualOffset(markerPill) {
            if (!markerPill) {
                return;
            }
            markerPill.style.transform = 'translate(0px, 0px)';
            markerPill.style.zIndex = '';
        }

        function setRenderedMarkerVisibility(markerPill, visible) {
            if (!markerPill) {
                return;
            }
            var wrapper = markerPill.closest('.leaflet-marker-icon');
            if (!wrapper) {
                return;
            }
            wrapper.style.display = visible ? '' : 'none';
            markerPill.style.pointerEvents = visible ? '' : 'none';
        }

        function getDuplicateMarkerLayoutMeta(markerPill) {
            if (!markerPill) {
                return null;
            }
            var groupKey = markerPill.dataset.duplicateGroupKey || '';
            var groupSize = parseInt(markerPill.dataset.duplicateGroupSize || '0', 10);
            var groupIndex = parseInt(markerPill.dataset.duplicateGroupIndex || '0', 10);
            if (!groupKey || groupSize <= 1 || groupIndex <= 0) {
                return null;
            }
            return {
                groupKey: groupKey,
                groupSize: groupSize,
                groupIndex: groupIndex,
            };
        }

        function buildDuplicateMarkerGroups(markerPills) {
            var duplicateGroups = {};
            markerPills.forEach(function(markerPill) {
                var meta = getDuplicateMarkerLayoutMeta(markerPill);
                if (!meta) {
                    return;
                }
                if (!duplicateGroups[meta.groupKey]) {
                    duplicateGroups[meta.groupKey] = [];
                }
                duplicateGroups[meta.groupKey].push({
                    pill: markerPill,
                    groupIndex: meta.groupIndex,
                });
            });
            return duplicateGroups;
        }

        function isDuplicateMarkerExpandedView() {
            if (!window.mapObject || typeof window.mapObject.getZoom !== 'function') {
                return true;
            }
            return window.mapObject.getZoom() >= window.duplicateMarkerZoomThreshold;
        }

        function applyDuplicateMarkerLayout() {
            var markerPills = getRenderedMarkerPills();
            if (!markerPills.length) {
                return;
            }

            markerPills.forEach(function(markerPill) {
                clearMarkerVisualOffset(markerPill);
                setRenderedMarkerVisibility(markerPill, true);
            });

            var duplicateGroups = buildDuplicateMarkerGroups(markerPills);
            var expandedView = isDuplicateMarkerExpandedView();

            Object.keys(duplicateGroups).forEach(function(groupKey) {
                var groupItems = duplicateGroups[groupKey];
                if (!groupItems || groupItems.length <= 1) {
                    return;
                }

                groupItems.sort(function(first, second) {
                    return first.groupIndex - second.groupIndex;
                });

                if (!expandedView) {
                    groupItems.forEach(function(groupItem, position) {
                        var routeState = groupItem.pill.dataset.routeState || 'none';
                        var forceVisible = routeState !== 'none';
                        var isRepresentative = position === 0;
                        setRenderedMarkerVisibility(groupItem.pill, isRepresentative || forceVisible);
                        clearMarkerVisualOffset(groupItem.pill);
                        if (isRepresentative || forceVisible) {
                            groupItem.pill.style.zIndex = String(300 + groupItems.length - position);
                        }
                    });
                    return;
                }

                var maxWidth = 0;
                var maxHeight = 0;
                groupItems.forEach(function(groupItem) {
                    var rect = groupItem.pill.getBoundingClientRect();
                    maxWidth = Math.max(maxWidth, rect.width || 0);
                    maxHeight = Math.max(maxHeight, rect.height || 0);
                });

                if (!maxWidth) {
                    maxWidth = 120;
                }
                if (!maxHeight) {
                    maxHeight = 36;
                }

                var columns = groupItems.length <= 4 ? groupItems.length : 3;
                var spacingX = Math.min(240, Math.max(88, Math.round(maxWidth * 1.1)));
                var spacingY = Math.max(52, Math.round(maxHeight * 1.35));

                groupItems.forEach(function(groupItem, position) {
                    var row = Math.floor(position / columns);
                    var rowStart = row * columns;
                    var rowCount = Math.min(columns, groupItems.length - rowStart);
                    var column = position % columns;
                    var rowCenter = (rowCount - 1) / 2;
                    var dx = Math.round((column - rowCenter) * spacingX);
                    var dy = -Math.round((row * spacingY) + (Math.abs(dx) * 0.16));

                    groupItem.pill.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';
                    groupItem.pill.style.zIndex = String(300 + position);
                });
            });
        }

        function applyMarkerTheme(markerPill, theme) {
            if (!markerPill || !theme) {
                return;
            }
            markerPill.style.background = theme.background;
            markerPill.style.border = (theme.borderWidth || '2px') + ' solid ' + theme.border;
            markerPill.style.color = theme.text;
            markerPill.style.boxShadow = '0 2px 8px ' + theme.shadow;
        }

        function getBaseMarkerTheme(markerPill) {
            return {
                background: markerPill.dataset.baseBackground || '#007bff',
                border: markerPill.dataset.baseBorder || '#ffffff',
                borderWidth: markerPill.dataset.baseBorderWidth || '2px',
                text: markerPill.dataset.baseText || '#ffffff',
                shadow: markerPill.dataset.baseShadow || 'rgba(0,0,0,0.25)',
            };
        }

        function getOverlapMarkerTheme(markerPill) {
            return {
                background: markerPill.dataset.overlapBackground || '#f8c8d8',
                border: markerPill.dataset.overlapBorder || '#e29ab7',
                borderWidth: markerPill.dataset.overlapBorderWidth || '2px',
                text: markerPill.dataset.overlapText || '#6c2845',
                shadow: markerPill.dataset.overlapShadow || 'rgba(232, 160, 186, 0.35)',
            };
        }

        function restoreMarkerTheme(markerPill) {
            if (!markerPill) {
                return;
            }
            if ((markerPill.dataset.routeState || 'none') !== 'none') {
                return;
            }
            if (markerPill.dataset.visualOverlap === 'true') {
                applyMarkerTheme(markerPill, getOverlapMarkerTheme(markerPill));
                return;
            }
            applyMarkerTheme(markerPill, getBaseMarkerTheme(markerPill));
        }

        function applyRouteMarkerTheme(markerPill, routeState) {
            if (!markerPill) {
                return;
            }
            markerPill.dataset.routeState = routeState || 'none';
            if (routeState === 'start') {
                applyMarkerTheme(markerPill, {
                    background: '#ff6b6b',
                    border: '#ff0000',
                    borderWidth: '3px',
                    text: '#ffffff',
                    shadow: 'rgba(0,0,0,0.25)',
                });
                return;
            }
            if (routeState === 'end') {
                applyMarkerTheme(markerPill, {
                    background: '#4caf50',
                    border: '#2e7d32',
                    borderWidth: '3px',
                    text: '#ffffff',
                    shadow: 'rgba(0,0,0,0.25)',
                });
                return;
            }
            restoreMarkerTheme(markerPill);
        }

        function rectanglesOverlap(firstRect, secondRect, padding) {
            var extra = padding || 0;
            return !(
                firstRect.right - extra <= secondRect.left + extra ||
                firstRect.left + extra >= secondRect.right - extra ||
                firstRect.bottom - extra <= secondRect.top + extra ||
                firstRect.top + extra >= secondRect.bottom - extra
            );
        }

        function hasDuplicateMarkerGroup(markerPill) {
            return !!getDuplicateMarkerLayoutMeta(markerPill);
        }

        function refreshVisualOverlapMarkers() {
            var markerPills = getRenderedMarkerPills();
            if (!markerPills.length) {
                return;
            }

            applyDuplicateMarkerLayout();

            markerPills.forEach(function(markerPill) {
                markerPill.dataset.visualOverlap = 'false';
                restoreMarkerTheme(markerPill);
            });

            var visibleMarkers = markerPills
                .map(function(markerPill) {
                    return {
                        pill: markerPill,
                        rect: markerPill.getBoundingClientRect(),
                    };
                })
                .filter(function(item) {
                    return item.rect.width > 0 && item.rect.height > 0;
                });

            var overlappingMarkers = new Set();
            for (var i = 0; i < visibleMarkers.length; i++) {
                for (var j = i + 1; j < visibleMarkers.length; j++) {
                    if (rectanglesOverlap(visibleMarkers[i].rect, visibleMarkers[j].rect, 6)) {
                        if (hasDuplicateMarkerGroup(visibleMarkers[i].pill)) {
                            overlappingMarkers.add(visibleMarkers[i].pill);
                        }
                        if (hasDuplicateMarkerGroup(visibleMarkers[j].pill)) {
                            overlappingMarkers.add(visibleMarkers[j].pill);
                        }
                    }
                }
            }

            overlappingMarkers.forEach(function(markerPill) {
                markerPill.dataset.visualOverlap = 'true';
                restoreMarkerTheme(markerPill);
            });
        }

        function scheduleVisualOverlapRefresh() {
            if (window.visualOverlapFrame) {
                window.cancelAnimationFrame(window.visualOverlapFrame);
            }
            window.visualOverlapFrame = window.requestAnimationFrame(function() {
                refreshVisualOverlapMarkers();
                window.visualOverlapFrame = null;
            });
        }

        function ensureRouteStatusPanel() {
            if (window.routeStatus) {
                return;
            }
            var statusDiv = document.createElement('div');
            statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); font-family: \"Malgun Gothic\", sans-serif; min-width: 250px; max-width: 400px; z-index: 1000;';
            statusDiv.innerHTML = '<h4 style=\"margin: 0 0 10px 0; color: #333;\">🚗 경로 계산</h4><p style=\"margin: 0; color: #666;\">주문 마커를 2개 선택하면 차량 이동 시간을 계산합니다.</p>';
            document.body.appendChild(statusDiv);
            window.routeStatus = statusDiv;
        }

        function escapeHtml(value) {
            return String(value == null ? '' : value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function bindMarkerClickDelegation() {
            if (window.markerClickDelegationBound) {
                return;
            }
            document.addEventListener('click', function(event) {
                var markerPill = event.target.closest('.leaflet-marker-icon .foms-map-marker');
                if (!markerPill) {
                    return;
                }
                handleMarkerClick(
                    parseFloat(markerPill.dataset.lat || '0'),
                    parseFloat(markerPill.dataset.lng || '0'),
                    markerPill.dataset.orderId || '',
                    markerPill.dataset.customerName || '',
                    parseInt(markerPill.dataset.markerIndex || '0', 10)
                );
            });
            window.markerClickDelegationBound = true;
        }
        
        // 마커 클릭 핸들러
        function handleMarkerClick(lat, lng, orderId, customerName, markerIndex) {
            if (!window.selectedMarkers) {
                window.selectedMarkers = [];
            }
            if (!markerIndex) {
                return;
            }
            ensureRouteStatusPanel();
            
            if (window.selectedMarkers.length === 0) {
                // 첫 번째 마커 선택
                window.selectedMarkers.push({lat: lat, lng: lng, orderId: orderId, name: customerName, index: markerIndex});
                applyRouteMarkerTheme(getMarkerPillByIndex(markerIndex), 'start');
                window.routeStatus.innerHTML = '<div style="background: #e3f2fd; padding: 10px; border-radius: 5px; margin-bottom: 10px;"><strong>출발지 선택됨:</strong> ' + escapeHtml(customerName) + '<br><small>도착지를 선택해주세요.</small></div>';
                
            } else if (window.selectedMarkers.length === 1) {
                var start = window.selectedMarkers[0];
                
                if (String(start.orderId) === String(orderId)) {
                    alert('같은 주문을 선택했습니다. 다른 주문을 선택해주세요.');
                    return;
                }
                
                // 두 번째 마커 선택
                var end = {lat: lat, lng: lng, orderId: orderId, name: customerName, index: markerIndex};
                window.selectedMarkers.push(end);
                applyRouteMarkerTheme(getMarkerPillByIndex(markerIndex), 'end');
                // 경로 계산 시작
                calculateRoute(start, end);
                
            } else {
                // 초기화 후 다시 시작
                resetRouteCalculation();
                handleMarkerClick(lat, lng, orderId, customerName, markerIndex);
            }
        }
        
        // 경로 계산 함수
        function calculateRoute(start, end) {
            window.routeStatus.innerHTML = '<div style="background: #fff3cd; padding: 10px; border-radius: 5px;"><strong>경로 계산 중...</strong><br><small>잠시만 기다려주세요.</small></div>';
            
            fetch(`/api/calculate_route?start_lat=${encodeURIComponent(start.lat)}&start_lng=${encodeURIComponent(start.lng)}&end_lat=${encodeURIComponent(end.lat)}&end_lng=${encodeURIComponent(end.lng)}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error('HTTP ' + response.status);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        var routeData = data.data;
                        var startName = escapeHtml(start.name);
                        var endName = escapeHtml(end.name);
                        var distanceText = escapeHtml(routeData.summary.distance_text);
                        var durationText = escapeHtml(routeData.summary.duration_text);
                        var tollText = escapeHtml(routeData.summary.toll_text);
                        
                        // 경로 라인 그리기
                        if (window.currentRouteLine) {
                            window.mapObject.removeLayer(window.currentRouteLine);
                        }
                        
                        if (routeData.route_coords && routeData.route_coords.length > 0) {
                            window.currentRouteLine = L.polyline(routeData.route_coords, {
                                color: '#ff4757',
                                weight: 5,
                                opacity: 0.8
                            }).addTo(window.mapObject);
                            
                            // 경로에 맞게 지도 범위 조정
                            var bounds = L.latLngBounds([
                                [start.lat, start.lng],
                                [end.lat, end.lng]
                            ]);
                            window.mapObject.fitBounds(bounds, {padding: [50, 50]});
                        }
                        
                        // 결과 표시
                        var resultHtml = `
                            <div style="background: #d4edda; padding: 15px; border-radius: 5px; border-left: 4px solid #28a745;">
                                <h4 style="margin: 0 0 10px 0; color: #155724;">🚗 경로 정보</h4>
                                <div style="margin-bottom: 8px;"><strong>출발:</strong> ${startName}</div>
                                <div style="margin-bottom: 8px;"><strong>도착:</strong> ${endName}</div>
                                <div style="margin-bottom: 8px;"><strong>거리:</strong> ${distanceText}</div>
                                <div style="margin-bottom: 8px;"><strong>소요시간:</strong> ${durationText}</div>
                                <div style="margin-bottom: 15px;"><strong>통행료:</strong> ${tollText}</div>
                                <button onclick="resetRouteCalculation()" style="background: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 12px;">초기화</button>
                            </div>
                        `;
                        window.routeStatus.innerHTML = resultHtml;
                        scheduleVisualOverlapRefresh();
                        
                    } else {
                        window.routeStatus.innerHTML = `<div style="background: #f8d7da; padding: 10px; border-radius: 5px; color: #721c24;"><strong>오류:</strong> ${escapeHtml(data.error)}</div>`;
                    }
                })
                .catch(error => {
                    console.error('경로 계산 오류:', error);
                    window.routeStatus.innerHTML = '<div style="background: #f8d7da; padding: 10px; border-radius: 5px; color: #721c24;"><strong>오류:</strong> 경로 계산에 실패했습니다.</div>';
                });
        }
        
        // 경로 계산 초기화
        function resetRouteCalculation() {
            if (window.selectedMarkers && window.selectedMarkers.length > 0) {
                window.selectedMarkers.forEach(function(selected) {
                    applyRouteMarkerTheme(getMarkerPillByIndex(selected.index), 'none');
                });
            }

            window.selectedMarkers = [];
            
            // 경로 라인 제거
            if (window.currentRouteLine && window.mapObject) {
                window.mapObject.removeLayer(window.currentRouteLine);
                window.currentRouteLine = null;
            }
            
            if (window.routeStatus) {
                window.routeStatus.innerHTML = '<h4 style="margin: 0 0 10px 0; color: #333;">🚗 경로 계산</h4><p style="margin: 0; color: #666;">주문 마커를 2개 선택하면 차량 이동 시간을 계산합니다.</p>';
            }
            scheduleVisualOverlapRefresh();
        }
        bindMarkerClickDelegation();
        </script>
        """
        
        getattr(m.get_root(), "html").add_child(folium.Element(route_js))
        
        return m
    
    def create_empty_map(self, title="지도"):
        """주문이 없을 때 빈 지도 생성"""
        # 기본 위치 (서울)
        center = [37.5665, 126.9780]
        
        # 지도 생성 - OpenStreetMap 스타일
        m = folium.Map(
            location=center,
            zoom_start=10,
            width="100%",
            height="100vh",
            tiles='OpenStreetMap'
        )
        
        # OpenStreetMap만 사용 (레이어 컨트롤 불필요)
        
        # 전체화면 플러그인 추가
        plugins.Fullscreen(
            position='topright',
            title='전체화면',
            title_cancel='전체화면 해제',
            force_separate_button=True
        ).add_to(m)
        
        # 메시지 범례 추가
        title_escaped = html.escape(str(title), quote=False)
        message_html = f"""
        <div style="position: fixed; 
                    bottom: 50px; left: 50px; width: 300px; height: auto; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 20px; font-family: 'Malgun Gothic', sans-serif;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.3); border-radius: 5px;">
        <h4 style="margin-top: 0; color: #007bff;">{title_escaped}</h4>
        <p><strong>표시할 주문이 없습니다</strong></p>
        <p>선택한 날짜에 해당하는 주문이 없거나<br/>
        좌표 변환에 실패했습니다.</p>
        <div style="margin-top: 15px; color: #666;">
            <i class="fas fa-info-circle"></i> 
            다른 날짜를 선택해보세요
        </div>
        </div>
        """
        
        getattr(m.get_root(), "html").add_child(folium.Element(message_html))
        
        return m
