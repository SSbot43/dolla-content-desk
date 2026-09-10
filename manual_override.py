"""Reviewed-article queue routes for Dolla Content Desk.

A human review action should be the final editorial step. PASS articles and explicit manual
overrides are saved to the local publishing queue immediately, the review UI returns at once,
and GitHub synchronisation continues in a background worker. This keeps editorial review fast
without dropping the remote queue sync.
"""
from __future__ import annotations

import json
import threading
import time

from flask import request


_PUSH_LOCK = threading.Lock()


def install(desk) -> None:
    app = desk.app

    def _background_push(brief) -> None:
        """Serialize Git pushes and retry transient failures without blocking the review UI."""
        with _PUSH_LOCK:
            last_error = None
            for attempt in range(3):
                try:
                    desk.push_queue(brief)
                    print(f"[Content Desk] GitHub queue sync complete: {brief.slug}", flush=True)
                    return
                except Exception as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(2 + attempt * 2)
            print(
                f"[Content Desk] WARNING: article remains safely queued locally but GitHub sync "
                f"failed for {brief.slug}: {last_error}",
                flush=True,
            )

    def _queue_now_sync_later(brief, notice: str):
        # Saving locally is the user-visible completion point. Once this succeeds the review tab
        # can close immediately; the slower fetch/merge/push is deliberately off the request path.
        brief = desk.queue_brief(brief)
        threading.Thread(target=_background_push, args=(brief,), daemon=True).start()
        return desk.show_review(brief, notice=notice)

    # Register each route independently. Older local sessions could already have one route
    # but not the other; a single early-return here previously caused BuildError.
    if "queue_reviewed" not in app.view_functions:
        @app.route("/queue-reviewed", methods=["POST"], endpoint="queue_reviewed")
        def queue_reviewed():
            brief = desk.Brief.from_dict(json.loads(request.form["brief_json"]))
            result = desk.gate_run(brief, published_bodies=desk.comparison_bodies(brief.slug))
            if not result.ok:
                return desk.show_review(
                    brief,
                    error="Still blocked — use the manual override only if you have personally reviewed the article.",
                )
            brief = result.fixed_brief or brief
            return _queue_now_sync_later(
                brief,
                "Approved and queued. GitHub sync is running in the background. Returning to the batch review list.",
            )

    if "queue_override" not in app.view_functions:
        @app.route("/queue-override", methods=["POST"], endpoint="queue_override")
        def queue_override():
            brief = desk.Brief.from_dict(json.loads(request.form["brief_json"]))
            brief.gate_override = True
            return _queue_now_sync_later(
                brief,
                "Queued with a manual editorial override. GitHub sync is running in the background. Returning to the batch review list.",
            )
