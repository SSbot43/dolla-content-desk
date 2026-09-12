from __future__ import annotations
import base64
import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

class WordPressError(RuntimeError):
    pass

class WordPressClient:
    def __init__(self, base_url: str, username: str, application_password: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api = self.base_url + "/wp-json/wp/v2"
        token = base64.b64encode(f"{username}:{application_password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "User-Agent": "ContentOS/0.1"}
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None, headers: dict | None = None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req_headers = dict(self.headers)
        if payload is not None:
            req_headers["Content-Type"] = "application/json"
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(self.api + path, data=data, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise WordPressError(f"WordPress HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise WordPressError(f"WordPress connection failed: {e}") from e

    def auth_check(self):
        return self._request("GET", "/users/me?context=edit")

    def list_categories(self, per_page: int = 100):
        return self._request("GET", f"/categories?per_page={per_page}")

    def list_tags(self, per_page: int = 100):
        return self._request("GET", f"/tags?per_page={per_page}")

    def find_post_by_slug(self, slug: str):
        result = self._request("GET", "/posts?slug=" + urllib.parse.quote(slug))
        return result[0] if result else None

    def create_post(self, payload: dict):
        return self._request("POST", "/posts", payload)

    def update_post(self, post_id: int, payload: dict):
        return self._request("POST", f"/posts/{post_id}", payload)

    def upload_media(self, file_path: str, alt_text: str = ""):
        path = Path(file_path)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        req_headers = dict(self.headers)
        req_headers.update({
            "Content-Type": mime,
            "Content-Disposition": f'attachment; filename="{path.name}"',
        })
        req = urllib.request.Request(self.api + "/media", data=path.read_bytes(), headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                media = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise WordPressError(f"Media upload HTTP {e.code}: {detail}") from e
        if alt_text:
            media = self._request("POST", f"/media/{media['id']}", {"alt_text": alt_text})
        return media
