from __future__ import annotations

import hashlib
import re

# Built from the approved 500-keyword Keys-Shop research file.
# Each family has 14 product/search phrases + 6 Keys-Shop trust/support phrases.
FAMILIES = [
    ("Claude Pro", "P1", "Existing GSC cluster — prioritise"),
    ("Claude Max", "P1", "Existing GSC cluster — prioritise"),
    ("ChatGPT Plus", "P1", "Semantic expansion — validate before publishing"),
    ("ChatGPT Pro", "P1", "Semantic expansion — validate before publishing"),
    ("Grok", "P1", "Existing GSC cluster — prioritise"),
    ("Gemini Advanced", "P2", "Semantic expansion — validate before publishing"),
    ("Perplexity Pro", "P2", "Semantic expansion — validate before publishing"),
    ("Canva Pro", "P2", "Existing GSC cluster — prioritise"),
    ("YouTube Premium", "P2", "Existing GSC cluster — prioritise"),
    ("Google One", "P2", "Existing GSC cluster — prioritise"),
    ("iCloud Storage", "P2", "Existing GSC cluster — prioritise"),
    ("Adobe Creative Cloud", "P2", "Existing GSC cluster — prioritise"),
    ("Adobe Photoshop", "P2", "Existing GSC cluster — prioritise"),
    ("Adobe Master Collection", "P3", "Existing GSC cluster — prioritise"),
    ("Office 365", "P3", "Existing GSC cluster — prioritise"),
    ("Microsoft Office", "P3", "Semantic expansion — validate before publishing"),
    ("Windows 11 Pro", "P3", "Semantic expansion — validate before publishing"),
    ("Windows 10 Pro", "P3", "Semantic expansion — validate before publishing"),
    ("Microsoft 365", "P3", "Semantic expansion — validate before publishing"),
    ("IPTV subscription", "P3", "Existing GSC cluster — prioritise"),
    ("NordVPN", "P3", "Semantic expansion — validate before publishing"),
    ("Busuu Premium", "P3", "Semantic expansion — validate before publishing"),
    ("Scribd", "P3", "Semantic expansion — validate before publishing"),
    ("Gamma AI", "P3", "Semantic expansion — validate before publishing"),
    ("cloud storage", "P3", "Existing GSC cluster — prioritise"),
]

PRODUCT_PATTERNS = [
    ("{F} price in india", "Price guide"),
    ("{F} price india", "Price guide"),
    ("{F} plans in india", "Plan comparison"),
    ("{F} subscription price", "Price guide"),
    ("{F} yearly plan india", "Annual-plan guide"),
    ("{F} monthly plan india", "Monthly-plan guide"),
    ("{F} how to buy in india", "How-to guide"),
    ("{F} payment methods in india", "Payment guide"),
    ("{F} upi payment india", "UPI guide"),
    ("{F} how to pay in india", "Payment guide"),
    ("{F} alternatives", "Comparison guide"),
    ("{F} vs alternatives", "Comparison guide"),
    ("{F} features", "Features guide"),
    ("{F} renewal price india", "Renewal guide"),
]

TRUST_PATTERNS = [
    ("is Keys-Shop safe for {F}", "Safety FAQ module"),
    ("Keys-Shop review for {F}", "Experience/review module"),
    ("how Keys-Shop delivers {F}", "Delivery-explainer module"),
    ("buy {F} from Keys-Shop", "from Keys-Shop module"),
    ("Keys-Shop payment options for {F}", "Payment-explainer module"),
    ("Keys-Shop support for {F}", "Support-explainer module"),
]

_STOP = {"the", "a", "an", "and", "or", "for", "to", "in", "on", "with", "of", "from", "guide", "how", "what", "why", "is", "are", "best", "buy", "india", "keys", "shop"}
_PRIORITY = {"P1": 30, "P2": 20, "P3": 10}


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _tokens(value: str) -> set[str]:
    return {x for x in _norm(value).split() if len(x) > 1 and x not in _STOP}


