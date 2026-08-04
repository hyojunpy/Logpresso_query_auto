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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {"status": "error", "message": "LLM response did not contain a JSON object"}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return {"status": "error", "message": f"invalid JSON object: {exc}"}


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
