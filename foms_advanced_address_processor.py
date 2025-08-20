#!/usr/bin/env python3
"""
FOMS용 고급 AI 주소 처리기
복잡하고 부정확한 주소를 정확한 주소로 변환하는 고급 시스템
"""

import re
import difflib
from typing import List, Dict, Tuple, Optional


class FOMSAdvancedAddressProcessor:
    """FOMS용 고급 주소 처리 및 교정 시스템"""
    
    def __init__(self):
        """고급 처리기 초기화"""
        self.city_mapping = self._build_city_mapping()
        self.district_mapping = self._build_district_mapping()
        self.building_patterns = self._build_building_patterns()
        self.common_mistakes = self._build_common_mistakes()
        self.furniture_related_terms = self._build_furniture_terms()
    
    def _build_city_mapping(self) -> Dict[str, str]:
        """시/도 매핑 테이블 구축"""
        return {
            # 서울
            '서울': '서울특별시',
            '서울시': '서울특별시',
            
            # 광역시
            '부산': '부산광역시',
            '대구': '대구광역시', 
            '인천': '인천광역시',
            '광주': '광주광역시',
            '대전': '대전광역시',
            '울산': '울산광역시',
            '세종': '세종특별자치시',
            
            # 도
            '경기': '경기도',
            '강원': '강원특별자치도',
            '충북': '충청북도',
            '충남': '충청남도',
            '전북': '전북특별자치도',
            '전남': '전라남도',
            '경북': '경상북도',
            '경남': '경상남도',
            '제주': '제주특별자치도'
        }
    
    def _build_district_mapping(self) -> Dict[str, List[str]]:
        """구/군 매핑 테이블 구축"""
        return {
            '서울특별시': [
                '강남구', '강동구', '강북구', '강서구', '관악구', '광진구', '구로구', '금천구',
                '노원구', '도봉구', '동대문구', '동작구', '마포구', '서대문구', '서초구', '성동구',
                '성북구', '송파구', '양천구', '영등포구', '용산구', '은평구', '종로구', '중구', '중랑구'
            ],
            '부산광역시': [
                '강서구', '금정구', '기장군', '남구', '동구', '동래구', '부산진구', '북구',
                '사상구', '사하구', '서구', '수영구', '연제구', '영도구', '중구', '해운대구'
            ],
            '인천광역시': [
                '강화군', '계양구', '미추홀구', '남동구', '동구', '부평구', '서구', '연수구', '옹진군', '중구'
            ],
            '경기도': [
                '가평군', '고양시', '과천시', '광명시', '광주시', '구리시', '군포시', '김포시',
                '남양주시', '동두천시', '부천시', '성남시', '수원시', '시흥시', '안산시', '안성시',
                '안양시', '양주시', '양평군', '여주시', '연천군', '오산시', '용인시', '의왕시',
                '의정부시', '이천시', '파주시', '평택시', '포천시', '하남시', '화성시'
            ]
        }
    
    def _build_building_patterns(self) -> List[Dict]:
        """건물 패턴 정의"""
        return [
            {'pattern': r'(\d+)-(\d+)', 'type': 'lot_number'},
            {'pattern': r'(\d+)동\s*(\d+)호', 'type': 'apartment'},
            {'pattern': r'(\d+)단지', 'type': 'complex'},
            {'pattern': r'(\w+)아파트', 'type': 'apartment_name'},
            {'pattern': r'(\w+)빌딩', 'type': 'building_name'},
            {'pattern': r'(\w+)타워', 'type': 'tower_name'},
            {'pattern': r'(\d+)층', 'type': 'floor'},
            {'pattern': r'(\w+)마을', 'type': 'village'},
            {'pattern': r'(\w+)주공', 'type': 'public_housing'},
        ]
    
    def _build_common_mistakes(self) -> Dict[str, str]:
        """흔한 오타 및 잘못된 표기 수정"""
        return {
            # 자주 틀리는 구 이름
            '강남': '강남구',
            '강서': '강서구',
            '송파': '송파구',
            '서초': '서초구',
            
            # 동 이름 수정
            '역삼': '역삼동',
            '신사': '신사동',
            '청담': '청담동',
            '압구정': '압구정동',
            
            # 로/길 구분
            '대로': '대로',
            '로': '로',
            '길': '길',
            
            # 번지 표기
            '번지': '',
            '번': '',
        }
    
    def _build_furniture_terms(self) -> List[str]:
        """가구 관련 용어들 (주소에서 제거해야 할)"""
        return [
            '가구', '침대', '소파', '테이블', '의자', '수납장', '장롱', '책상',
            '서랍장', '옷장', '붙박이장', '시스템가구', '주문제작', '맞춤가구',
            '원목', '합판', '도어', '서랍', '손잡이', '하드웨어'
        ]
    
    def process_address(self, raw_address: str) -> str:
        """주소 종합 처리"""
        if not raw_address or not isinstance(raw_address, str):
            return ""
        
        # 1단계: 기본 정리
        cleaned = self._basic_cleanup(raw_address)
        
        # 2단계: 가구 관련 용어 제거
        cleaned = self._remove_furniture_terms(cleaned)
        
        # 3단계: 시/도 정규화
        cleaned = self._normalize_city(cleaned)
        
        # 4단계: 구/군/동 정규화
        cleaned = self._normalize_district(cleaned)
        
        # 5단계: 건물 정보 정리
        cleaned = self._normalize_building_info(cleaned)
        
        # 6단계: 번지 정리
        cleaned = self._normalize_lot_numbers(cleaned)
        
        # 7단계: 최종 정리
        cleaned = self._final_cleanup(cleaned)
        
        return cleaned
    
    def _basic_cleanup(self, address: str) -> str:
        """기본 정리"""
        # 양쪽 공백 제거
        address = address.strip()
        
        # 특수문자 정리 (하이픈, 슬래시 등은 유지)
        address = re.sub(r'[^\w\s가-힣\-/()]', ' ', address)
        
        # 다중 공백을 단일 공백으로
        address = re.sub(r'\s+', ' ', address)
        
        # 괄호 안의 내용 처리 (상세 주소 정보가 아닌 경우)
        address = re.sub(r'\([^)]*tel[^)]*\)', '', address, flags=re.IGNORECASE)
        address = re.sub(r'\([^)]*전화[^)]*\)', '', address)
        address = re.sub(r'\([^)]*연락[^)]*\)', '', address)
        
        return address.strip()
    
    def _remove_furniture_terms(self, address: str) -> str:
        """가구 관련 용어 제거"""
        for term in self.furniture_related_terms:
            # 단어 경계를 고려해서 제거
            pattern = r'\b' + re.escape(term) + r'\b'
            address = re.sub(pattern, '', address, flags=re.IGNORECASE)
        
        return re.sub(r'\s+', ' ', address).strip()
    
    def _normalize_city(self, address: str) -> str:
        """시/도 정규화"""
        for short_name, full_name in self.city_mapping.items():
            # 시작 부분에 있는 경우만 교체
            if address.startswith(short_name + ' ') or address.startswith(short_name):
                if not address.startswith(full_name):
                    address = address.replace(short_name, full_name, 1)
                break
        
        return address
    
    def _normalize_district(self, address: str) -> str:
        """구/군/동 정규화"""
        # 구 이름 보완
        for mistake, correction in self.common_mistakes.items():
            if mistake in address and correction not in address:
                address = address.replace(mistake, correction)
        
        # 동 이름 처리
        address = re.sub(r'(\w+)동(?!\d)', r'\1동', address)
        
        return address
    
    def _normalize_building_info(self, address: str) -> str:
        """건물 정보 정리"""
        # 아파트 동호수 정리
        address = re.sub(r'(\d+)동\s*(\d+)호', r'\1동 \2호', address)
        
        # 단지 정보 정리
        address = re.sub(r'(\d+)\s*단지', r'\1단지', address)
        
        # 층 정보 처리 (주소에서는 보통 제거)
        address = re.sub(r'\d+층\s*', '', address)
        
        return address
    
    def _normalize_lot_numbers(self, address: str) -> str:
        """번지 정리"""
        # 번지 표기 정리
        address = re.sub(r'(\d+)\s*[-]\s*(\d+)', r'\1-\2', address)
        address = re.sub(r'(\d+)\s*번지', r'\1', address)
        address = re.sub(r'(\d+)\s*번(?!\w)', r'\1', address)
        
        return address
    
    def _final_cleanup(self, address: str) -> str:
        """최종 정리"""
        # 연속된 공백 제거
        address = re.sub(r'\s+', ' ', address)
        
        # 앞뒤 공백 제거
        address = address.strip()
        
        # 마지막에 불필요한 문자 제거
        address = re.sub(r'[,\s]+$', '', address)
        
        return address
    
    def suggest_corrections(self, address: str) -> List[str]:
        """주소 교정 제안"""
        suggestions = []
        
        # 원본 처리 결과
        processed = self.process_address(address)
        if processed != address:
            suggestions.append(processed)
        
        # 유사한 지명 찾기
        similar_places = self._find_similar_places(address)
        suggestions.extend(similar_places)
        
        # 중복 제거
        return list(set(suggestions))
    
    def _find_similar_places(self, address: str) -> List[str]:
        """유사한 지명 찾기"""
        suggestions = []
        
        # 모든 알려진 구/군과 비교
        for city, districts in self.district_mapping.items():
            for district in districts:
                # 부분 문자열이 포함된 경우
                if any(part in district for part in address.split() if len(part) > 1):
                    suggestions.append(f"{city} {district}")
        
        return suggestions[:5]  # 최대 5개만 반환
    
    def extract_address_components(self, address: str) -> Dict[str, Optional[str]]:
        """주소 구성 요소 추출"""
        processed = self.process_address(address)
        
        components = {
            'city': None,
            'district': None,
            'dong': None,
            'road': None,
            'building_number': None,
            'building_name': None,
            'apartment_info': None
        }
        
        # 시/도 추출
        for full_name in self.city_mapping.values():
            if full_name in processed:
                components['city'] = full_name
                break
        
        # 구/군 추출
        if components['city'] and components['city'] in self.district_mapping:
            for district in self.district_mapping[components['city']]:
                if district in processed:
                    components['district'] = district
                    break
        
        # 동 추출
        dong_match = re.search(r'(\w+동)', processed)
        if dong_match:
            components['dong'] = dong_match.group(1)
        
        # 도로명 추출
        road_match = re.search(r'(\w+(?:대로|로|길))', processed)
        if road_match:
            components['road'] = road_match.group(1)
        
        # 건물 번호 추출
        number_match = re.search(r'(\d+-?\d*)', processed)
        if number_match:
            components['building_number'] = number_match.group(1)
        
        # 아파트 정보 추출
        apt_match = re.search(r'(\d+동\s*\d+호)', processed)
        if apt_match:
            components['apartment_info'] = apt_match.group(1)
        
        return components
    
    def validate_address_structure(self, address: str) -> Dict[str, any]:
        """주소 구조 유효성 검사"""
        components = self.extract_address_components(address)
        
        validation = {
            'is_valid': True,
            'score': 0,
            'issues': [],
            'suggestions': []
        }
        
        # 필수 구성 요소 체크
        if not components['city']:
            validation['is_valid'] = False
            validation['issues'].append('시/도 정보 누락')
        else:
            validation['score'] += 20
        
        if not components['district']:
            validation['issues'].append('구/군 정보 누락')
        else:
            validation['score'] += 20
        
        if not components['dong'] and not components['road']:
            validation['issues'].append('동 또는 도로명 정보 누락')
        else:
            validation['score'] += 20
        
        if not components['building_number']:
            validation['issues'].append('건물 번호 정보 누락')
        else:
            validation['score'] += 20
        
        # 구조적 완성도 평가
        if validation['score'] >= 60:
            validation['is_valid'] = True
        
        return validation
