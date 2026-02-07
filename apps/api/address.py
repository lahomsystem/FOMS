
from flask import Blueprint, jsonify, request
from apps.auth import login_required
from map_config import KAKAO_REST_API_KEY
import requests
import traceback

address_bp = Blueprint('address', __name__, url_prefix='/api/address')

@address_bp.route('/search', methods=['GET'])
@login_required
def search():
    """Kakao Local API 프록시: 주소 검색"""
    try:
        q = (request.args.get('q') or '').strip()
        if not q:
            return jsonify({'success': False, 'message': 'q가 필요합니다.'}), 400

        size = int(request.args.get('size', 10))
        size = max(1, min(size, 15))

        url = "https://dapi.kakao.com/v2/local/search/address.json"
        headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
        params = {"query": q, "size": size}
        r = requests.get(url, headers=headers, params=params, timeout=10)

        if r.status_code != 200:
            return jsonify({'success': False, 'message': f'Kakao API 오류: {r.status_code}'}), 502

        data = r.json() or {}
        docs = data.get('documents', []) or []

        results = []
        for d in docs:
            addr = d.get('address') or {}
            road = d.get('road_address') or {}
            results.append({
                "address_name": d.get('address_name') or addr.get('address_name') or road.get('address_name'),
                "road_address_name": road.get('address_name'),
                "region_1depth_name": addr.get('region_1depth_name') or road.get('region_1depth_name'),
                "region_2depth_name": addr.get('region_2depth_name') or road.get('region_2depth_name'),
                "region_3depth_name": addr.get('region_3depth_name') or road.get('region_3depth_name'),
                "building_name": road.get('building_name'),
                "x": road.get('x') or addr.get('x'),
                "y": road.get('y') or addr.get('y'),
            })

        return jsonify({'success': True, 'results': results})
    except Exception as e:
        print(f"[ADDR] search error: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500
