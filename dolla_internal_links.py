"""Automatic internal-link planning for Dolla articles.

Keeps the article writer and renderer supplied with a small set of live Dolla destinations:
primary game first, then 1-3 genuinely related live games when we know the relationship, otherwise
homepage. Unknown/new games still get their own game URL plus homepage, so adding a game never
requires another code change just to get a valid internal link.
"""
from __future__ import annotations

from urllib.parse import urlparse

# Relationship hints are intentionally conservative. Every candidate is filtered against the
# dynamically discovered live lobby before being used.
RELATED = {
    "crash": ["voidrun", "limbo", "dice"],
    "voidrun": ["crash", "limbo", "dice"],
    "limbo": ["crash", "voidrun", "dice"],
    "dice": ["limbo", "crash", "plinko"],
    "plinko": ["dice", "mines", "keno"],
    "mines": ["plinko", "dice", "hilo"],
    "keno": ["plinko", "lucky7", "dice"],
    "hilo": ["blackjack", "mines", "deal-or-no-deal"],
    "blackjack": ["hilo", "roulette", "deal-or-no-deal"],
    "roulette": ["blackjack", "lucky7", "slots"],
    "slots": ["inferno", "olympus", "ruby-moolah"],
    "inferno": ["slots", "olympus", "ruby-moolah"],
    "olympus": ["slots", "inferno", "ruby-moolah"],
    "ruby-moolah": ["slots", "inferno", "olympus"],
    "bigscore": ["mines", "crash", "voidrun"],
    "balloon-blitz": ["crash", "voidrun", "mines"],
    "chariot": ["penalty", "roulette", "lucky7"],
    "penalty": ["chariot", "roulette", "lucky7"],
}


def _normalise_slug(url: str) -> str:
    return urlparse(url).path.strip("/")


def _plan(desk, brief) -> list[str]:
    roster = [d for d in desk.destinations() if d.get("slug") not in {"", "__custom__"}]
    live = {d["slug"]: d for d in roster if d.get("slug")}
    base = desk.APP_BASE.rstrip("/")
    links: list[str] = []

    def add(url: str) -> None:
        if url and url not in links:
            links.append(url)

    # Always link the article's own live/custom game when one is selected.
    if getattr(brief, "game", ""):
        add(f"{base}/{brief.game.strip('/')}")

    # Add up to three related games, but only when they are present in the current live lobby.
    for slug in RELATED.get(getattr(brief, "game", ""), []):
        if slug in live:
            add(f"{base}/{slug}")
        if len(links) >= 4:  # primary + at most 3 related
            break

    # Broad articles and unknown/new games still get a useful Dolla homepage/lobby link.
    if not getattr(brief, "game", "") or len(links) < 2:
        add(f"{base}/#games")

    return links[:4]


def install(desk) -> None:
    original_complete = desk.complete_headline_brief
    original_from_form = desk.brief_from_form
    original_prompt = desk.gen._prompt

    def assign(brief):
        brief.internal_links = _plan(desk, brief)
        return brief

    def complete_headline_brief(brief, trend_context=""):
        return assign(original_complete(brief, trend_context))

    def brief_from_form(form):
        return assign(original_from_form(form))

    def prompt_with_links(brief, repair_notes=None):
        assign(brief)
        prompt = original_prompt(brief, repair_notes)
        if not brief.internal_links:
            return prompt

        labels = {d["slug"]: d["label"] for d in desk.destinations() if d.get("slug")}
        planned = []
        for url in brief.internal_links:
            slug = _normalise_slug(url)
            if url.endswith("/#games") or slug == "":
                label = "Dolla game lobby"
            else:
                label = labels.get(slug, slug.replace("-", " ").title())
            planned.append(f"- {label}: {url}")

        section = """

INTERNAL LINK PLAN:
Use these Dolla links naturally inside the article body, not as a dumped list at the end.
- Link the primary game when relevant, preferably near the first meaningful mention or CTA.
- Use 1-3 related Dolla links only where the sentence genuinely fits.
- Vary anchor text naturally. Do not repeat exact-match anchors mechanically.
- Do not invent or alter URLs, and do not add links to games outside this supplied list.
""" + "\n".join(planned)

        marker = "\nReturn ONLY the Markdown body. No title line, no code fences."
        return prompt.replace(marker, section + marker)

    desk.complete_headline_brief = complete_headline_brief
    desk.brief_from_form = brief_from_form
    desk.gen._prompt = prompt_with_links
