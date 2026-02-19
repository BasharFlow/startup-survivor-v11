"""
core.effects
Economy / physics rules:
- delta sampling (templates + bounded noise)
- clamp rules
- delayed effects
- Turkey macro friction
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Tuple

from .modes import ModeSpec
from .rng import rng_from
from .state import Delta, DelayedEffect, Stats, clamp


# (base, variance) per stat, per tag
TEMPLATES: Dict[str, Dict[str, Tuple[float, float]]] = {
    "growth":       {"cash": (-60_000, 55_000), "mrr": (1_200, 900), "reputation": (3, 4), "support_load": (9, 6), "infra_load": (9, 6), "churn": (0.010, 0.010), "morale": (2, 4), "tech_debt": (6, 5)},
    "efficiency":   {"cash": (40_000, 50_000),  "mrr": (-200, 350), "reputation": (-2, 4), "support_load": (-6, 6), "infra_load": (-6, 6), "churn": (0.004, 0.008), "morale": (-1, 3), "tech_debt": (-3, 4)},
    "reliability":  {"cash": (-55_000, 45_000), "mrr": (-150, 250), "reputation": (4, 4), "support_load": (-10, 7), "infra_load": (-10, 7), "churn": (-0.008, 0.010), "morale": (1, 3), "tech_debt": (-6, 5)},
    "compliance":   {"cash": (-70_000, 55_000), "mrr": (-250, 250), "reputation": (6, 4), "support_load": (2, 4), "infra_load": (2, 4), "churn": (-0.004, 0.008), "morale": (-1, 2), "tech_debt": (1, 3)},
    "fundraising":  {"cash": (180_000, 160_000),"mrr": (0, 200),    "reputation": (1, 5), "support_load": (3, 4), "infra_load": (3, 4), "churn": (0.000, 0.006), "morale": (2, 4), "tech_debt": (2, 4)},
    "people":       {"cash": (-45_000, 45_000), "mrr": (150, 250),  "reputation": (3, 4), "support_load": (-8, 7), "infra_load": (-5, 6), "churn": (-0.003, 0.008), "morale": (7, 6), "tech_debt": (-1, 3)},
    "product":      {"cash": (-50_000, 45_000), "mrr": (700, 650),  "reputation": (3, 4), "support_load": (-3, 6), "infra_load": (2, 5), "churn": (-0.006, 0.010), "morale": (2, 4), "tech_debt": (2, 4)},
    "sales":        {"cash": (-25_000, 35_000), "mrr": (900, 850),  "reputation": (1, 4), "support_load": (4, 5), "infra_load": (3, 4), "churn": (0.006, 0.010), "morale": (1, 3), "tech_debt": (4, 4)},
    "marketing":    {"cash": (-45_000, 45_000), "mrr": (650, 650),  "reputation": (4, 4), "support_load": (2, 4), "infra_load": (2, 4), "churn": (-0.002, 0.009), "morale": (1, 3), "tech_debt": (2, 4)},
    "security":     {"cash": (-60_000, 50_000), "mrr": (-120, 250), "reputation": (5, 4), "support_load": (-6, 6), "infra_load": (-5, 6), "churn": (-0.006, 0.010), "morale": (-1, 3), "tech_debt": (2, 4)},
}



def sample_delta(tag: str, rng: random.Random, swing: float) -> Delta:
    tpl = TEMPLATES.get(tag, TEMPLATES["growth"])
    d: Dict[str, float] = {}
    for k, (base, var) in tpl.items():
        val = rng.uniform(base - var, base + var) * float(swing)
        d[k] = float(val)
    d["churn"] = clamp(float(d.get("churn", 0.0)), -0.05, 0.08)
    return d


def mode_adjustments(d: Delta, rng: random.Random, mode_key: str, spec: ModeSpec) -> Delta:
    d2 = dict(d)
    if spec.antagonistic:
        d2["cash"] = float(d2.get("cash", 0.0)) - rng.uniform(10_000, 40_000) * spec.swing
        d2["churn"] = float(d2.get("churn", 0.0)) + rng.uniform(0.002, 0.010) * spec.swing
        d2["reputation"] = float(d2.get("reputation", 0.0)) - rng.uniform(0, 4) * spec.swing
    if mode_key == "Zor":
        if rng.random() < 0.35:
            d2["cash"] = float(d2.get("cash", 0.0)) - rng.uniform(5_000, 25_000) * spec.swing
    return d2


def apply_case_bias(d: Delta, case_key: str, tag: str, month: int) -> Delta:
    # Keep identical to legacy behavior for now.
    out = dict(d)
    if case_key == "facebook_privacy_2019":
        if tag in {"compliance", "security"}:
            out["reputation"] = float(out.get("reputation", 0.0)) + 3.0
            out["churn"] = float(out.get("churn", 0.0)) - 0.004
        if tag in {"growth", "marketing"}:
            out["reputation"] = float(out.get("reputation", 0.0)) - 2.0
            out["churn"] = float(out.get("churn", 0.0)) + 0.004
    if case_key == "blackberry_platform_shift":
        if tag in {"product", "growth", "marketing"}:
            out["mrr"] = float(out.get("mrr", 0.0)) + 250
        if tag == "reliability":
            out["mrr"] = float(out.get("mrr", 0.0)) - 150
    if case_key == "wework_ipo_2019":
        if tag == "fundraising":
            out["cash"] = float(out.get("cash", 0.0)) + 60_000
            out["reputation"] = float(out.get("reputation", 0.0)) - 1.5
        if tag == "efficiency":
            out["reputation"] = float(out.get("reputation", 0.0)) + 1.5
    return out


def apply_delta(stats: Stats, delta: Delta) -> Stats:
    """Apply delta with clamp rules (pure function)."""
    cash = max(0.0, stats.cash + float(delta.get("cash", 0.0)))
    mrr = max(0.0, stats.mrr + float(delta.get("mrr", 0.0)))
    reputation = clamp(stats.reputation + float(delta.get("reputation", 0.0)), 0.0, 100.0)
    support_load = clamp(stats.support_load + float(delta.get("support_load", 0.0)), 0.0, 100.0)
    infra_load = clamp(stats.infra_load + float(delta.get("infra_load", 0.0)), 0.0, 100.0)
    churn = clamp(stats.churn + float(delta.get("churn", 0.0)), 0.0, 0.50)
    morale = clamp(stats.morale + float(delta.get("morale", 0.0)), 0.0, 100.0)
    tech_debt = clamp(stats.tech_debt + float(delta.get("tech_debt", 0.0)), 0.0, 100.0)
    return Stats(
        cash=float(cash),
        mrr=float(mrr),
        reputation=float(reputation),
        support_load=float(support_load),
        infra_load=float(infra_load),
        churn=float(churn),
        morale=float(morale),
        tech_debt=float(tech_debt),
    )


def due_delayed_effects(queue: List[DelayedEffect], month: int) -> Tuple[List[DelayedEffect], List[DelayedEffect]]:
    due = [x for x in queue if int(x.due_month) == int(month)]
    remaining = [x for x in queue if int(x.due_month) != int(month)]
    return due, remaining


def schedule_delayed_effect(
    queue: List[DelayedEffect],
    *,
    base_seed: int,
    scenario_seed: int,
    month: int,
    choice_key: str,
    tag: str,
    risk: str,
    seed_phrase: str,
    spec: ModeSpec,
) -> List[DelayedEffect]:
    """Possibly enqueue a delayed effect. Returns the new queue."""
    rng = rng_from('delay-roll', scenario_seed, month, choice_key, base_seed=base_seed)
    p = {"low": 0.35, "med": 0.60, "high": 0.82}.get(risk, 0.60)
    if spec.antagonistic:
        p = min(0.95, p + 0.10)
    if rng.random() > p:
        return queue

    due = month + (1 if rng.random() < 0.6 else 2)

    delayed_tag = tag
    if tag == "efficiency":
        delayed_tag = "people" if rng.random() < 0.5 else "reliability"
    if tag == "growth":
        delayed_tag = "reliability" if rng.random() < 0.4 else "growth"

    base = sample_delta(delayed_tag, rng, swing=0.55 * spec.swing)

    base["cash"] = float(base.get("cash", 0.0)) - abs(float(base.get("cash", 0.0))) * 0.25
    base["reputation"] = float(base.get("reputation", 0.0)) - max(0.0, float(base.get("reputation", 0.0))) * 0.15
    base["churn"] = float(base.get("churn", 0.0)) + abs(float(base.get("churn", 0.0))) * 0.35

    new_item = DelayedEffect(
        due_month=int(due),
        delta=base,
        hint=(seed_phrase or "Gecikmeli etki")[:80],
        from_month=int(month),
    )
    return [*queue, new_item]


def turkey_macro_cost(*, base_seed: int, scenario_seed: int, month: int) -> float:
    """Deterministic-ish macro pressure. Returns extra monthly cost."""
    rng = rng_from('turkey-macro', scenario_seed, month, base_seed=base_seed)
    inflation = 0.03 + (0.01 * (month / 6.0))
    fx_shock = rng.uniform(-0.01, 0.05)
    audit = rng.uniform(15_000, 85_000) if rng.random() < 0.18 else 0.0
    disaster = rng.uniform(25_000, 160_000) if rng.random() < 0.06 else 0.0
    return max(0.0, (inflation + fx_shock) * 40_000 + audit + disaster)


# -------------------------
# Engine helpers
# -------------------------


def apply_delta_to_state(state: "GameState", delta: Delta) -> "GameState":
    """Apply a delta to state's stats (pure)."""
    from .state import GameState

    new_stats = apply_delta(state.stats, delta)
    return GameState(month=int(state.month), stats=new_stats, delayed_queue=list(state.delayed_queue))


