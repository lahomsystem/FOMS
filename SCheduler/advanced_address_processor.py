#!/usr/bin/env python3
"""
고급 AI 주소 처리기
복잡하고 부정확한 주소를 정확한 주소로 변환하는 고급 시스템
"""

import re
import difflib
from typing import List, Dict, Tuple, Optional


class AdvancedAddressProcessor:
    """고급 주소 처리 및 교정 시스템"""
    
    def __init__(self):
        """고급 처리기 초기화"""
        self.city_mapping = self._build_city_mapping()
        self.district_mapping = self._build_district_mapping()
        self.building_patterns = self._build_building_patterns()
        self.common_mistakes = self._build_common_mistakes()
    
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
        """시/군/구 매핑 테이블 구축"""
        return {
            '성남': ['성남시', '경기도 성남시'],
            '수원': ['수원시', '경기도 수원시'],
            '용인': ['용인시', '경기도 용인시'],
            '화성': ['화성시', '경기도 화성시'],
            '안양': ['안양시', '경기도 안양시'],
            '평택': ['평택시', '경기도 평택시'],
            '시흥': ['시흥시', '경기도 시흥시'],
            '김포': ['김포시', '경기도 김포시'],
            '광명': ['광명시', '경기도 광명시'],
            '파주': ['파주시', '경기도 파주시'],
            
            # 자주 혼동되는 지역명
            '서원': ['서원구', '충청북도 청주시 서원구'],
            '청산': ['청산구', '충청남도 천안시'],
            '영통': ['영통구', '경기도 수원시 영통구'],
            '분당': ['분당구', '경기도 성남시 분당구'],
            '수지': ['수지구', '경기도 용인시 수지구'],
            '기흥': ['기흥구', '경기도 용인시 기흥구'],
            '처인': ['처인구', '경기도 용인시 처인구']
        }
    
    def _build_building_patterns(self) -> List[Dict]:
        """건물/아파트 패턴 정의"""
        return [
            # 아파트 단지
            {'pattern': r'(\w+)\s*파크\s*(\d+단지)?', 'type': 'apartment'},
            {'pattern': r'(\w+)\s*헤리티지', 'type': 'apartment'},
            {'pattern': r'(\w+)\s*빌\s*(\d+-\d+)?', 'type': 'apartment'}, 
            {'pattern': r'(\w+)\s*타워', 'type': 'apartment'},
            {'pattern': r'(\w+)\s*캐슬', 'type': 'apartment'},
            {'pattern': r'(\w+)\s*팰리스', 'type': 'apartment'},
            {'pattern': r'(\w+)\s*그랜드', 'type': 'apartment'},
            
            # 공공주택
            {'pattern': r'(\w+)\s*주공\s*(\d+단지)?', 'type': 'public_housing'},
            {'pattern': r'(\w+)\s*공원\s*(\w+)', 'type': 'public_housing'},
            
            # 상세 주소
            {'pattern': r'(\d+)-(\d+)', 'type': 'address_number'},
            {'pattern': r'(\d+)층', 'type': 'floor'},
            {'pattern': r'(\d+)호', 'type': 'room'}
        ]
    
    def _build_common_mistakes(self) -> Dict[str, str]:
        """흔한 오타 및 변형 매핑"""
        return {
            '한도': '한솔동',
            '와동마을': '와동',
            '매드리안': '메르디앙',
            '힐튼': '힐스테이트',
            '사이더': '시티',
            '유앤빌': 'U&VILLE',
            '새이김': '새김',
            '대컴로': '대학로',
        }
    
    def analyze_address_components(self, address: str) -> Dict[str, any]:
        """주소 구성요소 분석"""
        components = {
            'original': address,
            'city': None,
            'district': None,
            'dong': None,
            'building': None,
            'detail': None,
            'issues': []
        }
        
        # 1. 시/도 추출
        for abbr, full in self.city_mapping.items():
            if address.startswith(abbr):
                components['city'] = full
                address = address[len(abbr):].strip()
                break
        
        if not components['city']:
            components['issues'].append('시/도명 누락')
        
        # 2. 구/시 추출
        for abbr, options in self.district_mapping.items():
            if abbr in address:
                components['district'] = options[0]  # 첫 번째 옵션 사용
                break
        
        if not components['district']:
            components['issues'].append('구/시명 불명확')
        
        # 3. 건물/아파트 패턴 분석
        for pattern_info in self.building_patterns:
            matches = re.findall(pattern_info['pattern'], address)
            if matches:
                components['building'] = {
                    'type': pattern_info['type'],
                    'matches': matches
                }
                break
        
        # 4. 동 추출
        dong_match = re.search(r'(\w+동)', address)
        if dong_match:
            components['dong'] = dong_match.group(1)
        
        # 5. 상세 주소 추출
        detail_match = re.search(r'(\d+-\d+)', address)
        if detail_match:
            components['detail'] = detail_match.group(1)
        
        return components
    
    def generate_smart_suggestions(self, address: str) -> List[Dict[str, any]]:
        """스마트 주소 제안 생성"""
        suggestions = []
        components = self.analyze_address_components(address)
        
        # 제안 1: 행정구역 교정
        if components['city'] and components['district']:
            corrected = f"{components['city']} {components['district']}"
            if components['dong']:
                corrected += f" {components['dong']}"
            if components['detail']:
                corrected += f" {components['detail']}"
                
            suggestions.append({
                'address': corrected,
                'confidence': 0.8,
                'reason': '행정구역 교정',
                'changes': ['시/도명 확장', '구/시명 교정']
            })
        
        # 제안 2: 건물명 제거
        if components['building']:
            simplified = address
            for pattern_info in self.building_patterns:
                simplified = re.sub(pattern_info['pattern'], '', simplified)
            simplified = re.sub(r'\s+', ' ', simplified).strip()
            
            if simplified != address:
                suggestions.append({
                    'address': simplified,
                    'confidence': 0.7,
                    'reason': '건물명 제거 단순화',
                    'changes': ['아파트/건물명 제거']
                })
        
        # 제안 3: 오타 교정
        corrected_address = address
        changes = []
        for mistake, correction in self.common_mistakes.items():
            if mistake in corrected_address:
                corrected_address = corrected_address.replace(mistake, correction)
                changes.append(f'{mistake}→{correction}')
        
        if changes:
            suggestions.append({
                'address': corrected_address,
                'confidence': 0.6,
                'reason': '오타 교정',
                'changes': changes
            })
        
        # 제안 4: 상세 주소 제거
        if components['detail']:
            without_detail = re.sub(r'\d+-\d+.*', '', address).strip()
            suggestions.append({
                'address': without_detail,
                'confidence': 0.5,
                'reason': '상세 주소 제거',
                'changes': ['호수/상세번지 제거']
            })
        
        # 중복 제거 및 정렬
        unique_suggestions = []
        seen_addresses = set()
        
        for suggestion in suggestions:
            addr = suggestion['address']
            if addr not in seen_addresses and addr.strip() != address.strip():
                seen_addresses.add(addr)
                unique_suggestions.append(suggestion)
        
        # 신뢰도 순으로 정렬
        unique_suggestions.sort(key=lambda x: x['confidence'], reverse=True)
        
        return unique_suggestions[:5]  # 최대 5개
    
    def find_similar_addresses(self, address: str, known_addresses: List[str]) -> List[Dict[str, any]]:
        """유사한 주소 찾기 (기존 성공 사례 기반)"""
        similar = []
        
        for known in known_addresses:
            similarity = difflib.SequenceMatcher(None, address.lower(), known.lower()).ratio()
            
            if similarity > 0.6:  # 60% 이상 유사
                similar.append({
                    'address': known,
                    'confidence': similarity,
                    'reason': f'유사 주소 ({similarity:.1%} 일치)',
                    'changes': ['기존 성공 사례 기반']
                })
        
        return sorted(similar, key=lambda x: x['confidence'], reverse=True)[:3]
    
    def process_failed_address(self, address: str, known_addresses: List[str] = None) -> Dict[str, any]:
        """실패한 주소 종합 처리"""
        known_addresses = known_addresses or []
        
        # 구성요소 분석
        components = self.analyze_address_components(address)
        
        # 스마트 제안 생성
        smart_suggestions = self.generate_smart_suggestions(address)
        
        # 유사 주소 찾기
        similar_suggestions = self.find_similar_addresses(address, known_addresses)
        
        # 모든 제안 통합
        all_suggestions = smart_suggestions + similar_suggestions
        
        # 중복 제거 및 최종 정렬
        final_suggestions = []
        seen = set()
        
        for suggestion in all_suggestions:
            addr = suggestion['address']
            if addr not in seen:
                seen.add(addr)
                final_suggestions.append(suggestion)
        
        return {
            'original_address': address,
            'components': components,
            'suggestions': sorted(final_suggestions, key=lambda x: x['confidence'], reverse=True)[:5],
            'analysis': {
                'issues_found': len(components['issues']),
                'suggestions_generated': len(final_suggestions),
                'processing_strategy': 'advanced_ai_analysis'
            }
        } 