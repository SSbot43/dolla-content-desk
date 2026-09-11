from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "dist" / "Keys-Shop-Content-Desk"
ZIP = ROOT / "dist" / "Keys-Shop-Content-Desk.zip"

AI_KEYS = {
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
}


def read_env(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def parse_env(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def write_staff_env() -> None:
    keys_env = parse_env(read_env(ROOT / ".env.keys-shop"))
    dolla_env = parse_env(read_env(ROOT / ".env"))
    for key in AI_KEYS:
        if not keys_env.get(key) and dolla_env.get(key):
            keys_env[key] = dolla_env[key]

    preferred = [
        "KEYS_WP_URL",
        "KEYS_WP_USERNAME",
        "KEYS_WP_APP_PASSWORD",
        "KEYS_CONTENT_OS_SECRET",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "KEYS_DESK_PORT",
    ]
    lines = ["# Keys-Shop Content Desk only. Do not share this file outside authorised staff."]
    for key in preferred:
        if key in keys_env:
            lines.append(f"{key}={keys_env[key]}")
    for key, value in keys_env.items():
        if key not in preferred:
            lines.append(f"{key}={value}")
    (OUT / ".env.keys-shop").write_text("\n".join(lines) + "\n", encoding="utf-8")


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    # Keys-Shop runtime only.
    for name in [
        "keys_app.py",
        "requirements.txt",
        "START_KEYS_CONTENT_DESK.bat",
        "KEYS_SHOP_SETUP.md",
    ]:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, OUT / name)

    copy_tree(ROOT / "content_os", OUT / "content_os")

    (OUT / "templates").mkdir(exist_ok=True)
    for src in (ROOT / "templates").glob("keys_*.html"):
        shutil.copy2(src, OUT / "templates" / src.name)

    # Reuse styling assets only; no Dolla drafts/data/credentials are copied.
    copy_tree(ROOT / "static", OUT / "static")

    write_staff_env()

    readme = """# Keys-Shop Content Desk — Staff Package

This folder is intentionally isolated from the Dolla Content Desk.

## Start
Double-click `START_KEYS_CONTENT_DESK.bat`.
The desk opens at `http://127.0.0.1:5002/batch`.

## Scope
Use this desk only for Keys-Shop article generation, review, queueing and WordPress publishing.
It contains no Dolla queue, Dolla credentials, Dolla publisher configuration, or Dolla browser drafts.

## Important
- Do not share `.env.keys-shop`.
- Use `Publish immediately` only for genuinely time-sensitive content.
- Review BLOCKED articles before using an editorial override.
- Product/category targets should be selected from the live search rather than typed as arbitrary URLs.
"""
    (OUT / "STAFF_README.md").write_text(readme, encoding="utf-8")

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in OUT.rglob("*"):
            if path.is_file():
                zf.write(path, Path("Keys-Shop-Content-Desk") / path.relative_to(OUT))

    print(f"Created: {ZIP}")
    print("This ZIP contains Keys-Shop credentials copied locally from your env files. Treat it as sensitive.")


if __name__ == "__main__":
    main()
