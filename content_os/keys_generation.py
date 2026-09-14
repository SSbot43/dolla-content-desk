from __future__ import annotations

import json
import os
import re

from keys_keywords import topic_opportunities, select_targets


class GenerationError(RuntimeError):
    pass


def _clean_json(text: str):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start_candidates = [p for p in (text.find("{"), text.find("[")) if p >= 0]
    if not start_candidates:
        raise GenerationError("AI did not return JSON")
    start = min(start_candidates)
    end = max(text.rfind("}"), text.rfind("]"))
    if end <= start:
        raise GenerationError("AI returned incomplete JSON")
    try:
        return json.loads(text[start:end + 1])
    except Exception as exc:
        raise GenerationError(f"Could not parse AI JSON: {exc}") from exc


def _call_ai(prompt: str):
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            from google import genai as google_genai
            client = google_genai.Client(api_key=gemini_key)
            model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
            resp = client.models.generate_content(model=model, contents=prompt)
            return _clean_json(getattr(resp, "text", "") or ""), "gemini"
        except Exception:
            pass

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            model = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")
            resp = client.responses.create(model=model, input=prompt)
            return _clean_json(resp.output_text), "openai"
        except Exception as exc:
            raise GenerationError(f"Gemini failed and OpenAI fallback failed: {exc}") from exc

    raise GenerationError("No working GEMINI_API_KEY or OPENAI_API_KEY is available to the Keys-Shop desk")


def _target_context(target: dict | None) -> str:
    if not target:
        return "General Keys-Shop software and AI-products content."
    return (
        f"Primary destination type: {target.get('kind','product')}\n"
        f"Name: {target.get('title','')}\n"
        f"URL: {target.get('url','')}\n"
        f"SKU: {target.get('sku','')}\n"
        f"Category: {target.get('category','')}"
    )


def _topic_keyword_context(target: dict | None) -> str:
    hints = topic_opportunities(target)
    if not hints.get("family"):
        return "No matching keyword family in the approved Keys-Shop keyword research."
    product_lines = "\n".join(f"- {x}" for x in hints.get("product_keywords", [])) or "- none"
    trust_lines = "\n".join(f"- {x}" for x in hints.get("trust_keywords", [])) or "- none"
    return (
        f"Matched product family: {hints['family']}\n"
        "Product/search opportunities from approved research:\n"
        f"{product_lines}\n"
        "Keys-Shop trust/support phrases available for natural secondary sections:\n"
        f"{trust_lines}"
    )


def generate_topics(target: dict | None, count: int = 20, seed: str = "") -> tuple[list[str], str]:
    count = max(1, min(100, int(count)))
    keyword_context = _topic_keyword_context(target)
    prompt = f"""You are the editorial strategist for Keys-Shop.in, an established ecommerce store selling digital software and AI products.
Create exactly {count} useful SEO article ideas.

Primary commercial destination:
{_target_context(target)}

Approved keyword research for this selected product/category:
{keyword_context}

Optional editor direction: {seed or 'none'}

Rules:
- Every topic must be genuinely useful to a buyer or researcher, not generic AI SEO filler.
- Use the approved product/search opportunities to inspire different article angles over time. Do not try to cram every keyword into one title.
- Brand/trust phrases are usually secondary on-page sections or FAQs, not standalone thin articles.
- Mix commercial investigation, comparisons, setup/how-to, troubleshooting, buying guides, compatibility questions, practical use cases, and timely angles where appropriate.
- Do not invent prices, discounts, stock, compatibility, partnerships, testimonials, licensing rights, or product features.
- Avoid repetitive/cannibalizing titles.
- Avoid textbook openings and phrases such as 'understanding why', 'at its core', 'in conclusion', 'furthermore', and 'moreover'.
- Titles should sound publishable, natural and clickable without clickbait.
- The selected product/category should be a natural destination, not forced into every title.

Return ONLY JSON as an array of strings, exactly {count} titles.
"""
    data, provider = _call_ai(prompt)
    if not isinstance(data, list):
        raise GenerationError("Topic generator did not return a list")
    titles = [str(x).strip() for x in data if str(x).strip()]
    return titles[:count], provider


