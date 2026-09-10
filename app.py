"""Dolla Content Desk — local UI over the existing dolla_content engine.

The engine remains the source of truth for article generation, quality, claims, rendering, ramping
and publishing. This app adds a friendly headline-first workflow, trend discovery, image handling,
review, and one-click Git publishing around those calls.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

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
APP_BASE = os.environ.get("APP_BASE", "https://dolla.fo").rstrip("/")
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "svg"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024

DESTINATIONS = [
    {"slug": "", "label": "Dolla homepage / general"},
    {"slug": "plinko", "label": "Plinko"},
    {"slug": "mines", "label": "Mines"},
    {"slug": "crash", "label": "Crash"},
    {"slug": "voidrun", "label": "VOID Run"},
    {"slug": "dice", "label": "Dice"},
    {"slug": "limbo", "label": "Limbo"},
    {"slug": "keno", "label": "Keno"},
    {"slug": "hilo", "label": "Hi/Lo"},
    {"slug": "slots", "label": "Slots"},
    {"slug": "blackjack", "label": "Blackjack"},
    {"slug": "roulette", "label": "Roulette"},
    {"slug": "olympus", "label": "Gods of Olympus"},
    {"slug": "inferno", "label": "Inferno Vault"},
    {"slug": "bigscore", "label": "The Big Score"},
    {"slug": "chariot", "label": "Chariot Race"},
    {"slug": "penalty", "label": "Penalty Shooter"},
    {"slug": "lucky7", "label": "Lucky 7"},
    {"slug": "dond", "label": "Deal or No Deal"},
]

TREND_FEEDS = [
    (
        "Game trends & releases",
        '(casino game OR slot OR crash game OR blackjack OR roulette OR plinko) when:7d',
    ),
    (
        "Crypto casino & player UX",
        '("crypto casino" OR "crypto gambling" OR casino withdrawal OR casino deposit) when:7d',
    ),
    (
        "Player questions & market themes",
        '("online casino" OR "casino games") (demo OR no-KYC OR mobile OR crypto) when:7d',
    ),
]
_TREND_CACHE: dict[str, object] = {"at": 0.0, "ideas": [], "error": None}
TREND_CACHE_SECONDS = 15 * 60

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


def comparison_bodies(exclude_slug: str = "") -> list[str]:
    published = [
        v.get("body", "")
        for slug, v in load_published().items()
        if slug != exclude_slug and v.get("body")
    ]
    queued = [
        b.body_md
        for b in load_queue()
        if b.body_md and b.slug != exclude_slug
    ]
    return published + queued


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


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:90]


def destination_label(slug: str) -> str:
    return next((d["label"] for d in DESTINATIONS if d["slug"] == slug), slug or "Dolla")


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


def _clean_json_object(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini did not return a JSON object")
    return json.loads(text[start:end + 1])


def _fallback_meta(title: str, game: str) -> str:
    subject = destination_label(game)
    text = (
        f"{title}. A practical Dolla guide to {subject}, free-play practice, crypto basics "
        "and the key things players should check before real play."
    )
    if len(text) < 110:
        text += " Includes clear controls, safety checks and responsible-play context."
    return text[:155].rstrip(" ,;:-")


def complete_headline_brief(brief: Brief, trend_context: str = "") -> Brief:
    """Fill optional SEO brief fields for headline-first mode without changing the engine."""
    brief.h1 = brief.h1 or brief.title
    brief.intent = brief.intent or "informational"
    game_label = destination_label(brief.game)

    # Destination copy is deliberately deterministic. The writer may improve the keyword/angle,
    # but it must never invent a different Dolla game and hand a contradictory brief to the article
    # generator (for example, game=voidrun with an Olympus CTA).
    brief.meta_description = brief.meta_description or _fallback_meta(brief.title, brief.game)
    brief.why_dolla = brief.why_dolla or (
        f"Dolla offers a direct {game_label} experience with free-play demo access."
        if brief.game else
        "Dolla offers free-play demos, crypto play and a standard no-KYC flow."
    )

    missing = not all([brief.primary_keyword, brief.angle])
    if missing and os.environ.get("GEMINI_API_KEY", "").strip():
        try:
            from google import genai as google_genai

            context_line = (
                f"\nTrend inspiration: {trend_context}\n"
                "Treat it only as inspiration. Do not invent or repeat third-party numbers, wins, "
                "testimonials, release facts, or claims that are not independently present in the Dolla brief."
                if trend_context else ""
            )
            prompt = f"""Complete a compact SEO brief for an article on Dolla's editorial site.
