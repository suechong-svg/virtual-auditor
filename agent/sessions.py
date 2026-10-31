"""Registry of past chat sessions so an auditor can resume one after a restart.

The conversation transcript itself is stored by the agent runtime (Claude Agent SDK) on
this machine and reloaded with `resume=<session_id>`. This file only keeps the list
(id, title, who, when) so the UI can offer it. Production: a database table keyed by
user and Teams thread.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import config


def _load() -> list[dict]:
    if config.SESSIONS_FILE.exists():
        try:
            return json.loads(config.SESSIONS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def recent(limit: int = 5) -> list[dict]:
    items = sorted(_load(), key=lambda s: s.get("last_used", ""), reverse=True)
    return items[:limit]


def record(session_id: str, title: str) -> None:
    """Add a session, or bump last_used if it is already listed."""
    if not session_id:
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    items = _load()
    for s in items:
        if s["session_id"] == session_id:
            s["last_used"] = now
            break
    else:
        items.append({"session_id": session_id, "title": title[:80], "user": config.AUDITOR_NAME,
                      "started": now, "last_used": now})
    config.SESSIONS_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")
