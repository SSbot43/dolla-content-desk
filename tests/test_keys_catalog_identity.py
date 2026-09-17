import unittest
from unittest.mock import patch
from content_os import keys_generation as generation


class CatalogIdentityTests(unittest.TestCase):
    def test_exact_catalog_names_accept_relevant_topics(self):
        cases = [
            ("Capcut Pro For 1Year", "CapCut setup guide"),
            ("Capcut Pro For 1 Year", "CapCut Pro buying guide"),
            ("Capcut Pro For 12-month", "CapCut editing workflow"),
            ("Final Cut App Store license | One-time Purchase — No Subscription Renewal", "Final Cut Pro editing guide"),
            ("Final Cut App Store licence | One-time Purchase", "Final Cut vs Premiere Pro"),
            ("Windows 11 Pro For 1Year", "Windows 11 setup guide"),
        ]
        for name, topic in cases:
            with self.subTest(name=name), patch.object(generation, "_call_ai", return_value=([topic], "test")) as ai:
                self.assertEqual(generation.generate_topics({"kind": "product", "title": name}, 1)[0], [topic])
                ai.assert_called_once()

    def test_wrong_products_still_retry_and_fail(self):
        for name, wrong in [
            ("Capcut Pro For 1Year", "Claude Pro buying guide"),
            ("Final Cut App Store license | One-time Purchase — No Subscription Renewal", "Gemini setup guide"),
            ("Windows 11 Pro For 1Year", "Windows 10 setup guide"),
        ]:
            with self.subTest(name=name), patch.object(generation, "_call_ai", return_value=([wrong], "test")) as ai:
                with self.assertRaises(generation.GenerationError):
                    generation.generate_topics({"kind": "product", "title": name}, 1)
                self.assertEqual(ai.call_count, 2)

    def test_corrective_retry_accepts_core_product_name(self):
        target = {"kind": "product", "title": "Final Cut App Store license | One-time Purchase — No Subscription Renewal"}
        with patch.object(generation, "_call_ai", side_effect=[(["Gemini guide"], "test"), (["Final Cut setup guide"], "test")]) as ai:
            self.assertEqual(generation.generate_topics(target, 1)[0], ["Final Cut setup guide"])
            self.assertIn("Core name to include naturally in every title: final cut", ai.call_args_list[0].args[0])
            self.assertIn("CORRECTION", ai.call_args_list[1].args[0])

    def test_category_and_product_boundaries_remain_required(self):
        self.assertFalse(generation._topic_matches_target("Claude guide", {"kind": "category", "title": "Video Editing"}))
        self.assertTrue(generation._topic_matches_target("Video editing software guide", {"kind": "category", "title": "Video Editing"}))
        self.assertFalse(generation._topic_matches_target("Capcutters guide", {"title": "Capcut Pro For 1Year"}))


if __name__ == "__main__":
    unittest.main()
