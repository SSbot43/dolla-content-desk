from __future__ import annotations

import json
import os
import re
from pathlib import Path

from flask import Flask, jsonify, render_template, request

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

ROOT = Path(__file__).resolve().parent
if load_dotenv:
    # Reuse shared AI-provider keys from the existing Dolla desk, then let the
    # Keys-Shop-specific file override only site credentials/settings.
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(ROOT / ".env.keys-shop", override=True)

from content_os.adapters.wordpress_bridge import ContentBridgeClient, ContentBridgeError
from content_os.keys_generation import GenerationError, generate_article, generate_topics
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
        body_html=(form.get("body_html") or "").strip(),
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


def item_from_ai(data: dict, primary: dict | None, supporting: list[dict] | None = None) -> ContentItem:
    p = LinkTarget(**{k: (primary or {}).get(k, "") for k in LinkTarget.__dataclass_fields__}) if primary else None
    supports = [LinkTarget(**{k: x.get(k, "") for k in LinkTarget.__dataclass_fields__}) for x in (supporting or [])]
    links = [x.url for x in ([p] if p else []) + supports if x and x.url]
    generated_body = str(data.get("body_html") or data.get("body_md") or data.get("body") or "").strip()
    return ContentItem(
        slug=str(data.get("slug") or slugify(str(data.get("title") or ""))),
        title=str(data.get("title") or ""),
        body_html=generated_body,
        body_md=generated_body,
        meta_title=str(data.get("meta_title") or ""),
        meta_description=str(data.get("meta_description") or ""),
        primary_keyword=str(data.get("primary_keyword") or ""),
        excerpt=str(data.get("excerpt") or ""),
        internal_links=links,
        primary_target=p,
        supporting_targets=supports,
    )


@app.get("/")
def home():
    empty = ContentItem(slug="", title="")
    result = quality_run(empty)
    return render_template("keys_review.html", item=empty, result=result, notice="", error="")


@app.get("/batch")
def batch():
    return render_template("keys_batch.html")


@app.post("/review")
def review():
    item = build_item(request.form)
    known_urls = set(item.internal_links)
    result = quality_run(item, known_urls=known_urls)
    return render_template("keys_review.html", item=item, result=result, notice="Quality gate re-run.", error="")


@app.post("/review-generated")
def review_generated():
    try:
        data = json.loads(request.form.get("article_json") or "{}")
        primary = json.loads(request.form.get("primary_target") or "null")
        supporting = json.loads(request.form.get("supporting_targets") or "[]")
        item = item_from_ai(data, primary, supporting)
    except Exception as exc:
        empty = ContentItem(slug="", title="")
        return render_template("keys_review.html", item=empty, result=quality_run(empty), notice="", error=f"Could not open generated draft: {exc}"), 400
    result = quality_run(item, known_urls=set(item.internal_links))
    return render_template("keys_review.html", item=item, result=result, notice="Generated article opened for review.", error="")


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


@app.post("/api/generate-topics")
def api_generate_topics():
    data = request.get_json(silent=True) or {}
    try:
        topics, provider = generate_topics(data.get("target"), int(data.get("count") or 20), str(data.get("seed") or ""))
        return jsonify({"topics": topics, "provider": provider})
    except GenerationError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/generate-article")
def api_generate_article():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    try:
        article, provider = generate_article(title, data.get("target"), data.get("supporting") or [])
        item = item_from_ai(article, data.get("target"), data.get("supporting") or [])
        gate = quality_run(item, known_urls=set(item.internal_links))
        return jsonify({
            "article": article,
            "provider": provider,
            "gate_ok": gate.ok,
            "issues": [{"code": i.code, "detail": i.detail, "blocking": i.blocking} for i in gate.issues],
        })
    except GenerationError as exc:
        return jsonify({"error": str(exc)}), 400


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
