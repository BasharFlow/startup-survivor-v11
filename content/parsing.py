"""content.parsing

Robust JSON parsing for LLM outputs.

Goal: accept common messy formats seen in model outputs without becoming unsafe.
We do NOT execute code; we only:
- strip code fences
- extract the first JSON object block
- normalize smart quotes
- remove trailing commas
- escape bare newlines inside quoted strings
- json.loads, then ast.literal_eval fallback (after normalizing literals)
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ParseResult:
    data: Optional[Dict[str, Any]]
    raw: str
    cleaned: str
    error: str = ""


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def strip_code_fences(s: str) -> str:
    s = (s or "").strip()
    m = _FENCE_RE.search(s)
    if m:
        return (m.group(1) or "").strip()
    return s


def extract_first_object(s: str) -> str:
    """Extract the first {...} block (best effort)."""
    s = (s or "").strip()
    if not s:
        return s
    i = s.find("{")
    if i < 0:
        return s
    j = s.rfind("}")
    if j <= i:
        return s[i:]
    return s[i : j + 1]


def normalize_smart_quotes(s: str) -> str:
    return (
        (s or "")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u00a0", " ")
    )


def remove_trailing_commas(s: str) -> str:
    return re.sub(r",\s*([}\]])", r"\1", s)


def escape_newlines_in_json_strings(s: str) -> str:
    """Escape bare newlines inside quoted strings."""
    if not s:
        return s

    out = []
    in_str = False
    quote = ""
    esc = False

    for ch in s:
        if in_str:
            if esc:
                out.append(ch)
                esc = False
                continue
            if ch == "\\":
                out.append(ch)
                esc = True
                continue
            if ch == quote:
                out.append(ch)
                in_str = False
                quote = ""
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            out.append(ch)
        else:
            if ch in ('"', "'"):
                out.append(ch)
                in_str = True
                quote = ch
            else:
                out.append(ch)

    return "".join(out)


def try_parse_json(raw: str) -> ParseResult:
    """Best-effort parse. Returns ParseResult(data=None, error=...) on failure."""
    raw = (raw or "").strip()

    s = strip_code_fences(raw)
    s = extract_first_object(s)
    s = normalize_smart_quotes(s)
    s = escape_newlines_in_json_strings(s)
    s = remove_trailing_commas(s)

    # 1) JSON
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return ParseResult(data=obj, raw=raw, cleaned=s)
        return ParseResult(data=None, raw=raw, cleaned=s, error="JSON root is not an object")
    except Exception as e_json:
        err1 = f"json.loads: {type(e_json).__name__}: {e_json}"

    # 2) literal_eval fallback (single quotes, True/False/None)
    s2 = s
    s2 = re.sub(r"\btrue\b", "True", s2, flags=re.IGNORECASE)
    s2 = re.sub(r"\bfalse\b", "False", s2, flags=re.IGNORECASE)
    s2 = re.sub(r"\bnull\b", "None", s2, flags=re.IGNORECASE)
    try:
        obj2 = ast.literal_eval(s2)
        if isinstance(obj2, dict):
            # normalize into JSON-serializable types
            return ParseResult(data=json.loads(json.dumps(obj2)), raw=raw, cleaned=s)
        return ParseResult(data=None, raw=raw, cleaned=s, error=f"literal_eval root is not object; {err1}")
    except Exception as e_ast:
        err2 = f"literal_eval: {type(e_ast).__name__}: {e_ast}"
        return ParseResult(data=None, raw=raw, cleaned=s, error=f"{err1} | {err2}")


def must_parse_json(raw: str) -> Dict[str, Any]:
    res = try_parse_json(raw)
    if not res.data:
        raise ValueError(res.error or "JSON parse failed")
    return res.data
