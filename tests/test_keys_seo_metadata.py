from pathlib import Path

import pytest

from content_os import keys_generation
from keys_app import item_from_ai, wp_payload


FINAL_CUT = {
    "kind": "product",
    "title": "Final Cut App Store license | One-time Purchase — No Subscription Renewal",
    "url": "https://keys-shop.in/product/final-cut-app-store-license-for-lifetime/",
}


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Buy a Final Cut App Store License Safely in India", "Final Cut App Store license buying guide in India"),
        ("Final Cut App Store License Setup Guide After Purchase", "Final Cut App Store license setup guide"),
        ("Final Cut App Store License Payment Questions Answered", "Final Cut App Store license payment methods"),
    ],
)
def test_final_cut_metadata_is_deterministic_and_relevant(monkeypatch, title, expected):
    monkeypatch.setattr(keys_generation, "_call_ai", lambda prompt: ({
        "title": title,
        "body_html": "<p>Useful Final Cut article.</p>",
        "primary_keyword": "Google One alternatives",
        "meta_description": "Unrelated Google One copy.",
        "excerpt": "Unrelated excerpt.",
    }, "test"))

    article, _ = keys_generation.generate_article(title, FINAL_CUT, seo_targets={
        "family": "", "product_keywords": [], "trust_keywords": []
    })

    assert article["primary_keyword"] == expected
    assert article["meta_description"].startswith(expected + ":")
    assert "Google One" not in article["meta_description"]
    assert article["excerpt"] == article["meta_description"]
    assert len(article["meta_description"]) <= 160

    payload = wp_payload(item_from_ai(article, FINAL_CUT), "publish")
    assert payload["focus_keyword"] == expected
    assert payload["meta_description"] == article["meta_description"]
    assert payload["excerpt"] == article["meta_description"]


def test_approved_research_keyword_wins_over_ai_keyword(monkeypatch):
    monkeypatch.setattr(keys_generation, "_call_ai", lambda prompt: ({
        "title": "Claude Pro price guide",
        "body_html": "<p>Useful Claude article.</p>",
        "primary_keyword": "Google One alternatives",
    }, "test"))
    approved = {
        "family": "Claude Pro",
        "product_keywords": ["Claude Pro price in india"],
        "trust_keywords": [],
    }
    article, _ = keys_generation.generate_article("Claude Pro price guide", {"title": "Claude Pro"}, seo_targets=approved)
    assert article["primary_keyword"] == "Claude Pro price in india"
    assert article["meta_description"].startswith("Claude Pro price in india:")


def test_one_time_purchase_does_not_match_google_one_keyword_family():
    from keys_keywords import select_targets

    targets = select_targets("Final Cut setup guide", FINAL_CUT)
    assert targets["family"] == ""
    assert targets["product_keywords"] == []

    google_one = select_targets("Google One alternatives", {"title": "Google One For 1Year"})
    assert google_one["family"] == "Google One"


def test_wordpress_bridge_writes_all_yoast_fields_and_upserts_by_slug():
    source = Path("wordpress-plugin/keys-content-os-bridge/keys-content-os-bridge.php").read_text(encoding="utf-8")
    assert "'_yoast_wpseo_title'" in source
    assert "'_yoast_wpseo_metadesc'" in source
    assert "'_yoast_wpseo_focuskw'" in source
    assert "$postarr['ID'] = intval($existing->ID)" in source
    assert "new WP_Error('duplicate_slug'" not in source

