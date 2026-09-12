from content_os.models import ContentItem
from content_os.quality import run
from content_os.adapters.keys_shop import KeysShopAdapter

class FakeWP:
    def __init__(self):
        self.created = []
    def auth_check(self):
        return {"id": 7, "name": "Editor"}
    def find_post_by_slug(self, slug):
        return None
    def create_post(self, payload):
        self.created.append(payload)
        return {"id": 123, "link": "https://keys-shop.in/example/", "status": payload["status"]}
    def upload_media(self, file_path, alt_text=""):
        return {"id": 55}

def long_body():
    return " ".join(["Useful software buying guidance with specific checks and practical advice"] * 80)

def test_quality_blocks_risky_claim():
    item = ContentItem(slug="x", title="X", body_md=long_body() + " official partner")
    result = run(item)
    assert not result.ok
    assert any(i.code == "official_partner" for i in result.blocking)

def test_manual_override_is_recordable_and_allows_gate():
    item = ContentItem(slug="x", title="X", body_md=long_body() + " official partner", gate_override=True, override_reason="Verified by editor")
    result = run(item)
    assert result.ok
    assert result.blocking

def test_publish_payload_supports_wordpress_fields():
    wp = FakeWP()
    adapter = KeysShopAdapter(client=wp)
    item = ContentItem(slug="guide", title="Guide", body_html="<p>Body</p>", meta_description="Desc", category_ids=[2], tag_ids=[3], author_id=7, status="publish")
    result = adapter.publish(item)
    assert result["post_id"] == 123
    payload = wp.created[0]
    assert payload["categories"] == [2]
    assert payload["tags"] == [3]
    assert payload["author"] == 7
    assert payload["status"] == "publish"

def test_immediate_publish_bypasses_future_status():
    wp = FakeWP()
    adapter = KeysShopAdapter(client=wp)
    item = ContentItem(slug="breaking", title="Breaking", body_html="<p>Body</p>", publish_date="2026-09-20T10:00:00", status="future")
    adapter.publish(item, immediate=True)
    assert wp.created[0]["status"] == "publish"
    assert "date" not in wp.created[0]
