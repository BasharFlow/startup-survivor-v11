"""content.prompts

Prompt builders for the content generation layer.

These prompts intentionally keep game-economy logic OUT of the model.
Model produces narrative + option intent signals (tag/risk/delayed_seed + outcomes).
The engine later turns tags into deltas deterministically.

We also support interpreting the player's own plan (custom choice text) into a ChoiceIntent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

ALLOWED_TAGS = [
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
]


def _bucket(x: float, lo: float, hi: float) -> str:
    if x <= lo:
        return "düşük"
    if x >= hi:
        return "yüksek"
    return "orta"


def describe_stats(stats: Mapping[str, Any]) -> str:
    cash = float(stats.get("cash", 0.0))
    mrr = float(stats.get("mrr", 0.0))
    rep = float(stats.get("reputation", 50.0))
    support = float(stats.get("support_load", 20.0))
    infra = float(stats.get("infra_load", 20.0))
    churn = float(stats.get("churn", 0.05))
    morale = float(stats.get("morale", 55.0))
    tech = float(stats.get("tech_debt", 25.0))

    cash_s = "çok sıkışık" if cash < 120_000 else ("rahat" if cash > 650_000 else "kısıtlı")
    mrr_s = "çok erken" if mrr < 800 else ("sağlam" if mrr > 12_000 else "gelişen")
    rep_s = _bucket(rep, 35, 70)
    support_s = _bucket(support, 30, 70)
    infra_s = _bucket(infra, 30, 70)
    churn_s = "kontrollü" if churn < 0.05 else ("yüksek" if churn > 0.10 else "dalgalı")
    morale_s = _bucket(morale, 40, 75)
    tech_s = _bucket(tech, 30, 70)

    return (
        f"Nakit durumu: {cash_s}. "
        f"Gelir olgunluğu: {mrr_s}. "
        f"Pazarda itibar algısı: {rep_s}. "
        f"Müşteri kaybı: {churn_s}. "
        f"Destek yükü: {support_s}. "
        f"Altyapı baskısı: {infra_s}. "
        f"Ekip morali: {morale_s}. "
        f"Teknik borç: {tech_s}."
    )


def build_prompt(
    *,
    month: int,
    mode_title: str,
    mode_desc: str,
    mode_tone: str,
    idea: str,
    history: List[Dict[str, Any]],
    case_title: str,
    case_blurb: str,
    stats: Mapping[str, Any],
    character_name: str = "",
    character_trait: str = "",
) -> str:
    """Build the month-generation prompt (v2 schema).

    The model MUST output ONLY JSON matching the expected schema.
    """

    idea = (idea or "").strip() or "(boş)"

    last_tags = [str(h.get("tag", "")) for h in (history or [])][-4:]
    last_tags = [t for t in last_tags if t]
    last_tags_s = ", ".join(last_tags) if last_tags else "(yok)"

    stats_summary = describe_stats(stats)
    allowed_tags = "|".join(ALLOWED_TAGS)

    char_line = ""
    if (character_name or character_trait).strip():
        char_line = f"- Karakter: {character_name} — {character_trait}".strip()

    # Mode writing style: user asked for mode-based tone (realistic vs extreme irony)
    style = mode_tone or "gerçekçi ve net"
    if "Extreme" in (mode_title or ""):
        style = style + "; absürt olayları ölümcül ciddi bir dille anlat (deadpan), ironi buradan gelsin"

    return f"""
Sen bir startup simülasyonu için aylık anlatı paketi üreten 'narrative designer'sın.

Bağlam:
- Ay: {int(month)}
- Mod: {mode_title} — {mode_desc}
- Yazım tonu: {style}
- Sezon: {case_title} — {case_blurb}
{char_line}
- Ürün fikri: {idea}
- Son hamle etiketleri: {last_tags_s}
- Şu an resim: {stats_summary}

Amaç:
- Oyuncu karar vermek istemeli. Net trade-off, gerilim, sonuç hissi üret.
- Oyuncu isterse kendi çözümünü de yazacak (UI). Sen yine de 2-3 güçlü seçenek üret.

