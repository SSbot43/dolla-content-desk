import json
import unittest
from pathlib import Path

import destinations as roster
import dolla_internal_links as links
import dolla_keywords as keywords


ROOT = Path(__file__).resolve().parents[1]
NEW_GAMES = {
    "coin-pusher": "money_pusher",
    "balloon": "balloon_blitz",
    "chicken": "chicken_run",
    "penalty-nations-cup": "penalty_nations_cup",
    "ruby": "ruby_moolah",
}

LOBBY = """
<div class="game-card" data-game="coinpush" data-href="/coin-pusher"><div class="game-title">Dolla Money Pusher</div></div>
<div class="game-card" data-game="balloon" data-href="/balloon"><div class="game-title">Balloon Blitz</div></div>
<div class="game-card" data-game="chicken" data-href="/chicken"><div class="game-title">Chicken Run</div></div>
<div class="game-card" data-game="nations" data-href="/penalty-nations-cup"><div class="game-title">Penalty Nations Cup</div></div>
<div class="game-card" data-game="ruby" data-href="/ruby"><div class="game-title">Dolla Ruby Moolah</div></div>
"""


class GameRosterTests(unittest.TestCase):
    def test_new_lobby_cards_use_public_routes(self):
        parsed = roster.parse_lobby(LOBBY)
        self.assertEqual(
            [game["slug"] for game in parsed],
            list(NEW_GAMES),
        )

    def test_offline_fallback_includes_new_games(self):
        fallback = {game["slug"] for game in roster.FALLBACK}
        self.assertTrue(set(NEW_GAMES).issubset(fallback))

    def test_batch_aliases_use_live_slugs(self):
        batch = (ROOT / "static" / "batch.html").read_text(encoding="utf-8")
        for slug in NEW_GAMES:
            self.assertIn(f"['{slug}',", batch)
        self.assertNotIn("['balloon-blitz',", batch)
        self.assertNotIn("['ruby-moolah',", batch)

    def test_batch_builds_a_full_roster_gemini_headline_prompt(self):
        batch = (ROOT / "static" / "batch.html").read_text(encoding="utf-8")
        self.assertIn('id="copy-headline-prompt"', batch)
        self.assertIn("function buildHeadlinePrompt()", batch)
        self.assertIn("Use EVERY game in the roster below", batch)
        self.assertIn("Create exactly 3 distinct article ideas for EVERY listed game", batch)
        self.assertIn("DESTINATIONS.filter(([slug])=>slug&&slug!=='__custom__')", batch)

    def test_open_batch_refreshes_games_every_fifteen_minutes(self):
        batch = (ROOT / "static" / "batch.html").read_text(encoding="utf-8")
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("DESTINATION_REFRESH_MS=15*60*1000", batch)
        self.assertIn("setInterval(()=>loadDestinations(true),DESTINATION_REFRESH_MS)", batch)
        self.assertIn("/api/destinations?refresh=1", batch)
        self.assertIn('request.args.get("refresh") == "1"', app)

    def test_related_links_and_keyword_clusters_cover_new_games(self):
        bank = json.loads((ROOT / "seo_keywords.json").read_text(encoding="utf-8"))["clusters"]
        for slug, cluster in NEW_GAMES.items():
            self.assertIn(slug, links.RELATED)
            self.assertEqual(keywords.GAME_CLUSTER[slug], cluster)
            self.assertIn(cluster, keywords.CLUSTER_HINTS)
            self.assertIn(cluster, bank)


if __name__ == "__main__":
    unittest.main()
