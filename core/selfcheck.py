"""
core.selfcheck
Minimal "it runs" proof for Çatı 1.

Run:
  python -m core.selfcheck
"""

from __future__ import annotations

from dataclasses import asdict

from .effects import (
    apply_case_bias,
    apply_delta,
    due_delayed_effects,
    mode_adjustments,
    sample_delta,
    schedule_delayed_effect,
    turkey_macro_cost,
)
from .modes import get_mode_spec
from .rng import rng_from
from .state import GameState, Stats


def run_12_months_smoke() -> None:
    base_seed = 42
    scenario_seed = 2019
    case_key = "free"
    mode_key = "Gerçekçi"
    spec = get_mode_spec(mode_key)

    state = GameState(
        month=1,
        stats=Stats(cash=1_000_000, mrr=0.0, reputation=50.0, support_load=20.0, infra_load=20.0, churn=0.05, morale=60.0, tech_debt=20.0),
        delayed_queue=[],
    )

    expenses_total = 61_400  # arbitrary fixed monthly expense baseline

    for m in range(1, 13):
        # due delays first
        due, remaining = due_delayed_effects(state.delayed_queue, m)
        stats = state.stats
        for ev in due:
            stats = apply_delta(stats, ev.delta)

        # monthly expense + optional macro
        macro = turkey_macro_cost(base_seed=base_seed, scenario_seed=scenario_seed, month=m) if spec.turkey else 0.0
        stats = apply_delta(stats, {"cash": -(expenses_total + macro)})

        # choose alternating tags
        choice_key = "A" if m % 2 == 1 else "B"
        tag = "growth" if choice_key == "A" else "reliability"
        risk = "med"
        seed_phrase = "selfcheck"

        rng = rng_from('immediate', scenario_seed, m, choice_key, base_seed=base_seed)
        delta = sample_delta(tag, rng, swing=spec.swing)
        delta = mode_adjustments(delta, rng, mode_key, spec)
        delta = apply_case_bias(delta, case_key, tag, m)

        stats = apply_delta(stats, delta)

        # schedule delayed
        new_queue = schedule_delayed_effect(
            remaining,
            base_seed=base_seed,
            scenario_seed=scenario_seed,
            month=m,
            choice_key=choice_key,
            tag=tag,
            risk=risk,
            seed_phrase=seed_phrase,
            spec=spec,
        )

        state = GameState(month=m + 1, stats=stats, delayed_queue=new_queue)

        # invariants
        assert 0.0 <= state.stats.reputation <= 100.0
        assert 0.0 <= state.stats.support_load <= 100.0
        assert 0.0 <= state.stats.infra_load <= 100.0
        assert 0.0 <= state.stats.churn <= 0.50
        assert state.stats.cash >= 0.0
        assert state.stats.mrr >= 0.0

    print("OK: 12-month core smoke test passed.")
    print("Final stats:", asdict(state.stats))
    print("Delayed queue size:", len(state.delayed_queue))


if __name__ == "__main__":
    run_12_months_smoke()
