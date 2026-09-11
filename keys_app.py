from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

ROOT = Path(__file__).resolve().parent
if load_dotenv:
    load_dotenv(ROOT / ".env.keys-shop", override=True)

from content_os.adapters.wordpress_bridge import ContentBridgeClient, ContentBridgeError
from content_os.models import ContentItem, LinkTarget
from content_os.quality import run as quality_run

app = Flask(__name__)


def bridge() -> ContentBridgeClient:
    return ContentBridgeClient(
        os.environ.get("KEYS_WP_URL", "https://keys-shop.in"),
        os.environ.get("KEYS_CONTENT_OS_SECRET", ""),
    )


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:90]


def target_from_json(raw: str) -> LinkTarget | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return LinkTarget(**{k: data.get(k, "") for k in LinkTarget.__dataclass_fields__})
    except Exception:
        return None


def build_item(form) -> ContentItem:
    title = (form.get("title") or "").strip()
    primary = target_from_json((form.get("primary_target") or "").strip())
    supporting = []
    try:
        for row in json.loads(form.get("supporting_targets") or "[]"):
            if isinstance(row, dict):
                supporting.append(LinkTarget(**{k: row.get(k, "") for k in LinkTarget.__dataclass_fields__}))
    except Exception:
        pass

    internal_links = [t.url for t in ([primary] if primary else []) + supporting if t and t.url]
    return ContentItem(
        slug=(form.get("slug") or "").strip() or slugify(title),
        title=title,
        body_md=(form.get("body") or "").strip(),
        meta_title=(form.get("meta_title") or "").strip(),
        meta_description=(form.get("meta_description") or "").strip(),
        primary_keyword=(form.get("primary_keyword") or "").strip(),
        excerpt=(form.get("excerpt") or "").strip(),
        status="draft",
        internal_links=internal_links,
        primary_target=primary,
        supporting_targets=supporting,
    )


@app.get("/")
def home():
    empty = ContentItem(slug="", title="")
    result = quality_run(empty)
    return render_template("keys_review.html", item=empty, result=result, notice="", error="")


@app.post("/review")
def review():
    item = build_item(request.form)
    known_urls = set(item.internal_links)
    result = quality_run(item, known_urls=known_urls)
    return render_template("keys_review.html", item=item, result=result, notice="Quality gate re-run.", error="")


@app.get("/api/targets")
def targets():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    try:
        client = bridge()
        products = client.search_products(q, limit=12)
        categories = client.search_categories(q, limit=8)
        return jsonify(products + categories)
    except ContentBridgeError as e:
        return jsonify({"error": str(e)}), 502


@app.post("/create-draft")
def create_draft():
    item = build_item(request.form)
    result = quality_run(item, known_urls=set(item.internal_links))
    if not result.ok:
        return render_template("keys_review.html", item=item, result=result, notice="", error="Draft blocked by quality gate."), 400

    payload = {
        "title": item.title,
        "slug": item.slug,
        "content": item.body_html or item.body_md,
        "excerpt": item.excerpt or item.meta_description,
        "status": "draft",
        "meta_title": item.meta_title,
        "meta_description": item.meta_description,
    }
    created = bridge().create_post(payload)
    return render_template(
        "keys_review.html",
        item=item,
        result=result,
        notice=f"Draft created in WordPress — Post ID {created.get('id')}",
        error="",
    )


if __name__ == "__main__":
    port = int(os.environ.get("KEYS_DESK_PORT", "5002"))
    app.run(host="127.0.0.1", port=port, debug=False)
