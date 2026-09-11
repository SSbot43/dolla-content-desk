from __future__ import annotations
import os
import sys
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env.keys-shop"

try:
    from dotenv import load_dotenv
    load_dotenv(ENV_FILE, override=True)
except Exception:
    pass

from content_os.adapters.wordpress_bridge import ContentBridgeClient, ContentBridgeError

required = ["KEYS_WP_URL", "KEYS_CONTENT_OS_SECRET"]
missing = [k for k in required if not os.environ.get(k, "").strip()]
if missing:
    print(f"FAILED: missing from {ENV_FILE.name}: " + ", ".join(missing))
    sys.exit(1)

base = os.environ["KEYS_WP_URL"].rstrip("/")
secret = os.environ["KEYS_CONTENT_OS_SECRET"].strip()
client = ContentBridgeClient(base, secret)

print("Keys-Shop Content OS bridge test")
print("--------------------------------")
try:
    ping = client.ping()
    print("SUCCESS: signed bridge connection works")
    print(f"Bridge version: {ping.get('version', 'unknown')}")
    print(f"Site: {ping.get('site', base)}")
except ContentBridgeError as e:
    print("FAILED: bridge connection rejected")
    print(str(e))
    sys.exit(2)

print("\nLive WooCommerce product search")
print("-------------------------------")
try:
    query = os.environ.get("KEYS_TEST_PRODUCT_QUERY", "office").strip() or "office"
    products = client.search_products(query, limit=5)
    print(f"Search: {query!r}")
    print(f"Matches: {len(products)}")
    for product in products:
        title = product.get("title") or "(untitled)"
        sku = product.get("sku") or "no SKU"
        category = product.get("category") or "no category"
        print(f"- {title} | {sku} | {category}")
    if not products:
        print("Bridge works, but this search returned no products. That is not an auth failure.")
except ContentBridgeError as e:
    print("FAILED: product search rejected")
    print(str(e))
    sys.exit(3)

print("\nPASS: connection + product search tested. No post was created or published.")
