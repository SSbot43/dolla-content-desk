from content_os import keys_generation


def test_article_prompt_combines_human_style_with_keys_shop_guardrails(monkeypatch):
    captured = {}

    def fake_call_ai(prompt):
        captured["prompt"] = prompt
        return {
            "title": "A practical guide",
            "body_html": "<p>Useful article body.</p>",
        }, "test-provider"

    monkeypatch.setattr(keys_generation, "_call_ai", fake_call_ai)

    article, provider = keys_generation.generate_article(
        "A practical guide",
        {
            "kind": "product",
            "title": "Example Product",
            "url": "https://keys-shop.in/example-product/",
            "sku": "EXAMPLE-1",
            "category": "Software",
        },
        [{"title": "Related Product", "url": "https://keys-shop.in/related-product/"}],
    )

    prompt = captured["prompt"]

    for rule in (
        'Write mostly in active voice.',
        'Address the reader directly with "you" and "your" where natural.',
        'Use contractions where they sound natural.',
        'Prefer plain, practical language',
        'Mix short, medium, and long sentences',
        'Avoid semicolons.',
        'Do not use hashtags, emojis',
        'Do not use Markdown bold, <strong>, or <b> tags.',
        'Avoid mirrored contrast patterns',
        'Avoid rule-of-three or triad phrasing.',
        'Do not over-explain obvious points',
        'Be definite only when the supplied facts support certainty.',
        'Never invent statistics, trends, expert quotes, citations',
        'Keep the heading structure flexible and natural.',
        'Add an FAQ only when the topic and search intent genuinely benefit from one.',
    ):
        assert rule in prompt

    for existing_guardrail in (
        'Do not invent compatibility, official-partner status, discounts, prices, stock, testimonials, licensing rights, product features, or availability.',
        'Do not claim a license is lifetime unless the supplied product data explicitly says so.',
        'Never fabricate facts just to make the article sound authoritative.',
        'include its exact supplied URL naturally at least once',
        'Never invent an internal URL; use only the exact URLs supplied above.',
        'primary_keyword should be the single best Yoast focus keyphrase',
    ):
        assert existing_guardrail in prompt

    assert "https://keys-shop.in/example-product/" in prompt
    assert "https://keys-shop.in/related-product/" in prompt
    assert provider == "test-provider"
    assert article["body_html"] == "<p>Useful article body.</p>"
