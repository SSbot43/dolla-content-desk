import os
from pathlib import Path
from dotenv import load_dotenv
from content_os.adapters.wordpress_bridge import ContentBridgeClient

root = Path(__file__).resolve().parent
load_dotenv(root / '.env.keys-shop', override=True)
client = ContentBridgeClient(os.environ['KEYS_WP_URL'], os.environ['KEYS_CONTENT_OS_SECRET'])
result = client.create_post({
    'title': 'Keys Content Desk Draft Test',
    'slug': 'keys-content-desk-draft-test',
    'content': '<p>Private draft test for the Keys-Shop Content Desk. Do not publish.</p>',
    'excerpt': 'Private Content Desk test.',
    'status': 'draft',
    'meta_title': 'Keys Content Desk Draft Test',
    'meta_description': 'Private draft used only to verify the Content Desk bridge.'
})
print('SUCCESS: draft created')
print('Post ID:', result.get('id'))
print('Status:', result.get('status'))
print('URL:', result.get('url'))
