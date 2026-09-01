import os
import re
import requests
import threading
import time
from collections import OrderedDict
from datetime import datetime

from foms.services.common.address_ai_ops_loader import (
    FOMSAddressLearningSystem,
    FOMSAdvancedAddressProcessor,
)
from foms.services.common.address_query import query_variants, strip_detail
from foms.services.common.geocode_config import (
    DELAY_BETWEEN_REQUESTS,
    kakao_rest_headers,
    MAX_LAT,
    MAX_LNG,
    MAX_RETRIES,
    MIN_LAT,
    MIN_LNG,
)
from foms.services.geocode_retry import FAILURE_PERMANENT, FAILURE_TRANSIENT


def _read_int_env(name, default_value, min_value):
    try:
        value = int(os.environ.get(name, str(default_value)) or default_value)
    except (TypeError, ValueError):
        value = default_value
    return max(min_value, value)


_GEOCODE_CACHE_MAX_ENTRIES = _read_int_env('GEOCODE_CACHE_MAX_ENTRIES', 5000, 100)
_GEOCODE_CACHE_TTL_SECONDS = _read_int_env('GEOCODE_CACHE_TTL_SECONDS', 86400, 60)
_GEOCODE_CACHE_FAIL_TTL_SECONDS = _read_int_env('GEOCODE_CACHE_FAIL_TTL_SECONDS', 600, 15)
_geocode_cache = OrderedDict()
_geocode_cache_lock = threading.Lock()

# 변환 실패의 종류(GEO-FAILKIND-01). 저장 상태(``geocode_status``)를 가르는 근거다.
#:
#
# 2026-09-01 운영 사고: 실패 11건의 주소가 전부 무죄였는데(같은 코드·같은 키로 재변환하니
# 11/11 성공) DB 에는 failed 로 굳어 "주소오류" 배지가 붙어 있었다. 원인은 키 부재·
# 타임아웃·429·HTTP 비200 을 전부 except Exception 으로 삼켜 "주소를 찾을 수 없음"과
# 같은 취급을 한 것이다. 두 실패는 조치가 정반대다 — 하나는 다시 부르면 되고, 다른
# 하나는 사람이 주소를 고쳐야 한다.
#
# 상수 정의 정본은 foms.services.geocode_retry — 저장단이 변환기 모듈을 끌어오지
# 않고도 실패 종류를 읽을 수 있어야 하기 때문이다. 여기서는 이름만 다시 내보낸다.

#: 일시 오류로 볼 HTTP 상태코드. 401/403 은 키 문제(운영에서 키를 갈아끼우면 회복),
#: 429 는 쿼터, 5xx 는 카카오 장애다. 셋 다 주소와 무관하다.
_TRANSIENT_STATUS_CODES = frozenset({401, 403, 408, 429})


