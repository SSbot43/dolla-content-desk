"""Manual editorial override route for blocked Content Desk drafts.

This is intentionally separate from the normal queue route: a human must click the dedicated
button and confirm they have reviewed the article. The queued brief records gate_override=True so
the scheduled publisher can honor that decision later.
"""
from __future__ import annotations

import json

from flask import request


def install(desk) -> None:
    app = desk.app

    if "queue_override" in app.view_functions:
        return

    @app.route("/queue-override", methods=["POST"], endpoint="queue_override")
    def queue_override():
        brief = desk.Brief.from_dict(json.loads(request.form["brief_json"]))
        brief.gate_override = True
        brief = desk.queue_brief(brief)
        return desk.show_review(
            brief,
            notice="Queued with manual editorial override. The scheduled publisher will honor this override.",
        )
