from __future__ import annotations
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except Exception:
    pass

from content_os.adapters.keys_shop import KeysShopAdapter
from content_os.adapters.wordpress import WordPressError

required = ["KEYS_WP_URL", "KEYS_WP_USERNAME", "KEYS_WP_APP_PASSWORD"]
missing = [k for k in required if not os.environ.get(k, "").strip()]
if missing:
    print("FAILED: missing from .env: " + ", ".join(missing))
    sys.exit(1)

try:
    result = KeysShopAdapter().validate_connection()
    print("SUCCESS: connected to Keys-Shop WordPress")
    print(f"User: {result.get('name') or 'unknown'} (ID {result.get('user_id')})")
    print("No post was created or published.")
except WordPressError as e:
    print("FAILED: WordPress rejected the connection")
    print(str(e))
    sys.exit(2)
except Exception as e:
    print("FAILED: unexpected error")
    print(repr(e))
    sys.exit(3)
