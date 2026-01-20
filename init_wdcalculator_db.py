#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
견적 계산기 DB(또는 스키마) 초기화 스크립트

권장(운영 단순): DATABASE_URL 1개만 사용 + wdcalculator 스키마로 분리
레거시 호환: WD_CALCULATOR_DATABASE_URL을 설정하면 별도 DB로 동작
"""

import sys
import os

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask
from wdcalculator_db import (
    init_wdcalculator_db,
    WD_CALCULATOR_DB_URL,
    WD_CALCULATOR_IS_SEPARATE_DB,
    WD_CALCULATOR_SCHEMA,
)

app = Flask(__name__)

def main():
    """견적 계산기 데이터베이스 초기화"""
    print("=" * 60)
    print("견적 계산기 초기화 (DB/스키마)")
    print("=" * 60)
    print(f"데이터베이스 URL: {WD_CALCULATOR_DB_URL}")
    if WD_CALCULATOR_IS_SEPARATE_DB:
        print("모드: 별도 DB (레거시 호환)")
    else:
        print(f"모드: 단일 DB + 스키마 분리 (schema='{WD_CALCULATOR_SCHEMA}')")
    print()
    
    try:
        with app.app_context():
            init_wdcalculator_db()
            print("✓ 견적 계산기 데이터베이스 초기화 완료!")
            print()
            print("생성된 테이블:")
            print("  - estimates: 견적 저장")
            print("  - estimate_order_matches: 견적-주문 매칭")
            print("  - estimate_histories: 견적 수정 이력")
            print()
            if WD_CALCULATOR_IS_SEPARATE_DB:
                print("주의: WDCalculator는 FOMS와 완전히 분리된 별도 DB를 사용 중입니다.")
            else:
                print("주의: WDCalculator는 FOMS와 같은 DB를 사용하며, wdcalculator 스키마로 분리되어 있습니다.")
    except Exception as e:
        print(f"✗ 오류 발생: {str(e)}")
        print()
        if WD_CALCULATOR_IS_SEPARATE_DB:
            print("데이터베이스가 존재하지 않을 수 있습니다.")
            print("PostgreSQL에서 다음 명령으로 데이터베이스를 생성하세요:")
            print()
            print("  CREATE DATABASE wdcalculator_estimates;")
            print()
        sys.exit(1)

if __name__ == '__main__':
    main()




