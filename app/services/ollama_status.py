from __future__ import annotations

import json
from urllib import request
from urllib.error import HTTPError, URLError


def check_ollama(base_url: str, model: str, timeout_seconds: float = 3) -> dict[str, object]:
    """Explicit connectivity check only; never called during normal generation."""
    try:
        with request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [item.get("name") for item in payload.get("models", []) if isinstance(item, dict) and isinstance(item.get("name"), str)]
        return {"status": "reachable", "configured_model": model, "model_available": model in models or any(name.startswith(f"{model}:") for name in models), "models": models[:50], "external_call_made": True}
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return {"status": "unreachable", "configured_model": model, "model_available": False, "models": [], "external_call_made": True}
