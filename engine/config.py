"""engine.config

Engine configuration passed from UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class EngineConfig:
    base_seed: int
    scenario_seed: int
    mode_key: str
    case_key: str
    expenses: Dict[str, float]
    season_length: int = 12