class FOMSAddressConverter:
    """FOMS 시스템용 주소 변환 클래스"""
    
    def __init__(self):
        """API 키 설정 및 기본 URL 설정"""
        self.base_url = "https://dapi.kakao.com/v2/local/search/address.json"
        self.keyword_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        self.directions_url = "https://apis-navi.kakaomobility.com/v1/directions"
        # Kakao REST 헤더는 요청 시점에 fail-fast 로 조립(하드코딩 키 제거, SECRET-01).
        
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
    
    @staticmethod
    def _classify_http_status(status_code):
        """HTTP 상태코드를 실패 종류로 옮긴다.

        :param status_code: 카카오 응답의 HTTP 상태코드.
        :return: :data:`FAILURE_TRANSIENT` 또는 :data:`FAILURE_PERMANENT`.

        400(잘못된 질의)처럼 같은 입력으로 다시 불러도 같은 답이 오는 코드만 permanent 다.
        401/403/408/429/5xx 는 주소와 무관한 사정이라 transient 다.
        """
        if status_code in _TRANSIENT_STATUS_CODES or status_code >= 500:
            return FAILURE_TRANSIENT
        return FAILURE_PERMANENT

    def _try_address_api(self, address):
        """주소 API로 변환 시도.

        :param address: 시도할 주소 문자열.
        :return: ``(lat, lng, status, region_info, failure_kind)``. 성공 시 ``failure_kind``
            는 None, 실패 시 :data:`FAILURE_TRANSIENT` / :data:`FAILURE_PERMANENT`.
        """
        try:
            params = {"query": address}
            response = requests.get(
                self.base_url,
                headers=kakao_rest_headers(),
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                documents = data.get("documents", [])
                
                if documents:
                    doc = documents[0]
                    region_info = {}
                    
                    if 'address' in doc and doc['address']:
                        lat = float(doc['address']['y'])
                        lng = float(doc['address']['x'])
                        region_info = {
                            'region_1depth_name': doc['address'].get('region_1depth_name', ''),
                            'region_2depth_name': doc['address'].get('region_2depth_name', ''),
                            'region_3depth_name': doc['address'].get('region_3depth_name', '')
                        }
                        
                        if self._is_valid_coordinates(lat, lng):
                            return lat, lng, "성공", region_info, None

                    # road_address 시도
                    if 'road_address' in doc and doc['road_address']:
                        lat = float(doc['road_address']['y'])
                        lng = float(doc['road_address']['x'])
                        # 도로명 주소 정보가 있으면 덮어쓰거나 보완
                        if not region_info:
                            region_info = {
                                'region_1depth_name': doc['road_address'].get('region_1depth_name', ''),
                                'region_2depth_name': doc['road_address'].get('region_2depth_name', ''),
                                'region_3depth_name': doc['road_address'].get('region_3depth_name', '')
                            }
                        
                        if self._is_valid_coordinates(lat, lng):
                            return lat, lng, "성공", region_info, None

            if response.status_code != 200:
                # HTTP 비200 을 "주소를 찾을 수 없음"과 같이 취급하던 것이 2026-09-01
                # 사고의 자리다. 여기서 갈라야 재시도 경로가 산다.
                return None, None, f"API 응답 오류: {response.status_code}", None, \
                    self._classify_http_status(response.status_code)

            # 200 인데 후보가 없거나(문서 0건) 좌표가 한국 밖 — 주소 쪽 문제다.
            return None, None, "주소를 찾을 수 없음", None, FAILURE_PERMANENT

        except Exception as e:
            # 타임아웃·연결 실패·키 부재(RuntimeError)·JSON 파싱 실패 — 전부 주소와 무관.
            return None, None, f"API 오류: {str(e)}", None, FAILURE_TRANSIENT

    def _try_keyword_api(self, address):
        """키워드 API로 변환 시도.

        :param address: 시도할 검색어.
        :return: ``(lat, lng, status, region_info, failure_kind)`` — :meth:`_try_address_api`
            와 같은 계약.
        """
        try:
            params = {"query": address}
            response = requests.get(
                self.keyword_url,
                headers=kakao_rest_headers(),
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
                    # 키워드 검색 결과에는 상세 행정구역 정보가 없을 수도 있음 (place_name, address_name 등은 있음)
                    # address_name을 파싱하거나 보조 정보로 사용해야 할 수 있음. 여기서는 일단 None.
                    # 하지만 보통 documents[0]에 address_name "서울 광진구 ..." 형태로 들어있으므로 
                    # 필요하면 여기서 파싱 로직을 추가할 수도 있지만, API 스펙상 region depth 필드는 장소 검색에 직접적으로 없을 수 있음.
                    # (카카오 장소 검색 API 응답에는 address_name, road_address_name, category_group_code 등이 있음)
                    # 여기서는 일단 None 처리.
                    
                    if self._is_valid_coordinates(lat, lng):
                        return lat, lng, "키워드 검색 성공", None, None

            if response.status_code != 200:
                return None, None, f"키워드 API 응답 오류: {response.status_code}", None, \
                    self._classify_http_status(response.status_code)

            return None, None, "키워드 검색 실패", None, FAILURE_PERMANENT

        except Exception as e:
            return None, None, f"키워드 API 오류: {str(e)}", None, FAILURE_TRANSIENT
    
    def _strip_detail_for_geocoding(self, address):
        """지오코딩 전 상세주소(동/호수 등)를 떼고 핵심 주소만 반환.

        전처리 정본은 :mod:`foms.services.common.address_query` (GEO-QUERY-01) — 지도
        주소 검색 모달과 **같은** 규칙을 쓰기 위한 얇은 위임이다. 규칙을 여기에 다시
        쓰면 두 벌이 갈라져 "모달에선 찾는데 좌표는 안 나오는" 상태가 된다.

        :param address: 원본 주소.
        :return: 상세주소가 제거된 주소.
        """
        return strip_detail(address)

    def _cache_key(self, address):
        normalized = self._normalize_address(self._strip_detail_for_geocoding(address or ''))
        return normalized.lower().strip()

    def _cache_get(self, key):
        if not key:
            return None
        now_ts = time.time()
        with _geocode_cache_lock:
            item = _geocode_cache.get(key)
            if not item:
                return None
            expires_at, payload = item
            if expires_at <= now_ts:
                _geocode_cache.pop(key, None)
                return None
            _geocode_cache.move_to_end(key)
            return payload

    def _cache_set(self, key, lat, lng, status, region_info, failure_kind=None):
        """변환 결과를 프로세스 캐시에 넣는다.

        일시 오류(:data:`FAILURE_TRANSIENT`)는 **캐시하지 않는다** — 카카오가 잠깐 흔들린
        결과를 실패 TTL(기본 600초) 동안 되풀이해 돌려주면, 그 사이 들어온 재시도가 전부
        API 를 안 부르고 같은 오답을 받는다(2026-09-01 사고의 확산 경로).
        """
        if not key:
            return
        is_success = (lat is not None and lng is not None)
        if not is_success and failure_kind == FAILURE_TRANSIENT:
            return
        ttl = _GEOCODE_CACHE_TTL_SECONDS if is_success else _GEOCODE_CACHE_FAIL_TTL_SECONDS
        expires_at = time.time() + ttl
        payload = (lat, lng, status, region_info, failure_kind)
        with _geocode_cache_lock:
            _geocode_cache[key] = (expires_at, payload)
            _geocode_cache.move_to_end(key)
            while len(_geocode_cache) > _GEOCODE_CACHE_MAX_ENTRIES:
                _geocode_cache.popitem(last=False)

    @staticmethod
    def clear_geocode_cache():
        with _geocode_cache_lock:
            _geocode_cache.clear()
    
    def convert_address(self, address):
        """AI 기반 주소 변환 (기존 호환성 유지)"""
        lat, lng, status, _ = self.analyze_address(address)
        return lat, lng, status

    def convert_address_with_reason(self, address):
        """주소를 좌표로 변환하고 **실패 사유의 종류까지** 돌려준다 (GEO-FAILKIND-01).

        :param address: 변환할 주소.
        :return: ``(lat, lng, status, failure_kind)``. 성공하면 ``failure_kind`` 는 None,
            실패하면 :data:`FAILURE_TRANSIENT`(다시 부르면 될 실패) 또는
            :data:`FAILURE_PERMANENT`(주소를 고쳐야 하는 실패).

        저장단(:func:`foms.services.geocode_helpers.apply_geocode_to_order`)이 이 값으로
        ``geocode_status`` 를 가른다. 사유를 안 돌려주던 시절에는 네트워크 사고가
        ``failed``(=주소오류 배지)로 굳었다.
        """
        lat, lng, status, _region, failure_kind = self._analyze(address)
        return lat, lng, status, failure_kind

    def analyze_address(self, address):
        """AI 기반 주소 변환 및 분석 (상세 정보 포함).

        :param address: 변환할 주소.
        :return: ``(lat, lng, status, region_info)`` — 기존 호출자 계약 유지.
            실패 사유 종류가 필요하면 :meth:`convert_address_with_reason` 를 쓴다.
        """
        lat, lng, status, region_info, _kind = self._analyze(address)
        return lat, lng, status, region_info

    def _analyze(self, address):
        """변환 본체. :meth:`analyze_address` 의 4-튜플에 ``failure_kind`` 를 더해 반환한다.

        :param address: 변환할 주소.
        :return: ``(lat, lng, status, region_info, failure_kind)``.
        """
        if not address or str(address).strip() == '':
            # 부를 주소 자체가 없다 — 재시도해도 달라지지 않는다.
            return None, None, "빈 주소", None, FAILURE_PERMANENT

        cache_key = self._cache_key(address)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        #: 전략을 돌다 한 번이라도 일시 오류를 만났는지. 끝내 실패했을 때 그 실패를
        #: "주소가 나쁘다"로 단정하지 않기 위한 표식이다 — 첫 전략이 타임아웃으로 죽고
        #: 나머지가 permanent 였다면 그 주소는 아직 판정된 적이 없는 것이다.
        saw_transient = False

        # 1단계: 학습 데이터에서 검색
        try:
            learned_suggestion = self.learning_system.suggest_correction(address)
            if learned_suggestion and learned_suggestion.get('latitude') and learned_suggestion.get('longitude'):
                result = (
                    learned_suggestion['latitude'],
                    learned_suggestion['longitude'],
                    f"학습 데이터 매칭 (신뢰도: {learned_suggestion['confidence']:.2f})",
                    None,
                    None,
                )
                self._cache_set(cache_key, result[0], result[1], result[2], result[3])
                return result
        except Exception as e:
            pass  # failopen: intentional: 주소 학습 캐시 매칭 실패 시 폴백 경로로 계속
        
        # 2단계: 상세주소 분리 (동/호수 등 제거 → 핵심 주소만)
        stripped_address = self._strip_detail_for_geocoding(address)
        
        # 3단계: 고급 주소 처리
        try:
            processed_address = self.advanced_processor.process_address(address)
            processed_stripped = self._strip_detail_for_geocoding(processed_address)
        except Exception as e:
            processed_address = address
            processed_stripped = stripped_address
        
        # 4단계: 정규화된 주소로 API 시도
        normalized_address = self._normalize_address(processed_address)
        normalized_stripped = self._strip_detail_for_geocoding(normalized_address)
        
        # 5단계: 다중 전략 시도 (상세주소 제거 버전을 우선 시도)
        strategies = []
        seen = set()
        
        # 상세주소 제거 버전을 먼저 시도 (가장 정확)
        # GEO-QUERY-01: 모달 검색과 동일한 후보(붙여쓴 동호수 제거본 등)를 함께 시도해
        # "모달에선 찾는데 워커는 못 찾는" 비대칭을 없앤다.
        shared_variants = [
            (f"shared_variant{i}", v) for i, v in enumerate(query_variants(address or ""))
        ]
        for name, addr in [
            ("stripped", stripped_address),
            ("processed_stripped", processed_stripped),
            ("normalized_stripped", normalized_stripped),
            ("processed", processed_address),
            ("normalized", normalized_address),
            ("original", address)
        ] + shared_variants:
            if addr and addr.strip() and addr.strip() not in seen:
                seen.add(addr.strip())
                strategies.append((name, addr.strip()))
        
        for strategy_name, addr_to_try in strategies:
            if addr_to_try:
                # 주소 API 시도
                lat, lng, status, region_info, kind = self._try_address_api(addr_to_try)
                if lat is not None and lng is not None:
                    final_status = f"{status} ({strategy_name})"
                    self._cache_set(cache_key, lat, lng, final_status, region_info)
                    return lat, lng, final_status, region_info, None
                saw_transient = saw_transient or kind == FAILURE_TRANSIENT

                # 키워드 API 시도
                lat, lng, status, region_info, kind = self._try_keyword_api(addr_to_try)
                if lat is not None and lng is not None:
                    final_status = f"{status} ({strategy_name})"
                    self._cache_set(cache_key, lat, lng, final_status, region_info)
                    return lat, lng, final_status, region_info, None
                saw_transient = saw_transient or kind == FAILURE_TRANSIENT

        # 6단계: 주소 구성 요소로 좁혀 마지막 한 번 더 시도.
        #
        # 이 단계는 **주소가 가리키는 지점이 아니라 그 동네의 중심 좌표**를 돌려준다. 그래서
        # 두 가지를 지킨다(2026-09-02 운영 실측 근거).
        #
        # * **동까지 있을 때만** 시도한다. `시 + 구` 만으로 물어보면 구 중심 좌표(수 km 오차)가
        #   `success` 로 저장돼 지도 핀이 엉뚱한 곳에 정확한 얼굴로 꽂힌다.
        # * **일시 오류를 겪었으면 아예 시도하지 않는다.** 네트워크가 흔들려 앞 전략들이 죽은
        #   상황에서 동 중심 좌표로 덮으면, 재시도됐어야 할 건이 성공으로 굳는다(운영 #2418 이
        #   정확히 그 모양이었다 — 진짜 위치에서 2,214m).
        if saw_transient:
            self._cache_set(cache_key, None, None, "일시 오류로 변환 보류", None, FAILURE_TRANSIENT)
            return None, None, "일시 오류로 변환 보류", None, FAILURE_TRANSIENT

        try:
            components = self.advanced_processor.extract_address_components(address)
            if components['city'] and components['district'] and components['dong']:
                simplified_address = (
                    f"{components['city']} {components['district']} {components['dong']}"
                )

                lat, lng, status, region_info, kind = self._try_address_api(simplified_address)
                if lat is not None and lng is not None:
                    final_status = f"{status} (simplified)"
                    self._cache_set(cache_key, lat, lng, final_status, region_info)
                    return lat, lng, final_status, region_info, None
                saw_transient = saw_transient or kind == FAILURE_TRANSIENT
        except Exception as e:
            print(f"주소 구성 요소 분석 오류: {e}")
        
        # API 호출 간격 제어
        time.sleep(DELAY_BETWEEN_REQUESTS)
        
        # 전략을 다 돌고도 실패. 한 번이라도 일시 오류를 봤다면 이 주소는 아직 판정된 적이
        # 없는 것이다 — "AI 변환 실패"로 굳히지 않고 transient 로 올려 재시도 경로에 남긴다.
        failure_kind = FAILURE_TRANSIENT if saw_transient else FAILURE_PERMANENT
        final_status = "일시 오류로 변환 보류" if saw_transient else "AI 변환 실패"
        print(f"[CONVERTER] 모든 변환 시도 실패 (kind={failure_kind})")
        self._cache_set(cache_key, None, None, final_status, None, failure_kind)
        return None, None, final_status, None, failure_kind
    
    def add_learning_data(self, original_address, corrected_address, lat, lng):
        """학습 데이터 추가"""
        self.learning_system.add_correction(original_address, corrected_address, lat, lng)
        self.clear_geocode_cache()
    
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
    
    def calculate_route(self, start_lat, start_lng, end_lat, end_lng, timeout=None):
        """두 좌표 간의 차량 경로 및 소요시간 계산.

        Args:
            timeout: Optional seconds for the HTTP request. When omitted, behavior
                matches historical calls (no explicit requests timeout).
        """
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

            req_kwargs = {}
            if timeout is not None:
                req_kwargs["timeout"] = timeout
            response = requests.get(url, params=params, headers=kakao_rest_headers(), **req_kwargs)
            
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
