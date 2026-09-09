"""Dolla Content Desk launcher with bulk queue helpers.

Keeps app.py unchanged while adding two workflow routes:
- Queue for later: save approved articles locally without a Git push.
- Push all queued: commit/push the whole queue and all queued images in one go.
"""
from __future__ import annotations

import json
import os
from datetime import date

from flask import redirect, request, url_for

import app as desk

app = desk.app


@app.route("/queue-local", methods=["POST"])
def queue_local():
    brief = desk.Brief.from_dict(json.loads(request.form["brief_json"]))
    result = desk.gate_run(brief, published_bodies=desk.comparison_bodies(brief.slug))
    if not result.ok:
        return desk.show_review(brief, error="Still blocked — fix the blocking issues before queueing.")

    brief = desk.queue_brief(result.fixed_brief or brief)
    return desk.show_review(
        brief,
        notice=(
            "Queued locally — not pushed yet. You can approve more articles now, then use "
            "Push all queued on the dashboard once when you are finished."
        ),
    )


@app.route("/push-queued-all", methods=["POST"])
def push_queued_all():
    published = desk.load_published()
    queue = [b for b in desk.load_queue() if b.body_md and b.slug not in published]
    if not queue:
        return redirect(url_for("dashboard", pushed=0))

    paths = {"content/queue.json"}
    for brief in queue:
        image_path = desk.image_repo_path(brief.image)
        if image_path:
            paths.add(image_path)

    try:
        desk.commit_and_push(paths, f"Queue Dolla content batch {date.today().isoformat()}")
    except Exception as exc:
        return redirect(url_for("dashboard", push_error=str(exc)[:500]))

    return redirect(url_for("dashboard", pushed=len(queue)))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True)
