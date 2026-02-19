"""content.schemas

Contracts for:
- MonthDraft: narrative-only (LLM output): analysis/crisis + option intents.
- MonthBundle: validated, engine-ready contract that includes explicit deltas.

Design choice:
We keep economy (delta sampling/balancing) OUT of the LLM.
The engine converts MonthDraft -> MonthBundle deterministically.

Schema strategy:
- v2 is the preferred schema (month_title, kriz_title, options list, results).
- v1 (legacy A/B keys) is still accepted and is upgraded to v2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

Delta = Dict[str, float]

ALLOWED_TAGS = {
    "growth",
    "efficiency",
    "reliability",
    "compliance",
    "fundraising",
    "people",
    "product",
    "sales",
    "marketing",
    "security",
}

ALLOWED_RISKS = {"low", "med", "high"}
ALLOWED_OPTION_IDS = {"A", "B", "C"}


def _as_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def normalize_delta(d: Mapping[str, Any]) -> Delta:
    out: Dict[str, float] = {}
    for k, v in dict(d).items():
        if v is None:
            continue
        out[str(k)] = _as_float(v, 0.0)
    return out


def normalize_tag(tag: Any, default: str = "growth") -> str:
    t = str(tag or "").strip().lower()
    if t in ALLOWED_TAGS:
        return t
    # common TR variants
    aliases = {
        "büyüme": "growth",
        "verimlilik": "efficiency",
        "güvenilirlik": "reliability",
        "uyum": "compliance",
        "yatırım": "fundraising",
        "insan": "people",
        "ürün": "product",
        "satış": "sales",
        "pazarlama": "marketing",
        "güvenlik": "security",
    }
    return aliases.get(t, default)


def normalize_risk(risk: Any, default: str = "med") -> str:
    r = str(risk or "").strip().lower()
    if r in ALLOWED_RISKS:
        return r
    aliases = {
        "low": "low",
        "med": "med",
        "high": "high",
        "düşük": "low",
        "orta": "med",
        "yüksek": "high",
    }
    return aliases.get(r, default)


def normalize_steps(steps: Any) -> List[str]:
    if steps is None:
        return []
    if isinstance(steps, str):
        parts = [x.strip(" -•\t") for x in steps.splitlines()]
        return [p for p in parts if p]
    if isinstance(steps, list):
        out: List[str] = []
        for x in steps:
            s = str(x or "").strip()
            if s:
                out.append(s)
        return out
    return [str(steps).strip()] if str(steps).strip() else []


# =========================
# Draft (LLM output)
# =========================


@dataclass(frozen=True)
class OptionDraft:
    """LLM option intent (narrative-only)."""

    id: str  # A|B|C
    title: str
    tag: str
    steps: List[str]
    risk: str
    delayed_seed: str
    result: str = ""  # what happens if chosen (2-4 short paragraphs)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "tag": self.tag,
            "steps": list(self.steps),
            "risk": self.risk,
            "delayed_seed": self.delayed_seed,
            "result": self.result,
        }


@dataclass(frozen=True)
class MonthDraft:
    """Narrative-only month package returned by the LLM."""

    month_id: int
    month_title: str
    durum_analizi: str
    kriz_title: str
    kriz: str
    options: List[OptionDraft]

    # optional, for engagement / teaching
    note: str = ""
    cliffhanger: str = ""
    lesson: str = ""
    alternatives: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "month_id": int(self.month_id),
            "month_title": self.month_title,
            "durum_analizi": self.durum_analizi,
            "kriz_title": self.kriz_title,
            "kriz": self.kriz,
            "options": [o.to_dict() for o in self.options],
            "note": self.note,
            "cliffhanger": self.cliffhanger,
            "lesson": self.lesson,
            "alternatives": list(self.alternatives),
        }


def validate_month_draft(d: MonthDraft) -> None:
    if not isinstance(d.month_id, int) or d.month_id < 1:
        raise ValueError("draft.month_id must be int >= 1")
    if len((d.month_title or "").strip()) < 6:
        raise ValueError("draft.month_title too short")
    if len((d.durum_analizi or "").strip()) < 220:
        raise ValueError("draft.durum_analizi too short (>=220 chars)")
    if len((d.kriz_title or "").strip()) < 6:
        raise ValueError("draft.kriz_title too short")
    if len((d.kriz or "").strip()) < 220:
        raise ValueError("draft.kriz too short (>=220 chars)")

    if not isinstance(d.options, list) or len(d.options) < 2 or len(d.options) > 3:
        raise ValueError("draft.options must be a list of 2-3 OptionDraft items")

    ids = [str(o.id).strip().upper() for o in d.options]
    if len(set(ids)) != len(ids):
        raise ValueError("draft.options ids must be unique")
    if any(i not in ALLOWED_OPTION_IDS for i in ids):
        raise ValueError("draft.options ids must be A/B/C")

    for opt in d.options:
        oid = str(opt.id).strip().upper()
        if oid not in ALLOWED_OPTION_IDS:
            raise ValueError("draft option id must be A/B/C")
        if len((opt.title or "").strip()) < 4:
            raise ValueError(f"draft option {oid}: title too short")
        if normalize_tag(opt.tag) not in ALLOWED_TAGS:
            raise ValueError(f"draft option {oid}: invalid tag")
        if normalize_risk(opt.risk) not in ALLOWED_RISKS:
            raise ValueError(f"draft option {oid}: invalid risk")
        if len(list(opt.steps or [])) < 4:
            raise ValueError(f"draft option {oid}: steps must be >=4")
        if opt.result and len(opt.result.strip()) < 80:
            raise ValueError(f"draft option {oid}: result too short (>=80 chars) or empty")


def _parse_option(obj: Mapping[str, Any], *, default_id: str) -> OptionDraft:
    oid = str(obj.get("id") or default_id).strip().upper()
    if oid not in ALLOWED_OPTION_IDS:
        oid = default_id
    return OptionDraft(
        id=oid,
        title=str(obj.get("title") or obj.get("label") or f"Seçenek {oid}").strip(),
        tag=normalize_tag(obj.get("tag") or obj.get("focus") or "growth"),
        steps=normalize_steps(obj.get("steps", [])),
        risk=normalize_risk(obj.get("risk", "med")),
        delayed_seed=str(obj.get("delayed_seed", "") or "").strip()[:60],
        result=str(obj.get("result", "") or "").strip(),
    )


def draft_from_llm_v1(data: Mapping[str, Any], month_id: int) -> MonthDraft:
    """Parse legacy v1 JSON (A/B keys) into v2 MonthDraft."""

    a = dict(data.get("A") or {})
    b = dict(data.get("B") or {})

    # Heuristic titles.
    kriz_title = "Kritik Dönemeç"
    krz = str(data.get("kriz", "") or "")
    if "KRİZ:" in krz:
        kriz_title = krz.split("\n", 1)[0].replace("KRİZ:", "").strip() or kriz_title

    month_title = f"Ay {int(month_id)}: Karar Ayı"

    options = [
        _parse_option(a, default_id="A"),
        _parse_option(b, default_id="B"),
    ]

    d = MonthDraft(
        month_id=int(month_id),
        month_title=str(data.get("month_title") or month_title).strip(),
        durum_analizi=str(data.get("durum_analizi", "") or "").strip(),
        kriz_title=str(data.get("kriz_title") or kriz_title).strip(),
        kriz=str(data.get("kriz", "") or "").strip(),
        options=options,
        note=str(data.get("note", "") or "").strip(),
        cliffhanger=str(data.get("cliffhanger", "") or "").strip(),
        lesson=str(data.get("lesson", "") or "").strip(),
        alternatives=normalize_steps(data.get("alternatives", [])),
    )
    validate_month_draft(d)
    return d


def draft_from_llm_v2(data: Mapping[str, Any], month_id: int) -> MonthDraft:
    """Parse v2 JSON (options list) into MonthDraft."""

    # options: list of dicts
    raw_opts = data.get("options")
    options: List[OptionDraft] = []
    if isinstance(raw_opts, list):
        # default ids A/B/C in order if missing
        defaults = ["A", "B", "C"]
        for i, obj in enumerate(raw_opts[:3]):
            if not isinstance(obj, dict):
                continue
            options.append(_parse_option(obj, default_id=defaults[i]))
    else:
        # some models may still emit A/B keys
        return draft_from_llm_v1(data, month_id=int(month_id))

    if len(options) < 2:
        raise ValueError("v2 draft requires at least 2 options")

    d = MonthDraft(
        month_id=int(month_id),
        month_title=str(data.get("month_title") or f"Ay {int(month_id)}").strip(),
        durum_analizi=str(data.get("durum_analizi", "") or "").strip(),
        kriz_title=str(data.get("kriz_title") or "Kriz").strip(),
        kriz=str(data.get("kriz", "") or "").strip(),
        options=options,
        note=str(data.get("note", "") or "").strip(),
        cliffhanger=str(data.get("cliffhanger", "") or "").strip(),
        lesson=str(data.get("lesson", "") or "").strip(),
        alternatives=normalize_steps(data.get("alternatives", [])),
    )
    validate_month_draft(d)
    return d


def draft_from_llm(data: Mapping[str, Any], month_id: int) -> MonthDraft:
    """Auto-detect and parse MonthDraft."""
    if "options" in data:
        return draft_from_llm_v2(data, month_id=month_id)
    return draft_from_llm_v1(data, month_id=month_id)


# =========================
# Choice intent (player text)
# =========================


@dataclass(frozen=True)
class ChoiceIntent:
    """LLM interpretation of a player's custom plan."""

    title: str
    tag: str
    steps: List[str]
    risk: str
    delayed_seed: str
    result: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "tag": self.tag,
            "steps": list(self.steps),
            "risk": self.risk,
            "delayed_seed": self.delayed_seed,
            "result": self.result,
        }


