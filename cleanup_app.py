import os

file_path = r"c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\app.py"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

start_line_content = "# User Management Routes"
end_line_content = "return redirect(url_for('user_list'))"

start_idx = -1
end_idx = -1

# Scan for start line
for i in range(3000, 3300):
    if i < len(lines) and start_line_content in lines[i]:
        start_idx = i
        break

if start_idx != -1:
    # Scan for end line
    for i in range(start_idx, start_idx + 300):
        if i < len(lines) and end_line_content in lines[i]:
            end_idx = i + 1
            break

if start_idx != -1 and end_idx != -1:
    print(f"Deleting lines {start_idx+1} to {end_idx}")
    print(f"Start content: {lines[start_idx].strip()}")
    print(f"End content: {lines[end_idx-1].strip()}")
    
    del lines[start_idx:end_idx]
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("Successfully deleted lines.")
else:
    print(f"Could not find lines. Start: {start_idx}, End: {end_idx}")
