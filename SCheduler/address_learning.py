import json
import os
import re
from datetime import datetime
from difflib import SequenceMatcher
from collections import defaultdict
import Levenshtein


class AddressLearningSystem:
    """사용자 수정 데이터를 학습하여 주소 변환 정확도를 향상시키는 시스템"""
    
    def __init__(self, learning_file="address_learning_data.json"):
        self.learning_file = learning_file
        self.learning_data = self._load_learning_data()
        self.patterns = self._extract_patterns()
    
    def _load_learning_data(self):
        """학습 데이터 로드"""
        if os.path.exists(self.learning_file):
            try:
                with open(self.learning_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"학습 데이터 로드 오류: {e}")
                return {"corrections": [], "patterns": {}}
        return {"corrections": [], "patterns": {}}
    
    def _save_learning_data(self):
        """학습 데이터 저장"""
        try:
            with open(self.learning_file, 'w', encoding='utf-8') as f:
                json.dump(self.learning_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"학습 데이터 저장 오류: {e}")
    
    def add_correction(self, original_address, corrected_address, lat, lng):
        """사용자 수정 데이터 추가"""
        correction = {
            "original": original_address,
            "corrected": corrected_address,
            "latitude": lat,
            "longitude": lng,
            "timestamp": datetime.now().isoformat(),
            "similarity": self._calculate_similarity(original_address, corrected_address)
        }
        
        self.learning_data["corrections"].append(correction)
        self._update_patterns(original_address, corrected_address)
        self._save_learning_data()
        
        print(f"학습 데이터 추가: {original_address} → {corrected_address}")
    
    def _calculate_similarity(self, str1, str2):
        """두 문자열 간 유사도 계산"""
        return SequenceMatcher(None, str1, str2).ratio()
    
    def _extract_patterns(self):
        """기존 학습 데이터에서 패턴 추출"""
        patterns = defaultdict(list)
        
        for correction in self.learning_data.get("corrections", []):
            original = correction["original"]
            corrected = correction["corrected"]
            
            # 공통 패턴 찾기
            common_words = self._find_common_patterns(original, corrected)
            for pattern in common_words:
                patterns[pattern].append({
                    "original": original,
                    "corrected": corrected,
                    "count": patterns[pattern].__len__() + 1
                })
        
        return dict(patterns)
    
    def _find_common_patterns(self, original, corrected):
        """두 주소에서 공통 패턴 찾기"""
        patterns = []
        
        # 단어 단위 비교
        orig_words = original.split()
        corr_words = corrected.split()
        
        # 공통 단어 찾기
        common_words = set(orig_words) & set(corr_words)
        patterns.extend(common_words)
        
        # 지역명 패턴 (시, 구, 동, 로, 길 등)
        location_patterns = re.findall(r'[가-힣]+(?:시|구|군|동|읍|면|리|로|길|가)', original)
        patterns.extend(location_patterns)
        
        return patterns
    
    def _update_patterns(self, original, corrected):
        """패턴 업데이트"""
        common_patterns = self._find_common_patterns(original, corrected)
        
        for pattern in common_patterns:
            if pattern not in self.learning_data["patterns"]:
                self.learning_data["patterns"][pattern] = []
            
            self.learning_data["patterns"][pattern].append({
                "original": original,
                "corrected": corrected,
                "timestamp": datetime.now().isoformat()
            })
    
    def preprocess_address(self, address):
        """학습된 패턴을 활용한 주소 전처리"""
        if not address:
            return address
        
        processed_address = address.strip()
        
        # 1. 기본 정제
        processed_address = self._basic_cleanup(processed_address)
        
        # 2. 학습된 패턴 적용
        processed_address = self._apply_learned_patterns(processed_address)
        
        # 3. 일반적인 주소 정규화
        processed_address = self._normalize_address(processed_address)
        
        return processed_address
    
    def _basic_cleanup(self, address):
        """기본 주소 정제"""
        # 불필요한 공백 제거
        address = re.sub(r'\s+', ' ', address)
        
        # 특수문자 정리
        address = re.sub(r'[^\w\s가-힣-]', ' ', address)
        
        # 괄호 내용 제거 (우편번호 등)
        address = re.sub(r'\([^)]*\)', '', address)
        
        return address.strip()
    
    def _apply_learned_patterns(self, address):
        """학습된 패턴 적용"""
        # 가장 유사한 수정 사례 찾기
        best_match = self._find_best_correction_match(address)
        
        if best_match and best_match["similarity"] > 0.7:
            # 유사한 패턴이 있으면 적용
            original_parts = best_match["original"].split()
            corrected_parts = best_match["corrected"].split()
            address_parts = address.split()
            
            # 단어별 교체 시도
            for i, part in enumerate(address_parts):
                if part in original_parts:
                    idx = original_parts.index(part)
                    if idx < len(corrected_parts):
                        address_parts[i] = corrected_parts[idx]
            
            return ' '.join(address_parts)
        
        return address
    
    def _normalize_address(self, address):
        """일반적인 주소 정규화"""
        # 축약어 확장
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
            if address.startswith(abbr + ' '):
                address = address.replace(abbr + ' ', full + ' ', 1)
        
        return address
    
    def _find_best_correction_match(self, address):
        """가장 유사한 수정 사례 찾기"""
        best_match = None
        best_similarity = 0
        
        for correction in self.learning_data.get("corrections", []):
            similarity = Levenshtein.ratio(address, correction["original"])
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = {
                    "original": correction["original"],
                    "corrected": correction["corrected"],
                    "similarity": similarity
                }
        
        return best_match
    
    def suggest_correction(self, failed_address):
        """실패한 주소에 대한 수정 제안"""
        suggestions = []
        
        # 1. 유사한 성공 사례 찾기
        for correction in self.learning_data.get("corrections", []):
            similarity = Levenshtein.ratio(failed_address, correction["original"])
            if similarity > 0.6:
                suggestions.append({
                    "suggested": correction["corrected"],
                    "similarity": similarity,
                    "reason": f"유사한 주소 '{correction['original']}'의 수정 사례"
                })
        
        # 2. 패턴 기반 제안
        processed = self.preprocess_address(failed_address)
        if processed != failed_address:
            suggestions.append({
                "suggested": processed,
                "similarity": 0.8,
                "reason": "학습된 패턴 적용"
            })
        
        # 유사도 순으로 정렬
        suggestions.sort(key=lambda x: x["similarity"], reverse=True)
        
        return suggestions[:3]  # 상위 3개만 반환
    
    def get_learning_stats(self):
        """학습 통계 반환"""
        corrections_count = len(self.learning_data.get("corrections", []))
        patterns_count = len(self.learning_data.get("patterns", {}))
        
        return {
            "총_수정_사례": corrections_count,
            "학습된_패턴": patterns_count,
            "마지막_학습": self._get_last_learning_time()
        }
    
    def _get_last_learning_time(self):
        """마지막 학습 시간 반환"""
        corrections = self.learning_data.get("corrections", [])
        if corrections:
            return corrections[-1].get("timestamp", "알 수 없음")
        return "학습 데이터 없음" 