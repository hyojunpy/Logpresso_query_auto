from typing import Any
from urllib import request
import json

from app.core.config import settings
from app.models.document import SearchResult
from app.services.llm.base import LLMProvider
from app.services.llm.json_utils import parse_json_object


class OllamaProvider(LLMProvider):
    def generate_json(self, prompt: str, context: list[SearchResult]) -> dict[str, Any]:
        body = json.dumps(
            {
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            }
        ).encode("utf-8")
        req = request.Request(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=120) as response:
            raw = json.loads(response.read().decode("utf-8"))
            return parse_json_object(raw.get("response", raw))