The user supplied the headline, so DO NOT rewrite it.

Headline: {brief.title}
Target market: {brief.target_market}
Destination: {game_label}
Destination slug: {brief.game or 'homepage'}{context_line}

Return ONLY JSON with these keys:
primary_keyword: one natural search phrase, 2-6 words
angle: one short editorial angle

Allowed Dolla facts only:
- every public game has no-deposit demo/free-play
- demo credits are practice-only and cannot be withdrawn
- standard player flow does not require KYC
- eligible withdrawals are normally reviewed and approved within 5-10 minutes
- players should verify asset, network and wallet address before crypto transfers

Never mention RTP, house edge, odds, EV, symbol weights, guaranteed winnings, risk-free play,
provably-fair claims, invented player counts, testimonials, or guaranteed/instant withdrawals.
"""
            client = google_genai.Client(api_key=os.environ["GEMINI_API_KEY"].strip())
            model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
            resp = client.models.generate_content(model=model, contents=prompt)
            data = _clean_json_object(getattr(resp, "text", "") or "")
            brief.primary_keyword = brief.primary_keyword or str(data.get("primary_keyword", "")).strip()
            brief.angle = brief.angle or str(data.get("angle", "")).strip()
        except Exception:
            # Article generation still uses the engine's own retry/fallback path.
            pass

    brief.primary_keyword = brief.primary_keyword or re.sub(
        r"\b(the|a|an|and|or|of|to|for|in|on|with|why|how|what|is|are)\b",
        " ",
        brief.title.lower(),
    )
    brief.primary_keyword = re.sub(r"\s+", " ", brief.primary_keyword).strip()[:70] or brief.title[:70]
    brief.angle = brief.angle or (
        "clear first-party explainer tied naturally to Dolla; avoid unverified third-party claims"
    )
    return brief


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


def image_repo_path(image_url: str) -> str | None:
    if not image_url:
        return None
    name = Path(urlparse(image_url).path).name
    if not name:
        return None
    candidate = GUIDE_IMAGE_DIR / name
    if candidate.exists():
        return f"static/img/guides/{name}"
    return None


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


def commit_and_push(paths: set[str], message: str) -> bool:
    add = run_git("add", "--", *sorted(paths))
    if add.returncode != 0:
        raise RuntimeError(add.stderr.strip() or "git add failed")

    diff = run_git("diff", "--cached", "--quiet")
    committed = False
    if diff.returncode == 1:
        commit = run_git("commit", "-m", message)
        if commit.returncode != 0:
            raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "git commit failed")
        committed = True
    elif diff.returncode != 0:
        raise RuntimeError(diff.stderr.strip() or "git diff failed")

    push = run_git("push")
    if push.returncode != 0:
        raise RuntimeError(push.stderr.strip() or push.stdout.strip() or "git push failed")
    return committed


def push_queue(brief: Brief) -> bool:
    paths = {"content/queue.json"}
    image_path = image_repo_path(brief.image)
    if image_path:
        paths.add(image_path)
    return commit_and_push(paths, f"Queue Dolla guide {brief.slug}")


def publish_and_push(brief: Brief) -> dict:
    report = run_publish()
    paths = {
        "content/queue.json",
        "content/published.json",
        "static/index.html",
        "static/sitemap.xml",
    }
    paths.update(f"static/guides/{slug}.html" for slug in report.get("publishing", []))

    queued_by_slug = {b.slug: b for b in load_queue()}
    for slug in report.get("publishing", []):
        published_brief = queued_by_slug.get(slug)
        if published_brief:
            image_path = image_repo_path(published_brief.image)
            if image_path:
                paths.add(image_path)
    current_image = image_repo_path(brief.image)
    if current_image:
        paths.add(current_image)

    committed = commit_and_push(paths, f"Publish Dolla content {date.today().isoformat()}")
    return {"report": report, "committed": committed}


def show_review(brief: Brief, error: str | None = None, notice: str | None = None):
    result = gate_run(brief, published_bodies=comparison_bodies(brief.slug))
    brief = result.fixed_brief or brief
    return render_template(
        "review.html",
        brief=brief,
        result=result,
        preview=render_page(brief).html,
        error=error,
        notice=notice,
    )


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _too_similar_to_existing(title: str, existing: list[str]) -> bool:
    mine = _normalize_title(title)
    return any(SequenceMatcher(None, mine, _normalize_title(other)).ratio() >= 0.78 for other in existing)


def _guess_destination(text: str) -> str:
    t = text.lower()
    checks = [
        (("void run",), "voidrun"),
        (("crash", "crash game", "crash gambling", "crash casino"), "crash"),
        (("big heist", "vault breaker", "bank heist", "big score"), "bigscore"),
        (("inferno",), "inferno"),
        (("olympus", "zeus", "poseidon"), "olympus"),
        (("plinko",), "plinko"),
        (("mines", "mine game"), "mines"),
        (("blackjack",), "blackjack"),
        (("roulette",), "roulette"),
        (("keno",), "keno"),
        (("limbo",), "limbo"),
        (("dice",), "dice"),
        (("slot", "slots"), "slots"),
        (("higher lower", "hi lo", "hilo"), "hilo"),
    ]
    for needles, slug in checks:
        if any(n in t for n in needles):
            return slug
    return ""


def _safe_trend_headline(source_title: str, category: str) -> str:
    t = source_title.lower()
    if "crash" in t:
        return "Why Crash Games Keep Getting Attention From Online Casino Players"
    if "plinko" in t:
        return "Why Plinko Remains One of the Easiest Casino Games to Learn"
    if "slot" in t:
        return "What New Slot Releases Say About Where Online Casino Games Are Heading"
    if "blackjack" in t:
        return "Why Blackjack Keeps Getting New Digital Variations"
    if "roulette" in t:
        return "Why Roulette Still Works So Well as a Digital Casino Game"
    if "no kyc" in t or "no-kyc" in t:
        return "What No-KYC Casino Players Should Check Before They Play"
    if "withdraw" in t or "cashout" in t or "cash out" in t:
        return "What Crypto Casino Players Should Check Before Requesting a Withdrawal"
    if "deposit" in t or "wallet" in t or "bitcoin" in t or "crypto" in t:
        return "What Crypto Casino Players Should Check Before Depositing or Playing"
    if "demo" in t or "free play" in t or "free-play" in t:
        return "Why Free-Play Casino Demos Matter Before Real-Money Play"
    if "mobile" in t:
        return "What Makes a Casino Game Work Well on Mobile"
    if category == "Game trends & releases":
        return "What Is Changing in Online Casino Games Right Now"
    if category == "Crypto casino & player UX":
        return "What Crypto Casino Players Care About Most Right Now"
    return "What Online Casino Players Are Paying Attention to Right Now"


def _fetch_google_news(query: str, category: str, limit: int = 6) -> list[dict]:
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "DollaContentDesk/1.0"})
    with urllib.request.urlopen(req, timeout=7) as response:
        xml_data = response.read()
    root = ET.fromstring(xml_data)
    rows: list[dict] = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        source = (item.findtext("source") or "").strip()
        raw_date = (item.findtext("pubDate") or "").strip()
        published = raw_date
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date).date().isoformat()
            except Exception:
                pass
        if not title or not link:
            continue
        rows.append(
            {
                "category": category,
                "source_title": title,
                "source": source or "Google News",
                "source_url": link,
                "published": published,
                "headline": _safe_trend_headline(title, category),
                "game": _guess_destination(title),
            }
        )
    return rows


def load_trend_ideas(force: bool = False) -> tuple[list[dict], str | None]:
    now = time.time()
    cached_at = float(_TREND_CACHE.get("at", 0.0) or 0.0)
    if not force and now - cached_at < TREND_CACHE_SECONDS:
        return list(_TREND_CACHE.get("ideas", [])), _TREND_CACHE.get("error")  # type: ignore[arg-type]

    ideas: list[dict] = []
    errors: list[str] = []
    existing_titles = [
        str(v.get("title", ""))
        for v in load_published().values()
        if v.get("title")
    ] + [b.title for b in load_queue() if b.title]

    seen_headlines: set[str] = set()
    for category, query in TREND_FEEDS:
        try:
            rows = _fetch_google_news(query, category)
        except Exception as exc:
            errors.append(f"{category}: {exc}")
            continue
        for row in rows:
            headline_key = _normalize_title(row["headline"])
            if headline_key in seen_headlines:
                continue
            if _too_similar_to_existing(row["headline"], existing_titles):
                continue
            seen_headlines.add(headline_key)
            ideas.append(row)
            if len([i for i in ideas if i["category"] == category]) >= 4:
                break

    error = "; ".join(errors) if errors and not ideas else None
    _TREND_CACHE.update({"at": now, "ideas": ideas, "error": error})
    return ideas, error


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


@app.route("/ideas")
def ideas():
    force = request.args.get("refresh") == "1"
    trend_ideas, trend_error = load_trend_ideas(force=force)
    grouped = []
    for category, _ in TREND_FEEDS:
        grouped.append((category, [i for i in trend_ideas if i["category"] == category]))
    return render_template(
        "ideas.html",
        grouped=grouped,
        error=trend_error,
        destinations=DESTINATIONS,
    )


@app.route("/feed", methods=["GET", "POST"])
def feed():
    if request.method == "GET":
        prefill = {
            "mode": request.args.get("mode", "generate"),
            "title": request.args.get("title", ""),
            "game": request.args.get("game", ""),
            "market": request.args.get("market", "US"),
            "trend_context": request.args.get("trend_context", ""),
        }
        return render_template("feed.html", destinations=DESTINATIONS, prefill=prefill)

    brief = brief_from_form(request.form)
    try:
        process_image_upload(brief)
    except ValueError as exc:
        return show_review(brief, error=str(exc))

    error = None
    if request.form.get("mode") == "generate" and not brief.body_md:
        try:
            brief = complete_headline_brief(brief, request.form.get("trend_context", "").strip())
            brief, _ = gen.generate(brief, published_bodies=comparison_bodies(brief.slug))
        except gen.GenerationError as exc:
            error = str(exc)
        except Exception as exc:
            error = f"Could not prepare the Gemini brief: {exc}"
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
@app.route("/queue-local", methods=["POST"])
def queue_local():
    brief = Brief.from_dict(json.loads(request.form["brief_json"]))
    result = gate_run(brief, published_bodies=comparison_bodies(brief.slug))
    if not result.ok:
        return show_review(brief, error="Still blocked — fix the blocking issues before queueing.")

    brief = queue_brief(result.fixed_brief or brief)
    return show_review(
        brief,
        notice=(
            "Queued locally — not pushed yet. You can approve more articles now, then use "
            "Push all queued on the dashboard once when you are finished."
        ),
    )


@app.route("/push-queued-all", methods=["POST"])
def push_queued_all():
    published = load_published()
    queue = [b for b in load_queue() if b.body_md and b.slug not in published]
    if not queue:
        return redirect(url_for("dashboard", pushed=0))

    paths = {"content/queue.json"}
    for brief in queue:
        image_path = image_repo_path(brief.image)
        if image_path:
            paths.add(image_path)

    try:
        commit_and_push(paths, f"Queue Dolla content batch {date.today().isoformat()}")
    except Exception as exc:
        return redirect(url_for("dashboard", push_error=str(exc)[:500]))

    return redirect(url_for("dashboard", pushed=len(queue)))


@app.route("/publish-push", methods=["POST"])
def publish_push():
    brief = Brief.from_dict(json.loads(request.form["brief_json"]))
    result = gate_run(brief, published_bodies=comparison_bodies(brief.slug))
    if not result.ok:
        return show_review(brief, error="Still blocked — fix the blocking issues before publishing.")

    brief = queue_brief(result.fixed_brief or brief)
    try:
        outcome = publish_and_push(brief)
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
        url = save_image_bytes(
            data,
            upload.filename or "pasted-image.png",
            request.form.get("slug", "guide"),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "url": url})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True)
