"""Discover the Dolla lobby roster without maintaining a second game list."""

from __future__ import annotations

import os
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

HOME = {"slug": "", "label": "Dolla homepage / general"}
CUSTOM = {"slug": "__custom__", "label": "Custom / new game"}
FALLBACK = [
    {"slug": "plinko", "label": "Plinko"},
    {"slug": "mines", "label": "Mines"},
    {"slug": "crash", "label": "Crash"},
    {"slug": "voidrun", "label": "VOID Run"},
]
# These are compatibility names, not a roster. Discovery decides which games exist.
LEGACY_LABELS = {
    "voidrun": "VOID Run", "slots": "Slots", "blackjack": "Blackjack",
    "inferno": "Inferno Vault", "penalty": "Penalty Shooter", "plinko": "Plinko",
}
SAFE_PATH = re.compile(r"[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)*")
CACHE_SECONDS = 15 * 60
_cache: dict = {"at": 0.0, "games": []}


def clean_path(value: str) -> str:
    value = value.strip().strip("/")
    if not SAFE_PATH.fullmatch(value):
        raise ValueError("Enter a Dolla game path using lowercase letters, numbers, hyphens and optional / separators.")
    return value


class LobbyParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.games: list[dict[str, str]] = []
        self._depth = 0
        self._card: dict[str, str] | None = None
        self._title_depth = 0

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        classes = (attr.get("class") or "").split()
        if self._card is not None and tag == "div":
            self._depth += 1
        elif tag == "div" and "game-card" in classes and attr.get("data-game"):
            self._card = {"key": attr["data-game"], "path": attr.get("data-href", ""), "title": ""}
            self._depth = 1
        if self._card is not None and "game-title" in classes:
            self._title_depth = self._depth

    def handle_data(self, data):
        if self._card is not None and self._title_depth:
            self._card["title"] += data

    def handle_endtag(self, tag):
        if self._card is None or tag != "div":
            return
        if self._title_depth == self._depth:
            self._title_depth = 0
        self._depth -= 1
        if self._depth == 0:
            key = self._card["key"].strip()
            path = self._card["path"].strip().strip("/") or key
            if key == "slot":  # Keep the desk's existing Slots destination.
                path = "slots"
            title = " ".join(self._card["title"].split())
            if title and SAFE_PATH.fullmatch(path):
                self.games.append({"slug": path, "label": LEGACY_LABELS.get(path, title)})
            self._card = None


def parse_lobby(html: str) -> list[dict[str, str]]:
    parser = LobbyParser()
    parser.feed(html)
    unique = {}
    for game in parser.games:
        unique.setdefault(game["slug"], game)
    return list(unique.values())


def discover_games() -> list[dict[str, str]]:
    site_repo = os.environ.get("DOLLA_SITE_REPO", "").strip()
    if site_repo:
        return parse_lobby((Path(site_repo) / "static" / "index.html").read_text(encoding="utf-8"))
    base = os.environ.get("APP_BASE", "https://dolla.fo").rstrip("/")
    req = urllib.request.Request(base + "/", headers={"User-Agent": "DollaContentDesk/1.0"})
    with urllib.request.urlopen(req, timeout=5) as response:
        return parse_lobby(response.read().decode("utf-8"))


def destinations(force: bool = False) -> list[dict[str, str]]:
    now = time.time()
    if force or now - _cache["at"] >= CACHE_SECONDS:
        try:
            found = discover_games()
            if not found:
                raise ValueError("No Dolla game cards found")
            _cache["games"] = found
        except (OSError, ValueError, UnicodeError):
            if not _cache["games"]:
                _cache["games"] = FALLBACK
        _cache["at"] = now
    return [HOME, *_cache["games"], CUSTOM]
