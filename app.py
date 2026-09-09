"""Dolla Content Desk — local UI over the existing dolla_content engine.

The engine remains the source of truth for generation, quality, claims, rendering, ramping and
publishing. This app only provides a friendlier workflow around those calls.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CONTENT_REPO = Path(
    os.environ.get(
        "CONTENT_REPO",
        Path(__file__).resolve().parent.parent / "dollacasino-content",
    )
).resolve()
sys.path.insert(0, str(CONTENT_REPO / "src"))

from dolla_content.models import Brief                       # noqa: E402
from dolla_content.quality_gate import run as gate_run       # noqa: E402
from dolla_content.render import render as render_page       # noqa: E402
from dolla_content.ramp import daily_cap                     # noqa: E402
from dolla_content import generate as gen                    # noqa: E402
from dolla_content.publish import run_publish                # noqa: E402

QUEUE = CONTENT_REPO / "content" / "queue.json"
QUEUE_FALLBACK = CONTENT_REPO / "content" / "queue.sample.json"
PUBLISHED = CONTENT_REPO / "content" / "published.json"
GUIDE_IMAGE_DIR = CONTENT_REPO / "static" / "img" / "guides"
SITE_BASE = os.environ.get("SITE_BASE", "https://dollacasino.com").rstrip("/")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "svg"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


def load_queue() -> list[Brief]:
    path = QUEUE if QUEUE.exists() else QUEUE_FALLBACK
    if not path.exists():
        return []
    return [Brief.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def save_queue(briefs: list[Brief]) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(
        json.dumps([b.to_dict() for b in briefs], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_published() -> dict:
    return json.loads(PUBLISHED.read_text(encoding="utf-8")) if PUBLISHED.exists() else {}


def next_slot(queue: list[Brief]) -> str:
    counts: dict[str, int] = {}
    for b in queue:
        if b.publish_date:
            counts[b.publish_date] = counts.get(b.publish_date, 0) + 1
    d = date.today()
    for _ in range(400):
        iso = d.isoformat()
        if counts.get(iso, 0) < daily_cap(d):
            return iso
        d += timedelta(days=1)
    return date.today().isoformat()


def published_bodies() -> list[str]:
    return [v.get("body", "") for v in load_published().values()] + [
        b.body_md for b in load_queue() if b.body_md
    ]


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:90]


def brief_from_form(f) -> Brief:
    title = f.get("title", "").strip()
    slug = f.get("slug", "").strip() or slugify(title or f.get("keyword", ""))
    return Brief(
        slug=slug,
        title=title,
        meta_description=f.get("meta", "").strip(),
        h1=f.get("h1", "").strip() or title,
        body_md=f.get("body", "").strip(),
        primary_keyword=f.get("keyword", "").strip(),
        angle=f.get("angle", "").strip(),
        game=f.get("game", "").strip(),
        target_market=f.get("market", "US").strip(),
        publish_date=f.get("publish_date", "").strip(),
        image=f.get("image", "").strip(),
        alt=f.get("alt", "").strip(),
        intent=f.get("intent", "informational").strip(),
        why_dolla=f.get("why", "").strip(),
    )


def save_image_bytes(data: bytes, filename: str, slug_hint: str = "guide") -> str:
    filename = secure_filename(filename or "pasted-image.png")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image type: .{ext}")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image is larger than 5 MB")
    GUIDE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    stem = slugify(slug_hint) or "guide"
    candidate = GUIDE_IMAGE_DIR / f"{stem}.{ext}"
    n = 2
    while candidate.exists():
        candidate = GUIDE_IMAGE_DIR / f"{stem}-{n}.{ext}"
        n += 1
    candidate.write_bytes(data)
    return f"{SITE_BASE}/img/guides/{candidate.name}"


def process_image_upload(brief: Brief) -> str | None:
    upload = request.files.get("image_file")
    if not upload or not upload.filename:
        return None
    data = upload.read(MAX_IMAGE_BYTES + 1)
    brief.image = save_image_bytes(data, upload.filename, brief.slug or brief.title)
    return brief.image


def queue_brief(brief: Brief) -> Brief:
    queue = load_queue()
    brief.publish_date = brief.publish_date or next_slot(queue)
    brief.status = "queued"
    queue = [b for b in queue if b.slug != brief.slug] + [brief]
    save_queue(queue)
    return brief


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(CONTENT_REPO), *args],
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )


def publish_and_push() -> dict:
    report = run_publish()

    # Stage only files owned by the content workflow, avoiding unrelated local work.
    paths = {
        "content/queue.json",
        "content/published.json",
        "static/index.html",
        "static/sitemap.xml",
    }
    paths.update(f"static/guides/{slug}.html" for slug in report.get("publishing", []))

    img_status = run_git("status", "--porcelain", "--", "static/img/guides")
    if img_status.returncode == 0:
        for line in img_status.stdout.splitlines():
            rel = line[3:].strip().replace("\\", "/")
            if rel.startswith("static/img/guides/"):
                paths.add(rel)

    add = run_git("add", "--", *sorted(paths))
    if add.returncode != 0:
        raise RuntimeError(add.stderr.strip() or "git add failed")

    diff = run_git("diff", "--cached", "--quiet")
    committed = False
    if diff.returncode == 1:
        commit = run_git("commit", "-m", f"Publish Dolla content {date.today().isoformat()}")
        if commit.returncode != 0:
            raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")
        committed = True
    elif diff.returncode != 0:
        raise RuntimeError(diff.stderr.strip() or "git diff failed")

    push = run_git("push")
    if push.returncode != 0:
        raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push failed")

    return {"report": report, "committed": committed}


def show_review(brief: Brief, error: str | None = None, notice: str | None = None):
    result = gate_run(brief, published_bodies=published_bodies())
    brief = result.fixed_brief or brief
    return render_template(
        "review.html",
        brief=brief,
        result=result,
        preview=render_page(brief).html,
        error=error,
        notice=notice,
    )


@app.route("/")
def dashboard():
    queue = load_queue()
    published = load_published()
    upcoming = sorted(
        [b for b in queue if b.body_md and b.slug not in published],
        key=lambda b: b.publish_date or "9999",
    )
    return render_template(
        "dashboard.html",
        cap_today=daily_cap(date.today()),
        queued=len(upcoming),
        drafts=len([b for b in queue if not b.body_md]),
        live=len(published),
        upcoming=upcoming[:40],
        published=list(reversed(list(published.values())))[:25],
        gemini_ready=bool(os.environ.get("GEMINI_API_KEY")),
        content_repo_ok=CONTENT_REPO.exists(),
        site_base=SITE_BASE,
    )


@app.route("/feed", methods=["GET", "POST"])
def feed():
    if request.method == "GET":
        return render_template("feed.html")

    brief = brief_from_form(request.form)
    try:
        process_image_upload(brief)
    except ValueError as exc:
        return show_review(brief, error=str(exc))

    error = None
    if request.form.get("mode") == "generate" and not brief.body_md:
        try:
            brief, _ = gen.generate(brief, published_bodies=published_bodies())
        except gen.GenerationError as exc:
            error = str(exc)
    return show_review(brief, error=error)


@app.route("/review", methods=["POST"])
def review():
    brief = brief_from_form(request.form)
    try:
        process_image_upload(brief)
    except ValueError as exc:
        return show_review(brief, error=str(exc))
    return show_review(brief, notice="Quality gate re-run on your edits.")


@app.route("/queue", methods=["POST"])
def enqueue():
    brief = Brief.from_dict(json.loads(request.form["brief_json"]))
    result = gate_run(brief, published_bodies=published_bodies())
    if not result.ok:
        return show_review(brief, error="Still blocked — fix the blocking issues before queueing.")
    queue_brief(result.fixed_brief or brief)
    return redirect(url_for("dashboard"))


@app.route("/publish-push", methods=["POST"])
def publish_push():
    brief = Brief.from_dict(json.loads(request.form["brief_json"]))
    result = gate_run(brief, published_bodies=published_bodies())
    if not result.ok:
        return show_review(brief, error="Still blocked — fix the blocking issues before publishing.")

    brief = queue_brief(result.fixed_brief or brief)
    try:
        outcome = publish_and_push()
    except Exception as exc:
        return show_review(brief, error=f"Article is safely queued, but Publish & Push failed: {exc}")

    report = outcome["report"]
    if brief.slug in report.get("publishing", []):
        notice = f"Published and pushed. Cloudflare should deploy /guides/{brief.slug} shortly."
    else:
        notice = (
            "Queued and pushed successfully. The publisher kept it in the ramp schedule instead "
            f"of publishing today (cap {report.get('cap')}, due {report.get('due')})."
        )
    return show_review(brief, notice=notice)


@app.route("/upload-image", methods=["POST"])
def upload_image():
    upload = request.files.get("image")
    if not upload:
        return jsonify({"ok": False, "error": "No image received"}), 400
    try:
        data = upload.read(MAX_IMAGE_BYTES + 1)
        url = save_image_bytes(data, upload.filename or "pasted-image.png", request.form.get("slug", "guide"))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "url": url})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True)
