from typing import Any
from urllib import request
import json

from app.core.config import settings
from app.models.document import SearchResult
from app.services.llm.base import LLMProvider
from app.services.llm.json_utils import extract_openai_text, parse_json_object


class OpenAIProvider(LLMProvider):
    def generate_json(self, prompt: str, context: list[SearchResult]) -> dict[str, Any]:
        if not settings.openai_api_key:
            return {"status": "error", "message": "OPENAI_API_KEY is not set"}
        body = json.dumps(
            {
                "model": settings.openai_model,
                "input": prompt,
                "text": {"format": {"type": "json_object"}},
            }
        ).encode("utf-8")
        req = request.Request(
            "https://api.openai.com/v1/responses",
            data=body,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=60) as response:
            raw = json.loads(response.read().decode("utf-8"))
            return parse_json_object(extract_openai_text(raw) or raw)