def generate_article(
    title: str,
    target: dict | None,
    supporting: list[dict] | None = None,
    seo_targets: dict | None = None,
) -> tuple[dict, str]:
    supporting = supporting or []
    seo_targets = seo_targets or select_targets(title, target)
    support_text = "\n".join(f"- {x.get('title','')}: {x.get('url','')}" for x in supporting[:5]) or "none"
    product_keywords = seo_targets.get("product_keywords", [])
    trust_keywords = seo_targets.get("trust_keywords", [])
    product_text = "\n".join(f"- {x}" for x in product_keywords) or "- none matched"
    trust_text = "\n".join(f"- {x}" for x in trust_keywords) or "- none matched"
    prompt = f"""Write a polished Keys-Shop.in article from this approved headline:
{title}

Primary destination:
{_target_context(target)}

Verified supporting internal links:
{support_text}

APPROVED SEO TARGETS FROM KEYS-SHOP RESEARCH
Matched product family: {seo_targets.get('family') or 'none'}
Product-specific phrases for this exact article angle:
{product_text}
Keys-Shop trust/safety/support phrase for a natural factual section or FAQ:
{trust_text}

Return ONLY one JSON object with these keys:
title, slug, primary_keyword, meta_title, meta_description, excerpt, body_html

Editorial requirements:
- 800-1400 useful words unless the topic truly needs less.
- Natural, direct commercial editorial tone with varied sentence lengths.
- No generic textbook intro. Start with the useful point quickly.
- Do not use: 'it is important to note', 'understanding why', 'in conclusion', 'furthermore', 'moreover', 'at its core'.

Keyword-use rules:
- Naturally weave in the supplied product-specific phrases that genuinely fit this article. Aim to use 2-4 product phrases, but never distort a sentence just to hit an exact match.
- Use the supplied Keys-Shop trust/safety/support phrase once where a factual sentence, short section, or FAQ genuinely supports it.
- The trust phrase is NOT permission to invent security, delivery, review, payment, support, or reputation claims. Only state facts supported by the supplied Keys-Shop/product context.
- Do not turn every keyword into a heading. Do not repeat exact-match phrases mechanically.
- Do not introduce keywords from unrelated products.
- Not all keywords for a product belong in one article. Future articles will target different subsets and angles.
- primary_keyword should normally be the best product-specific phrase from the supplied list, not the trust phrase, unless the approved headline itself is specifically about Keys-Shop trust/safety.

Human writing rules:
- Write mostly in active voice.
- Address the reader directly with "you" and "your" where natural.
- Use contractions where they sound natural.
- Prefer plain, practical language over formal, abstract, corporate, or jargon-heavy wording.
- Stay direct and concise. Get to the useful point quickly.
- Mix short, medium, and long sentences so the rhythm feels natural.
- Avoid semicolons. Use periods or commas instead.
- Do not use hashtags, emojis, decorative symbols, or bold text in the article body. Do not use Markdown bold, <strong>, or <b> tags.
- Avoid mirrored contrast patterns such as "not X, but Y", "it's not about X, it's about Y", or "rather than X, Y" unless the contrast is genuinely necessary.
- Avoid rule-of-three or triad phrasing. Do not habitually stack three adjectives, benefits, examples, or punchy fragments just because the pattern sounds neat.
- Do not over-explain obvious points or repeat a clear idea in a safer, longer paragraph. Once the point is clear, move on.
- Be definite only when the supplied facts support certainty. Never turn uncertainty into a factual claim just to sound confident.
- Never invent statistics, trends, expert quotes, citations, or source-backed claims that were not supplied.

SEO structure:
- Keep the heading structure flexible and natural. Use H2 and H3 headings only when they help the reader; do not force a fixed number or repetitive outline.
- Add an FAQ only when the topic and search intent genuinely benefit from one. A trust/safety phrase may be used as an FAQ when that is the most natural factual placement.
- Keep metadata concise, specific, accurate, and readable by humans.

Keys-Shop product accuracy and safety:
- Do not invent compatibility, official-partner status, discounts, prices, stock, testimonials, licensing rights, product features, or availability.
- Do not claim a license is lifetime unless the supplied product data explicitly says so.
- Never fabricate facts just to make the article sound authoritative.
- When the primary destination is relevant, include its exact supplied URL naturally at least once, with descriptive anchor text rather than a naked URL.
- Use 1-3 verified supporting internal links when they genuinely fit the article. Do not force irrelevant links.
- Never invent an internal URL; use only the exact URLs supplied above.
- Spread internal links naturally through useful sentences; do not dump them into a spammy link list.
- Use clean HTML paragraphs and h2/h3 headings in body_html; no H1 inside the body.
- Meta title should normally fit about 60 characters; meta description about 150-160 characters.
- The article should help a reader make a buying/use decision and should not read like mass-produced SEO filler.
"""
    data, provider = _call_ai(prompt)
    if not isinstance(data, dict):
        raise GenerationError("Article generator did not return an object")
    data["title"] = str(data.get("title") or title).strip()
    data["body_html"] = str(data.get("body_html") or "").strip()
    if not data["body_html"]:
        raise GenerationError("AI returned an empty article")
    return data, provider