Görev:
1) Bu ayın temasını tek cümlelik bir "month_title" ile kur.
2) Açıklayıcı "durum_analizi" yaz (uzun form, analitik, net; 3-5 paragraf).
3) Tek bir ana kriz üret: "kriz_title" + "kriz" (en az 3 paragraf).
4) 2 veya 3 seçenek üret (options listesi):
   - Her seçenek: id (A,B,(opsiyonel C)) + title + tag + risk + 4-6 adımlık plan (steps)
   - Her seçenek için 2-4 kısa paragraf "result" yaz (seçilirse ne olur?).
   - tag sadece şu listeden biri olmalı: {allowed_tags}
   - risk sadece: low|med|high
5) (Opsiyonel ama önerilir) "lesson" alanına 1-2 cümlelik ders yaz.
6) (Opsiyonel) "alternatives" alanına oyuncuya "farklı yöntem" olarak 2-3 kısa madde ekle.
7) Ayın sonunda bir cümlelik "cliffhanger" yaz (gelecek ayı merak ettirsin).

ÇIKTI FORMATIN: SADECE JSON (başka hiçbir metin yok, markdown yok).

JSON ŞEMA:
{{
  "month_title": "string (>= 6 karakter)",
  "durum_analizi": "string (>= 220 karakter)",
  "kriz_title": "string (>= 6 karakter)",
  "kriz": "string (>= 220 karakter)",
  "options": [
    {{
      "id": "A",
      "title": "string",
      "tag": "{allowed_tags}",
      "risk": "low|med|high",
      "steps": ["string", "string", "string", "string"],
      "delayed_seed": "kısa anahtar kelime/ifade",
      "result": "string"
    }}
  ],
  "lesson": "string (opsiyonel)",
  "alternatives": ["string", "string"],
  "cliffhanger": "string",
  "note": "string (opsiyonel)"
}}
""".strip()


def build_choice_intent_prompt(
    *,
    month: int,
    mode_title: str,
    mode_tone: str,
    idea: str,
    crisis_title: str,
    crisis: str,
    player_text: str,
) -> str:
    """Interpret the player's custom plan into a ChoiceIntent (JSON only)."""

    idea = (idea or "").strip() or "(boş)"
    player_text = (player_text or "").strip()

    style = mode_tone or "gerçekçi ve net"
    if "Extreme" in (mode_title or ""):
        style = style + "; absürt olayları ölümcül ciddi bir dille anlat (deadpan), ironi buradan gelsin"

    allowed_tags = "|".join(ALLOWED_TAGS)

    # Keep it short to reduce hallucination risk; we only need intent signals.
    return f"""
Sen bir startup simülasyonunda oyuncunun yazdığı serbest çözümü yapılandıran bir 'decision interpreter'sın.
Sadece JSON üret.

Bağlam:
- Ay: {int(month)}
- Mod: {mode_title}
- Yazım tonu: {style}
- Ürün fikri: {idea}
- Kriz başlığı: {crisis_title}
- Kriz özeti: {crisis[:500]}

Oyuncunun çözümü (aynen):
{player_text}

Görev:
- Bu çözümü bir "title" ile özetle.
- Birincil "tag" seç (sadece: {allowed_tags})
- "risk" seç (low|med|high)
- 3-6 maddelik uygulanabilir "steps" yaz.
- "delayed_seed" üret (kısa anahtar ifade).
- "result" alanına 1-3 kısa paragraf: bu plan uygulanırsa ne olur? (gerilim + sonuç hissi)

ÇIKTI FORMATIN: SADECE JSON.

JSON ŞEMA:
{{
  "title": "string",
  "tag": "{allowed_tags}",
  "risk": "low|med|high",
  "steps": ["string", "string", "string"],
  "delayed_seed": "string",
  "result": "string"
}}
""".strip()


def build_json_repair_prompt(broken_text: str) -> str:
    broken_text = str(broken_text or "")
    return f"""Aşağıdaki metin bozuk JSON içeriyor. Görevin: SADECE geçerli JSON döndürmek.
- Yorum ekleme, markdown kullanma.
- Alan isimlerini değiştirme, sadece düzelt.
- Eksik virgül/quote vb. sorunları düzelt.

BOZUK METİN:
{broken_text}
""".strip()
