
import os

path = r"c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\app.py"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Line 3067 (0-indexed) is line number 3068 in editor.
# We want to remove lines 3068 to 3108 (inclusive).
# Line 3109 (0-indexed 3108) should remain.
# Python slice [start:end] includes start but excludes end.
# So we need lines[3067:3109] ?? No.
# If end index is 3108 (which is line 3109), it excludes line 3109. Perfect.

start_idx = 3067
end_idx = 3108

print(f"Deleting from line {start_idx+1}: {lines[start_idx].strip()}")
print(f"Deleting to line {end_idx}: {lines[end_idx-1].strip()}")
print(f"Next line will be (line {end_idx+1}): {lines[end_idx].strip()}")

del lines[start_idx:end_idx]

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)
    
print("Successfully deleted garbage lines.")
