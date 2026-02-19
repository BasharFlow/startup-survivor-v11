"""content.providers.gemini

Gemini provider (LLM).

- Supports google-genai (preferred) and google-generativeai (legacy).
- Always returns MonthDraft (validated) or raises a helpful error.

Important: This provider is UI-agnostic (no Streamlit dependency).
Secrets/env loading is done in the Streamlit app.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..parsing import try_parse_json
from ..schemas import MonthDraft, ChoiceIntent, draft_from_llm, intent_from_llm, validate_intent
from .base import ProviderStatus


@dataclass
class GeminiProvider:
    api_keys: List[str]

    # runtime
    backend: str = "none"  # genai | legacy | none
    model_in_use: str = ""
    last_error: str = ""

    _client: Any = None
    _legacy: Any = None

    def __post_init__(self) -> None:
        self.api_keys = [k.strip() for k in (self.api_keys or []) if str(k).strip()]
        self._init_backend()

    @staticmethod
    def from_api_key_string(raw: str) -> "GeminiProvider":
        if not raw:
            return GeminiProvider([])
        raw = str(raw)
        keys = [x.strip() for x in raw.split(",") if x.strip()] if "," in raw else [raw.strip()]
        return GeminiProvider(keys)

    def _init_backend(self) -> None:
        self._client = None
        self._legacy = None
        self.backend = "none"
        self.model_in_use = ""

        if not self.api_keys:
            self.last_error = "API key yok."
            return

        # Try new SDK: google-genai
        try:
            from google import genai  # type: ignore

            self._client = genai.Client(api_key=self.api_keys[0])
            self.backend = "genai"
            self.model_in_use = "gemini-2.5-pro"
            self.last_error = ""
            return
        except Exception as e:
            self.last_error = f"google-genai yok/başarısız: {e}"

        # Try legacy: google-generativeai
        try:
            import google.generativeai as genai_legacy  # type: ignore

            genai_legacy.configure(api_key=self.api_keys[0])
            self._legacy = genai_legacy
            self.backend = "legacy"
            self.model_in_use = "gemini-2.5-pro"
            self.last_error = ""
            return
        except Exception as e:
            self.backend = "none"
            self.last_error = f"google-generativeai yok/başarısız: {e}"

    def status(self) -> ProviderStatus:
        if self.backend == "none":
            return ProviderStatus(False, "none", "", note="", error=str(self.last_error or ""))
        return ProviderStatus(True, self.backend, self.model_in_use, note="", error="")

    def _rotate_key(self) -> None:
        if len(self.api_keys) <= 1:
            return
        self.api_keys = self.api_keys[1:] + self.api_keys[:1]
        self._init_backend()

    def _generate_text(self, prompt: str, temperature: float, max_output_tokens: int) -> str:
        candidates = [
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.5-pro-latest",
        ]

        last_err: Optional[Exception] = None

        for _ in range(max(1, len(self.api_keys))):
            if self.backend == "genai" and self._client is not None:
                for m in candidates:
                    try:
                        cfg: Dict[str, Any] = {
                            "temperature": float(temperature),
                            "max_output_tokens": int(max_output_tokens),
                        }
                        # Try to force JSON output when supported.
                        try:
                            cfg2 = dict(cfg)
                            cfg2["response_mime_type"] = "application/json"
                            resp = self._client.models.generate_content(model=m, contents=prompt, config=cfg2)
                        except TypeError:
                            resp = self._client.models.generate_content(model=m, contents=prompt, config=cfg)

                        txt = (getattr(resp, "text", "") or "").strip()
                        if txt:
                            self.model_in_use = m
                            return txt
                    except Exception as e:
                        last_err = e
                        continue

            if self.backend == "legacy" and self._legacy is not None:
                for m in candidates:
                    try:
                        model = self._legacy.GenerativeModel(m)
                        try:
                            resp = model.generate_content(
                                prompt,
                                generation_config={
                                    "temperature": float(temperature),
                                    "max_output_tokens": int(max_output_tokens),
                                    "response_mime_type": "application/json",
                                },
                            )
                        except Exception:
                            resp = model.generate_content(
                                prompt,
                                generation_config={
                                    "temperature": float(temperature),
                                    "max_output_tokens": int(max_output_tokens),
                                },
                            )
                        txt = (getattr(resp, "text", "") or "").strip()
                        if txt:
                            self.model_in_use = m
                            return txt
                    except Exception as e:
                        last_err = e
                        continue

            self._rotate_key()

        raise RuntimeError(f"Gemini hata: {last_err}" if last_err else "Gemini yanıt veremedi.")

    def _parse_or_raise(self, raw: str) -> Dict[str, Any]:
        res = try_parse_json(raw)
        if res.data:
            return res.data
        # try direct json as last attempt
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        raise ValueError(res.error or "JSON parse edilemedi")

    def generate_month_draft(
        self,
        *,
        month_id: int,
        prompt: str,
        temperature: float = 0.8,
        max_output_tokens: int = 2200,
        repair_on_fail: bool = True,
    ) -> Tuple[MonthDraft, str]:
        """Generate and validate MonthDraft.

        Strategy:
        1) Try main prompt.
        2) If parse/validation fails and repair_on_fail is True, run one repair pass.
        """
        raw = self._generate_text(prompt, temperature=temperature, max_output_tokens=max_output_tokens)
        try:
            data = self._parse_or_raise(raw)
            # month_id is supplied by the caller (engine/UI) and validated in draft_from_llm_v1.
            # draft_from_llm_v1 validates minimum lengths/steps and normalizes tag/risk.
            # (No placeholder; we use the provided month_id.)
            draft = draft_from_llm(data, month_id=int(month_id))
            return draft, raw
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"

        if repair_on_fail:
            from ..prompts import build_json_repair_prompt
            repair_prompt = build_json_repair_prompt(raw)
            raw2 = self._generate_text(repair_prompt, temperature=0.1, max_output_tokens=max_output_tokens + 300)
            data2 = self._parse_or_raise(raw2)
            draft2 = draft_from_llm(data2, month_id=int(month_id))
            return draft2, raw2

        raise RuntimeError(self.last_error or "Gemini çıktı doğrulanamadı")


    def generate_choice_intent(
        self,
        *,
        prompt: str,
        temperature: float = 0.6,
        max_output_tokens: int = 1200,
        repair_on_fail: bool = True,
    ) -> Tuple[ChoiceIntent, str]:
        """Generate and validate ChoiceIntent (player custom plan).

        Strategy:
        1) Try main prompt.
        2) If parse/validation fails and repair_on_fail is True, run one repair pass.
        """
        raw = self._generate_text(prompt, temperature=temperature, max_output_tokens=max_output_tokens)
        try:
            data = self._parse_or_raise(raw)
            intent = intent_from_llm(data)
            validate_intent(intent)
            return intent, raw
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"

        if repair_on_fail:
            from ..prompts import build_json_repair_prompt

            repair_prompt = build_json_repair_prompt(raw)
            raw2 = self._generate_text(repair_prompt, temperature=0.1, max_output_tokens=max_output_tokens + 200)
            data2 = self._parse_or_raise(raw2)
            intent2 = intent_from_llm(data2)
            validate_intent(intent2)
            return intent2, raw2

        raise RuntimeError(self.last_error or "Gemini intent çıktı doğrulanamadı")