def apply_delayed_effects_due(state: "GameState", month: int) -> tuple["GameState", list[DelayedEffect]]:
    """Apply due delayed effects for this month and remove them from queue."""
    from .state import GameState

    due, remaining = due_delayed_effects(list(state.delayed_queue), int(month))
    stats = state.stats
    for ev in due:
        stats = apply_delta(stats, ev.delta)
    return GameState(month=int(state.month), stats=stats, delayed_queue=remaining), due


def apply_monthly_burn(
    state: "GameState",
    *,
    expenses: Dict[str, float],
    base_seed: int,
    scenario_seed: int,
    month: int,
    turkey_mode: bool,
) -> tuple["GameState", float, float]:
    """Apply monthly cashflow: +MRR, -expenses, -macro friction.

    Returns (new_state, total_burn, macro_cost)
    """
    from .state import GameState

    fixed = float(sum(float(v) for v in dict(expenses).values()))
    macro = float(turkey_macro_cost(base_seed=int(base_seed), scenario_seed=int(scenario_seed), month=int(month))) if turkey_mode else 0.0

    net = float(state.stats.mrr) - fixed - macro
    new_stats = apply_delta(state.stats, {"cash": net})
    return GameState(month=int(state.month), stats=new_stats, delayed_queue=list(state.delayed_queue)), float(fixed + macro), float(macro)
