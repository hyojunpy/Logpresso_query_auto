from __future__ import annotations

from typing import Any
import json
import re


def parse_json_object(raw: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    text = raw.strip()
    if not text:
        return {"status": "error", "message": "empty LLM response"}
    candidates = [text]
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        candidates.insert(0, fenced.group(1))
    embedded = _first_balanced_object(text)
    if embedded and embedded not in candidates:
        candidates.append(embedded)
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            # Small local models commonly leave a trailing comma before a
            # closing brace/array even when JSON mode is requested.
            repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
            if repaired != candidate:
                try:
                    value = json.loads(repaired)
                    if isinstance(value, dict):
                        return value
                except json.JSONDecodeError:
                    pass
    if not embedded:
        return {"status": "error", "message": "LLM response did not contain a JSON object"}
    return {"status": "error", "message": "invalid JSON object"}


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote:
            escaped = True
            continue
        if char == '"':
            quote = None if quote else '"'
            continue
        if quote:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return None


def extract_openai_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)
