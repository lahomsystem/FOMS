
path = r"c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\app.py"
print(f"Searching in {path}...")
try:
    with open(path, "r", encoding="utf-8") as f:
        found = False
        for i, line in enumerate(f):
            if "erp_beta" in line:
                print(f"{i+1}: {line.strip()}")
                found = True
        if not found:
            print("String 'erp_beta' not found in file.")
except Exception as e:
    print(f"Error: {e}")
