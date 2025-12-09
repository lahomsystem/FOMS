#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
견적 계산기 독립 데이터베이스 초기화 스크립트
FOMS 시스템과 완전히 분리된 독립 데이터베이스를 생성합니다.
"""

import sys
import os

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from wdcalculator_db import init_wdcalculator_db, WD_CALCULATOR_DB_URL

app = Flask(__name__)

def main():
    """견적 계산기 데이터베이스 초기화"""
    print("=" * 60)
    print("견적 계산기 독립 데이터베이스 초기화")
    print("=" * 60)
    print(f"데이터베이스 URL: {WD_CALCULATOR_DB_URL}")
    print()
    
    try:
        with app.app_context():
            init_wdcalculator_db()
            print("✓ 견적 계산기 데이터베이스 초기화 완료!")
            print()
            print("생성된 테이블:")
            print("  - estimates: 견적 저장")
            print("  - estimate_order_matches: 견적-주문 매칭")
            print()
            print("주의: 이 데이터베이스는 FOMS 데이터베이스와 완전히 분리되어 있습니다.")
    except Exception as e:
        print(f"✗ 오류 발생: {str(e)}")
        print()
        print("데이터베이스가 존재하지 않을 수 있습니다.")
        print("PostgreSQL에서 다음 명령으로 데이터베이스를 생성하세요:")
        print()
        print("  CREATE DATABASE wdcalculator_estimates;")
        print()
        sys.exit(1)

if __name__ == '__main__':
    main()

