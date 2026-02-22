"""Startup Survivor RPG (Streamlit)

ÇATI 4 — UI/Experience

Principles:
- UI only renders + triggers.
- Core domain and engine are pure Python modules.
- Content is LLM-only (Gemini). If LLM fails we show a clear error (no silent offline fallback).

Entry point for Streamlit Cloud: app.py
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from core.modes import DEFAULT_MODES, get_mode_spec
from core.rng import stable_int_seed

# Core imports are bootstrapped at runtime to avoid Streamlit hard-crash
# in case the repo was partially updated.
DelayedEffect = GameState = Stats = None  # type: ignore
stats_to_dict = default_start_state = None  # type: ignore


from content.prompts import build_prompt, build_choice_intent_prompt
try:
    from content.providers.gemini import GeminiProvider, RateLimitError
except Exception:
    # Repo partially updated olabilir: eski gemini.py RateLimitError tanımlamıyor olabilir.
    from content.providers.gemini import GeminiProvider  # type: ignore

    class RateLimitError(RuntimeError):
        def __init__(self, message: str, retry_after_s: int = 0) -> None:
            super().__init__(message)
            self.retry_after_s = int(retry_after_s or 0)

from content.providers.base import ProviderStatus

from engine.config import EngineConfig
from engine.pipeline import apply_choice, apply_option_spec, draft_to_bundle, intent_to_option_spec


APP_TITLE = "Startup Survivor RPG"
APP_SUBTITLE = "Ay bazlı startup simülasyonu: Durum Analizi → Kriz → A/B kararı. (LLM içerik + deterministik ekonomi)"
APP_VERSION = "3.2.1"
BUILD_ID = "v11.8.1-import-hotfix-20260222"

st.set_page_config(page_title=APP_TITLE, page_icon="🧠", layout="wide", initial_sidebar_state="expanded")

CSS = """
<style>
.block-container {padding-top: 3.2rem; padding-bottom: 2rem;}
section[data-testid="stSidebar"] .block-container {padding-top: 2.0rem;}
.card {
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  padding: 14px 16px;
  background: rgba(255,255,255,0.03);
}
.choice {
  border: 1px solid rgba(255,255,255,0.10);
  border-radius: 18px;
  padding: 18px 18px 14px 18px;
  background: rgba(255,255,255,0.02);
}
.pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.12);
  font-size: 12px;
  opacity: .85;
}
.pill.warn {border-color: rgba(255,190,90,0.35);}
.pill.ok {border-color: rgba(120,255,160,0.25);}
.pill.bad {border-color: rgba(255,120,120,0.25);}
hr.soft {border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 1rem 0;}
.muted {opacity:.75;}
.small {font-size: 13px; opacity:.75;}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


def bootstrap_core_or_stop() -> None:
    """Import core API lazily and stop with a helpful message if repo is inconsistent."""
    global DelayedEffect, GameState, Stats, stats_to_dict, default_start_state

    try:
        import core  # noqa: F401
        from core.state import DelayedEffect as _DelayedEffect, GameState as _GameState, Stats as _Stats
        from core.state import stats_to_dict as _stats_to_dict, default_start_state as _default_start_state
    except Exception as e:
        st.error(
            "Core modülleri yüklenemedi (repo kısmi güncellenmiş olabilir).\n\n"
            "Çözüm: Zip içindeki TÜM dosyaları repo köküne overwrite edip tekrar deploy et.\n\n"
            f"Hata: {type(e).__name__}: {e}"
        )
        st.stop()

    api_ver = getattr(__import__("core"), "API_VERSION", None)
    if api_ver != "core-v10-20260219":
        st.error(
            "Core sürümü ile app sürümü uyuşmuyor (repo karışmış olabilir).\n\n"
            "Çözüm: Zip içindeki TÜM dosyaları overwrite edip deploy et.\n\n"
            f"Beklenen core: core-v10-20260219, bulunan: {api_ver!r}"
        )
        st.stop()

    # Validate expected Stats fields (dataclass fields live on instances, not the class).
    fields = set()
    fields.update(getattr(_Stats, '__annotations__', {}).keys())
    fields.update(getattr(getattr(_Stats, '__dataclass_fields__', {}), 'keys', lambda: [])())

    missing = [k for k in ('morale', 'tech_debt') if k not in fields]
    if missing:
        import core.state as _cs
        st.error(
            "Core Stats alanları eksik görünüyor (morale/tech_debt).\n\n"
            "Bu genelde repo kısmi güncellendiğinde veya yanlış 'core' paketi import edildiğinde olur.\n\n"
            f"Yüklenen core.state yolu: {_cs.__file__}\n"
            f"Bulunan alanlar: {sorted(fields)}\n"
            f"Eksik: {missing}\n\n"
            "Çözüm: Zip içindeki TÜM dosyaları repo köküne overwrite edip tekrar deploy et (ve Cloud'da Reboot/Clear cache)."
        )
        st.stop()

    DelayedEffect, GameState, Stats = _DelayedEffect, _GameState, _Stats
    stats_to_dict, default_start_state = _stats_to_dict, _default_start_state


