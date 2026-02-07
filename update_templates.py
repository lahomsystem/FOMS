
import os

template_dir = r"c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates"

replacements = [
    ("url_for('user_list')", "url_for('auth.user_list')"),
    ("url_for('add_user')", "url_for('auth.add_user')"),
    ("url_for('edit_user',", "url_for('auth.edit_user',"),
    ("url_for('delete_user',", "url_for('auth.delete_user',"),
    ('url_for("user_list")', 'url_for("auth.user_list")'),
    ('url_for("add_user")', 'url_for("auth.add_user")'),
    ('url_for("edit_user",', 'url_for("auth.edit_user",'),
    ('url_for("delete_user",', 'url_for("auth.delete_user",'),
]

target_files = ["user_list.html", "add_user.html", "edit_user.html", "admin.html", "layout.html"]

for filename in target_files:
    path = os.path.join(template_dir, filename)
    if not os.path.exists(path):
        print(f"File not found: {path}")
        continue
        
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    new_content = content
    for old, new in replacements:
        # Avoid double prefixing
        if new in content:
            print(f"Skipping {old} in {filename} (already updated?)")
            continue
        new_content = new_content.replace(old, new)
        
    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated {filename}")
    else:
        print(f"No changes in {filename}")
