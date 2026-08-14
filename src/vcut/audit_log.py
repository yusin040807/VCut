from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def append_event(project_root: Path, event: str, outcome: str = "success", **details: Any) -> None:
    record = {"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "event": event, "outcome": outcome, **details}
    path = project_root / "audit_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
