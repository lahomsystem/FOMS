import json
import os
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from collections import defaultdict
try:
    import Levenshtein
except ImportError:
    # Levenshtein이 없으면 기본 difflib 사용
    Levenshtein = None


class FOMSAddressLearningSystem:
    """FOMS 시스템용 주소 학습 시스템"""
    
    def __init__(self, learning_file="foms_address_learning_data.json"):
        self.learning_file = learning_file
        self.learning_data = self._load_learning_data()
        self._clean_patterns()  # 기존 데이터 정리
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
    
    def _clean_patterns(self):
        """기존 패턴 데이터 정리"""
        try:
            patterns = self.learning_data.get("patterns", {})
            cleaned_patterns = {}
            
            for word, replacements in patterns.items():
                if isinstance(replacements, list):
                    # 올바른 형식의 replacement만 유지
                    cleaned_replacements = []
                    for replacement in replacements:
                        if isinstance(replacement, dict) and "replacement" in replacement:
                            cleaned_replacements.append(replacement)
                        elif isinstance(replacement, str):
                            # 문자열인 경우 dict 형태로 변환
                            cleaned_replacements.append({
                                "replacement": replacement,
                                "confidence": 0.8,
                                "count": 1
                            })
                    
                    if cleaned_replacements:
                        cleaned_patterns[word] = cleaned_replacements
                elif isinstance(replacements, str):
                    # 문자열인 경우 리스트로 변환
                    cleaned_patterns[word] = [{
                        "replacement": replacements,
                        "confidence": 0.8,
                        "count": 1
                    }]
            
            self.learning_data["patterns"] = cleaned_patterns
            
        except Exception as e:
            print(f"패턴 정리 오류: {e}")
            # 오류 발생 시 패턴 초기화
            self.learning_data["patterns"] = {}
    
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
        print(f"학습 데이터 추가: {original_address} -> {corrected_address}")
    
    def _calculate_similarity(self, addr1, addr2):
        """두 주소 간의 유사도 계산"""
        if Levenshtein:
            return 1 - (Levenshtein.distance(addr1, addr2) / max(len(addr1), len(addr2)))
        else:
            return SequenceMatcher(None, addr1, addr2).ratio()
    
    def _update_patterns(self, original, corrected):
        """패턴 업데이트"""
        # 간단한 패턴 추출
        original_words = re.findall(r'\w+', original)
        corrected_words = re.findall(r'\w+', corrected)
        
        for orig_word in original_words:
            for corr_word in corrected_words:
                if orig_word != corr_word and len(orig_word) > 1 and len(corr_word) > 1:
                    similarity = self._calculate_similarity(orig_word, corr_word)
                    if similarity > 0.7:  # 유사한 단어들만 패턴으로 저장
                        if orig_word not in self.learning_data["patterns"]:
                            self.learning_data["patterns"][orig_word] = []
                        
                        # 기존 replacement가 있는지 확인
                        existing_replacement = None
                        for replacement in self.learning_data["patterns"][orig_word]:
                            if isinstance(replacement, dict) and replacement.get("replacement") == corr_word:
                                existing_replacement = replacement
                                break
                        
                        if existing_replacement:
                            # 기존 항목의 count 증가
                            existing_replacement["count"] = existing_replacement.get("count", 0) + 1
                            existing_replacement["confidence"] = max(existing_replacement.get("confidence", 0), similarity)
                        else:
                            # 새 항목 추가
                            self.learning_data["patterns"][orig_word].append({
                                "replacement": corr_word,
                                "confidence": similarity,
                                "count": 1
                            })
    
    def _extract_patterns(self):
        """저장된 데이터에서 패턴 추출"""
        patterns = {}
        
        for correction in self.learning_data.get("corrections", []):
            original = correction["original"]
            corrected = correction["corrected"]
            
            # 도시/구 패턴 추출
            city_pattern = self._extract_city_pattern(original, corrected)
            if city_pattern:
                patterns.update(city_pattern)
        
        return patterns
    
    def _extract_city_pattern(self, original, corrected):
        """도시/구 패턴 추출"""
        patterns = {}
        
        # 시/도 패턴
        city_regex = r'(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)'
        
        orig_cities = re.findall(city_regex, original)
        corr_cities = re.findall(city_regex, corrected)
        
        if orig_cities and corr_cities and orig_cities[0] != corr_cities[0]:
            patterns[orig_cities[0]] = corr_cities[0]
        
        return patterns
    
    def suggest_correction(self, address):
        """주소에 대한 수정 제안"""
        try:
            # 완전 일치 검색
            corrections = self.learning_data.get("corrections", [])
            for correction in corrections:
                if isinstance(correction, dict) and correction.get("original") == address:
                    return {
                        "suggested_address": correction.get("corrected", ""),
                        "latitude": correction.get("latitude"),
                        "longitude": correction.get("longitude"),
                        "confidence": 1.0,
                        "source": "exact_match"
                    }
            
            # 유사도 기반 검색
            best_match = None
            best_similarity = 0.0
            
            for correction in corrections:
                if isinstance(correction, dict) and "original" in correction:
                    try:
                        similarity = self._calculate_similarity(address, correction["original"])
                        if similarity > 0.8 and similarity > best_similarity:
                            best_similarity = similarity
                            best_match = correction
                    except Exception:
                        continue
            
            if best_match:
                return {
                    "suggested_address": best_match.get("corrected", ""),
                    "latitude": best_match.get("latitude"),
                    "longitude": best_match.get("longitude"),
                    "confidence": best_similarity,
                    "source": "similarity_match"
                }
            
            # 패턴 기반 수정
            try:
                corrected_address = self._apply_patterns(address)
                if corrected_address != address:
                    return {
                        "suggested_address": corrected_address,
                        "latitude": None,
                        "longitude": None,
                        "confidence": 0.7,
                        "source": "pattern_match"
                    }
            except Exception:
                pass
            
            return None
            
        except Exception as e:
            print(f"제안 생성 오류: {e}")
            return None
    
    def _apply_patterns(self, address):
        """저장된 패턴을 주소에 적용"""
        try:
            corrected = address
            
            # 도시/구 패턴 적용
            if hasattr(self, 'patterns') and isinstance(self.patterns, dict):
                for pattern, replacement in self.patterns.items():
                    if isinstance(pattern, str) and isinstance(replacement, str):
                        if pattern in corrected:
                            corrected = corrected.replace(pattern, replacement)
            
            # 저장된 패턴 적용
            patterns_data = self.learning_data.get("patterns", {})
            if isinstance(patterns_data, dict):
                for word, replacements in patterns_data.items():
                    if not isinstance(word, str) or word not in corrected:
                        continue
                    
                    if isinstance(replacements, list) and replacements:
                        try:
                            # 유효한 replacement만 필터링
                            valid_replacements = [
                                r for r in replacements 
                                if isinstance(r, dict) and "replacement" in r and "confidence" in r
                            ]
                            
                            if valid_replacements:
                                best_replacement = max(valid_replacements, key=lambda x: x.get("confidence", 0))
                                replacement_text = best_replacement.get("replacement", "")
                                if isinstance(replacement_text, str):
                                    corrected = corrected.replace(word, replacement_text)
                        except Exception:
                            continue
            
            return corrected
            
        except Exception as e:
            print(f"패턴 적용 오류: {e}")
            return address
    
    def get_learning_statistics(self):
        """학습 통계 정보 반환"""
        corrections = self.learning_data.get("corrections", [])
        
        return {
            "total_corrections": len(corrections),
            "total_patterns": len(self.learning_data.get("patterns", {})),
            "last_updated": corrections[-1]["timestamp"] if corrections else None,
            "avg_similarity": sum(c.get("similarity", 0) for c in corrections) / len(corrections) if corrections else 0
        }
    
    def clear_old_data(self, days=30):
        """오래된 학습 데이터 정리"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        original_count = len(self.learning_data.get("corrections", []))
        
        self.learning_data["corrections"] = [
            correction for correction in self.learning_data.get("corrections", [])
            if datetime.fromisoformat(correction["timestamp"]) > cutoff_date
        ]
        
        new_count = len(self.learning_data["corrections"])
        
        if original_count != new_count:
            self._save_learning_data()
            print(f"오래된 데이터 {original_count - new_count}개 정리됨")
    
    def export_learning_data(self, filename=None):
        """학습 데이터 내보내기"""
        if filename is None:
            filename = f"foms_learning_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.learning_data, f, ensure_ascii=False, indent=2)
            return filename
        except Exception as e:
            print(f"데이터 내보내기 오류: {e}")
            return None
    
    def import_learning_data(self, filename):
        """외부 학습 데이터 가져오기"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                imported_data = json.load(f)
            
            # 기존 데이터와 병합
            existing_corrections = {
                c["original"]: c for c in self.learning_data.get("corrections", [])
            }
            
            for correction in imported_data.get("corrections", []):
                original = correction["original"]
                if original not in existing_corrections:
                    self.learning_data["corrections"].append(correction)
            
            # 패턴 병합
            for pattern, replacements in imported_data.get("patterns", {}).items():
                if pattern not in self.learning_data["patterns"]:
                    self.learning_data["patterns"][pattern] = replacements
                else:
                    self.learning_data["patterns"][pattern].extend(replacements)
            
            self._save_learning_data()
            self.patterns = self._extract_patterns()
            
            print(f"학습 데이터 가져오기 완료: {filename}")
            return True
            
        except Exception as e:
            print(f"데이터 가져오기 오류: {e}")
            return False