def catalog() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for family, priority, evidence in FAMILIES:
        for pattern, article_type in PRODUCT_PATTERNS:
            rows.append({
                "family": family,
                "priority": priority,
                "keyword": pattern.format(F=family),
                "article_type": article_type,
                "intent": "Product / informational-commercial",
                "evidence": evidence,
            })
        for pattern, article_type in TRUST_PATTERNS:
            rows.append({
                "family": family,
                "priority": priority,
                "keyword": pattern.format(F=family),
                "article_type": article_type,
                "intent": "Brand / trust",
                "evidence": "Brand-support keyword — factual claims only",
            })
    return rows


def infer_family(title: str, target: dict | None) -> str:
    # The selected name owns identity; broad categories and old headlines do not.
    if target and target.get("title"):
        title = str(target["title"])
        target = None
    context = " ".join(str(x or "") for x in (title, (target or {}).get("title"), (target or {}).get("category"), (target or {}).get("sku")))
    ncontext = _norm(context)
    names = [x[0] for x in FAMILIES]
    direct = [family for family in names if _norm(family) in ncontext]
    if direct:
        return max(direct, key=lambda x: len(_norm(x)))
    ctokens = _tokens(context)
    best = ("", 0.0)
    for family in names:
        ftokens = _tokens(family)
        distinctive = ftokens - {"pro", "premium", "advanced", "max", "plus", "subscription", "storage", "cloud"}
        if not distinctive or not (ctokens & distinctive):
            continue
        if not ftokens:
            continue
        overlap = len(ctokens & ftokens)
        score = overlap / len(ftokens)
        if overlap and score > best[1]:
            best = (family, score)
    return best[0] if best[1] >= 0.5 else ""


def _relevance(row: dict[str, str], title: str) -> int:
    score = _PRIORITY.get(row.get("priority", ""), 0)
    title_tokens = _tokens(title)
    key_tokens = _tokens(row.get("keyword", ""))
    score += 8 * len(title_tokens & key_tokens)
    if _norm(row.get("keyword", "")) and _norm(row["keyword"]) in _norm(title):
        score += 40
    article_type = row.get("article_type", "").lower()
    t = title.lower()
    angle_words = {
        "price": ("price", "cost", "pricing"),
        "payment": ("payment", "pay", "upi"),
        "comparison": (" vs ", "versus", "alternative", "compare"),
        "renewal": ("renew", "renewal"),
        "feature": ("feature", "benefit"),
        "how-to": ("how to",),
    }
    for marker, words in angle_words.items():
        if marker in article_type and any(word in t for word in words):
            score += 14
    return score


def select_targets(title: str, target: dict | None, max_product: int = 3) -> dict:
    family = infer_family(title, target)
    if not family:
        return {"family": "", "product_keywords": [], "trust_keywords": [], "all_keywords": []}
    rows = [r for r in catalog() if r["family"] == family]
    product_rows = [r for r in rows if r["intent"] != "Brand / trust"]
    trust_rows = [r for r in rows if r["intent"] == "Brand / trust"]
    ranked = sorted(product_rows, key=lambda r: (-_relevance(r, title), r["keyword"].lower()))
    product_keywords = [r["keyword"] for r in ranked[:max(2, min(4, max_product))]]

    # Prefer the explicit safety/security phrase. Use one trust term per article so it remains natural.
    trust_keywords: list[str] = []
    safety = [r for r in trust_rows if "safe" in r["keyword"].lower()]
    pool = safety or trust_rows
    if pool:
        digest = hashlib.sha256(f"{family}|{title}".encode("utf-8")).digest()
        chosen = pool[int.from_bytes(digest[:2], "big") % len(pool)]
        trust_keywords = [chosen["keyword"]]

    return {
        "family": family,
        "product_keywords": product_keywords[:4],
        "trust_keywords": trust_keywords[:1],
        "all_keywords": (product_keywords + trust_keywords)[:5],
    }


def topic_opportunities(target: dict | None, limit: int = 12) -> dict:
    family = infer_family("", target)
    if not family:
        return {"family": "", "product_keywords": [], "trust_keywords": []}
    rows = [r for r in catalog() if r["family"] == family]
    products = [r for r in rows if r["intent"] != "Brand / trust"]
    trusts = [r for r in rows if r["intent"] == "Brand / trust"]
    return {
        "family": family,
        "product_keywords": [r["keyword"] for r in products[:limit]],
        "trust_keywords": [r["keyword"] for r in trusts[:3]],
    }
