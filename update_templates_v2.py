
import os

template_dir = r"c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS\templates"

replacements = [
    ("url_for('user_list')", "url_for('auth.user_list')"),
    ("url_for('add_user')", "url_for('auth.add_user')"),
    ("url_for('edit_user',", "url_for('auth.edit_user',"),
    ("url_for('delete_user',", "url_for('auth.delete_user',"),
    ("url_for('login')", "url_for('auth.login')"),
    ("url_for('logout')", "url_for('auth.logout')"),
    ("url_for('register')", "url_for('auth.register')"),
    ('url_for("user_list")', 'url_for("auth.user_list")'),
    ('url_for("add_user")', 'url_for("auth.add_user")'),
    ('url_for("edit_user",', 'url_for("auth.edit_user",'),
    ('url_for("delete_user",', 'url_for("auth.delete_user",'),
    ('url_for("login")', 'url_for("auth.login")'),
    ('url_for("logout")', 'url_for("auth.logout")'),
    ('url_for("register")', 'url_for("auth.register")'),
]

target_files = ["user_list.html", "add_user.html", "edit_user.html", "admin.html", "layout.html", "login.html", "register.html"]

for filename in target_files:
    path = os.path.join(template_dir, filename)
    if not os.path.exists(path):
        print(f"File not found: {path}")
        continue
        
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    new_content = content
    for old, new in replacements:
        if new in content:
            # Already updated or partially matches
            # But wait, url_for('auth.login') contains url_for('login') as substring?
            # No, because 'auth.' is unique.
            # But simple check might skip valid replacements if file was partially updated.
            # Let's rely on replace. replace is idempotent if pattern doesn't match result.
            # But url_for('login') is NOT in url_for('auth.login') string literally?
            # 'url_for(\'login\')' vs 'url_for(\'auth.login\')'.
            # Yes they are different.
            pass
            
        new_content = new_content.replace(old, new)
        
    if new_content != content:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated {filename}")
    else:
        print(f"No changes in {filename}")
