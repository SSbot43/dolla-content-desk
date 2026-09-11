from __future__ import annotations
from dataclasses import dataclass, field, asdict

@dataclass
class ContentItem:
    slug: str
    title: str
    body_html: str = ""
    body_md: str = ""
    meta_title: str = ""
    meta_description: str = ""
    primary_keyword: str = ""
    excerpt: str = ""
    status: str = "draft"
    publish_date: str = ""
    author_id: int | None = None
    category_ids: list[int] = field(default_factory=list)
    tag_ids: list[int] = field(default_factory=list)
    featured_media_id: int | None = None
    featured_image_path: str = ""
    internal_links: list[str] = field(default_factory=list)
    gate_override: bool = False
    override_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
