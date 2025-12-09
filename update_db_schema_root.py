from sqlalchemy import create_engine
import sys
import os

# Add current directory to path so imports work
sys.path.append(os.getcwd())

from wdcalculator_models import WDCalculatorBase
from wdcalculator_db import WD_CALCULATOR_DB_URL

engine = create_engine(WD_CALCULATOR_DB_URL)
WDCalculatorBase.metadata.create_all(engine)
print("Updated database schema.")

