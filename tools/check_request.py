
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

client = app.test_client()

print("Testing /login route...")
try:
    response = client.get('/login')
    print(f"Status: {response.status_code}")
    if response.status_code == 500:
        print("Response data (first 500 chars):")
        print(response.data[:500])
except Exception as e:
    print(f"EXCEPTION on /login: {e}")
    import traceback
    traceback.print_exc()

print("\nTesting /debug-r2 route...")
try:
    response = client.get('/debug-r2')
    print(f"Status: {response.status_code}")
    if response.status_code != 200:
         print(response.data[:500])
    else:
         print(response.data[:500])
except Exception as e:
    print(f"EXCEPTION on /debug-r2: {e}")
    import traceback
    traceback.print_exc()
