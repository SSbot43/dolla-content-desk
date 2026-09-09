# dolla-content-desk

Local **desktop dashboard** for the `dollacasino.com` content sprint. One screen to feed the
pipeline: drop a keyword → **Gemini** writes a draft → the **quality gate** validates → you queue it
→ the publisher (in `dollacasino-content`) ships it on the ramp.

It wraps the `dolla_content` backbone and adds no content logic of its own — the gate, claims policy,
render and Gemini link all live in the content repo.

## Run
```bash
pip install -r requirements.txt
set CONTENT_REPO=E:/Claude work/dollacasino-content   # path to the backbone repo
set GEMINI_API_KEY=...                                 # from aistudio.google.com (generate mode only)
python app.py                                          # http://127.0.0.1:5000
```

## Screens
- **Dashboard** — today's ramp cap, queued / drafts / live counts, Gemini-key status, upcoming queue, recently live.
- **New article** — pick *Generate with Gemini (from keyword)* or *paste the body*; fill the brief.
- **Review** — quality-gate verdict (pass/block + every issue + auto-fixes) and a live page preview; **Queue it** is disabled unless the gate passes.

## How it connects
- Reads/writes `CONTENT_REPO/content/queue.json` (creating it from `queue.sample.json` on first write).
- Assigns each queued article the **next free date under the ramp** (`daily_cap`).
- Re-validates server-side on queue — never trusts the browser round-trip.

Packaging into a real `.exe` (PyInstaller/Electron wrap) is a later step; it runs as a local web app today.
