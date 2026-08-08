from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError
import json

from app.core.config import settings
from app.models.document import SearchResult
from app.services.llm.base import LLMProvider
from app.services.llm.json_utils import parse_json_object


class OllamaProvider(LLMProvider):
    def generate_json(self, prompt: str, context: list[SearchResult]) -> dict[str, Any]:
        response_format: dict[str, Any] | str = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["generated", "needs_clarification", "unsupported"]},
                "query": {"type": ["string", "null"]},
                "clarifying_questions": {"type": "array", "items": {"type": "string"}},
                "assumptions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "query"],
        }
        try:
            prompt_data = json.loads(prompt)
            if isinstance(prompt_data, dict) and isinstance(prompt_data.get("response_schema"), dict):
                response_format = prompt_data["response_schema"]
        except (TypeError, ValueError):
            pass
        body = json.dumps(
            {
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": response_format,
                "options": {
                    "temperature": 0,
                    "num_predict": 96,
                },
            }
        ).encode("utf-8")
        req = request.Request(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(2):
            try:
                with request.urlopen(req, timeout=settings.ollama_timeout_seconds) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                    data = parse_json_object(raw.get("response", raw))
                    data["retry_count"] = attempt
                    return data
            except TimeoutError:
                error = {"status": "error", "error_type": "timeout", "message": "Ollama request timed out"}
            except HTTPError as exc:
                error = {"status": "error", "error_type": "http_error", "message": f"Ollama returned HTTP {exc.code}"}
                if exc.code < 500:
                    return error
            except URLError as exc:
                error_type = "timeout" if isinstance(exc.reason, TimeoutError) else "connection_error"
                error = {"status": "error", "error_type": error_type, "message": "Ollama connection failed"}
            except (json.JSONDecodeError, ValueError, TypeError):
                return {"status": "error", "error_type": "invalid_response", "message": "Ollama returned an invalid response"}
            if attempt == 1:
                return {**error, "retry_count": attempt}
        return {"status": "error", "error_type": "unknown", "message": "Ollama request failed"}
