"""
core.state
Core domain data models (UI/LLM independent).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


Delta = Dict[str, float]


@dataclass(frozen=True)
class Stats:
    """Primary game metrics.

    All values are numeric; clamping rules are applied by core.effects.apply_delta().

    Minimal-but-useful set:
    - cash, mrr, reputation, churn
    - support_load, infra_load
    - morale (team): affects resilience
    - tech_debt: affects future risk / reliability cost
    """

    cash: float
    mrr: float
    reputation: float        # 0..100
    support_load: float      # 0..100
    infra_load: float        # 0..100
    churn: float             # 0..0.50
    morale: float            # 0..100
    tech_debt: float         # 0..100


@dataclass(frozen=True)
class DelayedEffect:
    """A delta that will apply at a future month."""
    due_month: int
    delta: Delta
    hint: str
    from_month: int


@dataclass(frozen=True)
class GameState:
    """Minimal core state.

    The UI may store extra fields, but core only needs:
    - month index
    - stats
    - delayed effects queue
    """
    month: int
    stats: Stats
    delayed_queue: List[DelayedEffect] = field(default_factory=list)


def stats_from_mapping(d: Mapping[str, float]) -> Stats:
    """Bridge helper for legacy dict-based stats."""
    return Stats(
        cash=float(d.get("cash", 0.0)),
        mrr=float(d.get("mrr", 0.0)),
        reputation=float(d.get("reputation", 50.0)),
        support_load=float(d.get("support_load", 20.0)),
        infra_load=float(d.get("infra_load", 20.0)),
        churn=float(d.get("churn", 0.05)),
        morale=float(d.get("morale", 55.0)),
        tech_debt=float(d.get("tech_debt", 25.0)),
    )


def stats_to_dict(s: Stats) -> Dict[str, float]:
    return {
        "cash": float(s.cash),
        "mrr": float(s.mrr),
        "reputation": float(s.reputation),
        "support_load": float(s.support_load),
        "infra_load": float(s.infra_load),
        "churn": float(s.churn),
        "morale": float(s.morale),
        "tech_debt": float(s.tech_debt),
    }


def default_start_state() -> GameState:
    """Baseline start state.

    Keep it in core so headless tests and UI share the same baseline.
    """
    return GameState(
        month=1,
        stats=Stats(
            cash=550_000.0,
            mrr=900.0,
            reputation=50.0,
            support_load=22.0,
            infra_load=22.0,
            churn=0.055,
            morale=58.0,
            tech_debt=22.0,
        ),
        delayed_queue=[],
    )
