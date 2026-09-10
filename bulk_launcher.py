"""Backward-compatible launcher for the Dolla Content Desk Flask app.

All routes live in app.py so importing or running the app directly has the complete workflow.
"""
from __future__ import annotations

import os

import app as desk

app = desk.app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True)
