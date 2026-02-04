import sys
import io
import os

# Enforce UTF-8 for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

print("Starting Simple DB Init...")

try:
    from db import engine, Base
    # Import all models to ensure they are registered with Base.metadata
    from models import (
        Order, User, AccessLog, SecurityLog,
        ChatRoom, ChatRoomMember, ChatMessage, ChatAttachment,
        OrderAttachment, OrderEvent, OrderTask
    )
    from wdcalculator_models import Estimate, EstimateOrderMatch, EstimateHistory
    from wdcalculator_db import init_wdcalculator_db
    
    print("Creating Main Tables...")
    Base.metadata.create_all(bind=engine)
    print("Main Tables Created.")

    print("Creating WDCalculator Tables...")
    init_wdcalculator_db()
    
    print("SUCCESS: Database initialized.")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
