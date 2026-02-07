
import os

file_path = r"c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\app.py"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

start_marker = "@app.route('/admin/users/edit"
delete_marker = "@app.route('/admin/users/delete"
end_marker = "return redirect(url_for('user_list'))"

start_idx = -1
delete_idx = -1
end_idx = -1

# Scan for start (edit_user)
for i in range(2900, 3300):
    if i < len(lines) and start_marker in lines[i]:
        start_idx = i
        break

if start_idx != -1:
    # Scan for delete_user start
    for i in range(start_idx, start_idx + 300):
        if i < len(lines) and delete_marker in lines[i]:
            delete_idx = i
            break

if delete_idx != -1:
    # Scan for delete_user end
    for i in range(delete_idx, delete_idx + 100):
        if i < len(lines) and end_marker in lines[i]:
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
    print(f"Could not find lines. Start: {start_idx}, Delete: {delete_idx}, End: {end_idx}")
