
import os

path = r"c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\app.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Removing lines 103, 104, 105 (0-indexed: 102, 103, 104)
# "# Auth Blueprint", "from apps.auth import auth_bp", "app.register_blueprint(auth_bp)"
# Check content first
line_103 = lines[102].strip()
line_104 = lines[103].strip()
line_105 = lines[104].strip()

print(f"Checking removal lines:")
print(f"Line 103: {line_103}")
print(f"Line 104: {line_104}")
print(f"Line 105: {line_105}")

if "Auth Blueprint" in line_103 and "auth_bp" in line_105:
    del lines[102:105]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("Successfully removed duplicate registration.")
else:
    print("Content did not match expected lines. Aborting.")
