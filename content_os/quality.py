from __future__ import annotations
from dataclasses import dataclass, field
import re
from urllib.parse import urlparse

@dataclass
class GateIssue:
    code: str
    detail: str
    blocking: bool = True

@dataclass
class GateResult:
    ok: bool
    issues: list[GateIssue] = field(default_factory=list)

    @property
    def blocking(self) -> list[GateIssue]:
        return [i for i in self.issues if i.blocking]

BANNED_PHRASES = [
    "it is important to note", "understanding why", "in conclusion",
    "furthermore", "moreover", "at its core"
]
RISKY_CLAIMS = [
    (r"\bofficial partner\b", "official_partner", "'official partner' requires verification"),
    (r"\bguaranteed compatible\b", "compatibility", "Compatibility must be sourced from a live product/source"),
    (r"\bin stock\b|\bavailable now\b", "availability", "Do not invent stock/availability"),
    (r"\bverified customer(s)? say\b|\busers love\b", "testimonial", "Do not invent testimonials or review consensus"),
    (r"\blifetime license\b", "licensing", "Licensing duration/type must match the actual product listing"),
]

def _is_keys_shop_url(url: str, site_base: str) -> bool:
    try:
        return urlparse(url).netloc.lower() == urlparse(site_base).netloc.lower()
    except Exception:
        return False

def run(item, *, site_base: str = "https://keys-shop.in", known_urls: set[str] | None = None,
        comparison_bodies: list[str] | None = None) -> GateResult:
    text = f"{item.title}\n{item.meta_title}\n{item.meta_description}\n{item.body_md}\n{item.body_html}".lower()
    issues: list[GateIssue] = []

    for phrase in BANNED_PHRASES:
        if phrase in text:
            issues.append(GateIssue("ai_phrase", f"Remove AI-style phrase: {phrase}", blocking=False))

    for pattern, code, detail in RISKY_CLAIMS:
        if re.search(pattern, text, re.I):
            issues.append(GateIssue(code, detail, blocking=True))

    words = re.findall(r"\b\w+\b", item.body_md or item.body_html)
    if len(words) < 450:
        issues.append(GateIssue("thin_content", f"Article is thin ({len(words)} words); target 550+ useful words", True))

    links = set(re.findall(r'https?://[^\s)\]"\'>]+', item.body_md or item.body_html))
    if known_urls is not None:
        for link in links:
            clean = link.rstrip(".,;:")
            if _is_keys_shop_url(clean, site_base) and clean not in known_urls:
                issues.append(GateIssue("broken_internal_link", f"Internal link does not exist: {clean}", True))

    body = (item.body_md or item.body_html).strip().lower()
    if comparison_bodies and body:
        body_terms = set(re.findall(r"\b[a-z0-9]{4,}\b", body))
        for existing in comparison_bodies:
            other = set(re.findall(r"\b[a-z0-9]{4,}\b", (existing or "").lower()))
            if body_terms and other:
                overlap = len(body_terms & other) / max(1, len(body_terms | other))
                if overlap >= 0.72:
                    issues.append(GateIssue("cannibalization", f"Very high topical overlap ({overlap:.0%}) with existing/queued content", True))
                    break

    ok = not any(i.blocking for i in issues) or bool(getattr(item, "gate_override", False))
    return GateResult(ok=ok, issues=issues)
