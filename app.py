"""dolla-content-desk — local Flask dashboard for the dollacasino.com content sprint.

One screen to: drop keywords -> Gemini writes -> quality gate -> queue -> (publisher ships on the
ramp). Wraps the proven `dolla_content` backbone; adds no content logic of its own.

Run:
    pip install -r requirements.txt
    # point at the content repo (default assumes it's a sibling folder)
    set CONTENT_REPO=E:/Claude work/dollacasino-content
    set GEMINI_API_KEY=...            # from Google AI Studio
    python app.py                      # http://127.0.0.1:5000
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

try:
    from dotenv import load_dotenv
    load_dotenv()  # read .env in this folder (GEMINI_API_KEY, CONTENT_REPO, LAUNCH_DATE, ...)
except ImportError:
    pass

# --- wire in the backbone (sibling repo) ---
CONTENT_REPO = Path(os.environ.get("CONTENT_REPO", Path(__file__).resolve().parent.parent / "dollacasino-content"))
sys.path.insert(0, str(CONTENT_REPO / "src"))

from dolla_content.models import Brief                       # noqa: E402
from dolla_content.quality_gate import run as gate_run       # noqa: E402
from dolla_content.render import render as render_page       # noqa: E402
from dolla_content.ramp import daily_cap                     # noqa: E402
from dolla_content import generate as gen                    # noqa: E402

QUEUE = CONTENT_REPO / "content" / "queue.json"
QUEUE_FALLBACK = CONTENT_REPO / "content" / "queue.sample.json"
PUBLISHED = CONTENT_REPO / "content" / "published.json"

app = Flask(__name__)


# ---------- queue helpers ----------
def load_queue() -> list[Brief]:
    path = QUEUE if QUEUE.exists() else QUEUE_FALLBACK
    if not path.exists():
        return []
    return [Brief.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def save_queue(briefs: list[Brief]) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps([b.to_dict() for b in briefs], indent=2), encoding="utf-8")


def load_published() -> dict:
    return json.loads(PUBLISHED.read_text(encoding="utf-8")) if PUBLISHED.exists() else {}


def next_slot(queue: list[Brief]) -> str:
    """First date (from today) whose queued count is below that day's ramp cap."""
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
    return [v.get("body", "") for v in load_published().values()] + \
           [b.body_md for b in load_queue() if b.body_md]


# ---------- routes ----------
@app.route("/")
def dashboard():
    queue = load_queue()
    published = load_published()
    upcoming = sorted([b for b in queue if b.body_md], key=lambda b: b.publish_date or "9999")
    return render_template(
        "dashboard.html",
        cap_today=daily_cap(date.today()),
        queued=len([b for b in queue if b.body_md]),
        drafts=len([b for b in queue if not b.body_md]),
        live=len(published),
        upcoming=upcoming[:25],
        published=list(published.values())[:25],
        gemini_ready=bool(os.environ.get("GEMINI_API_KEY")),
    )


@app.route("/feed", methods=["GET", "POST"])
def feed():
    if request.method == "GET":
        return render_template("feed.html")

    f = request.form
    brief = Brief(
        slug=f.get("slug", "").strip(),
        title=f.get("title", "").strip(),
        meta_description=f.get("meta", "").strip(),
        h1=f.get("h1", "").strip() or f.get("title", "").strip(),
        body_md=f.get("body", "").strip(),
        primary_keyword=f.get("keyword", "").strip(),
        angle=f.get("angle", "").strip(),
        game=f.get("game", "").strip(),
        target_market=f.get("market", "US").strip(),
        intent=f.get("intent", "").strip(),
        why_dolla=f.get("why", "").strip(),
        image=f.get("image", "").strip(),
        alt=f.get("alt", "").strip(),
    )

    error = None
    if f.get("mode") == "generate" and not brief.body_md:
        try:
            brief, _ = gen.generate(brief, published_bodies=published_bodies())
        except gen.GenerationError as e:
            error = str(e)

    result = gate_run(brief, published_bodies=published_bodies())
    brief = result.fixed_brief or brief
    preview = render_page(brief).html
    return render_template("review.html", brief=brief, result=result, preview=preview, error=error)


@app.route("/queue", methods=["POST"])
def enqueue():
    f = request.form
    brief = Brief.from_dict(json.loads(f["brief_json"]))
    # gate again server-side — never trust the round-trip
    result = gate_run(brief, published_bodies=published_bodies())
    if not result.ok:
        preview = render_page(brief).html
        return render_template("review.html", brief=brief, result=result, preview=preview,
                               error="Still blocked — fix before queueing.")
    brief = result.fixed_brief or brief
    queue = load_queue()
    brief.publish_date = brief.publish_date or next_slot(queue)
    brief.status = "queued"
    queue = [b for b in queue if b.slug != brief.slug] + [brief]  # replace-by-slug
    save_queue(queue)
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True)
