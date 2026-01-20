#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Railway 배포 직후 1회 실행용 부트스트랩 스크립트.

- 메인(FOMS) 테이블 생성
- WDCalculator 스키마(wdcalculator) 생성 + 테이블 생성

사용 예:
- (로컬)  python railway_bootstrap.py
- (Railway) railway run python railway_bootstrap.py
"""

import os


def main():
    from app import app
    from db import init_db
    from wdcalculator_db import init_wdcalculator_db, WD_CALCULATOR_IS_SEPARATE_DB, WD_CALCULATOR_SCHEMA

    print("=" * 60)
    print("FOMS Railway Bootstrap")
    print("=" * 60)
    print(f"DATABASE_URL set: {bool(os.getenv('DATABASE_URL'))}")
    print(f"STORAGE_TYPE: {os.getenv('STORAGE_TYPE') or '(not set)'}")
    print(
        "WDCalculator mode:",
        "separate-db" if WD_CALCULATOR_IS_SEPARATE_DB else f"single-db(schema={WD_CALCULATOR_SCHEMA})",
    )
    print()

    with app.app_context():
        print("[1/2] init_db() ...")
        init_db()
        print("[OK] main tables ready")

        print("[2/2] init_wdcalculator_db() ...")
        init_wdcalculator_db()
        print("[OK] wdcalculator tables ready")

    print()
    print("[SUCCESS] bootstrap completed")


if __name__ == "__main__":
    main()

