# dolla-content-desk

Local **content control desk** for the `dollacasino.com` SEO sprint. It sits on top of the existing
`dollacasino-content` engine; it does **not** reimplement generation, claims policy, quality gating,
rendering, ramp scheduling, or publishing.

## Run
```bash
pip install -r requirements.txt
set CONTENT_REPO=C:/path/to/dollacasino-content
set GEMINI_API_KEY=...
python bulk_launcher.py
```
Then open `http://127.0.0.1:5000`.

On Windows, `START_WINDOWS.bat` automatically uses a sibling `dollacasino-content` folder and
overrides stale `CONTENT_REPO` values from copied `.env` files.

## Current workflow
- **Dashboard** — today's ramp cap, queued/draft/live counts, system status, upcoming queue, live guides.
- **Generate with Gemini** — fill the brief and let the existing engine generate + repair the draft.
- **My own article** — paste your own Markdown/article text and send it through the exact same quality and claims gate.
- **Optional images** — publish without an image, or paste one from the clipboard, drag/drop one, choose a file, or use an image URL. Attached images require alt text and uploads are saved under `static/img/guides/` in the content repo.
- **Editable review** — edit title, meta, H1, body, image, market and other Brief fields, then re-run the quality gate.
- **Queue & Push** — assigns the next valid ramp slot, commits the queue (and its local image when needed), and pushes to GitHub so the scheduled publisher can see it.
- **Publish & Push** — one click from a passing review: queue → existing `run_publish()` → stage content-owned output → commit → `git push`. Cloudflare then deploys from the content repo push.

## Safety / architecture
- The `dolla_content` engine remains the source of truth.
- Every queue/publish action re-runs the server-side quality gate.
- A blocked article cannot queue or publish.
- Publish commits stage only content-workflow files and referenced guide images, rather than sweeping unrelated local changes into the commit.
- Git uses the machine's existing credential manager; the UI does not store a GitHub token.
