"""The record store — the unified place every domain's results land.

One JSON file per record, named by its content-addressed run_id, under a flat
directory. That's deliberately dumb: it's the "unified store" the dashboard reads
instead of a cosim-specific log, and because run_id is a content hash, re-running
the same experiment overwrites the same file (idempotent) rather than piling up.

Later steps read from here: the regression trend groups records by
(type, source_sha); cross-domain aggregation groups by type. Nothing here knows
what any domain means — it just stores and lists records.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class RecordStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, record: dict) -> dict:
        """Persist one record (dict form). Stamps created_at if the adapter left it
        blank. Keyed by run_id, so identical inputs overwrite in place."""
        if not record.get("created_at"):
            record["created_at"] = (
                datetime.now(timezone.utc).replace(microsecond=0)
                .isoformat().replace("+00:00", "Z"))
        run_id = record.get("run_id") or "unknown"
        (self.root / f"{run_id}.json").write_text(json.dumps(record, indent=2, default=str))
        return record

    def save_many(self, records) -> int:
        n = 0
        for rec in records:
            self.save(rec.to_dict() if hasattr(rec, "to_dict") else rec)
            n += 1
        return n

    def all(self) -> list[dict]:
        out = []
        for f in self.root.glob("*.json"):
            try:
                out.append(json.loads(f.read_text()))
            except (OSError, json.JSONDecodeError):
                continue
        out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return out

    def by_type(self, type_: str) -> list[dict]:
        return [r for r in self.all() if r.get("type") == type_]
