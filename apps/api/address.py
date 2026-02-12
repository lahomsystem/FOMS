from flask import Blueprint, jsonify, request
from apps.auth import login_required
from map_config import KAKAO_REST_API_KEY
import requests
import traceback

address_bp = Blueprint('address', __name__, url_prefix='/api/address')

HEADERS = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}


def _doc_to_result(d, source='address'):
    """주소 API 문서를 공통 결과 형식으로 변환"""
    addr = d.get('address') or {}
    road = d.get('road_address') or {}
    return {
        "address_name": d.get('address_name') or addr.get('address_name') or road.get('address_name'),
        "road_address_name": road.get('address_name'),
        "region_1depth_name": addr.get('region_1depth_name') or road.get('region_1depth_name'),
        "region_2depth_name": addr.get('region_2depth_name') or road.get('region_2depth_name'),
        "region_3depth_name": addr.get('region_3depth_name') or road.get('region_3depth_name'),
        "building_name": road.get('building_name'),
        "x": road.get('x') or addr.get('x'),
        "y": road.get('y') or addr.get('y'),
    }


def _keyword_doc_to_result(d):
    """키워드 API 문서를 공통 결과 형식으로 변환 (아파트·건물명 검색용)
    키워드 API는 place_name, address_name, road_address_name, x, y 를 최상위에 반환함.
    """
    addr = d.get('address') or {}
    road = d.get('road_address') or {}
    x = d.get('x') or road.get('x') or addr.get('x')
    y = d.get('y') or road.get('y') or addr.get('y')
    if x is None or y is None:
        return None
    return {
        "address_name": d.get('address_name') or addr.get('address_name') or road.get('address_name') or d.get('place_name') or '',
        "road_address_name": road.get('address_name') if road else (d.get('road_address_name') or ''),
        "region_1depth_name": addr.get('region_1depth_name') or (road.get('region_1depth_name') if road else None) or d.get('region_1depth_name'),
        "region_2depth_name": addr.get('region_2depth_name') or (road.get('region_2depth_name') if road else None) or d.get('region_2depth_name'),
        "region_3depth_name": addr.get('region_3depth_name') or (road.get('region_3depth_name') if road else None) or d.get('region_3depth_name'),
        "building_name": (road.get('building_name') if road else None) or d.get('place_name') or d.get('building_name'),
        "x": str(x),
        "y": str(y),
    }


@address_bp.route('/search', methods=['GET'])
@login_required
def search():
    """Kakao Local API 프록시: 주소 검색 + 아파트/건물명 키워드 검색 보조"""
    try:
        q = (request.args.get('q') or '').strip()
        if not q:
            return jsonify({'success': False, 'message': 'q가 필요합니다.'}), 400

        size = int(request.args.get('size', 10))
        size = max(1, min(size, 15))

        results = []
        seen_keys = set()

        def add_unique(r):
            key = (r.get('x'), r.get('y'), (r.get('road_address_name') or r.get('address_name') or ''))
            if key in seen_keys or not r.get('x') or not r.get('y'):
                return
            seen_keys.add(key)
            results.append(r)

        # 1) 주소 API (도로명/지번)
        url_address = "https://dapi.kakao.com/v2/local/search/address.json"
        r = requests.get(url_address, headers=HEADERS, params={"query": q, "size": size}, timeout=10)
        if r.status_code == 200:
            data = r.json() or {}
            for d in (data.get('documents') or [])[:size]:
                add_unique(_doc_to_result(d))

        # 2) 결과가 없거나 적으면 키워드 API로 아파트·건물명 검색 (물향기, 센트레빌 등)
        if len(results) < size:
            url_keyword = "https://dapi.kakao.com/v2/local/search/keyword.json"
            rk = requests.get(url_keyword, headers=HEADERS, params={"query": q, "size": size}, timeout=10)
            if rk.status_code == 200:
                data_k = rk.json() or {}
                for d in (data_k.get('documents') or []):
                    if len(results) >= size:
                        break
                    res = _keyword_doc_to_result(d)
                    if res:
                        add_unique(res)

        return jsonify({'success': True, 'results': results})
    except Exception as e:
        print(f"[ADDR] search error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500
