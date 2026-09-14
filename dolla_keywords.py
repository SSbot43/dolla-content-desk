"""SEO keyword-bank support for the Dolla Content Desk.

The bank lives in seo_keywords.json so it can be expanded without changing Python.
For each article we select a small, relevant subset (2-5 terms) and pass only those
terms to the article-generation prompt. The goal is broad topical coverage across
many articles, not stuffing an entire cluster into one page.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

from flask import redirect, request

ROOT = Path(__file__).resolve().parent
BANK_PATH = ROOT / "seo_keywords.json"

GAME_CLUSTER = {
    "crash": "crash",
    "plinko": "plinko",
    "mines": "mines",
    "limbo": "limbo",
    "dice": "dice",
    "keno": "keno",
    "hilo": "hilo",
    "roulette": "roulette",
    "blackjack": "blackjack",
    "deal-or-no-deal": "deal_or_no_deal",
    "dond": "deal_or_no_deal",
    "lucky7": "lucky_7",
    "lucky-7": "lucky_7",
    "penalty": "penalty",
    "tower": "tower",
    "wheel": "wheel",
}

CLUSTER_HINTS = {
    "no_kyc_privacy": ["kyc", "verification", "verify", "anonymous", "privacy", "passport", "id verification", "without id"],
    "withdrawals_payouts": ["withdraw", "withdrawal", "cashout", "cash out", "payout", "pending", "processing time", "payment speed"],
    "free_demo_browser": ["free", "demo", "browser", "no download", "practice", "virtual credits", "without depositing"],
    "crash": ["crash", "multiplier", "cash out strategy"],
    "plinko": ["plinko", "risk level", "multipliers"],
    "mines": ["mines", "grid", "mine game"],
    "limbo": ["limbo"],
    "dice": ["dice"],
    "keno": ["keno"],
    "hilo": ["hilo", "hi lo", "higher lower", "higher or lower"],
    "roulette": ["roulette"],
    "blackjack": ["blackjack", "21 rules", "hit or stand", "split rules", "double down"],
    "deal_or_no_deal": ["deal or no deal", "banker offer"],
    "lucky_7": ["lucky 7", "lucky seven", "under over"],
    "penalty": ["penalty", "shootout", "penalty kick"],
    "tower": ["tower"],
    "wheel": ["wheel"],
    "crypto_deposits": ["deposit", "wallet address", "network fee", "wrong network", "minimum deposit"],
    "crypto_casino_general": ["crypto casino", "bitcoin casino", "usdt casino", "litecoin casino", "cryptocurrency casino"],
    "online_casino_general": ["online casino", "online gambling", "browser gambling", "real money casino"],
}

STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "what", "why", "how",
    "is", "are", "at", "from", "your", "you", "game", "casino", "online", "crypto", "guide", "explained",
}


def _load_bank() -> dict:
    try:
        data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("clusters"), dict):
            raise ValueError("keyword bank must contain a clusters object")
        return data
    except Exception:
        return {"version": 1, "instructions": "", "clusters": {}}


def _clean_keywords(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        value = re.sub(r"\s+", " ", str(value or "")).strip()
        key = value.lower()
        if value and key not in seen:
            out.append(value)
            seen.add(key)
    return out


def _tokens(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(word) > 1 and word not in STOP
    }


def _cluster_scores(brief, clusters: dict[str, list[str]]) -> dict[str, float]:
    text = " ".join([
        getattr(brief, "title", "") or "",
        getattr(brief, "angle", "") or "",
        getattr(brief, "primary_keyword", "") or "",
        getattr(brief, "game_label", "") or "",
    ]).lower()
    title_tokens = _tokens(text)
    scores: dict[str, float] = {name: 0.0 for name in clusters}

    game = (getattr(brief, "game", "") or "").strip("/").lower()
    game_cluster = GAME_CLUSTER.get(game)
    if game_cluster in scores:
        scores[game_cluster] += 12.0

    for cluster, hints in CLUSTER_HINTS.items():
        if cluster not in scores:
            continue
        for hint in hints:
            if hint in text:
                scores[cluster] += 5.0

    for cluster, words in clusters.items():
        cluster_tokens = _tokens(cluster.replace("_", " "))
        scores[cluster] += 1.5 * len(title_tokens & cluster_tokens)
        best_overlap = 0
        for keyword in words:
            best_overlap = max(best_overlap, len(title_tokens & _tokens(keyword)))
        scores[cluster] += min(4.0, best_overlap * 1.2)

    return scores


def _choose_cluster(brief, clusters: dict[str, list[str]]) -> str | None:
    if not clusters:
        return None
    scores = _cluster_scores(brief, clusters)
    winner, score = max(scores.items(), key=lambda item: item[1])
    if score > 0:
        return winner
    # Broad articles still benefit from the general keyword pools.
    for fallback in ("crypto_casino_general", "online_casino_general", "free_demo_browser"):
        if fallback in clusters:
            return fallback
    return next(iter(clusters), None)


def keyword_plan(brief) -> tuple[str | None, list[str]]:
    bank = _load_bank()
    clusters = {
        str(name): _clean_keywords(values)
        for name, values in bank.get("clusters", {}).items()
        if isinstance(values, list) and _clean_keywords(values)
    }
    cluster = _choose_cluster(brief, clusters)
    if not cluster:
        return None, []

    pool = clusters[cluster]
    context = " ".join([
        getattr(brief, "title", "") or "",
        getattr(brief, "angle", "") or "",
        getattr(brief, "primary_keyword", "") or "",
    ])
    context_tokens = _tokens(context)
    seed_text = f"{getattr(brief, 'slug', '')}|{getattr(brief, 'title', '')}|{cluster}"

    def rank(keyword: str) -> tuple[int, int]:
        overlap = len(context_tokens & _tokens(keyword))
        digest = hashlib.sha256(f"{seed_text}|{keyword}".encode("utf-8")).hexdigest()
        # Higher semantic overlap first; hash makes equally relevant articles rotate through the pool.
        return overlap, int(digest[:10], 16)

    ranked = sorted(pool, key=rank, reverse=True)
    # Four is the normal target. Small clusters may naturally supply only 2-3.
    count = min(4, len(ranked))
    selected = ranked[:count]

    primary = re.sub(r"\s+", " ", getattr(brief, "primary_keyword", "") or "").strip()
    if primary and primary.lower() not in {x.lower() for x in selected}:
        # Keep a manually supplied/focus keyword, but never exceed the 5-keyword ceiling.
        selected = [primary] + selected[:4]

    return cluster, _clean_keywords(selected)[:5]


def _prompt_section(brief) -> str:
    cluster, keywords = keyword_plan(brief)
    if len(keywords) < 2:
        return ""
    lines = "\n".join(f"- {word}" for word in keywords)
    return f"""