def intent_from_llm(data: Mapping[str, Any]) -> ChoiceIntent:
    return ChoiceIntent(
        title=str(data.get("title") or "Kullanıcının Planı").strip(),
        tag=normalize_tag(data.get("tag") or "product"),
        steps=normalize_steps(data.get("steps", [])),
        risk=normalize_risk(data.get("risk", "med")),
        delayed_seed=str(data.get("delayed_seed", "") or "").strip()[:60],
        result=str(data.get("result", "") or "").strip(),
    )


def validate_intent(i: ChoiceIntent) -> None:
    if len((i.title or "").strip()) < 3:
        raise ValueError("intent.title too short")
    if normalize_tag(i.tag) not in ALLOWED_TAGS:
        raise ValueError("intent.tag invalid")
    if normalize_risk(i.risk) not in ALLOWED_RISKS:
        raise ValueError("intent.risk invalid")
    if len(list(i.steps or [])) < 3:
        raise ValueError("intent.steps must be >=3")
    if i.result and len(i.result.strip()) < 60:
        raise ValueError("intent.result too short (>=60) or empty")


# =========================
# Bundle (engine-ready)
# =========================


@dataclass(frozen=True)
class DelayedEffectSpec:
    delay_months: int
    delta: Delta
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {"delay_months": int(self.delay_months), "delta": dict(self.delta), "description": str(self.description)}


