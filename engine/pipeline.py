"""engine.pipeline

Core month flow (headless).

Responsibilities:
- Convert MonthDraft (narrative + intent) -> MonthBundle (includes deltas)
- Apply due delayed effects + expenses + choice delta
- Schedule delayed effects

This layer is UI-agnostic.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Tuple

from core.effects import (
    DelayedEffect,
    apply_case_bias,
    apply_delta,
    due_delayed_effects,
    mode_adjustments,
    sample_delta,
    schedule_delayed_effect,
    turkey_macro_cost,
)
from core.modes import get_mode_spec
from core.rng import rng_from
from core.state import GameState, stats_to_dict

from content.schemas import (
    ChoiceIntent,
    DelayedEffectSpec,
    MonthBundle,
    MonthDraft,
    OptionSpec,
    validate_month_bundle,
)

from .config import EngineConfig


def _risk_tr(r: str) -> str:
    return {"low": "Düşük", "med": "Orta", "high": "Yüksek"}.get(r, r)


def _steps_to_text(steps: List[str]) -> str:
    return "\n".join([f"- {s}" for s in steps])


def draft_to_bundle(draft: MonthDraft, config: EngineConfig) -> MonthBundle:
    """Deterministically convert narrative draft into engine-ready MonthBundle."""
    spec = get_mode_spec(config.mode_key)

    options: List[OptionSpec] = []
    for opt in list(draft.options):
        rng = rng_from(
            "choice",
            int(config.scenario_seed),
            int(draft.month_id),
            str(opt.id),
            base_seed=int(config.base_seed),
        )
        delta = sample_delta(opt.tag, rng, swing=float(spec.swing))
        delta = mode_adjustments(delta, rng, config.mode_key, spec)
        delta = apply_case_bias(delta, config.case_key, opt.tag, int(draft.month_id))

        # delayed effect: reuse the deterministic scheduler, but convert into a spec list
        q0: List[DelayedEffect] = []
        q1 = schedule_delayed_effect(
            q0,
            base_seed=int(config.base_seed),
            scenario_seed=int(config.scenario_seed),
            month=int(draft.month_id),
            choice_key=str(opt.id),
            tag=str(opt.tag),
            risk=str(opt.risk),
            seed_phrase=str(opt.delayed_seed),
            spec=spec,
        )
        delayed_specs: List[DelayedEffectSpec] = []
        for ev in q1:
            delayed_specs.append(
                DelayedEffectSpec(
                    delay_months=int(ev.due_month) - int(draft.month_id),
                    delta=dict(ev.delta),
                    description=str(ev.hint or "Gecikmeli etki"),
                )
            )
        desc = (
            f"{_steps_to_text(list(opt.steps))}\n\n"
            f"Risk: {_risk_tr(opt.risk)}\n"
            f"Odak: {opt.tag}"
        )

        options.append(
            OptionSpec(
                id=str(opt.id),
                label=str(opt.title),
                tag=str(opt.tag),
                risk=str(opt.risk),
                steps=list(opt.steps),
                description=desc,
                immediate_effects=dict(delta),
                delayed_effects=list(delayed_specs),
                narrative_result=str(getattr(opt, "result", "") or "").strip(),
            )
        )

    title = (draft.month_title or f"Ay {int(draft.month_id)}: Karar Ayı").strip()

    bundle = MonthBundle(
        month_id=int(draft.month_id),
        title=title,
        context=str(draft.durum_analizi),
        crisis_title=str(draft.kriz_title or "Kriz"),
        crisis=str(draft.kriz),
        options=options,
        tags=[str(o.tag) for o in list(draft.options)],
        intensity=None,
        stakeholders=[],
        risk_notes=str(draft.note or ""),
        cliffhanger=str(getattr(draft, "cliffhanger", "") or "").strip(),
        lesson=str(getattr(draft, "lesson", "") or "").strip(),
        alternatives=list(getattr(draft, "alternatives", []) or []),
    )

    validate_month_bundle(bundle)
    return bundle


def apply_choice(
    *,
    state: GameState,
    bundle: MonthBundle,
    choice_id: str,
    config: EngineConfig,
) -> Tuple[GameState, Dict[str, Any]]:
    """Apply a choice to a state and advance to next month.

    Returns (new_state, month_log).
    """
    month = int(state.month)
    if int(bundle.month_id) != month:
        # allow, but log mismatch
        pass

    spec = get_mode_spec(config.mode_key)

    before_stats = stats_to_dict(state.stats)

    # 1) due delayed effects
    due, remaining = due_delayed_effects(list(state.delayed_queue), month)
    s = state.stats
    due_events: List[Dict[str, Any]] = []
    for ev in due:
        s = apply_delta(s, ev.delta)
        due_events.append({"from_month": int(ev.from_month), "hint": str(ev.hint), "delta": dict(ev.delta)})

    # 2) expenses + optional TR macro
    total_exp = float(sum((config.expenses or {}).values()))
    macro_extra = float(turkey_macro_cost(base_seed=int(config.base_seed), scenario_seed=int(config.scenario_seed), month=month)) if spec.turkey else 0.0
    s = apply_delta(s, {"cash": -(total_exp + macro_extra)})

    # 3) choice delta
    opt = next((o for o in bundle.options if str(o.id) == str(choice_id)), None)
    if opt is None:
        raise ValueError(f"Unknown choice_id: {choice_id}")

    s = apply_delta(s, opt.immediate_effects)

    # 4) schedule delayed effects explicitly
    q: List[DelayedEffect] = list(remaining)
    for ds in list(opt.delayed_effects or []):
        q.append(
            DelayedEffect(
                due_month=int(month) + int(ds.delay_months),
                delta=dict(ds.delta),
                hint=str(ds.description),
                from_month=int(month),
            )
        )

    new_state = GameState(month=month + 1, stats=s, delayed_queue=q)

    after_stats = stats_to_dict(new_state.stats)

    log: Dict[str, Any] = {
        "month": month,
        "choice": str(choice_id),
        "choice_label": opt.label,
        "before": dict(before_stats),
        "after": dict(after_stats),
        "due_effects": due_events,
        "expenses": float(total_exp),
        "macro_extra": float(macro_extra),
        "immediate_delta": dict(opt.immediate_effects),
        "scheduled_delays": [asdict(ds) for ds in list(opt.delayed_effects or [])],
    }
    return new_state, log


def intent_to_option_spec(
    *,
    intent: ChoiceIntent,
    month_id: int,
    config: EngineConfig,
    choice_id: str = "YOU",
) -> OptionSpec:
    """Deterministically convert a player's ChoiceIntent into an OptionSpec.

    Economy remains deterministic: we only use intent.tag/risk/delayed_seed as signals.
    """
    spec = get_mode_spec(config.mode_key)
    rng = rng_from("player-choice", int(config.scenario_seed), int(month_id), str(choice_id), base_seed=int(config.base_seed))
    delta = sample_delta(str(intent.tag), rng, swing=float(spec.swing))
    delta = mode_adjustments(delta, rng, config.mode_key, spec)
    delta = apply_case_bias(delta, config.case_key, str(intent.tag), int(month_id))

    q0: List[DelayedEffect] = []
    q1 = schedule_delayed_effect(
        q0,
        base_seed=int(config.base_seed),
        scenario_seed=int(config.scenario_seed),
        month=int(month_id),
        choice_key=str(choice_id),
        tag=str(intent.tag),
        risk=str(intent.risk),
        seed_phrase=str(intent.delayed_seed),
        spec=spec,
    )
    delayed_specs: List[DelayedEffectSpec] = []
    for ev in q1:
        delayed_specs.append(
            DelayedEffectSpec(
                delay_months=int(ev.due_month) - int(month_id),
                delta=dict(ev.delta),
                description=str(ev.hint or "Gecikmeli etki"),
            )
        )
    desc = (
        f"{_steps_to_text(list(intent.steps))}\n\n"
        f"Risk: {_risk_tr(str(intent.risk))}\n"
        f"Odak: {intent.tag}"
    )

    return OptionSpec(
        id=str(choice_id),
        label=str(intent.title),
        tag=str(intent.tag),
        risk=str(intent.risk),
        steps=list(intent.steps),
        description=desc,
        immediate_effects=dict(delta),
        delayed_effects=list(delayed_specs),
        narrative_result=str(intent.result or "").strip(),
    )


def apply_option_spec(
    *,
    state: GameState,
    option: OptionSpec,
    month_id: int,
    config: EngineConfig,
) -> Tuple[GameState, Dict[str, Any]]:
    """Apply an OptionSpec (used for custom player plans).

    Mirrors apply_choice() logic, but does not require the option to be inside a MonthBundle.
    """
    spec = get_mode_spec(config.mode_key)

    before_stats = stats_to_dict(state.stats)

    # 1) due delayed effects
    due, remaining = due_delayed_effects(list(state.delayed_queue), int(month_id))
    s = state.stats
    due_events: List[Dict[str, Any]] = []
    for ev in due:
        s = apply_delta(s, ev.delta)
        due_events.append({"from_month": int(ev.from_month), "hint": str(ev.hint), "delta": dict(ev.delta)})

    # 2) expenses + optional TR macro
    total_exp = float(sum((config.expenses or {}).values()))
    macro_extra = float(turkey_macro_cost(base_seed=int(config.base_seed), scenario_seed=int(config.scenario_seed), month=int(month_id))) if spec.turkey else 0.0
    s = apply_delta(s, {"cash": -(total_exp + macro_extra)})

    # 3) option delta
    s = apply_delta(s, option.immediate_effects)

    # 4) schedule delayed effects explicitly
    q: List[DelayedEffect] = list(remaining)
    for ds in list(option.delayed_effects or []):
        q.append(
            DelayedEffect(
                due_month=int(month_id) + int(ds.delay_months),
                delta=dict(ds.delta),
                hint=str(ds.description),
                from_month=int(month_id),
            )
        )

    new_state = GameState(month=int(month_id) + 1, stats=s, delayed_queue=q)
    after_stats = stats_to_dict(new_state.stats)

    log: Dict[str, Any] = {
        "month": int(month_id),
        "choice": str(option.id),
        "choice_label": option.label,
        "before": dict(before_stats),
        "after": dict(after_stats),
        "due_effects": due_events,
        "expenses": float(total_exp),
        "macro_extra": float(macro_extra),
        "immediate_delta": dict(option.immediate_effects),
        "scheduled_delays": [asdict(ds) for ds in list(option.delayed_effects or [])],
    }
    return new_state, log