bootstrap_core_or_stop()



# =========================
# Data (Çatı 5-lite)
# =========================

CHARACTERS: Dict[str, Dict[str, Any]] = {
    "anon": {
        "name": "İsimsiz Girişimci",
        "trait": "Dengeli. Doğru kararları bulursan istikrarlı büyür.",
        "start_overrides": {},
    },
    "hacker": {
        "name": "Hacker Founder",
        "trait": "Ürünü hızlı iter; ama pazarlama/satış tarafında kör noktaları var.",
        "start_overrides": {"infra_load": 10.0, "support_load": 25.0, "reputation": 45.0},
    },
    "sales": {
        "name": "Sales Founder",
        "trait": "Pipeline kurar, MRR odaklıdır; teknik borcu büyütmeye yatkın.",
        "start_overrides": {"mrr": 1500.0, "infra_load": 35.0, "reputation": 55.0},
    },
    "ops": {
        "name": "Ops Founder",
        "trait": "Sistem kurar; büyüme hızını feda edebilir.",
        "start_overrides": {"support_load": 15.0, "infra_load": 15.0, "mrr": 700.0},
    },
}

CASES: Dict[str, Dict[str, Any]] = {
    "free": {
        "title": "Greenfield",
        "blurb": "Sıfırdan bir ürün fikriyle başlıyorsun. Pazar belirsiz; her karar, ritim ve odak savaşını belirleyecek.",
        "scenario_seed": 872341,
        "case_key": "default",
    },
    "true_story_privacy": {
        "title": "True Story — Gizlilik Krizi",
        "blurb": "Büyüme iyi gidiyor ama gizlilik/güvenlikte bir açık söylentisi var. Ders odaklı, gerçekçi bir kriz hattı.",
        "scenario_seed": 903155,
        "case_key": "facebook_privacy_2019",
    },
    "pricing_wall": {
        "title": "Fiyat Duvarı",
        "blurb": "Kullanıcı var ama ödeme yok. Ücretlendirme denemeleri churn'u patlatabilir; doğru segment/teklif bulmalısın.",
        "scenario_seed": 441928,
        "case_key": "default",
    },
    "support_avalanche": {
        "title": "Destek Çığlığı",
        "blurb": "Ürün erken tuttu. Şimdi destek talepleri çığ gibi. Süreç mi, self-serve mi, yoksa feature mı?",
        "scenario_seed": 128044,
        "case_key": "default",
    },
    "funding_winter": {
        "title": "Yatırım Kışı",
        "blurb": "Piyasada para pahalı. Runway'i uzatmak için kesinti, gelir veya yatırım arasında zor kararlar var.",
        "scenario_seed": 770212,
        "case_key": "default",
    },
    "viral_but_broken": {
        "title": "Viral Ama Çöken",
        "blurb": "Bir içerik patladı ve trafik 10x oldu. Sunucu yanıyor; sosyal medyada itibar bir gecede yükselip düşebilir.",
        "scenario_seed": 555901,
        "case_key": "default",
    },
    "enterprise_trap": {
        "title": "Enterprise Tuzak mı?",
        "blurb": "Büyük bir müşteri 'evet' demeye yakın ama ağır entegrasyon ve özel talepler istiyor. Odak bozulursa ürün çürür.",
        "scenario_seed": 620077,
        "case_key": "default",
    },
}


DEFAULT_EXPENSES = {
    "payroll": 90_000.0,
    "tools": 10_000.0,
    "infra": 15_000.0,
    "misc": 7_500.0,
}


# =========================
# Helpers
# =========================


def _now_id() -> str:
    return datetime.utcnow().strftime("%Y%m%d%H%M%S%f")


def _mask_key(k: str) -> str:
    k = (k or '').strip()
    if not k:
        return ''
    if len(k) <= 8:
        return '*' * len(k)
    return f"{k[:4]}…{k[-4:]} (len={len(k)})"


