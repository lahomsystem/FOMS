import requests
import time
import re
from datetime import datetime
from map_config import KAKAO_REST_API_KEY, MAX_RETRIES, DELAY_BETWEEN_REQUESTS, MIN_LAT, MAX_LAT, MIN_LNG, MAX_LNG
from foms_address_learning import FOMSAddressLearningSystem
from foms_advanced_address_processor import FOMSAdvancedAddressProcessor


class FOMSAddressConverter:
    """FOMS 시스템용 주소 변환 클래스"""
    
    def __init__(self):
        """API 키 설정 및 기본 URL 설정"""
        self.api_key = KAKAO_REST_API_KEY
        self.base_url = "https://dapi.kakao.com/v2/local/search/address.json"
        self.keyword_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        self.directions_url = "https://apis-navi.kakaomobility.com/v1/directions"
        self.headers = {"Authorization": f"KakaoAK {self.api_key}"}
        
        # AI 시스템 초기화
        self.learning_system = FOMSAddressLearningSystem()
        self.advanced_processor = FOMSAdvancedAddressProcessor()
        self.ai_enabled = True
    
    def _is_valid_coordinates(self, lat, lng):
        """좌표가 한국 영토 내에 있는지 검증"""
        return MIN_LAT <= lat <= MAX_LAT and MIN_LNG <= lng <= MAX_LNG
    
    def _normalize_address(self, address):
        """주소 정규화"""
        address = str(address).strip()
        
        # 기본 정규화
        address = re.sub(r'\s+', ' ', address)  # 다중 공백 제거
        address = re.sub(r'[^\w\s가-힣\-]', ' ', address)  # 특수문자 제거 (하이픈 제외)
        
        # 행정구역 축약어 확장
        replacements = {
            r'^서울\s': '서울특별시 ',
            r'^부산\s': '부산광역시 ',
            r'^대구\s': '대구광역시 ',
            r'^인천\s': '인천광역시 ',
            r'^광주\s': '광주광역시 ',
            r'^대전\s': '대전광역시 ',
            r'^울산\s': '울산광역시 ',
            r'^세종\s': '세종특별자치시 ',
            r'^경기\s': '경기도 ',
            r'^강원\s': '강원특별자치도 ',
            r'^충북\s': '충청북도 ',
            r'^충남\s': '충청남도 ',
            r'^전북\s': '전북특별자치도 ',
            r'^전남\s': '전라남도 ',
            r'^경북\s': '경상북도 ',
            r'^경남\s': '경상남도 ',
            r'^제주\s': '제주특별자치도 '
        }
        
        for pattern, replacement in replacements.items():
            address = re.sub(pattern, replacement, address)
        
        return address.strip()
    
    def _try_address_api(self, address):
        """주소 API로 변환 시도"""
        try:
            params = {"query": address}
            response = requests.get(
                self.base_url, 
                headers=self.headers, 
                params=params, 
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                documents = data.get("documents", [])
                
                if documents:
                    doc = documents[0]
                    if 'address' in doc and doc['address']:
                        lat = float(doc['address']['y'])
                        lng = float(doc['address']['x'])
                        
                        if self._is_valid_coordinates(lat, lng):
                            return lat, lng, "성공"
                    
                    # road_address 시도
                    if 'road_address' in doc and doc['road_address']:
                        lat = float(doc['road_address']['y'])
                        lng = float(doc['road_address']['x'])
                        
                        if self._is_valid_coordinates(lat, lng):
                            return lat, lng, "성공"
            
            return None, None, "주소를 찾을 수 없음"
            
        except Exception as e:
            return None, None, f"API 오류: {str(e)}"
    
    def _try_keyword_api(self, address):
        """키워드 API로 변환 시도"""
        try:
            params = {"query": address}
            response = requests.get(
                self.keyword_url, 
                headers=self.headers, 
                params=params, 
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                documents = data.get("documents", [])
                
                if documents:
                    doc = documents[0]
                    lat = float(doc['y'])
                    lng = float(doc['x'])
                    
                    if self._is_valid_coordinates(lat, lng):
                        return lat, lng, "키워드 검색 성공"
            
            return None, None, "키워드 검색 실패"
            
        except Exception as e:
            return None, None, f"키워드 API 오류: {str(e)}"
    
    def convert_address(self, address):
        """AI 기반 주소 변환"""
        if not address or str(address).strip() == '':
            return None, None, "빈 주소"
        
        # 1단계: 학습 데이터에서 검색
        try:
            learned_suggestion = self.learning_system.suggest_correction(address)
            if learned_suggestion and learned_suggestion.get('latitude') and learned_suggestion.get('longitude'):
                return (
                    learned_suggestion['latitude'], 
                    learned_suggestion['longitude'], 
                    f"학습 데이터 매칭 (신뢰도: {learned_suggestion['confidence']:.2f})"
                )
        except Exception as e:
            pass
        
        # 2단계: 고급 주소 처리
        try:
            processed_address = self.advanced_processor.process_address(address)
        except Exception as e:
            processed_address = address
        
        # 3단계: 정규화된 주소로 API 시도
        normalized_address = self._normalize_address(processed_address)
        
        # 4단계: 다중 전략 시도
        strategies = [
            ("processed", processed_address),
            ("normalized", normalized_address),
            ("original", address)
        ]
        
        for strategy_name, addr_to_try in strategies:
            if addr_to_try and addr_to_try.strip():
                # 주소 API 시도
                lat, lng, status = self._try_address_api(addr_to_try)
                if lat is not None and lng is not None:
                    return lat, lng, f"{status} ({strategy_name})"
                
                # 키워드 API 시도
                lat, lng, status = self._try_keyword_api(addr_to_try)
                if lat is not None and lng is not None:
                    return lat, lng, f"{status} ({strategy_name})"
        
        # 5단계: 주소 구성 요소 분석 후 재시도
        try:
            components = self.advanced_processor.extract_address_components(address)
            if components['city'] and components['district']:
                simplified_address = f"{components['city']} {components['district']}"
                if components['dong']:
                    simplified_address += f" {components['dong']}"
                
                lat, lng, status = self._try_address_api(simplified_address)
                if lat is not None and lng is not None:
                    return lat, lng, f"{status} (simplified)"
        except Exception as e:
            print(f"주소 구성 요소 분석 오류: {e}")
        
        # API 호출 간격 제어
        time.sleep(DELAY_BETWEEN_REQUESTS)
        
        print(f"[CONVERTER] 모든 변환 시도 실패")
        return None, None, "AI 변환 실패"
    
    def add_learning_data(self, original_address, corrected_address, lat, lng):
        """학습 데이터 추가"""
        self.learning_system.add_correction(original_address, corrected_address, lat, lng)
    
    def get_address_suggestions(self, address):
        """주소 교정 제안"""
        suggestions = []
        
        # 학습 시스템 제안
        learned_suggestion = self.learning_system.suggest_correction(address)
        if learned_suggestion:
            suggestions.append({
                'address': learned_suggestion['suggested_address'],
                'source': 'learning_system',
                'confidence': learned_suggestion['confidence']
            })
        
        # 고급 처리기 제안
        processor_suggestions = self.advanced_processor.suggest_corrections(address)
        for suggestion in processor_suggestions:
            suggestions.append({
                'address': suggestion,
                'source': 'advanced_processor',
                'confidence': 0.8
            })
        
        return suggestions
    
    def validate_address(self, address):
        """주소 유효성 검증"""
        return self.advanced_processor.validate_address_structure(address)
    
    def convert_addresses_batch(self, addresses):
        """여러 주소를 일괄 변환"""
        results = []
        
        for i, address in enumerate(addresses):
            lat, lng, status = self.convert_address(address)
            results.append({
                'original_address': address,
                'latitude': lat,
                'longitude': lng,
                'status': status
            })
            
            # API 호출 제한 준수
            if i < len(addresses) - 1:
                time.sleep(DELAY_BETWEEN_REQUESTS)
        
        return results
    
    def calculate_route(self, start_lat, start_lng, end_lat, end_lng):
        """두 좌표 간의 차량 경로 및 소요시간 계산"""
        try:
            # 카카오 내비게이션 API 사용
            url = self.directions_url
            params = {
                'origin': f"{start_lng},{start_lat}",  # 경도,위도 순서
                'destination': f"{end_lng},{end_lat}",
                'priority': 'RECOMMEND',  # 추천 경로
                'car_fuel': 'GASOLINE',
                'car_hipass': 'false',
                'alternatives': 'false'
            }
            
            response = requests.get(url, params=params, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                
                if 'routes' in data and len(data['routes']) > 0:
                    route = data['routes'][0]
                    summary = route.get('summary', {})
                    
                    # 거리 (미터) -> 킬로미터로 변환
                    distance_m = summary.get('distance', 0)
                    distance_km = round(distance_m / 1000, 1)
                    
                    # 소요시간 (초) -> 분으로 변환
                    duration_s = summary.get('duration', 0)
                    duration_min = round(duration_s / 60)
                    
                    # 통행료
                    fare = summary.get('fare', {})
                    toll = fare.get('toll', 0)
                    
                    # 경로 좌표들
                    sections = route.get('sections', [])
                    route_coords = []
                    
                    for section in sections:
                        roads = section.get('roads', [])
                        for road in roads:
                            vertexes = road.get('vertexes', [])
                            # vertexes는 [lng, lat, lng, lat, ...] 형태
                            for i in range(0, len(vertexes), 2):
                                if i + 1 < len(vertexes):
                                    lng = vertexes[i]
                                    lat = vertexes[i + 1]
                                    route_coords.append([lat, lng])
                    
                    return {
                        'status': 'success',
                        'distance_km': distance_km,
                        'duration_min': duration_min,
                        'toll': toll,
                        'route_coords': route_coords,
                        'summary': {
                            'distance_text': f"{distance_km}km",
                            'duration_text': f"{duration_min}분",
                            'toll_text': f"{toll:,}원" if toll > 0 else "무료"
                        }
                    }
                else:
                    return {
                        'status': 'error',
                        'message': '경로를 찾을 수 없습니다.'
                    }
            else:
                return {
                    'status': 'error', 
                    'message': f'API 요청 실패: {response.status_code}'
                }
                
        except Exception as e:
            return {
                'status': 'error',
                'message': f'경로 계산 중 오류 발생: {str(e)}'
            }
