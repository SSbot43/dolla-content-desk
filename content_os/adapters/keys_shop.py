from __future__ import annotations
import os
from .wordpress import WordPressClient, WordPressError

class KeysShopAdapter:
    site_base = "https://keys-shop.in"

    def __init__(self, client: WordPressClient | None = None):
        self.client = client or WordPressClient(
            os.environ.get("KEYS_WP_URL", self.site_base),
            os.environ.get("KEYS_WP_USERNAME", ""),
            os.environ.get("KEYS_WP_APP_PASSWORD", ""),
        )

    def validate_connection(self) -> dict:
        user = self.client.auth_check()
        return {"ok": True, "user_id": user.get("id"), "name": user.get("name")}

    def publish(self, item, *, immediate: bool = False, dry_run: bool = False) -> dict:
        existing = self.client.find_post_by_slug(item.slug)
        if existing:
            raise WordPressError(f"Duplicate slug already exists in WordPress: {item.slug}")

        featured_media = item.featured_media_id
        if item.featured_image_path and not featured_media and not dry_run:
            featured_media = self.client.upload_media(item.featured_image_path, getattr(item, "image_alt", ""))["id"]

        status = "publish" if immediate else (item.status if item.status in {"draft", "future", "publish", "pending"} else "draft")
        payload = {
            "title": item.title,
            "slug": item.slug,
            "content": item.body_html or item.body_md,
            "excerpt": item.excerpt or item.meta_description,
            "status": status,
        }
        if item.publish_date and not immediate:
            payload["date"] = item.publish_date
            if status == "draft":
                payload["status"] = "future"
        if item.author_id:
            payload["author"] = item.author_id
        if item.category_ids:
            payload["categories"] = item.category_ids
        if item.tag_ids:
            payload["tags"] = item.tag_ids
        if featured_media:
            payload["featured_media"] = featured_media

        yoast_meta = {}
        if item.meta_title:
            yoast_meta["_yoast_wpseo_title"] = item.meta_title
        if item.meta_description:
            yoast_meta["_yoast_wpseo_metadesc"] = item.meta_description
        if os.environ.get("KEYS_YOAST_META_WRITABLE", "").lower() in {"1", "true", "yes"} and yoast_meta:
            payload["meta"] = yoast_meta

        if dry_run:
            return {"dry_run": True, "payload": payload}
        created = self.client.create_post(payload)
        return {"dry_run": False, "post_id": created.get("id"), "url": created.get("link"), "status": created.get("status")}
