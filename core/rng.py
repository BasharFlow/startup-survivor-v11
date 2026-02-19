"""
core.rng
Deterministic RNG helpers that do NOT rely on Python's built-in hash().

Goal:
- Same (base_seed + inputs) => same Random stream across platforms & runs.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any


def stable_int_seed(*parts: Any, salt: str = "startup-survivor") -> int:
    """Return a stable 32-bit integer seed derived from arbitrary inputs.

    Uses SHA-256 over a canonical JSON representation of `parts`.
    This avoids Python's randomized hash() and is stable across processes/platforms.

    Notes:
    - `default=str` ensures non-JSON types still serialize deterministically enough for our usage.
    - Output is 0..2**32-1 (works with random.Random).
    """
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    h = hashlib.sha256((salt + "|" + payload).encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big", signed=False)


def rng_from(*parts: Any, base_seed: int) -> random.Random:
    """Create a Random instance from (base_seed + parts)."""
    seed = stable_int_seed(base_seed, *parts)
    return random.Random(seed)
