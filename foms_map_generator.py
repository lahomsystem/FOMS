import folium
from folium import plugins
from map_config import DEFAULT_CENTER


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
            'CONFIRMED': '#28a745',     # 초록색 - 확인
            'IN_PRODUCTION': '#ffc107', # 노란색 - 제작중
            'COMPLETED': '#6c757d',     # 회색 - 완료
            'SHIPPED': '#17a2b8',       # 청록색 - 배송
            'DELIVERED': '#20c997',     # 민트색 - 배송완료
            'CANCELLED': '#dc3545',     # 빨간색 - 취소
            'ON_HOLD': '#fd7e14'        # 주황색 - 보류
        }
        return status_colors.get(status, '#6c757d')
    
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
        valid_data = [
            order for order in order_data 
            if order.get('latitude') is not None and order.get('longitude') is not None
        ]
        
        if not valid_data:
            return None
        
        # 지도 중심점과 줌 레벨 계산
        center = self._calculate_center(valid_data)
        zoom_level = self._calculate_zoom_level(valid_data)
        
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
        
        # 마커 추가
        for idx, order in enumerate(valid_data, 1):
            lat = order['latitude']
            lng = order['longitude']
            
            # 주문 정보
            customer_name = order.get('customer_name', '정보없음')
            address = order.get('address', '주소없음')
            product = order.get('product', '제품없음')
            status = order.get('status', 'UNKNOWN')
            received_date = order.get('received_date', '날짜없음')
            phone = order.get('phone', '연락처없음')
            
            # 상태별 색상
            color = self._get_status_color(status)
            
            # 팝업 텍스트 구성
            popup_html = f"""
            <div style="width: 300px; font-family: 'Malgun Gothic', sans-serif;">
                <h4 style="margin: 0 0 10px 0; color: {color};">주문 #{order.get('id', idx)}</h4>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 3px; font-weight: bold;">고객명:</td><td style="padding: 3px;">{customer_name}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">연락처:</td><td style="padding: 3px;">{phone}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">주소:</td><td style="padding: 3px;">{address}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">제품:</td><td style="padding: 3px;">{product}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">상태:</td><td style="padding: 3px; color: {color};">{status}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">접수일:</td><td style="padding: 3px;">{received_date}</td></tr>
                    <tr><td style="padding: 3px; font-weight: bold;">좌표:</td><td style="padding: 3px;">{lat:.6f}, {lng:.6f}</td></tr>
                </table>
            </div>
            """
            
            # 마커 아이콘 HTML (상태별 색상)
            icon_html = f"""
            <div style="
                background: {color}; 
                color: white; 
                border-radius: 50%; 
                width: 30px; 
                height: 30px; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                font-weight: bold; 
                font-size: 12px;
                border: 2px solid white;
                box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                font-family: 'Malgun Gothic', sans-serif;
            ">
                {idx}
            </div>
            """
            
            # 마커 클릭 시 경로 계산을 위한 JavaScript 코드
            marker_click_js = f"""
            function(e) {{
                var marker = e.target;
                var lat = {lat};
                var lng = {lng};
                var orderId = {order.get('id', idx)};
                var customerName = "{customer_name}";
                
                if (window.selectedMarkers) {{
                    if (window.selectedMarkers.length === 0) {{
                        // 첫 번째 마커 선택
                        window.selectedMarkers.push({{lat: lat, lng: lng, orderId: orderId, name: customerName}});
                        marker.setIcon(L.divIcon({{
                            html: '<div style="background: #ff6b6b; color: white; border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 12px; border: 3px solid #ff0000; box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-family: \\'Malgun Gothic\\', sans-serif;">{idx}</div>',
                            iconSize: [30, 30],
                            iconAnchor: [15, 15]
                        }}));
                        window.routeStatus.innerHTML = '<div style="background: #e3f2fd; padding: 10px; border-radius: 5px; margin-bottom: 10px;"><strong>출발지 선택됨:</strong> ' + customerName + '<br><small>도착지를 선택해주세요.</small></div>';
                    }} else if (window.selectedMarkers.length === 1) {{
                        // 두 번째 마커 선택 - 경로 계산
                        var start = window.selectedMarkers[0];
                        var end = {{lat: lat, lng: lng, orderId: orderId, name: customerName}};
                        
                        if (start.orderId === end.orderId) {{
                            alert('같은 주문을 선택했습니다. 다른 주문을 선택해주세요.');
                            return;
                        }}
                        
                        window.selectedMarkers.push(end);
                        marker.setIcon(L.divIcon({{
                            html: '<div style="background: #4caf50; color: white; border-radius: 50%; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 12px; border: 3px solid #2e7d32; box-shadow: 0 2px 6px rgba(0,0,0,0.3); font-family: \\'Malgun Gothic\\', sans-serif;">{idx}</div>',
                            iconSize: [30, 30],
                            iconAnchor: [15, 15]
                        }}));
                        
                        // 경로 계산 시작
                        calculateRoute(start, end);
                    }} else {{
                        // 초기화
                        resetRouteCalculation();
                    }}
                }} else {{
                    // 전역 변수 초기화
                    window.selectedMarkers = [];
                    window.currentRouteLine = null;
                    
                    // 상태 표시 영역 생성
                    if (!window.routeStatus) {{
                        var statusDiv = L.control({{position: 'topright'}});
                        statusDiv.onAdd = function(map) {{
                            var div = L.DomUtil.create('div', 'route-status');
                            div.style.cssText = 'background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); font-family: "Malgun Gothic", sans-serif; min-width: 250px; max-width: 400px;';
                            div.innerHTML = '<h4 style="margin: 0 0 10px 0; color: #333;">🚗 경로 계산</h4><p style="margin: 0; color: #666;">주문 마커를 2개 선택하면 차량 이동 시간을 계산합니다.</p>';
                            return div;
                        }};
                        statusDiv.addTo(window.mapObject);
                        window.routeStatus = statusDiv.getContainer().querySelector('.route-status');
                    }}
                    
                    // 첫 번째 마커로 다시 시도
                    this.click();
                }}
            }}
            """
            
            # DivIcon을 사용한 커스텀 마커
            marker = folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(popup_html, max_width=350),
                tooltip=f"#{idx}: {customer_name} - {status}",
                icon=folium.DivIcon(
                    html=icon_html,
                    icon_size=(30, 30),
                    icon_anchor=(15, 15)
                )
            )
            
            marker.add_to(m)
            
            # 마커에 클릭 이벤트 추가를 위한 JavaScript 코드
            click_js = f"""
            <script>
            document.addEventListener('DOMContentLoaded', function() {{
                setTimeout(function() {{
                    var markers = document.querySelectorAll('.leaflet-marker-icon');
                    markers.forEach(function(markerEl, index) {{
                        if (index === {idx - 1}) {{ // 현재 마커 인덱스
                            markerEl.addEventListener('click', function() {{
                                handleMarkerClick({lat}, {lng}, {order.get('id', idx)}, "{customer_name}", {idx});
                            }});
                        }}
                    }});
                }}, 1000);
            }});
            </script>
            """
            m.get_root().html.add_child(folium.Element(click_js))
        
        # 범례 추가
        legend_html = f"""
        <div style="position: fixed; 
                    bottom: 50px; left: 50px; width: 200px; height: auto; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px; font-family: 'Malgun Gothic', sans-serif;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.3); border-radius: 5px;">
        <h4 style="margin-top: 0;">{title}</h4>
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
        </div>
        </div>
        """
        
        m.get_root().html.add_child(folium.Element(legend_html))
        
        # 경로 계산을 위한 JavaScript 함수들 추가
        route_js = """
        <script>
        // 전역 변수
        window.selectedMarkers = [];
        window.currentRouteLine = null;
        window.routeStatus = null;
        window.mapObject = null;
        
        // 지도 객체 참조 설정 (DOM 로드 후)
        document.addEventListener('DOMContentLoaded', function() {
            // Folium 지도 객체 찾기
            var mapKeys = Object.keys(window).filter(key => key.startsWith('map_'));
            if (mapKeys.length > 0) {
                window.mapObject = window[mapKeys[0]];
            }
        });
        
        // 마커 클릭 핸들러
        function handleMarkerClick(lat, lng, orderId, customerName, markerIndex) {
            if (!window.selectedMarkers) {
                window.selectedMarkers = [];
            }
            
            // 상태 표시 영역 생성 (아직 없다면)
            if (!window.routeStatus) {
                var statusDiv = document.createElement('div');
                statusDiv.style.cssText = 'position: fixed; top: 20px; right: 20px; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); font-family: "Malgun Gothic", sans-serif; min-width: 250px; max-width: 400px; z-index: 1000;';
                statusDiv.innerHTML = '<h4 style="margin: 0 0 10px 0; color: #333;">🚗 경로 계산</h4><p style="margin: 0; color: #666;">주문 마커를 2개 선택하면 차량 이동 시간을 계산합니다.</p>';
                document.body.appendChild(statusDiv);
                window.routeStatus = statusDiv;
            }
            
            if (window.selectedMarkers.length === 0) {
                // 첫 번째 마커 선택
                window.selectedMarkers.push({lat: lat, lng: lng, orderId: orderId, name: customerName, index: markerIndex});
                
                // 마커 색상 변경 (빨간색 - 출발지)
                var markers = document.querySelectorAll('.leaflet-marker-icon');
                if (markers[markerIndex - 1]) {
                    var markerEl = markers[markerIndex - 1];
                    var divEl = markerEl.querySelector('div');
                    if (divEl) {
                        divEl.style.background = '#ff6b6b';
                        divEl.style.border = '3px solid #ff0000';
                    }
                }
                
                window.routeStatus.innerHTML = '<div style="background: #e3f2fd; padding: 10px; border-radius: 5px; margin-bottom: 10px;"><strong>출발지 선택됨:</strong> ' + customerName + '<br><small>도착지를 선택해주세요.</small></div>';
                
            } else if (window.selectedMarkers.length === 1) {
                var start = window.selectedMarkers[0];
                
                if (start.orderId === orderId) {
                    alert('같은 주문을 선택했습니다. 다른 주문을 선택해주세요.');
                    return;
                }
                
                // 두 번째 마커 선택
                var end = {lat: lat, lng: lng, orderId: orderId, name: customerName, index: markerIndex};
                window.selectedMarkers.push(end);
                
                // 마커 색상 변경 (초록색 - 도착지)
                var markers = document.querySelectorAll('.leaflet-marker-icon');
                if (markers[markerIndex - 1]) {
                    var markerEl = markers[markerIndex - 1];
                    var divEl = markerEl.querySelector('div');
                    if (divEl) {
                        divEl.style.background = '#4caf50';
                        divEl.style.border = '3px solid #2e7d32';
                    }
                }
                
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
            
            fetch(`/api/calculate_route?start_lat=${start.lat}&start_lng=${start.lng}&end_lat=${end.lat}&end_lng=${end.lng}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        var routeData = data.data;
                        
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
                                <div style="margin-bottom: 8px;"><strong>출발:</strong> ${start.name}</div>
                                <div style="margin-bottom: 8px;"><strong>도착:</strong> ${end.name}</div>
                                <div style="margin-bottom: 8px;"><strong>거리:</strong> ${routeData.summary.distance_text}</div>
                                <div style="margin-bottom: 8px;"><strong>소요시간:</strong> ${routeData.summary.duration_text}</div>
                                <div style="margin-bottom: 15px;"><strong>통행료:</strong> ${routeData.summary.toll_text}</div>
                                <button onclick="resetRouteCalculation()" style="background: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 12px;">초기화</button>
                            </div>
                        `;
                        window.routeStatus.innerHTML = resultHtml;
                        
                    } else {
                        window.routeStatus.innerHTML = `<div style="background: #f8d7da; padding: 10px; border-radius: 5px; color: #721c24;"><strong>오류:</strong> ${data.error}</div>`;
                    }
                })
                .catch(error => {
                    console.error('경로 계산 오류:', error);
                    window.routeStatus.innerHTML = '<div style="background: #f8d7da; padding: 10px; border-radius: 5px; color: #721c24;"><strong>오류:</strong> 경로 계산에 실패했습니다.</div>';
                });
        }
        
        // 경로 계산 초기화
        function resetRouteCalculation() {
            // 선택된 마커들의 색상 복원
            if (window.selectedMarkers && window.selectedMarkers.length > 0) {
                var markers = document.querySelectorAll('.leaflet-marker-icon');
                window.selectedMarkers.forEach(function(selected) {
                    if (markers[selected.index - 1]) {
                        var markerEl = markers[selected.index - 1];
                        var divEl = markerEl.querySelector('div');
                        if (divEl) {
                            // 원래 색상으로 복원 (기본 파란색)
                            divEl.style.background = '#007bff';
                            divEl.style.border = '2px solid white';
                        }
                    }
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
        }
        </script>
        """
        
        m.get_root().html.add_child(folium.Element(route_js))
        
        return m
    
    def create_empty_map(self, title="지도"):
        """주문이 없을 때 빈 지도 생성"""
        # 기본 위치 (서울)
        center = [37.5665, 126.9780]
        
        # 지도 생성 - 카카오맵 스타일
        m = folium.Map(
            location=center,
            zoom_start=10,
            width="100%",
            height="100vh",
            tiles=None
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
        message_html = f"""
        <div style="position: fixed; 
                    bottom: 50px; left: 50px; width: 300px; height: auto; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 20px; font-family: 'Malgun Gothic', sans-serif;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.3); border-radius: 5px;">
        <h4 style="margin-top: 0; color: #007bff;">{title}</h4>
        <p><strong>표시할 주문이 없습니다</strong></p>
        <p>선택한 날짜에 해당하는 주문이 없거나<br/>
        좌표 변환에 실패했습니다.</p>
        <div style="margin-top: 15px; color: #666;">
            <i class="fas fa-info-circle"></i> 
            다른 날짜를 선택해보세요
        </div>
        </div>
        """
        
        m.get_root().html.add_child(folium.Element(message_html))
        
        return m
