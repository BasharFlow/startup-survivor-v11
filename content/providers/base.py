"""content.providers.base

Provider interfaces.

A provider's job is to produce a MonthDraft (narrative + intent signals).
The engine will convert MonthDraft -> MonthBundle with deterministic economy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Tuple

from ..schemas import MonthDraft


@dataclass(frozen=True)
class ProviderStatus:
    ok: bool
    backend: str
    model: str
    note: str = ""
    error: str = ""


class ContentProvider(Protocol):
    def status(self) -> ProviderStatus: ...

    def generate_month_draft(
        self,
        *,
        month_id: int,
        prompt: str,
        temperature: float = 0.8,
        max_output_tokens: int = 2200,
        repair_on_fail: bool = True,
    ) -> Tuple[MonthDraft, str]:
        """Return (draft, raw_text_used)."""
        ...
