
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Attempting to import app...")
try:
    from app import app
    print("SUCCESS: App imported successfully.")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
