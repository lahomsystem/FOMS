#!/usr/bin/env python3
"""
실제 FOMS 시스템에서 지도 생성 API 테스트
"""

import sys
import os
import requests
from requests.auth import HTTPBasicAuth
import json

# FOMS 시스템 설정
FOMS_URL = "http://localhost:5000"

def test_map_api_with_login():
    """로그인 후 지도 API 테스트"""
    session = requests.Session()
    
    print("🔐 FOMS 시스템 로그인 시도...")
    
    # 1. 로그인 페이지에서 세션 확인
    login_page = session.get(f"{FOMS_URL}/login")
    print(f"로그인 페이지 상태: {login_page.status_code}")
    
    # 2. 로그인 시도 (기본 관리자 계정)
    login_data = {
        "username": "admin",  # 기본 관리자 계정
        "password": "admin123"  # 기본 비밀번호
    }
    
    login_response = session.post(f"{FOMS_URL}/login", data=login_data)
    print(f"로그인 응답 상태: {login_response.status_code}")
    
    if login_response.status_code == 200 and "로그인" not in login_response.text:
        print("✅ 로그인 성공!")
        
        # 3. 지도 생성 API 호출
        print("\n🗺️ 지도 생성 API 호출...")
        map_params = {
            "date": "2024-08-26",
            "status": "ALL",
            "title": "테스트 지도"
        }
        
        map_response = session.get(f"{FOMS_URL}/api/generate_map", params=map_params)
        print(f"지도 API 응답 상태: {map_response.status_code}")
        
        if map_response.status_code == 200:
            try:
                data = map_response.json()
                print(f"✅ API 응답 성공: {data.get('success', False)}")
                if not data.get('success', False):
                    print(f"❌ 오류 메시지: {data.get('error', 'Unknown error')}")
                else:
                    print(f"📊 총 주문 수: {data.get('total_orders', 0)}")
                    map_html_length = len(data.get('map_html', ''))
                    print(f"📄 지도 HTML 길이: {map_html_length}자")
                    
            except json.JSONDecodeError:
                print("❌ JSON 파싱 실패")
                print(f"응답 내용 (첫 500자): {map_response.text[:500]}")
        else:
            print(f"❌ API 호출 실패: {map_response.status_code}")
            print(f"응답 내용: {map_response.text[:200]}")
    
    else:
        print("❌ 로그인 실패")
        print("기본 계정이 없거나 비밀번호가 다를 수 있습니다.")
        return False
    
    return True

def test_with_different_credentials():
    """다른 계정 정보들로 테스트"""
    possible_accounts = [
        ("admin", "admin"),
        ("admin", "admin123"),
        ("admin", "password"),
        ("test", "test"),
        ("user", "user"),
    ]
    
    for username, password in possible_accounts:
        print(f"\n🔑 계정 테스트: {username}/{password}")
        session = requests.Session()
        
        login_data = {"username": username, "password": password}
        response = session.post(f"{FOMS_URL}/login", data=login_data)
        
        if response.status_code == 200 and "로그인" not in response.text:
            print(f"✅ {username} 계정으로 로그인 성공!")
            
            # 지도 API 테스트
            map_response = session.get(f"{FOMS_URL}/api/generate_map?date=2024-08-26&status=ALL")
            print(f"지도 API 상태: {map_response.status_code}")
            
            if map_response.status_code == 200:
                try:
                    data = map_response.json()
                    if data.get('success'):
                        print("✅ 지도 생성 성공!")
                        return True
                    else:
                        print(f"❌ 지도 생성 실패: {data.get('error')}")
                except:
                    print("❌ JSON 응답 파싱 실패")
            break
        else:
            print(f"❌ {username} 로그인 실패")
    
    return False

if __name__ == "__main__":
    print("🧪 FOMS 실시간 지도 API 테스트")
    print("=" * 50)
    
    # FOMS 서버 연결 확인
    try:
        response = requests.get(FOMS_URL, timeout=5)
        print(f"✅ FOMS 서버 연결 성공 (상태: {response.status_code})")
    except requests.exceptions.ConnectionError:
        print("❌ FOMS 서버에 연결할 수 없습니다.")
        print("python app.py로 서버를 먼저 시작해주세요.")
        sys.exit(1)
    
    # 로그인 후 테스트
    if not test_map_api_with_login():
        print("\n🔄 다른 계정들로 시도...")
        test_with_different_credentials()
    
    print("\n💡 브라우저에서 직접 확인:")
    print("1. http://localhost:5000 접속")
    print("2. 로그인 후 캘린더 > 지도 보기 클릭")
    print("3. 개발자 도구(F12) > Console 탭에서 오류 확인")
