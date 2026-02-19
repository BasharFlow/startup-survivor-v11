"""
core.modes
Mode specifications (difficulty / volatility / macro toggles).

Kept in core so balancing lives in one place, but UI can still display labels.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ModeSpec:
    key: str
    desc: str
    temp: float
    swing: float
    require_reason: bool
    deceptive: bool
    antagonistic: bool
    turkey: bool
    absurd: bool
    tone: str


DEFAULT_MODES: Dict[str, ModeSpec] = {
    "Gerçekçi": ModeSpec(
        key="Gerçekçi",
        desc="Tam gerçek dünya hissi. Trade-off net, mucize yok.",
        temp=0.75,
        swing=1.00,
        require_reason=False,
        deceptive=False,
        antagonistic=False,
        turkey=False,
        absurd=False,
        tone="tamamen gerçekçi, operatif, net; abartı yok; ölçülü dramatik",
    ),
    "Zor": ModeSpec(
        key="Zor",
        desc="Gerçekçi ama daha zor. Seçenekler yanıltıcı olabilir; kısa gerekçe ister.",
        temp=0.82,
        swing=1.25,
        require_reason=True,
        deceptive=True,
        antagonistic=False,
        turkey=False,
        absurd=False,
        tone="sert ama adil; belirsizlik yüksek; hızlı karar baskısı",
    ),
    "Spartan": ModeSpec(
        key="Spartan",
        desc="En zor. Anlatıcı antagonistik; dünya acımasız ama mantıklı.",
        temp=0.88,
        swing=1.45,
        require_reason=True,
        deceptive=True,
        antagonistic=True,
        turkey=False,
        absurd=False,
        tone="acımasız derecede gerçekçi; iğneleyici ama saygılı; baskı çok yüksek",
    ),
    "Türkiye": ModeSpec(
        key="Türkiye",
        desc="Türkiye şartları: kur/enflasyon, vergi/SGK, denetimler, tahsilat gecikmesi, afet riski.",
        temp=0.78,
        swing=1.10,
        require_reason=False,
        deceptive=False,
        antagonistic=False,
        turkey=True,
        absurd=False,
        tone="Türkiye iş dünyası gerçekleri; maliyet ve uyum detaylı; somut ve gerçekçi",
    ),
    "Extreme": ModeSpec(
        key="Extreme",
        desc="Absürt ve komik. Mantıksız ama eğlenceli krizler (sadece bu modda).",
        temp=1.05,
        swing=1.40,
        require_reason=False,
        deceptive=False,
        antagonistic=False,
        turkey=False,
        absurd=True,
        tone="absürt olay + ölümcül ciddi (deadpan) anlatım; ironik; hızlı tempo",
    ),
}


def get_mode_spec(mode_key: str) -> ModeSpec:
    return DEFAULT_MODES.get(mode_key, DEFAULT_MODES["Gerçekçi"])
