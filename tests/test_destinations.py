import html
import json
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("CONTENT_REPO", str(Path(__file__).resolve().parents[2] / "dollacasino-content"))

import app as desk
import destinations as roster


LOBBY = '''
<div class="game-card" data-game="voidrun" data-href="/voidrun"><div class="game-title">Void Run</div></div>
<div class="game-card" data-game="tower" data-href="/tower"><div class="game-title">Tower of Fortune</div></div>
<div class="game-card" data-game="slot"><div class="game-title">Wizards &amp; Alchemy</div></div>
<div class="game-card" data-game="tower" data-href="/tower"><div class="game-title">Tower of Fortune</div></div>
<div class="game-card" data-game="bad" data-href="https://other.example/"><div class="game-title">Bad</div></div>
'''


class DestinationTests(unittest.TestCase):
    def setUp(self):
        roster._cache.update(at=0.0, games=[])

    def test_lobby_discovery_deduplicates_and_preserves_legacy_names(self):
        self.assertEqual(roster.parse_lobby(LOBBY), [
            {"slug": "voidrun", "label": "VOID Run"},
            {"slug": "tower", "label": "Tower of Fortune"},
            {"slug": "slots", "label": "Slots"},
        ])

    def test_refresh_and_fallback(self):
        with patch.object(roster, "discover_games", return_value=roster.parse_lobby(LOBBY)):
            choices = roster.destinations()
        self.assertEqual([d["slug"] for d in choices], ["", "voidrun", "tower", "slots", "__custom__"])
        with patch.object(roster, "discover_games", side_effect=OSError("offline")):
            self.assertIn({"slug": "tower", "label": "Tower of Fortune"}, roster.destinations(force=True))
        roster._cache.update(at=0.0, games=[])
        with patch.object(roster, "discover_games", side_effect=OSError("offline")):
            self.assertEqual(roster.destinations(force=True)[1:-1], roster.FALLBACK)

    def test_custom_form_and_review_keep_name_and_path(self):
        with patch.object(roster, "discover_games", return_value=roster.parse_lobby(LOBBY)):
            client = desk.app.test_client()
            self.assertIn(b'Tower of Fortune', client.get('/api/destinations').data)
            self.assertEqual(desk._guess_destination('How Tower of Fortune works'), 'tower')
            response = client.post('/feed', data={
                'mode': 'paste', 'title': 'A new game', 'game': '__custom__',
                'custom_game_name': 'Moon Quest', 'custom_game_path': 'games/moon-quest',
            })
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'value="games/moon-quest"', response.data)
            self.assertIn(b'value="Moon Quest"', response.data)
            match = re.search(rb'name="brief_json" value="([^"]+)"', response.data)
            self.assertIsNotNone(match)
            brief = json.loads(html.unescape(match.group(1).decode()))
            self.assertEqual((brief['game'], brief['game_label']), ('games/moon-quest', 'Moon Quest'))
            review = client.post('/review', data={
                'title': 'A new game', 'game': '__custom__',
                'custom_game_name': 'Moon Quest', 'custom_game_path': 'games/moon-quest',
            })
            self.assertEqual(review.status_code, 200)
            self.assertIn(b'value="games/moon-quest"', review.data)

    def test_invalid_custom_path_is_rejected(self):
        with patch.object(roster, "discover_games", return_value=roster.parse_lobby(LOBBY)):
            response = desk.app.test_client().post('/feed', data={
                'title': 'Bad path', 'game': '__custom__',
                'custom_game_name': 'Bad', 'custom_game_path': 'https://other.example/',
            })
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
