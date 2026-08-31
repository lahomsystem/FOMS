"""
Canonical Kakao address search proxy API (Wave 3).

Wave 8 (W8-B5): legacy `apps.api.address` direct-import bridge removed; use this module.
"""
from __future__ import annotations

import logging
import re

import requests
from flask import Blueprint, jsonify, request

from foms.web.auth import login_required
from foms.services.common.address_query import query_variants, strip_detail
from foms.services.common.geocode_config import kakao_rest_headers

logger = logging.getLogger(__name__)

address_bp = Blueprint("address", __name__, url_prefix="/api/address")


def _strip_detail(q: str) -> str:
    """검색어에서 동호수·상세주소 노이즈를 제거하고 핵심 부분만 반환.

    전처리 정본은 :mod:`foms.services.common.address_query` (GEO-QUERY-01) — 지오코딩
    워커와 **같은** 규칙을 쓰기 위한 얇은 위임이다. 여기에 규칙을 다시 쓰지 말 것.

    :param q: 원본 검색어.
    :return: 상세주소가 제거된 검색어.
    """
    return strip_detail(q)


def _query_variants(q: str) -> list[str]:
    """검색에 사용할 쿼리 후보 목록 (우선순위 순).

    전처리 정본은 :mod:`foms.services.common.address_query` (GEO-QUERY-01).

    :param q: 원본 검색어.
    :return: 중복 제거된 후보 목록.
    """
    return query_variants(q)


def _doc_to_result(d, source="address"):
    """주소 API 문서를 공통 결과 형식으로 변환"""
    addr = d.get("address") or {}
    road = d.get("road_address") or {}
    return {
        "address_name": d.get("address_name") or addr.get("address_name") or road.get("address_name"),
        "road_address_name": road.get("address_name"),
        "region_1depth_name": addr.get("region_1depth_name") or road.get("region_1depth_name"),
        "region_2depth_name": addr.get("region_2depth_name") or road.get("region_2depth_name"),
        "region_3depth_name": addr.get("region_3depth_name") or road.get("region_3depth_name"),
        "building_name": road.get("building_name"),
        "x": road.get("x") or addr.get("x"),
        "y": road.get("y") or addr.get("y"),
    }


def _keyword_doc_to_result(d):
    """키워드 API 문서를 공통 결과 형식으로 변환 (아파트·건물명 검색용)
    키워드 API는 place_name, address_name, road_address_name, x, y 를 최상위에 반환함.
    """
    addr = d.get("address") or {}
    road = d.get("road_address") or {}
    x = d.get("x") or road.get("x") or addr.get("x")
    y = d.get("y") or road.get("y") or addr.get("y")
    if x is None or y is None:
        return None
    return {
        "address_name": d.get("address_name")
        or addr.get("address_name")
        or road.get("address_name")
        or d.get("place_name")
        or "",
        "road_address_name": road.get("address_name") if road else (d.get("road_address_name") or ""),
        "region_1depth_name": addr.get("region_1depth_name")
        or (road.get("region_1depth_name") if road else None)
        or d.get("region_1depth_name"),
        "region_2depth_name": addr.get("region_2depth_name")
        or (road.get("region_2depth_name") if road else None)
        or d.get("region_2depth_name"),
        "region_3depth_name": addr.get("region_3depth_name")
        or (road.get("region_3depth_name") if road else None)
        or d.get("region_3depth_name"),
        "building_name": (road.get("building_name") if road else None)
        or d.get("place_name")
        or d.get("building_name"),
        "x": str(x),
        "y": str(y),
    }


@address_bp.route("/search", methods=["GET"])
@login_required
def search():
    """Kakao Local API 프록시: 주소 검색 + 아파트/건물명 키워드 검색 보조.

    전처리 폴백 전략:
      쿼리 후보 목록(원본 → 동호수제거 → 앞부분 축약 → 공백제거) 순으로 각각
      주소API → 키워드API를 시도해 size 건이 채워지면 조기 종료.
    """
    try:
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify({"success": False, "message": "q가 필요합니다."}), 400

        size = int(request.args.get("size", 10))
        size = max(1, min(size, 15))

        results: list = []
        seen_keys: set = set()

        def add_unique(r):
            key = (r.get("x"), r.get("y"), (r.get("road_address_name") or r.get("address_name") or ""))
            if key in seen_keys or not r.get("x") or not r.get("y"):
                return
            seen_keys.add(key)
            results.append(r)

        url_address = "https://dapi.kakao.com/v2/local/search/address.json"
        url_keyword = "https://dapi.kakao.com/v2/local/search/keyword.json"

        for variant in _query_variants(q):
            if len(results) >= size:
                break

            # 주소 API (도로명/지번) - 원본 쿼리 한 번만 시도
            if variant == q:
                r = requests.get(
                    url_address,
                    headers=kakao_rest_headers(),
                    params={"query": variant, "size": size},
                    timeout=10,
                )
                if r.status_code == 200:
                    for d in (r.json() or {}).get("documents") or []:
                        add_unique(_doc_to_result(d))

            # 키워드 API (아파트·건물명 등)
            if len(results) < size:
                rk = requests.get(
                    url_keyword,
                    headers=kakao_rest_headers(),
                    params={"query": variant, "size": size},
                    timeout=10,
                )
                if rk.status_code == 200:
                    for d in (rk.json() or {}).get("documents") or []:
                        if len(results) >= size:
                            break
                        res = _keyword_doc_to_result(d)
                        if res:
                            add_unique(res)

        return jsonify({"success": True, "results": results})
    except Exception:
        logger.exception("주소 검색 오류")
        return (
            jsonify(
                {
                    "success": False,
                    "message": "주소 검색 중 오류가 발생했습니다.",
                }
            ),
            500,
        )
