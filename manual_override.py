"""Reviewed-article queue routes for Dolla Content Desk.

A human review action should be the final editorial step. Normal PASS articles and explicit manual
overrides are queued locally and pushed to GitHub immediately so there is no separate dashboard
"push queued" step for individually reviewed drafts.
"""
from __future__ import annotations

import json

from flask import request


def install(desk) -> None:
    app = desk.app

    def _queue_and_push(brief, notice: str):
        brief = desk.queue_brief(brief)
        try:
            desk.push_queue(brief)
        except Exception as exc:
            return desk.show_review(
                brief,
                error=(
                    "Article is safely queued on this PC, but GitHub push failed: " + str(exc)
                ),
            )
        return desk.show_review(brief, notice=notice)

    # Register each route independently. Older local sessions could already have one route
    # but not the other; a single early-return here caused BuildError for queue_reviewed.
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
            return _queue_and_push(
                brief,
                "Approved, queued and pushed to GitHub. Returning to the batch review list.",
            )

    if "queue_override" not in app.view_functions:
        @app.route("/queue-override", methods=["POST"], endpoint="queue_override")
        def queue_override():
            brief = desk.Brief.from_dict(json.loads(request.form["brief_json"]))
            brief.gate_override = True
            return _queue_and_push(
                brief,
                "Queued with a manual editorial override and pushed to GitHub. Returning to the batch review list.",
            )