def _coerce_key_list(v: Any) -> List[str]:
    """Accept TOML list, multiline string, or comma-separated string."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        out: List[str] = []
        for x in v:
            if x is None:
                continue
            out.extend(_coerce_key_list(x))
        return [k for k in out if k]

    s = str(v).strip()
    if not s:
        return []
    # Multiline
    if "\n" in s:
        return [ln.strip() for ln in s.splitlines() if ln.strip()]
    # CSV
    if "," in s:
        return [x.strip() for x in s.split(",") if x.strip()]
    return [s]


def _get_api_keys() -> tuple[List[str], str]:
    """Return (api_keys, source_label).

    Streamlit Community Cloud keeps secrets in st.secrets (NOT env vars).
    We accept either list or single key for convenience.

    Preferred:
      - GEMINI_API_KEYS = ["k1", "k2", ...]
    Also supported:
      - GEMINI_API_KEY = "k1"  (or "k1,k2,k3")
      - GOOGLE_API_KEYS / GOOGLE_API_KEY
    """
    if hasattr(st, "secrets"):
        for k in ("GEMINI_API_KEYS", "GOOGLE_API_KEYS"):
            if k in st.secrets:
                keys = _coerce_key_list(st.secrets[k])  # type: ignore[index]
                return keys, f"st.secrets:{k}"
        for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            if k in st.secrets:
                keys = _coerce_key_list(st.secrets[k])  # type: ignore[index]
                return keys, f"st.secrets:{k}"

    env_val = (
        os.getenv("GEMINI_API_KEYS")
        or os.getenv("GOOGLE_API_KEYS")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    )
    if env_val:
        return _coerce_key_list(env_val), "env"
    return [], "missing"


def _provider() -> GeminiProvider:
    """Session-cached provider.

    Important: If we created a new provider instance on every call, key rotation
    would never persist and a key pool would be useless. We therefore keep a
    provider per Streamlit session and distribute load round-robin.
    """
    keys, _src = _get_api_keys()
    sig = "|".join(keys)

    # Make a session nonce so different users don't all start from key #0.
    if "_session_nonce" not in st.session_state:
        st.session_state["_session_nonce"] = os.urandom(8).hex()

    cached_sig = st.session_state.get("_gemini_keys_sig")
    if st.session_state.get("_gemini_provider") is None or cached_sig != sig:
        # Pick a deterministic offset per user session to spread traffic.
        if keys:
            off = stable_int_seed(f"keypool:{st.session_state['_session_nonce']}") % max(1, len(keys))
            keys = keys[off:] + keys[:off]
        st.session_state["_gemini_provider"] = GeminiProvider(keys)
        st.session_state["_gemini_keys_sig"] = sig

    return st.session_state["_gemini_provider"]
def _provider_status() -> ProviderStatus:
    try:
        return _provider().status()
    except Exception as e:
        return ProviderStatus(False, "none", "", note="", error=str(e))


def _stat_badge(val: float, lo: float, hi: float) -> str:
    if val <= lo:
        return "bad"
    if val >= hi:
        return "ok"
    return "warn"


def _runway_months(cash: float, burn: float) -> float:
    if burn <= 1:
        return 99.0
    return max(0.0, cash / burn)


def _tension_index(stats: Dict[str, float], burn: float) -> float:
    """0..1 (higher = more tension). Pure UI metric."""
    cash = float(stats.get("cash", 0.0))
    churn = float(stats.get("churn", 0.05))
    support = float(stats.get("support_load", 20.0))
    infra = float(stats.get("infra_load", 20.0))
    tech = float(stats.get("tech_debt", 25.0))
    morale = float(stats.get("morale", 55.0))

    runway = _runway_months(cash, burn)
    a = 1.0 - min(1.0, runway / 10.0)  # <10 months runway = tension
    b = min(1.0, max(0.0, (churn - 0.04) / 0.10))
    c = min(1.0, max(0.0, (support - 35.0) / 60.0))
    d = min(1.0, max(0.0, (infra - 35.0) / 60.0))
    e = min(1.0, max(0.0, (tech - 30.0) / 70.0))
    f = 1.0 - min(1.0, max(0.0, morale / 100.0))  # low morale => higher tension
    return max(0.0, min(1.0, 0.36 * a + 0.20 * b + 0.14 * c + 0.14 * d + 0.10 * e + 0.06 * f))


def _delta_summary(delta: Dict[str, float]) -> str:
    """Human summary, no fancy numbers."""
    parts: List[str] = []
    def add(k: str, up: str, down: str) -> None:
        v = float(delta.get(k, 0.0))
        if abs(v) < 1e-9:
            return
        parts.append(up if v > 0 else down)

    add("mrr", "MRR ↑", "MRR ↓")
    add("cash", "Nakit ↑", "Nakit ↓")
    add("reputation", "İtibar ↑", "İtibar ↓")
    add("churn", "Churn ↑", "Churn ↓")
    add("support_load", "Destek yükü ↑", "Destek yükü ↓")
    add("infra_load", "Altyapı yükü ↑", "Altyapı yükü ↓")
    add("morale", "Moral ↑", "Moral ↓")
    add("tech_debt", "Tech Debt ↑", "Tech Debt ↓")
    return " · ".join(parts) if parts else "Denge" 


# =========================
# Session State
# =========================


def _ensure_state() -> None:
    ss = st.session_state
    if "run_id" not in ss:
        ss.run_id = _now_id()
    if "started" not in ss:
        ss.started = False
    if "season_len" not in ss:
        ss.season_len = 12
    if "base_seed" not in ss:
        ss.base_seed = 42
    if "idea" not in ss:
        ss.idea = ""
    if "player_name" not in ss:
        ss.player_name = ""
    if "mode_key" not in ss:
        ss.mode_key = "Gerçekçi"
    if "character_key" not in ss:
        ss.character_key = "anon"
    if "case_key" not in ss:
        ss.case_key = "free"

    if "engine_config" not in ss:
        ss.engine_config = None
    if "game_state" not in ss:
        ss.game_state = None

    if "current_bundle" not in ss:
        ss.current_bundle = None
    if "current_draft" not in ss:
        ss.current_draft = None
    if "current_raw" not in ss:
        ss.current_raw = ""

    if "logs" not in ss:
        ss.logs = []
    if "history" not in ss:
        ss.history = []
    if "last_outcome" not in ss:
        ss.last_outcome = ""


def _reset_run() -> None:
    ss = st.session_state
    keep = {
        "player_name": ss.get("player_name", ""),
    }
    for k in list(ss.keys()):
        del ss[k]
    for k, v in keep.items():
        ss[k] = v
    _ensure_state()


def _start_run() -> None:
    ss = st.session_state

    case = CASES.get(ss.case_key, CASES["free"])
    char = CHARACTERS.get(ss.character_key, CHARACTERS["anon"])

    base = default_start_state()
    # character starting overrides
    sdict = stats_to_dict(base.stats)
    for k, v in dict(char.get("start_overrides", {}) or {}).items():
        try:
            sdict[str(k)] = float(v)
        except Exception:
            continue
    state = GameState(
        month=1,
        stats=Stats(**sdict),
        delayed_queue=[],
    )

    cfg = EngineConfig(
        base_seed=int(ss.base_seed),
        mode_key=str(ss.mode_key),
        scenario_seed=int(case["scenario_seed"]),
        case_key=str(case["case_key"]),
        season_length=int(ss.season_len),
        expenses=dict(DEFAULT_EXPENSES),
    )

    ss.engine_config = cfg
    ss.game_state = state
    ss.started = True
    ss.current_bundle = None
    ss.current_draft = None
    ss.current_raw = ""
    ss.logs = []
    ss.history = []
    ss.last_outcome = ""


# =========================
# Content generation
# =========================


def _generate_month_bundle() -> None:
    ss = st.session_state
    cfg: EngineConfig = ss.engine_config
    state: GameState = ss.game_state

    provider = _provider()
    stt = provider.status()
    ss.provider_status = asdict(stt)

    if not stt.ok:
        raise RuntimeError(f"Gemini hazır değil: {stt.error or 'API key?'}")

    mode = get_mode_spec(cfg.mode_key)
    case = CASES.get(ss.case_key, CASES["free"])
    char = CHARACTERS.get(ss.character_key, CHARACTERS["anon"])

    prompt = build_prompt(
        month=int(state.month),
        mode_title=mode.key,
        mode_desc=mode.desc,
        mode_tone=mode.tone,
        idea=str(ss.idea),
        history=list(ss.history),
        case_title=str(case["title"]),
        case_blurb=str(case["blurb"]),
        stats=stats_to_dict(state.stats),
        character_name=str(char["name"]),
        character_trait=str(char["trait"]),
    )

    # We cannot fully guarantee determinism with an LLM.
    # But we store the returned draft/bundle so the run is stable after generation.

    draft, raw = provider.generate_month_draft(
        month_id=int(state.month),
        prompt=prompt,
        temperature=float(mode.temp),
        max_output_tokens=2600,
        repair_on_fail=True,
    )

    bundle = draft_to_bundle(draft, cfg)

    ss.current_draft = draft
    ss.current_raw = raw
    ss.current_bundle = bundle


# =========================
# UI Pages
# =========================


def page_setup() -> None:
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    c = st.container()
    with c:
        st.markdown("""
        ### Nasıl oynanır?
        - Her ay önce **Durum Analizi**, sonra tek bir **Kriz** görürsün.
        - İki yaklaşım (A/B) seçersin. Etkiler anında gelir, bazıları **1-2 ay sonra** döner.
        - Hedef: runway'ı uzat, MRR'ı büyüt, reputasyonu koru.

        **Not:** İçerik üretimi Gemini üzerinden. API key yoksa oyun başlayamaz.
        """)


\
\
def page_run() -> None:
    ss = st.session_state
    cfg: EngineConfig = ss.engine_config
    state: GameState = ss.game_state

    season_len = int(ss.season_len)

    # top header
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    # metrics row
    stats = stats_to_dict(state.stats)
    burn = float(sum(cfg.expenses.values()))
    runway = _runway_months(float(stats.get("cash", 0.0)), burn)
    tension = _tension_index(stats, burn)

    a, b, c, d, e = st.columns([1.2, 1.0, 1.0, 1.0, 1.4])
    a.metric("Ay", f"{state.month}/{season_len}")
    b.metric("Nakit", f"{stats.get('cash', 0.0):,.0f} ₺")
    c.metric("MRR", f"{stats.get('mrr', 0.0):,.0f} ₺")
    d.metric("Runway", f"{runway:.1f} ay")
    e.progress(tension, text=f"Tansiyon: {int(tension*100)}")

    with st.expander("📊 Detay statlar"):
        r1, r2, r3, r4, r5, r6 = st.columns(6)
        r1.metric("İtibar", f"{stats.get('reputation', 0.0):.0f}/100")
        r2.metric("Churn", f"{stats.get('churn', 0.0)*100:.1f}%")
        r3.metric("Destek", f"{stats.get('support_load', 0.0):.0f}/100")
        r4.metric("Altyapı", f"{stats.get('infra_load', 0.0):.0f}/100")
        r5.metric("Moral", f"{stats.get('morale', 0.0):.0f}/100")
        r6.metric("Tech Debt", f"{stats.get('tech_debt', 0.0):.0f}/100")

    st.markdown("<hr class='soft'/>", unsafe_allow_html=True)

    # last outcome
    if ss.last_outcome:
        st.markdown("### Sonuç")
        st.markdown(ss.last_outcome)
        ss.last_outcome = ""
        st.markdown("<hr class='soft'/>", unsafe_allow_html=True)

    # end condition
    if float(stats.get("cash", 0.0)) <= 0:
        st.error("💀 Nakit bitti. Oyun bitti.")
        return
    if int(state.month) > season_len:
        st.success("🏁 Sezon bitti. Tebrikler, hayatta kaldın!")
        return

    # generate month
    if ss.current_bundle is None:
        with st.spinner("Bu ayın paketi hazırlanıyor (Gemini)…"):
            _generate_month_bundle()

    bundle = ss.current_bundle

    st.markdown(f"## {bundle.title}")

    # Situation analysis
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(f"#### 🧩 Durum Analizi (Ay {bundle.month_id})")
    st.markdown(bundle.context)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)

    # Crisis
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(f"#### ⚠️ Kriz — {bundle.crisis_title}")
    st.markdown(bundle.crisis)
    if bundle.risk_notes:
        st.markdown(f"<div class='small'>Not: {bundle.risk_notes}</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # educational extras (optional)
    if getattr(bundle, "alternatives", None):
        with st.expander("🧭 Alternatif yaklaşımlar (öğretici)"):
            for x in list(bundle.alternatives or [])[:6]:
                st.markdown(f"- {x}")

    st.markdown("<hr class='soft'/>", unsafe_allow_html=True)

    # --- Callbacks ---
    def _on_choose(choice_id: str) -> None:
        ss = st.session_state
        cfg: EngineConfig = ss.engine_config
        state: GameState = ss.game_state
        bundle = ss.current_bundle

        new_state, log = apply_choice(state=state, bundle=bundle, choice_id=choice_id, config=cfg)

        # outcome narrative
        opt = next(o for o in bundle.options if str(o.id) == str(choice_id))
        outcome = ""
        if opt.narrative_result:
            outcome += opt.narrative_result.strip() + "\n\n"

        # due effects shown as flavour
        due = log.get("due_effects") or []
        if due:
            outcome += "**Gecikmeli etkiler bu ay vurdu:**\n"
            for ev in due:
                outcome += f"- {ev.get('hint','Gecikmeli etki')} (Ay {ev.get('from_month')})\n"
            outcome += "\n"

        if getattr(bundle, "lesson", ""):
            outcome += f"---\n**Bu ayın dersi:** {bundle.lesson.strip()}\n\n"

        # cliffhanger
        if bundle.cliffhanger:
            outcome += f"---\n*{bundle.cliffhanger.strip()}*"

        # store history + logs
        ss.logs.append({
            "month": int(log.get("month", state.month)),
            "choice": str(choice_id),
            "choice_label": str(log.get("choice_label", "")),
            "bundle": bundle.to_dict(),
            "log": {**log, "player_plan": str(ss.get("player_plan","")).strip()},
        })
        chosen_tag = str(getattr(opt, "tag", "") or opt.label)
        ss.history.append({"month": int(log.get("month", state.month)), "tag": str(chosen_tag), "choice": str(choice_id)})

        ss.game_state = new_state
        ss.current_bundle = None
        ss.current_draft = None
        ss.current_raw = ""
        ss.player_plan = ""
        ss.last_outcome = outcome

        st.rerun()

    def _on_apply_player_plan() -> None:
        ss = st.session_state
        cfg: EngineConfig = ss.engine_config
        state: GameState = ss.game_state
        bundle = ss.current_bundle

        txt = str(ss.get("player_plan", "") or "").strip()
        if len(txt) < 25:
            raise ValueError("Plan çok kısa. En az 1-2 paragraf yaz (>=25 karakter).")

        provider = _provider()
        stt = provider.status()
        ss.provider_status = asdict(stt)
        if not stt.ok:
            raise RuntimeError(f"Gemini hazır değil: {stt.error or 'API key?'}")

        mode = get_mode_spec(cfg.mode_key)

        prompt2 = build_choice_intent_prompt(
            month=int(state.month),
            mode_title=mode.key,
            mode_tone=mode.tone,
            idea=str(ss.idea),
            crisis_title=str(bundle.crisis_title),
            crisis=str(bundle.crisis),
            player_text=txt,
        )

        with st.spinner("Planın değerlendiriliyor (Gemini)…"):
            intent, raw_intent = provider.generate_choice_intent(
                prompt=prompt2,
                temperature=max(0.2, float(mode.temp) * 0.6),
            )

        opt_spec = intent_to_option_spec(intent=intent, month_id=int(bundle.month_id), config=cfg, choice_id="YOU")

        new_state, log = apply_option_spec(state=state, option=opt_spec, month_id=int(bundle.month_id), config=cfg)

        outcome = ""
        if opt_spec.narrative_result:
            outcome += opt_spec.narrative_result.strip() + "\n\n"

        due = log.get("due_effects") or []
        if due:
            outcome += "**Gecikmeli etkiler bu ay vurdu:**\n"
            for ev in due:
                outcome += f"- {ev.get('hint','Gecikmeli etki')} (Ay {ev.get('from_month')})\n"
            outcome += "\n"

        if getattr(bundle, "lesson", ""):
            outcome += f"---\n**Bu ayın dersi:** {bundle.lesson.strip()}\n\n"

        if bundle.cliffhanger:
            outcome += f"---\n*{bundle.cliffhanger.strip()}*"

        ss.logs.append({
            "month": int(log.get("month", state.month)),
            "choice": "YOU",
            "choice_label": opt_spec.label,
            "bundle": bundle.to_dict(),
            "log": {**log, "player_text": txt, "intent": intent.to_dict(), "intent_raw": raw_intent},
        })
        ss.history.append({"month": int(log.get("month", state.month)), "tag": str(opt_spec.tag), "choice": "YOU"})

        ss.game_state = new_state
        ss.current_bundle = None
        ss.current_draft = None
        ss.current_raw = ""
        ss.player_plan = ""
        ss.last_outcome = outcome

        st.rerun()

    # --- Choices UI ---
    st.markdown(f"### Ay {bundle.month_id}: Kararını ver")
    cols = st.columns(len(bundle.options)) if 2 <= len(bundle.options) <= 3 else st.columns(2)

    def render_option(col, opt) -> None:
        with col:
            st.markdown("<div class='choice'>", unsafe_allow_html=True)
            st.markdown(f"#### {opt.id}. {opt.label}")

            pill_cls = "ok" if str(opt.risk) == "low" else ("warn" if str(opt.risk) == "med" else "bad")
            st.markdown(
                f"<span class='pill {pill_cls}'>Risk</span> "
                f"<span class='pill'>{_delta_summary(opt.immediate_effects)}</span> "
                f"<span class='pill'>Odak: {opt.tag}</span>",
                unsafe_allow_html=True,
            )

            st.markdown("\n" + str(opt.description))

            if st.button(f"{opt.id} seç", key=f"choose_{bundle.month_id}_{opt.id}", use_container_width=True):
                _on_choose(str(opt.id))

            st.markdown("</div>", unsafe_allow_html=True)

    for i, opt in enumerate(list(bundle.options)[:3]):
        render_option(cols[i], opt)

    st.markdown("<hr class='soft'/>", unsafe_allow_html=True)

    # --- Player plan ---
    st.markdown("### ✍️ Kendi çözümün (oyuna dahil et)")
    ss.player_plan = st.text_area(
        "Bu kriz için sen ne yaparsın? (1-2 paragraf yaz; istersen maddeler halinde)",
        value=str(ss.get("player_plan", "")),
        height=130,
    )
    c1, c2 = st.columns([1.0, 1.0])
    with c1:
        if st.button("Bu planı uygula", key=f"apply_player_{bundle.month_id}", use_container_width=True):
            _on_apply_player_plan()
    with c2:
        if st.button("Sadece not et (oyun ilerlemesin)", key=f"note_player_{bundle.month_id}", use_container_width=True):
            ss.logs.append({
                "month": int(state.month),
                "choice": "NOTE",
                "choice_label": "Oyuncu notu",
                "bundle": bundle.to_dict(),
                "log": {"note_only": True},
                "note": str(ss.get("player_plan","")).strip(),
            })
            ss.player_plan = ""
            st.success("Not kaydedildi (oyun ilerlemedi).")
            st.rerun()


def page_history() -> None:
    ss = st.session_state
    st.title("Geçmiş")
    st.caption("Bu run içinde üretilen ay kayıtları.")

    if not ss.logs:
        st.info("Henüz kayıt yok.")
        return

    for item in reversed(ss.logs):
        m = item.get("month")
        choice = item.get("choice")
        label = item.get("choice_label")
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.markdown(f"#### Ay {m} — {choice}: {label}")
        note = (item.get("note") or (item.get("log") or {}).get("player_plan") or "").strip()
        if note:
            st.markdown(f"**Notun:** {note}")
        st.markdown("<details><summary>Bundle (JSON)</summary>")
        st.json(item.get("bundle"))
        st.markdown("</details>")
        st.markdown("</div>", unsafe_allow_html=True)
        st.write("")


def page_debug() -> None:
    ss = st.session_state
    st.title("Debug")

    st.subheader("Provider")
    st.json(ss.get("provider_status") or asdict(_provider_status()))

    st.subheader("EngineConfig")
    st.json(asdict(ss.engine_config) if ss.engine_config else {})

    st.subheader("GameState")
    st.json(asdict(ss.game_state) if ss.game_state else {})

    st.subheader("Last raw model output")
    st.code(ss.get("current_raw", "") or "", language="json")

    st.subheader("Last bundle")
    if ss.get("current_bundle"):
        st.json(ss.current_bundle.to_dict())


def export_import_controls() -> None:
    ss = st.session_state
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Run Export / Import")

    export_payload = {
        "meta": {
            "app": APP_TITLE,
            "version": APP_VERSION,
            "build": BUILD_ID,
            "exported_at": datetime.utcnow().isoformat() + "Z",
        },
        "setup": {
            "player_name": ss.get("player_name"),
            "idea": ss.get("idea"),
            "mode_key": ss.get("mode_key"),
            "character_key": ss.get("character_key"),
            "case_key": ss.get("case_key"),
            "season_len": ss.get("season_len"),
            "base_seed": ss.get("base_seed"),
        },
        "engine_config": asdict(ss.engine_config) if ss.get("engine_config") else None,
        "game_state": asdict(ss.game_state) if ss.get("game_state") else None,
        "logs": ss.get("logs", []),
        "history": ss.get("history", []),
    }

    st.sidebar.download_button(
        "Run dosyasını indir",
        data=json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=f"startup_survivor_run_{ss.get('run_id','run')}.json",
        mime="application/json",
        disabled=not bool(ss.get("started")),
    )

    up = st.sidebar.file_uploader("Run dosyası yükle", type=["json"], accept_multiple_files=False)
    if up is not None:
        try:
            data = json.loads(up.read().decode("utf-8"))
            setup = data.get("setup") or {}
            ss.player_name = setup.get("player_name", ss.get("player_name", ""))
            ss.idea = setup.get("idea", "")
            ss.mode_key = setup.get("mode_key", "Gerçekçi")
            ss.character_key = setup.get("character_key", "anon")
            ss.case_key = setup.get("case_key", "free")
            ss.season_len = int(setup.get("season_len", 12))
            ss.base_seed = int(setup.get("base_seed", 42))

            cfg = data.get("engine_config")
            if cfg:
                ss.engine_config = EngineConfig(**cfg)
            gs = data.get("game_state")
            if gs:
                sdict = gs.get("stats") or {}
                q = []
                for ev in (gs.get("delayed_queue") or []):
                    try:
                        q.append(
                            DelayedEffect(
                                due_month=int(ev.get("due_month")),
                                delta=dict(ev.get("delta") or {}),
                                hint=str(ev.get("hint") or ""),
                                from_month=int(ev.get("from_month")),
                            )
                        )
                    except Exception:
                        continue
                ss.game_state = GameState(
                    month=int(gs.get("month", 1)),
                    stats=Stats(**{k: float(v) for k, v in dict(sdict).items()}),
                    delayed_queue=q,
                )

            ss.logs = data.get("logs", []) or []
            ss.history = data.get("history", []) or []
            ss.started = True
            ss.current_bundle = None
            ss.current_draft = None
            ss.current_raw = ""
            st.sidebar.success("Run yüklendi.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Import başarısız: {e}")


# =========================
# Sidebar
# =========================


def sidebar() -> str:
    ss = st.session_state

    st.sidebar.markdown(f"**{APP_TITLE}**  ")
    st.sidebar.markdown(f"v{APP_VERSION} · {BUILD_ID}")

    # API key diagnostics (masked) + pool info
    _keys, _src = _get_api_keys()
    if _keys:
        current = _keys[0]
        st.sidebar.caption(f"🔑 Key pool: {len(_keys)} · current: {_mask_key(current)} · source={_src}")
        if not str(current).strip().startswith("AIza"):
            st.sidebar.warning("Key formatı alışılmadık görünüyor (genelde 'AIza…'). Yanlış anahtar (OpenAI/Claude vb.) koymuş olabilirsin.")
        st.sidebar.caption("Pool modu: round-robin + hata olursa diğer key.")
    else:
        st.sidebar.warning("🔑 API key bulunamadı. Secrets'e GEMINI_API_KEYS (liste) veya GEMINI_API_KEY ekle.")

    st.sidebar.markdown("---")

    ss.player_name = st.sidebar.text_input("İsim", value=str(ss.get("player_name", "")))
    ss.idea = st.sidebar.text_area("Ürün fikri (1-3 cümle)", value=str(ss.get("idea", "")), height=90)

    mode_names = list(DEFAULT_MODES.keys())
    mode_ix = mode_names.index(ss.mode_key) if ss.mode_key in mode_names else 0
    ss.mode_key = st.sidebar.selectbox("Mod", mode_names, index=mode_ix, disabled=ss.started)
    st.sidebar.caption(get_mode_spec(ss.mode_key).desc)

    case_keys = list(CASES.keys())
    case_labels = [CASES[k]["title"] for k in case_keys]
    case_ix = case_keys.index(ss.case_key) if ss.case_key in case_keys else 0
    ss.case_key = st.sidebar.selectbox("Vaka sezonu", case_keys, index=case_ix, format_func=lambda k: CASES[k]["title"], disabled=ss.started)
    st.sidebar.caption(CASES[ss.case_key]["blurb"])

    char_keys = list(CHARACTERS.keys())
    char_ix = char_keys.index(ss.character_key) if ss.character_key in char_keys else 0
    ss.character_key = st.sidebar.selectbox("Karakter", char_keys, index=char_ix, format_func=lambda k: CHARACTERS[k]["name"], disabled=ss.started)
    st.sidebar.caption(CHARACTERS[ss.character_key]["trait"])

    ss.season_len = st.sidebar.slider("Sezon uzunluğu (ay)", min_value=6, max_value=24, value=int(ss.season_len), step=1, disabled=ss.started)
    ss.base_seed = st.sidebar.number_input("Seed (deterministik ekonomi)", value=int(ss.base_seed), step=1, disabled=ss.started)

    st.sidebar.markdown("---")

    ps = _provider_status()
    if ps.ok:
        st.sidebar.success(f"Gemini hazır ({ps.backend} / {ps.model})")
    else:
        st.sidebar.error("Gemini hazır değil")
        st.sidebar.caption(ps.error or "API key eksik")

    cols = st.sidebar.columns(2)
    with cols[0]:
        if st.button("Sezonu başlat", disabled=ss.started or not ps.ok, use_container_width=True):
            _start_run()
            st.rerun()
    with cols[1]:
        if st.button("Reset", use_container_width=True):
            _reset_run()
            st.rerun()

    export_import_controls()

    st.sidebar.markdown("---")
    page = st.sidebar.radio("Sayfa", ["Oyna", "Geçmiş", "Debug"], index=0)
    return page


# =========================
# Main
# =========================


def main() -> None:
    _ensure_state()
    page = sidebar()

    ss = st.session_state

    if not ss.started:
        page_setup()
        return

    # Safety: config/state must exist
    if ss.engine_config is None or ss.game_state is None:
        st.error("Run config/state eksik. Reset at.")
        return

    if page == "Oyna":
        try:
            page_run()
        except Exception as e:
            # Friendlier handling for rate limits / quota exhaustion
            if isinstance(e, RateLimitError):
                delay = int(getattr(e, "retry_after_s", 0) or 0)
                msg = str(e)
                if delay > 0:
                    st.error(f"Sistem şu an cevap veremiyor: {msg}\n\n⏳ Öneri: {delay} saniye bekleyip tekrar dene.")
                else:
                    st.error(f"Sistem şu an cevap veremiyor: {msg}")
                st.info(
                    "Not: Gemini rate limit'leri **proje bazlıdır**, API key bazlı değil. Aynı projeden üretilmiş çok key, kota artışı sağlamaz. "
                    "Key havuzunun işe yaraması için key'lerin farklı projelere (tercihen farklı billing/tier) bağlı olması gerekir."
                )
            else:
                st.error(f"Sistem şu an cevap veremiyor: {e}")
                if 'API_KEY_INVALID' in str(e) or 'API key not valid' in str(e):
                    st.info(
                        "API key geçersiz görünüyor. Kontrol listesi: (1) Streamlit Secrets'te doğru anahtar mı? "
                        "(2) Anahtarda kopyalama sırasında boşluk/newline var mı? "
                        "(3) Google Cloud API Key restriction (HTTP referrer / IP) açıksa kaldır. "
                        "(4) Doğru servis: Google AI Studio / Generative Language API anahtarı."
                    )
                st.info("Gemini timeout / API hatası olabilir. Debug sayfasından raw output'a bakabilirsin.")
            # keep bundle None so user can retry by rerun
            ss.current_bundle = None
    elif page == "Geçmiş":
        page_history()
    else:
        page_debug()


if __name__ == "__main__":
    main()