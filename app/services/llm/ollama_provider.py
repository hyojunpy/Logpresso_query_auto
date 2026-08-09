from typing import Any
from urllib import request
from urllib.error import HTTPError, URLError
import json
from time import perf_counter

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
                    "num_predict": settings.ollama_num_predict,
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
            started = perf_counter()
            try:
                with request.urlopen(req, timeout=settings.ollama_timeout_seconds) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                    data = parse_json_object(raw.get("response", raw))
                    if data.get("status") not in {"generated", "needs_clarification", "unsupported"}:
                        return _error(
                            "invalid_response",
                            "Ollama returned an invalid response",
                            attempt,
                            started,
                            raw,
                        )
                    data["retry_count"] = attempt
                    data["timing"] = _timing_metadata(raw, perf_counter() - started)
                    return data
            except TimeoutError:
                return _error("timeout", "Ollama request timed out", attempt, started)
            except HTTPError as exc:
                error = {"status": "error", "error_type": "http_error", "message": f"Ollama returned HTTP {exc.code}"}
                if exc.code < 500:
                    return {**error, "retry_count": attempt, "timing": _timing_metadata({}, perf_counter() - started)}
            except URLError as exc:
                error_type = "timeout" if isinstance(exc.reason, TimeoutError) else "connection_error"
                error = {"status": "error", "error_type": error_type, "message": "Ollama connection failed"}
                if error_type == "timeout":
                    return {**error, "retry_count": attempt, "timing": _timing_metadata({}, perf_counter() - started)}
            except (json.JSONDecodeError, ValueError, TypeError):
                return _error("invalid_response", "Ollama returned an invalid response", attempt, started)
            if attempt == 1:
                return {**error, "retry_count": attempt, "timing": _timing_metadata({}, perf_counter() - started)}
        return {"status": "error", "error_type": "unknown", "message": "Ollama request failed"}


def _error(
    error_type: str,
    message: str,
    retry_count: int,
    started: float,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "error",
        "error_type": error_type,
        "message": message,
        "retry_count": retry_count,
        "timing": _timing_metadata(raw or {}, perf_counter() - started),
    }


def _timing_metadata(raw: dict[str, Any], elapsed_seconds: float) -> dict[str, int]:
    """Expose only numeric timing data; response text and request content never leave the provider."""
    timing = {"client_duration_ms": max(0, round(elapsed_seconds * 1000))}
    for source, target in {
        "total_duration": "total_duration_ms",
        "load_duration": "load_duration_ms",
        "prompt_eval_duration": "prompt_eval_duration_ms",
        "eval_duration": "eval_duration_ms",
    }.items():
        value = raw.get(source)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            timing[target] = round(value / 1_000_000)
    return timing
