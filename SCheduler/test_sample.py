#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
지능형 주소 변환 시스템 테스트 스크립트
"""

from address_converter import AddressConverter
from address_learning import AddressLearningSystem
from web_address_learner import WebAddressLearner

def test_basic_conversion():
    """기본 주소 변환 테스트"""
    print("🔄 기본 주소 변환 테스트 시작...")
    
    # 학습 시스템 없이 기본 변환
    basic_converter = AddressConverter()
    
    test_addresses = [
        "서울특별시 강남구 테헤란로 123",
        "부산광역시 해운대구 센텀로 45",
        "잘못된주소입니다",
        "강남역"
    ]
    
    for address in test_addresses:
        lat, lng, status = basic_converter.convert_address(address)
        print(f"  📍 {address}")
        print(f"     결과: {status}")
        if lat and lng:
            print(f"     좌표: ({lat:.6f}, {lng:.6f})")
        print()

def test_learning_system():
    """AI 학습 시스템 테스트"""
    print("🧠 AI 학습 시스템 테스트 시작...")
    
    learning_system = AddressLearningSystem()
    
    # 테스트 학습 데이터 추가
    learning_system.add_correction(
        "강남역",
        "서울특별시 강남구 강남대로 390",
        37.4975,
        127.0276
    )
    
    # 학습 통계 확인
    stats = learning_system.get_learning_stats()
    print(f"  📊 학습 통계: {stats}")
    
    # 제안 시스템 테스트
    suggestions = learning_system.suggest_correction("강남역근처")
    print(f"  💡 제안사항: {suggestions}")
    print()

def test_ai_converter():
    """AI 통합 변환기 테스트"""
    print("🤖 AI 통합 변환기 테스트 시작...")
    
    learning_system = AddressLearningSystem()
    ai_converter = AddressConverter(learning_system)
    
    test_addresses = [
        "강남역",
        "서울 강남구",
        "부산해운대"
    ]
    
    for address in test_addresses:
        lat, lng, status = ai_converter.convert_address(address)
        print(f"  🧠 {address}")
        print(f"     AI 결과: {status}")
        if lat and lng:
            print(f"     좌표: ({lat:.6f}, {lng:.6f})")
        print()

def test_web_learner():
    """웹 학습 시스템 테스트"""
    print("🌐 웹 학습 시스템 테스트 시작...")
    
    web_learner = WebAddressLearner()
    
    # 패턴 추출 테스트
    patterns = web_learner._extract_address_patterns("서울특별시 강남구 테헤란로 123")
    print(f"  🔍 추출된 패턴: {patterns}")
    
    # 랜드마크 인식 테스트
    enhancement = web_learner.enhance_address_with_context("롯데타워")
    print(f"  🏢 랜드마크 인식: {enhancement}")
    
    # 제안 생성 테스트
    suggestions = web_learner._generate_suggestions("서울 강남", patterns)
    print(f"  💭 웹 제안사항: {suggestions}")
    print()

if __name__ == "__main__":
    print("=" * 60)
    print("🧠 지능형 주소 변환 시스템 테스트")
    print("=" * 60)
    print()
    
    try:
        test_basic_conversion()
        test_learning_system()
        test_ai_converter()
        test_web_learner()
        
        print("✅ 모든 테스트 완료!")
        print()
        print("🚀 이제 메인 애플리케이션을 실행하세요:")
        print("   streamlit run main_app.py --server.port 8503")
        
    except Exception as e:
        print(f"❌ 테스트 중 오류 발생: {e}")
        print("🔧 의존성 설치를 확인하세요: pip install -r requirements.txt") 