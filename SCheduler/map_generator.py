import folium
from config import DEFAULT_CENTER


class MapGenerator:
    """Folium을 사용한 지도 생성 클래스"""
    
    def __init__(self):
        """지도 생성기 초기화"""
        pass
    
    def _calculate_center(self, coordinates_data):
        """유효한 좌표들의 중심점 계산"""
        valid_coords = [
            (row['위도'], row['경도']) 
            for row in coordinates_data 
            if row['위도'] is not None and row['경도'] is not None
        ]
        
        if not valid_coords:
            return DEFAULT_CENTER
        
        avg_lat = sum(coord[0] for coord in valid_coords) / len(valid_coords)
        avg_lng = sum(coord[1] for coord in valid_coords) / len(valid_coords)
        
        return [avg_lat, avg_lng]
    
    def _calculate_zoom_level(self, coordinates_data):
        """좌표 분포에 따른 적절한 줌 레벨 계산"""
        valid_coords = [
            (row['위도'], row['경도']) 
            for row in coordinates_data 
            if row['위도'] is not None and row['경도'] is not None
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
    
    def create_map(self, coordinates_data, width=None, height=None):
        """
        좌표 데이터로 Folium 지도 생성 (카카오맵 스타일)
        Args: 
            coordinates_data - List[Dict] with '위도', '경도', '주소' keys
            width - 지도 너비 (픽셀 또는 "100%")
            height - 지도 높이 (픽셀 또는 "100vh")
        Returns: folium.Map object or None
        """
        if not coordinates_data:
            return None
        
        # 성공한 좌표만 필터링
        valid_data = [
            row for row in coordinates_data 
            if row['위도'] is not None and row['경도'] is not None and '성공' in str(row['상태'])
        ]
        
        if not valid_data:
            return None
        
        # 지도 중심점과 줌 레벨 계산
        center = self._calculate_center(valid_data)
        zoom_level = self._calculate_zoom_level(valid_data)
        
        # 지도 생성 - 크기 파라미터 처리
        map_kwargs = {
            'location': center,
            'zoom_start': zoom_level,
            'tiles': None  # 기본 타일 제거하고 커스텀 타일 사용
        }
        
        # 크기 파라미터 처리
        if width and height:
            if width == "100%" and height == "100vh":
                # 전체화면 모드
                map_kwargs['width'] = "100%"
                map_kwargs['height'] = "90vh"  # 브라우저 창 높이의 90%
            else:
                map_kwargs['width'] = f'{width}px'
                map_kwargs['height'] = f'{height}px'
        
        # 카카오맵 스타일을 기본 타일로 직접 설정
        map_kwargs['tiles'] = 'https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png'
        map_kwargs['attr'] = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        
        m = folium.Map(**map_kwargs)
        
        # 추가 지도 스타일 옵션들을 레이어로 추가
        folium.TileLayer(
            tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            name='기본 지도',
            overlay=False,
            control=True
        ).add_to(m)
        
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Tiles &copy; Esri',
            name='위성 지도',
            overlay=False,
            control=True
        ).add_to(m)
        
        # 레이어 컨트롤 추가
        folium.LayerControl().add_to(m)
        
        # 전체화면 플러그인 추가
        from folium import plugins
        plugins.Fullscreen(
            position='topright',
            title='전체화면',
            title_cancel='전체화면 해제',
            force_separate_button=True
        ).add_to(m)
        
        # 미니맵 추가
        minimap = plugins.MiniMap(toggle_display=True)
        m.add_child(minimap)
        
        # 마커 추가 (카카오맵 스타일)
        for idx, row in enumerate(valid_data, 1):
            lat = row['위도']
            lng = row['경도']
            address = row['주소']
            
            # 팝업과 툴팁에 주소와 순서 표시
            popup_text = f"<b>#{idx}: {address}</b><br/>위도: {lat:.6f}<br/>경도: {lng:.6f}"
            
            # 카카오맵 스타일의 마커 아이콘 (주황색 그라데이션)
            icon_html = f"""
            <div style="
                background: linear-gradient(45deg, #ff6b35, #ff8c42); 
                color: white; 
                border-radius: 50%; 
                width: 32px; 
                height: 32px; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
                font-weight: bold; 
                font-size: 13px;
                border: 3px solid white;
                box-shadow: 0 3px 8px rgba(0,0,0,0.4);
                font-family: 'Malgun Gothic', sans-serif;
            ">
                {idx}
            </div>
            """
            
            # DivIcon을 사용한 커스텀 마커
            folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(popup_text, max_width=300),
                tooltip=f"#{idx}: {address}",
                icon=folium.DivIcon(
                    html=icon_html,
                    icon_size=(32, 32),
                    icon_anchor=(16, 16)
                )
            ).add_to(m)
        
        return m 