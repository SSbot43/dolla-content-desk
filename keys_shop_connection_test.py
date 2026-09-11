from __future__ import annotations
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env.keys-shop"

try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)
except Exception:
    pass

from content_os.adapters.keys_shop import KeysShopAdapter
from content_os.adapters.wordpress import WordPressError

required = ["KEYS_WP_URL", "KEYS_WP_USERNAME", "KEYS_WP_APP_PASSWORD"]
missing = [k for k in required if not os.environ.get(k, "").strip()]
if missing:
    print(f"FAILED: missing from {ENV_FILE.name}: " + ", ".join(missing))
    sys.exit(1)

base = os.environ["KEYS_WP_URL"].rstrip("/")
print("Keys-Shop REST diagnostics")
print("--------------------------")

# Public REST index: tells us whether WordPress considers Application Passwords available.
try:
    req = urllib.request.Request(base + "/wp-json/", headers={"User-Agent": "ContentOS-Diagnostic/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = json.loads(resp.read().decode("utf-8"))
    auth = root.get("authentication") or {}
    app_pw = auth.get("application-passwords")
    print("REST API: reachable")
    print("Application Passwords advertised by WordPress:", "YES" if app_pw else "NO")
    if app_pw:
        endpoints = app_pw.get("endpoints") or {}
        if endpoints:
            print("Application Password authorization endpoint: present")
except Exception as e:
    print("REST API public-index check failed:", repr(e))

print("\nAuthenticated user check")
print("------------------------")
try:
    result = KeysShopAdapter().validate_connection()
    print("SUCCESS: connected to Keys-Shop WordPress")
    print(f"User: {result.get('name') or 'unknown'} (ID {result.get('user_id')})")
    print("No post was created or published.")
except WordPressError as e:
    message = str(e)
    print("FAILED: WordPress rejected the connection")
    print(message)
    if "rest_not_logged_in" in message:
        print("\nDIAGNOSIS: WordPress did not see an authenticated Basic-Auth user.")
        print("If Application Passwords above says YES and the password is correct,")
        print("the Authorization header is being stripped before WordPress/PHP.")
    sys.exit(2)
except Exception as e:
    print("FAILED: unexpected error")
    print(repr(e))
    sys.exit(3)
