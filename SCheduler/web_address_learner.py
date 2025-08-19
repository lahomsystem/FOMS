import requests
import re
import json
import time
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import quote
import logging


class WebAddressLearner:
    """인터넷에서 주소 패턴을 학습하는 클래스"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.learned_patterns = []
        self.location_database = {}
        
    def learn_from_web(self, failed_addresses):
        """실패한 주소들을 웹에서 학습"""
        learned_info = []
        
        for address in failed_addresses:
            try:
                # 1. 네이버 지도에서 검색
                naver_result = self._search_naver_map(address)
                
                # 2. 다음 지도에서 검색
                daum_result = self._search_daum_map(address)
                
                # 3. 구글에서 일반 검색
                google_result = self._search_google(address)
                
                # 결과 통합 및 분석
                combined_result = self._combine_results(address, naver_result, daum_result, google_result)
                
                if combined_result:
                    learned_info.append(combined_result)
                
                # API 요청 간격 조절
                time.sleep(1)
                
            except Exception as e:
                logging.error(f"웹 학습 오류 - {address}: {e}")
                continue
        
        return learned_info
    
    def _search_naver_map(self, address):
        """네이버 지도에서 주소 검색"""
        try:
            # 네이버 지도 API 또는 웹 검색
            search_url = f"https://map.naver.com/v5/search/{quote(address)}"
            
            # 실제 구현에서는 네이버 개발자 API 사용 권장
            # 여기서는 기본 패턴 분석만 수행
            
            patterns = self._extract_address_patterns(address)
            return {
                "source": "naver",
                "patterns": patterns,
                "suggestions": self._generate_suggestions(address, patterns)
            }
            
        except Exception as e:
            logging.error(f"네이버 지도 검색 오류: {e}")
            return None
    
    def _search_daum_map(self, address):
        """다음 지도에서 주소 검색"""
        try:
            # 카카오맵 API와 연동 가능
            patterns = self._extract_address_patterns(address)
            
            return {
                "source": "daum",
                "patterns": patterns,
                "suggestions": self._generate_suggestions(address, patterns)
            }
            
        except Exception as e:
            logging.error(f"다음 지도 검색 오류: {e}")
            return None
    
    def _search_google(self, address):
        """구글에서 일반 검색"""
        try:
            # 구글 검색을 통한 주소 정보 수집
            search_query = f"{address} 주소 위치"
            
            # 실제 구현에서는 Google Custom Search API 사용 권장
            patterns = self._extract_address_patterns(address)
            
            return {
                "source": "google",
                "patterns": patterns,
                "suggestions": self._generate_suggestions(address, patterns)
            }
            
        except Exception as e:
            logging.error(f"구글 검색 오류: {e}")
            return None
    
    def _extract_address_patterns(self, address):
        """주소에서 패턴 추출"""
        patterns = {
            "지역명": [],
            "도로명": [],
            "건물명": [],
            "번지": [],
            "행정구역": []
        }
        
        # 정규식을 사용한 패턴 추출
        
        # 시/도 패턴
        sido_pattern = r'([가-힣]+(?:특별시|광역시|특별자치시|도|특별자치도))'
        sido_matches = re.findall(sido_pattern, address)
        patterns["행정구역"].extend(sido_matches)
        
        # 구/군 패턴
        sigungu_pattern = r'([가-힣]+(?:구|군|시))'
        sigungu_matches = re.findall(sigungu_pattern, address)
        patterns["행정구역"].extend(sigungu_matches)
        
        # 동/읍/면 패턴
        dong_pattern = r'([가-힣]+(?:동|읍|면|리))'
        dong_matches = re.findall(dong_pattern, address)
        patterns["지역명"].extend(dong_matches)
        
        # 도로명 패턴
        road_pattern = r'([가-힣0-9]+(?:로|길|대로))'
        road_matches = re.findall(road_pattern, address)
        patterns["도로명"].extend(road_matches)
        
        # 번지 패턴
        number_pattern = r'(\d+(?:-\d+)?(?:번지|번|호)?)'
        number_matches = re.findall(number_pattern, address)
        patterns["번지"].extend(number_matches)
        
        # 건물명 패턴 (한글 + 영문)
        building_pattern = r'([가-힣A-Za-z]+(?:빌딩|타워|센터|아파트|맨션|오피스텔|상가|마트|병원|학교|공원))'
        building_matches = re.findall(building_pattern, address)
        patterns["건물명"].extend(building_matches)
        
        return patterns
    
    def _generate_suggestions(self, original_address, patterns):
        """패턴을 기반으로 주소 제안 생성"""
        suggestions = []
        
        # 1. 완전한 행정구역명 추가
        full_address = original_address
        
        # 시/도 축약어 확장
        replacements = {
            '서울': '서울특별시',
            '부산': '부산광역시',
            '대구': '대구광역시',
            '인천': '인천광역시',
            '광주': '광주광역시',
            '대전': '대전광역시',
            '울산': '울산광역시',
            '세종': '세종특별자치시',
            '경기': '경기도',
            '강원': '강원도',
            '충북': '충청북도',
            '충남': '충청남도',
            '전북': '전라북도',
            '전남': '전라남도',
            '경북': '경상북도',
            '경남': '경상남도',
            '제주': '제주특별자치도'
        }
        
        for abbr, full in replacements.items():
            if original_address.startswith(abbr):
                suggested = original_address.replace(abbr, full, 1)
                suggestions.append({
                    "address": suggested,
                    "confidence": 0.8,
                    "reason": "시/도명 확장"
                })
        
        # 2. 도로명주소 변환 제안
        if patterns["지역명"] and patterns["번지"]:
            # 지번주소를 도로명주소로 변환 제안
            for dong in patterns["지역명"]:
                for road in patterns["도로명"]:
                    suggested = f"{' '.join(patterns['행정구역'])} {dong} {road}"
                    suggestions.append({
                        "address": suggested,
                        "confidence": 0.6,
                        "reason": "도로명주소 변환"
                    })
        
        # 3. 띄어쓰기 정규화
        normalized = re.sub(r'\s+', ' ', original_address).strip()
        if normalized != original_address:
            suggestions.append({
                "address": normalized,
                "confidence": 0.9,
                "reason": "띄어쓰기 정규화"
            })
        
        return suggestions
    
    def _combine_results(self, original_address, naver_result, daum_result, google_result):
        """여러 소스의 결과를 통합"""
        all_suggestions = []
        
        # 각 소스의 제안사항 수집
        for result in [naver_result, daum_result, google_result]:
            if result and "suggestions" in result:
                all_suggestions.extend(result["suggestions"])
        
        # 중복 제거 및 신뢰도 순 정렬
        unique_suggestions = {}
        for suggestion in all_suggestions:
            addr = suggestion["address"]
            if addr not in unique_suggestions or suggestion["confidence"] > unique_suggestions[addr]["confidence"]:
                unique_suggestions[addr] = suggestion
        
        # 신뢰도 순으로 정렬
        sorted_suggestions = sorted(unique_suggestions.values(), key=lambda x: x["confidence"], reverse=True)
        
        return {
            "original": original_address,
            "suggestions": sorted_suggestions[:5],  # 상위 5개만
            "learned_at": datetime.now().isoformat()
        }
    
    def enhance_address_with_context(self, address):
        """맥락 정보를 활용한 주소 향상"""
        enhanced = address
        
        # 1. 유명 랜드마크 인식
        landmarks = {
            "롯데타워": "서울특별시 송파구 올림픽로 300",
            "63빌딩": "서울특별시 영등포구 여의도동 60",
            "부산역": "부산광역시 동구 중앙대로 206",
            "김포공항": "서울특별시 강서구 하늘길 112",
            "인천공항": "인천광역시 중구 공항로 272",
            "여의도": "서울특별시 영등포구 여의도동",
            "강남역": "서울특별시 강남구 강남대로 390"
        }
        
        for landmark, full_address in landmarks.items():
            if landmark in address:
                return {
                    "enhanced_address": full_address,
                    "confidence": 0.9,
                    "method": "랜드마크 인식"
                }
        
        # 2. 지하철역 정보 활용
        subway_pattern = r'([가-힣]+역)'
        subway_matches = re.findall(subway_pattern, address)
        
        if subway_matches:
            station = subway_matches[0]
            # 실제로는 지하철역 DB에서 조회
            return {
                "enhanced_address": f"{address} (지하철 {station} 인근)",
                "confidence": 0.7,
                "method": "지하철역 정보 활용"
            }
        
        return None
    
    def get_learning_summary(self):
        """웹 학습 요약 정보"""
        return {
            "총_학습된_패턴": len(self.learned_patterns),
            "위치_데이터베이스_크기": len(self.location_database),
            "마지막_학습_시간": datetime.now().isoformat()
        } 