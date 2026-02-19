"""engine.sim_runner

Headless runner for quick sanity checks.

This keeps tests deterministic and CI-friendly by avoiding network calls.
It uses a tiny built-in fake draft provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from content.schemas import MonthDraft, OptionDraft
from core.state import GameState, Stats

from .config import EngineConfig
from .pipeline import apply_choice, draft_to_bundle


@dataclass
class FakeDraftProvider:
    """Deterministic provider for tests (no LLM)."""

    def make_draft(self, month_id: int) -> MonthDraft:
        return MonthDraft(
            month_id=month_id,
            month_title=f"Ay {month_id}: Test Dönemeç",
            durum_analizi=(
                "Bu ayın genel resmi: talep var ama sistem sınırda. "
                "Doğru hamleyle hızlanırsın; yanlış hamleyle yük birikir ve kalite algısı kırılır. "
                "Kısa vadeli kazanım ile uzun vadeli sağlamlık arasında seçim yapman gerekecek. "
                "Ekip motivasyonu ve müşteri güveni aynı anda etkilenebilir. "
                "Odak dağıtırsan küçük sorunlar birleşip büyük krize dönüşebilir. "
                * 4
            )[:520],
            kriz_title="Rakip baskısı",
            kriz=(
                "Rakipler agresif kampanya açtı ve kullanıcılar alternatifleri deniyor. "
                "Şikâyetler artarsa hem itibar hem gelir aynı anda zarar görür. "
                "Bu ay tek kritik iş: büyüme atağını mı basacaksın yoksa sistemi sadeleştirip dayanıklılığı mı artıracaksın? "
                * 4
            )[:520],
            options=[
                OptionDraft(
                    id="A",
                    title="Tek kanala yüklen",
                    tag="growth",
                    steps=[
                        "En hızlı kanalı seç ve tek mesajla agresif test yap",
                        "Landing + onboarding'i sadeleştir",
                        "1 metrikte kazan-kaybet hedefi koy",
                        "Hızlı iterasyon takvimi çıkar",
                    ],
                    risk="med",
                    delayed_seed="kısa vadeli ivme",
                    result=(
                        "Kısa sürede görünürlük artar ve pipeline hareketlenir. "
                        "Ama yük birikirse ekip yangın söndürmeye kayabilir; müşteri deneyimi hassaslaşır."
                    ),
                ),
                OptionDraft(
                    id="B",
                    title="Sistemi güçlendir",
                    tag="reliability",
                    steps=[
                        "En büyük 2 darboğazı seç ve fix listesi çıkar",
                        "On-call / destek sürecini netleştir",
                        "Kritik metrikler için alarmları ayarla",
                        "Release disiplinini sıkılaştır",
                    ],
                    risk="low",
                    delayed_seed="temiz altyapı",
                    result=(
                        "Görünür büyüme yavaşlar ama sistem nefes alır. "
                        "Şikâyetler azalır; itibar ve churn kontrol altına girer."
                    ),
                ),
            ],
            lesson="Büyüme mi dayanıklılık mı? Seçim, gelecekteki yangınların sayısını belirler.",
            alternatives=[
                "Büyüme kanalını kıs, ama onboarding'in en kritik 1 adımını iyileştir.",
                "Destek yükünü azaltmak için tek bir self-serve çözüm yayınla.",
            ],
            cliffhanger="Rakip yeni bir fiyat kırma hamlesi sinyali veriyor…",
        )


def run_headless_sim(months: int = 12) -> Dict[str, Any]:
    """Run a deterministic simulation and return summary."""
    cfg = EngineConfig(
        base_seed=123,
        scenario_seed=777,
        mode_key="classic",
        case_key="default",
        expenses={"payroll": 120_000, "infra": 25_000, "misc": 15_000},
    )

    state = GameState(month=1, stats=Stats(cash=550_000, mrr=900, reputation=50, support_load=22, infra_load=22, churn=0.055, morale=58, tech_debt=22), delayed_queue=[])

    provider = FakeDraftProvider()
    logs: List[Dict[str, Any]] = []

    for _ in range(months):
        draft = provider.make_draft(state.month)
        bundle = draft_to_bundle(draft, cfg)

        # pick the option with slightly lower risk deterministically
        choice_id = "A"
        if bundle.options and len(bundle.options) >= 2:
            # prefer low risk; else A
            risks = {o.id: getattr(o, "risk", "med") for o in bundle.options}
            if risks.get("B") == "low":
                choice_id = "B"

        state, log = apply_choice(state=state, bundle=bundle, choice_id=choice_id, config=cfg)
        logs.append(log)

    return {
        "months": months,
        "final": state,
        "logs": logs,
    }
