from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OWNER = "SSbot43"
REPO = "dolla-content-desk"
BRANCH = "content-os-keys-shop-mvp"
RAW_BASE = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}"
MANIFEST_URL = f"{RAW_BASE}/keys_staff_manifest.json"
TIMEOUT = 12


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Keys-Shop-Content-Desk-Updater/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def _safe_path(rel: str) -> Path:
    rel = rel.replace("\\", "/").lstrip("/")
    target = (ROOT / rel).resolve()
    if ROOT.resolve() not in target.parents and target != ROOT.resolve():
        raise ValueError(f"Unsafe update path: {rel}")
    return target


def _write_atomic(path: Path, data: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return False
    with tempfile.NamedTemporaryFile(delete=False, dir=str(path.parent), prefix=path.name + ".", suffix=".tmp") as fh:
        fh.write(data)
        tmp = Path(fh.name)
    os.replace(tmp, path)
    return True


def main() -> int:
    try:
        manifest = json.loads(_get(MANIFEST_URL).decode("utf-8"))
        files = manifest.get("files") or []
        if not isinstance(files, list):
            raise ValueError("Invalid update manifest")

        changed = 0
        for rel in files:
            rel = str(rel).strip()
            if not rel or rel in {".env", ".env.keys-shop"}:
                continue
            data = _get(f"{RAW_BASE}/{rel}")
            if _write_atomic(_safe_path(rel), data):
                changed += 1

        # Keep a local copy of the manifest for troubleshooting/version visibility.
        _write_atomic(ROOT / "keys_staff_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"))
        if changed:
            print(f"[Keys-Shop updater] Updated {changed} file(s).")
        else:
            print("[Keys-Shop updater] Already up to date.")
        return 0
    except Exception as exc:
        # Staff should still be able to work if GitHub or the internet is temporarily unavailable.
        print(f"[Keys-Shop updater] Update skipped: {exc}")
        print("[Keys-Shop updater] Starting the installed version instead.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
