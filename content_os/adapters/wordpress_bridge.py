from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request


class ContentBridgeError(RuntimeError):
    pass


class ContentBridgeClient:
    """Signed client for the small WordPress Content OS bridge plugin."""

    def __init__(self, base_url: str, secret: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api = self.base_url + "/wp-json/keys-content-os/v1"
        self.secret = secret.strip()
        self.timeout = timeout

    @staticmethod
    def _query_string(params: dict | None) -> str:
        if not params:
            return ""
        items = sorted((str(k), str(v)) for k, v in params.items())
        return urllib.parse.urlencode(items, quote_via=urllib.parse.quote, safe="")

    def _headers(self, method: str, route: str, body: bytes, query: str, extra: dict | None = None) -> dict:
        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(body).hexdigest()
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
        canonical = f"{method.upper()}\n{route}\n{timestamp}\n{body_hash}\n{query_hash}"
        signature = hmac.new(self.secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        headers = {
            "User-Agent": "ContentOS/0.1",
            "X-Content-Desk-Timestamp": timestamp,
            "X-Content-Desk-Signature": signature,
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 payload: dict | None = None, raw_body: bytes | None = None,
                 headers: dict | None = None):
        route = "/keys-content-os/v1" + path
        query = self._query_string(params)
        url = self.api + path + (("?" + query) if query else "")
        if raw_body is not None:
            body = raw_body
        elif payload is not None:
            body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        else:
            body = b""
        req_headers = self._headers(method, route, body, query, headers)
        if payload is not None:
            req_headers["Content-Type"] = "application/json"
        data = body if method.upper() in {"POST", "PUT", "PATCH"} else None
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise ContentBridgeError(f"Bridge HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise ContentBridgeError(f"Bridge connection failed: {e}") from e

    def ping(self) -> dict:
        return self._request("GET", "/ping")

    def search_products(self, query: str, limit: int = 15) -> list[dict]:
        return self._request("GET", "/products", params={"q": query, "limit": limit})

    def search_categories(self, query: str, limit: int = 15) -> list[dict]:
        return self._request("GET", "/categories", params={"q": query, "limit": limit})

    def create_post(self, payload: dict) -> dict:
        return self._request("POST", "/posts", payload=payload)

    def upload_media(self, data: bytes, filename: str, alt_text: str = "") -> dict:
        return self._request(
            "POST", "/media", raw_body=data,
            headers={"Content-Type": "application/octet-stream",
                     "X-Content-Desk-Filename": filename,
                     "X-Content-Desk-Alt": alt_text},
        )
