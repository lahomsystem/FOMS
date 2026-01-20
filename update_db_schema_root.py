import sys
import os

# Add current directory to path so imports work
sys.path.append(os.getcwd())

from wdcalculator_models import WDCalculatorBase  # noqa: F401  (import triggers model registration)
from wdcalculator_db import init_wdcalculator_db

# 스키마/테이블 생성까지 포함 (단일 DB + 스키마 분리 모드 대응)
init_wdcalculator_db()
print("Updated database schema.")