SEO KEYWORD PLAN:
This article is one page in a larger topical-authority strategy. Target ONLY the 2-5 phrases below for this article; other keywords in the wider cluster are intentionally reserved for future articles.
Cluster: {cluster}
Target phrases:
{lines}

SEO writing rules:
- Incorporate these phrases naturally where they genuinely fit the article's exact angle.
- It is fine to use close grammatical variants when that reads better.
- Do not keyword-stuff, repeat exact-match phrases mechanically, or make awkward headings just to fit a term.
- Do not drag unrelated keywords from the wider cluster into this article.
- Future articles on the same game/topic will target different subsets, so do NOT try to exhaust the cluster here.
- Prefer useful topical coverage and natural language over raw repetition.
- Keywords never override factual/claims/safety rules. Never invent a Dolla feature or promise merely to fit a keyword.
"""


def _page_html(message: str = "") -> str:
    bank = _load_bank()
    clusters = bank.get("clusters", {})
    blocks = []
    for name, values in clusters.items():
        text = "\n".join(_clean_keywords(values))
        blocks.append(
            f'<section><label><strong>{html.escape(name)}</strong></label>'
            f'<textarea name="cluster__{html.escape(name)}" rows="8">{html.escape(text)}</textarea></section>'
        )
    message_html = f'<p class="ok">{html.escape(message)}</p>' if message else ""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Dolla SEO Keyword Bank</title>
<style>
body{{font-family:Arial,sans-serif;max-width:1000px;margin:30px auto;padding:0 20px;background:#fafafa;color:#171717}}
h1{{margin-bottom:8px}} .note{{color:#555;line-height:1.5}} section{{background:white;border:1px solid #ddd;border-radius:10px;padding:14px;margin:14px 0}}
textarea{{width:100%;box-sizing:border-box;margin-top:8px;font:14px/1.4 monospace;padding:10px}} input{{padding:9px;width:280px}} button{{padding:10px 18px;font-weight:700;cursor:pointer}} .ok{{background:#e9f8ee;padding:10px;border-radius:8px}}
</style></head><body>
<h1>Dolla SEO Keyword Bank</h1>
<p class="note">One keyword per line. The writer automatically picks only <strong>2-5 closely related phrases per article</strong>. It does not try to use the whole cluster at once, so later articles can target different keyword subsets.</p>
{message_html}
<form method="post">
{''.join(blocks)}
<section><strong>Add a new cluster</strong><br><br><input name="new_cluster" placeholder="e.g. balloon_blitz"><br><textarea name="new_keywords" rows="6" placeholder="one keyword per line"></textarea></section>
<button type="submit">Save keyword bank</button>
</form>
<p class="note">Stored in <code>seo_keywords.json</code>. You can also edit that file directly whenever you get a new keyword export.</p>
</body></html>"""


def _save_from_form(form) -> None:
    current = _load_bank()
    clusters: dict[str, list[str]] = {}
    for key in form.keys():
        if not key.startswith("cluster__"):
            continue
        name = key[len("cluster__"):].strip()
        if not name:
            continue
        words = _clean_keywords((form.get(key) or "").splitlines())
        if words:
            clusters[name] = words

    new_name = re.sub(r"[^a-z0-9_]+", "_", (form.get("new_cluster") or "").lower()).strip("_")
    new_words = _clean_keywords((form.get("new_keywords") or "").splitlines())
    if new_name and new_words:
        clusters.setdefault(new_name, [])
        clusters[new_name] = _clean_keywords(clusters[new_name] + new_words)

    current["clusters"] = clusters
    current["instructions"] = (
        "Each article should naturally target 2-5 closely related keywords. Do not try to use an entire "
        "cluster in one article. Unused keywords remain available for future articles on the same game/topic."
    )
    BANK_PATH.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def install(desk) -> None:
    if getattr(desk, "_dolla_keywords_installed", False):
        return
    desk._dolla_keywords_installed = True

    original_prompt = desk.gen._prompt

    def prompt_with_keywords(brief, repair_notes=None):
        prompt = original_prompt(brief, repair_notes)
        section = _prompt_section(brief)
        if not section:
            return prompt
        marker = "\nReturn ONLY the Markdown body. No title line, no code fences."
        if marker in prompt:
            return prompt.replace(marker, section + marker)
        return prompt + section

    desk.gen._prompt = prompt_with_keywords

    def keyword_editor():
        if request.method == "POST":
            _save_from_form(request.form)
            return redirect("/keywords?saved=1")
        return _page_html("Keyword bank saved." if request.args.get("saved") == "1" else "")

    desk.app.add_url_rule("/keywords", "dolla_keywords", keyword_editor, methods=["GET", "POST"])