@dataclass(frozen=True)
class OptionSpec:
    id: str  # A|B|C|YOU
    label: str
    tag: str
    risk: str
    steps: List[str]
    description: str
    immediate_effects: Delta
    delayed_effects: List[DelayedEffectSpec] = field(default_factory=list)
    narrative_result: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "label": str(self.label),
            "tag": str(self.tag),
            "risk": str(self.risk),
            "steps": list(self.steps),
            "description": str(self.description),
            "immediate_effects": dict(self.immediate_effects),
            "delayed_effects": [x.to_dict() for x in self.delayed_effects],
            "narrative_result": str(self.narrative_result),
        }


@dataclass(frozen=True)
class MonthBundle:
    month_id: int
    title: str
    context: str
    crisis_title: str
    crisis: str
    options: List[OptionSpec]
    tags: List[str] = field(default_factory=list)
    intensity: Optional[float] = None
    stakeholders: List[str] = field(default_factory=list)
    risk_notes: str = ""
    cliffhanger: str = ""
    lesson: str = ""
    alternatives: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "month_id": int(self.month_id),
            "title": str(self.title),
            "context": str(self.context),
            "crisis_title": str(self.crisis_title),
            "crisis": str(self.crisis),
            "options": [o.to_dict() for o in self.options],
            "tags": list(self.tags),
            "intensity": None if self.intensity is None else float(self.intensity),
            "stakeholders": list(self.stakeholders),
            "risk_notes": str(self.risk_notes),
            "cliffhanger": str(self.cliffhanger),
            "lesson": str(self.lesson),
            "alternatives": list(self.alternatives),
        }


def validate_month_bundle(b: MonthBundle) -> None:
    if not isinstance(b.month_id, int) or b.month_id < 1:
        raise ValueError("month_id must be int >= 1")
    if not b.title or len(b.title.strip()) < 4:
        raise ValueError("title too short")
    if not b.context or len(b.context.strip()) < 80:
        raise ValueError("context too short")
    if not b.crisis_title or len(b.crisis_title.strip()) < 4:
        raise ValueError("crisis_title too short")
    if not b.crisis or len(b.crisis.strip()) < 80:
        raise ValueError("crisis too short")
    if not isinstance(b.options, list) or len(b.options) < 2 or len(b.options) > 3:
        raise ValueError("options must be a list of 2-3 OptionSpec items")

    ids = [str(o.id) for o in b.options]
    if len(set(ids)) != len(ids):
        raise ValueError("option ids must be unique")

    for o in b.options:
        if str(o.id).upper() not in {"A", "B", "C"} and str(o.id) != "YOU":
            raise ValueError("invalid option id")
        if len((o.label or "").strip()) < 3:
            raise ValueError("option label too short")
        if normalize_tag(o.tag) not in ALLOWED_TAGS:
            raise ValueError("option tag invalid")
        if normalize_risk(o.risk) not in ALLOWED_RISKS:
            raise ValueError("option risk invalid")
        if len(list(o.steps or [])) < 3:
            raise ValueError("option steps too short")
        if not isinstance(o.immediate_effects, dict):
            raise ValueError("option immediate_effects must be dict")

    return None
