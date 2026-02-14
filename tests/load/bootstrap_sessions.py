import os
import sys
import requests


BASE_URL = os.environ.get("BASE_URL", "https://lahom-dev.up.railway.app").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "Admin123")
COOKIE_NAME = os.environ.get("COOKIE_NAME", "session_staging")
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "8"))

TARGET_USERS = int(os.environ.get("TARGET_USERS", "150"))
USER_PREFIX = os.environ.get("USER_PREFIX", "loadtest_u")
USER_PASSWORD = os.environ.get("USER_PASSWORD", "LoadUser123!")
USER_ROLE = os.environ.get("USER_ROLE", "STAFF")
USER_TEAM = os.environ.get("USER_TEAM", "CS")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(SCRIPT_DIR, "session_cookies.txt")
USER_FILE = os.path.join(SCRIPT_DIR, "loadtest_users.txt")


def login(session: requests.Session, username: str, password: str) -> bool:
    login_url = f"{BASE_URL}/login"
    res = session.post(
        login_url,
        data={"username": username, "password": password},
        allow_redirects=False,
        timeout=HTTP_TIMEOUT,
    )
    if res.status_code not in (302, 303):
        return False
    cookie = session.cookies.get(COOKIE_NAME)
    return bool(cookie)


def ensure_users(admin_session: requests.Session, users):
    add_url = f"{BASE_URL}/admin/users/add"
    created = 0
    skipped = 0
    failed = 0

    total = len(users)
    for idx, username in enumerate(users, start=1):
        payload = {
            "username": username,
            "password": USER_PASSWORD,
            "name": username,
            "role": USER_ROLE,
            "team": USER_TEAM,
        }
        try:
            res = admin_session.post(add_url, data=payload, allow_redirects=False, timeout=HTTP_TIMEOUT)
        except Exception:
            failed += 1
            continue

        if res.status_code in (302, 303):
            created += 1
        elif res.status_code == 200:
            # Usually duplicate username or validation error page re-render
            skipped += 1
        else:
            failed += 1

        if idx % 10 == 0 or idx == total:
            print(f"[PROGRESS] ensure_users {idx}/{total}", flush=True)

    return created, skipped, failed


def collect_cookies(users):
    cookies = []
    auth_fail = []
    total = len(users)
    for idx, username in enumerate(users, start=1):
        s = requests.Session()
        try:
            ok = login(s, username, USER_PASSWORD)
        except Exception:
            ok = False
        if not ok:
            auth_fail.append(username)
            continue
        cookie = s.cookies.get(COOKIE_NAME)
        if cookie:
            cookies.append(cookie)
        if idx % 10 == 0 or idx == total:
            print(f"[PROGRESS] collect_cookies {idx}/{total}", flush=True)
    return cookies, auth_fail


def main():
    users = [f"{USER_PREFIX}{i:03d}" for i in range(1, TARGET_USERS + 1)]

    admin = requests.Session()
    if not login(admin, ADMIN_USER, ADMIN_PASS):
        print("[ERROR] Admin login failed. Check ADMIN_USER/ADMIN_PASS and COOKIE_NAME.")
        return 1

    created, skipped, failed = ensure_users(admin, users)

    cookies, auth_fail = collect_cookies(users)

    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        for c in cookies:
            f.write(c + "\n")

    with open(USER_FILE, "w", encoding="utf-8") as f:
        for u in users:
            f.write(f"{u},{USER_PASSWORD}\n")

    print(f"[INFO] base_url={BASE_URL}")
    print(f"[INFO] users_target={TARGET_USERS}")
    print(f"[INFO] users_created={created}, users_skipped={skipped}, users_failed={failed}")
    print(f"[INFO] cookies_collected={len(cookies)} -> {COOKIE_FILE}")
    print(f"[INFO] credentials_file={USER_FILE}")

    if auth_fail:
        print(f"[WARN] login_failed_users={len(auth_fail)}")
        sample = ", ".join(auth_fail[:10])
        print(f"[WARN] sample={sample}")

    if len(cookies) < TARGET_USERS:
        print("[ERROR] Not enough cookies collected for strict 150-user test.")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
