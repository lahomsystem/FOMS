from app import app
from db import get_db
from models import Order
import json
import copy
from datetime import datetime
import sys

# Test Script: Reproduce Issue (deepcopy only, no flag_modified)
with app.app_context():
    db = get_db()
    
    # 1. Find target order
    # Try to find a CONFIRM order
    order = db.query(Order).filter(Order.status == 'CONFIRM', Order.is_erp_beta == True).first()
    
    if not order:
        print("No CONFIRM order found. Creating one for test...")
        # Find any ERP order
        order = db.query(Order).filter(Order.is_erp_beta == True).first()
        if not order:
            print("No ERP order available.")
            sys.exit(1)
            
        # Set to CONFIRM manually
        sd = order.structured_data or {}
        if isinstance(sd, str): sd = json.loads(sd)
        wf = sd.get('workflow') or {}
        wf['stage'] = 'CONFIRM' 
        sd['workflow'] = wf
        
        # Use simple assignment for setup
        order.structured_data = copy.deepcopy(sd)
        order.status = 'CONFIRM'
        db.commit()
        print(f"Order {order.id} forced to CONFIRM for testing.")
        
        # Refresh
        db.expire(order)
        order = db.query(Order).get(order.id)

    print(f"Test Order ID: {order.id}")
    sd = order.structured_data or {}
    if isinstance(sd, str): sd = json.loads(sd)
    wf = sd.get('workflow') or {}
    print(f"Initial State: stage={wf.get('stage')}, status={order.status}")

    # 2. Apply Update Logic (Simulating api_production_start)
    wf['stage'] = 'PRODUCTION'
    wf['stage_updated_at'] = datetime.now().isoformat()
    wf['stage_updated_by'] = 'TestScript'
    
    hst = wf.get('history') or []
    hst.append({'stage': 'PRODUCTION', 'note': 'Test'})
    wf['history'] = hst
    sd['workflow'] = wf
    
    # Update using deepcopy (Current Implementation)
    order.structured_data = copy.deepcopy(sd)
    order.status = 'PRODUCTION'
    
    db.commit()
    print("Commit executed.")
    
    # 3. Verify
    db.expire(order)
    order = db.query(Order).get(order.id)
    sd = order.structured_data or {}
    if isinstance(sd, str): sd = json.loads(sd)
    
    final_stage = sd.get('workflow', {}).get('stage')
    final_status = order.status
    
    print(f"Final State: stage={final_stage}, status={final_status}")
    
    if final_stage == 'PRODUCTION':
        print("RESULT: SUCCESS (Update reflected)")
    else:
        print("RESULT: FAILURE (Update NOT reflected)")
