# Keys-Shop Content OS MVP

This branch adds the first reusable Content OS layer without changing the live Dolla workflow.

## One-time WordPress setup

1. In WordPress, create a dedicated user named something like `content-desk` with the **Editor** role.
2. Open that user's profile and create an **Application Password** named `Keys Content Desk`.
3. Put the values in the local `.env` file (do not commit them):

```env
KEYS_WP_URL=https://keys-shop.in
KEYS_WP_USERNAME=content-desk
KEYS_WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
```

The existing `GEMINI_API_KEY` and optional `OPENAI_API_KEY` can be reused by the shared generation engine.

## Yoast metadata

Yoast SEO exposes metadata in REST responses, but its SEO title/description fields are not reliably writable through the standard WordPress post endpoint by default. The adapter therefore does not send Yoast private meta unless a small WordPress-side bridge explicitly registers those fields as REST-writable.

When that bridge is installed and tested, enable:

```env
KEYS_YOAST_META_WRITABLE=true
```

## Safety

- Duplicate slugs are blocked before publishing.
- The Keys-Shop gate blocks risky claims and thin content and warns on AI-style filler phrases.
- Manual override remains possible and carries an override reason in the shared content model.
- `immediate=True` bypasses scheduling only for an explicitly requested immediate publish.
- Nothing on this branch is deployed to WordPress until the authenticated REST connection and a draft post are tested successfully.
