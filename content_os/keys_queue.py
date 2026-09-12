from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class KeysQueue:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def save(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(self, item: dict) -> dict:
        rows = self.load()
        slug = str(item.get("slug") or "")
        rows = [r for r in rows if str(r.get("slug") or "") != slug]
        row = dict(item)
        row["queued_at"] = datetime.now(timezone.utc).isoformat()
        row["status"] = "queued"
        rows.append(row)
        self.save(rows)
        return row

    def remove(self, slug: str) -> None:
        self.save([r for r in self.load() if str(r.get("slug") or "") != slug])

    def first(self) -> dict | None:
        rows = self.load()
        return rows[0] if rows else None
