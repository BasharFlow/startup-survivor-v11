"""engine.logging

Small helpers for storing run logs.

A run log is JSON-serializable so it can be exported/imported later.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, List

from core.state import GameState


def make_run_export(*, seed: int, config: Dict[str, Any], initial_state: GameState, month_logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "version": 1,
        "seed": int(seed),
        "config": dict(config),
        "initial_state": asdict(initial_state),
        "month_logs": list(month_logs),
    }


def dumps_run_export(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
