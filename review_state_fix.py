"""Normalize review state for legacy browser drafts.

Older generated drafts were created when Brief.status defaulted to ``queued``. Those drafts may
still live in browser localStorage, so simply changing the model default does not repair them.
This shim makes review pages treat an article as queued only after a real queue action has just
succeeded. Normal review / re-run requests are always shown as proposed until the user approves
or manually overrides them.
"""
from __future__ import annotations


def install(desk) -> None:
    original_show_review = desk.show_review

    def show_review(brief, error=None, notice=None):
        # A real queue response always carries a queue-success notice. Legacy browser drafts can
        # carry status='queued' even though the user never approved them; neutralize that stale
        # status on ordinary review/gate rerun pages.
        queue_action_succeeded = bool(notice and "queued" in notice.lower())
        if not queue_action_succeeded:
            brief.status = "proposed"
        return original_show_review(brief, error=error, notice=notice)

    desk.show_review = show_review
