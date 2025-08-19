import requests
import time
import re
from datetime import datetime
from config import KAKAO_REST_API_KEY, MAX_RETRIES, DELAY_BETWEEN_REQUESTS, MIN_LAT, MAX_LAT, MIN_LNG, MAX_LNG


class AddressConverter:
    """카카오 API를 사용한 주소 변환 클래스 (다중 전략 지원)"""
    
    def __init__(self, learning_system=None):
        """API 키 설정 및 기본 URL 설정"""
        self.api_key = KAKAO_REST_API_KEY
        self.base_url = "https://dapi.kakao.com/v2/local/search/address.json"
        self.keyword_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        self.headers = {"Authorization": f"KakaoAK {self.api_key}"}
        self.learning_system = learning_system
    
    def _is_valid_coordinates(self, lat, lng):
        """좌표가 한국 영토 내에 있는지 검증"""
        return MIN_LAT <= lat <= MAX_LAT and MIN_LNG <= lng <= MAX_LNG
    
    def _normalize_address(self, address):
        """주소 정규화 (다양한 패턴 지원)"""
        address = str(address).strip()
        
        # 1. 기본 정규화
        address = re.sub(r'\s+', ' ', address)  # 다중 공백 제거
        address = re.sub(r'[^\w\s가-힣]', ' ', address)  # 특수문자 제거
        
        # 2. 행정구역 축약어 확장
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
        
        # 3. 동/읍/면 정규화
        address = re.sub(r'(\d+)-(\d+)', r'\1-\2', address)  # 번지 정규화
        address = re.sub(r'(\d+)번지', r'\1', address)  # "번지" 제거
        
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
                        else:
                            return None, None, "좌표 범위 초과"
                    
                    # road_address 시도
                    if 'road_address' in doc and doc['road_address']:
                        lat = float(doc['road_address']['y'])
                        lng = float(doc['road_address']['x'])
                        
                        if self._is_valid_coordinates(lat, lng):
                            return lat, lng, "성공"
            
            return None, None, f"주소 API 실패 (HTTP {response.status_code})"
            
        except Exception as e:
            return None, None, f"주소 API 오류: {str(e)}"
    
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
                        return lat, lng, "성공"
                    else:
                        return None, None, "좌표 범위 초과"
            
            return None, None, f"키워드 API 실패 (HTTP {response.status_code})"
            
        except Exception as e:
            return None, None, f"키워드 API 오류: {str(e)}"
    
    def _generate_address_variants(self, address):
        """주소의 다양한 변형 생성"""
        variants = [address]
        
        # 1. 동/읍/면 변형
        if '동' in address:
            # "동"이 있으면 제거한 버전도 시도
            variants.append(re.sub(r'\s*동\s*', ' ', address).strip())
            
        # 2. 번지/호 변형  
        if re.search(r'\d+-\d+', address):
            # 상세 번지가 있으면 제거한 버전도 시도
            simplified = re.sub(r'-\d+', '', address)
            variants.append(simplified)
        
        # 3. 건물명 제거 시도
        if '(' in address and ')' in address:
            without_building = re.sub(r'\([^)]*\)', '', address).strip()
            variants.append(without_building)
        
        # 4. 층수/호수 제거
        floor_pattern = r'\s*\d+층.*'
        variants.append(re.sub(floor_pattern, '', address).strip())
        
        # 5. 마지막 숫자 제거 (상세 주소 제거)
        last_num_removed = re.sub(r'\s+\d+\s*$', '', address).strip()
        if last_num_removed != address:
            variants.append(last_num_removed)
        
        # 중복 제거
        return list(dict.fromkeys(variant for variant in variants if variant.strip()))
    
    def convert_address(self, address):
        """
        다중 전략 주소 변환 (성공률 80% 이상 목표)
        Returns: (위도, 경도, 상태) 튜플
        """
        if not address or str(address).strip() == "":
            return (None, None, "빈 주소")
        
        original_address = str(address).strip()
        
        # AI 학습 시스템 전처리 적용
        if self.learning_system:
            processed_address = self.learning_system.preprocess_address(original_address)
        else:
            processed_address = self._normalize_address(original_address)
        
        # 전략 1: 원본 주소로 시도
        for attempt in range(MAX_RETRIES):
            try:
                # 주소 API 먼저 시도
                lat, lng, status = self._try_address_api(original_address)
                if status == "성공":
                    return (lat, lng, status)
                
                # 키워드 API 시도
                lat, lng, status = self._try_keyword_api(original_address)
                if status == "성공":
                    return (lat, lng, "성공")
                
                time.sleep(DELAY_BETWEEN_REQUESTS)
                
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    break
                time.sleep(DELAY_BETWEEN_REQUESTS)
        
        # 전략 2: 정규화된 주소로 시도
        if processed_address != original_address:
            for attempt in range(MAX_RETRIES):
                try:
                    lat, lng, status = self._try_address_api(processed_address)
                    if status == "성공":
                        return (lat, lng, "성공")
                    
                    lat, lng, status = self._try_keyword_api(processed_address)
                    if status == "성공":
                        return (lat, lng, "성공")
                    
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                    
                except Exception as e:
                    if attempt == MAX_RETRIES - 1:
                        break
                    time.sleep(DELAY_BETWEEN_REQUESTS)
        
        # 전략 3: 주소 변형들로 시도
        variants = self._generate_address_variants(processed_address)
        for variant in variants[:5]:  # 최대 5개 변형만 시도
            try:
                lat, lng, status = self._try_address_api(variant)
                if status == "성공":
                    return (lat, lng, "성공")
                
                lat, lng, status = self._try_keyword_api(variant)
                if status == "성공":
                    return (lat, lng, "성공")
                
                time.sleep(DELAY_BETWEEN_REQUESTS / 2)  # 빠른 시도
                
            except Exception as e:
                continue
        
        return (None, None, "모든 변환 시도 실패")
    
    def convert_multiple_addresses(self, addresses, progress_callback=None):
        """
        여러 주소를 일괄 변환 (진행률 콜백 지원)
        """
        results = []
        total = len(addresses)
        
        for i, address in enumerate(addresses):
            lat, lng, status = self.convert_address(address)
            
            result = {
                '주소': address,
                '위도': lat,
                '경도': lng,
                '상태': status,
                '변환날짜': datetime.now().strftime('%Y-%m-%d'),
                '변환시간': datetime.now().strftime('%H:%M:%S')
            }
            results.append(result)
            
            # 진행률 콜백 호출
            if progress_callback:
                progress_callback(i + 1, total, result)
        
        return results 