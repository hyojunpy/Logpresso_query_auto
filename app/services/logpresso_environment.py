from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


LOGGER_FIELDS = (
    "id", "guid", "name", "description", "table_name", "interval", "cron_schedule",
    "enabled", "status", "failure", "is_passive", "model_guid", "model_name",
    "site_guid", "site_name", "node_pair_guid", "node_pair_name", "sentry_guid",
    "asset_guid", "asset_ip", "hostname", "log_count", "log_volume", "drop_count",
    "drop_volume", "created", "updated",
)
SCHEMA_FIELDS = ("code", "name", "description", "created", "updated", "app_code", "app_built_in")
PARSER_FIELDS = (
    "code", "name", "description", "factory_name", "factory_display_name", "builtin",
    "schema_code", "schema_name", "created", "updated",
)
TABLE_FIELDS = (
    "table_name", "layout", "compression", "retention", "encrypted", "table_size",
    "index_size", "ratio", "group_guid", "group_name", "min_day", "max_day",
)
MODEL_FIELDS = ("guid", "name", "description", "version", "factory_name", "created", "updated")


class LogpressoConnectionError(RuntimeError):
    pass


class LogpressoClient:
    """Minimal read-only Sonar client. Responses are allow-listed before persistence."""

    def __init__(
        self, base_url: str, api_key: str, *, verify_tls: bool = True, timeout: float = 15,
        transport: httpx.BaseTransport | None = None,
    ):
        parsed = urlparse(base_url.rstrip("/"))
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Logpresso 주소는 HTTPS여야 합니다.")
        if not api_key.strip():
            raise ValueError("Logpresso API 키가 없습니다.")
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key.strip()}"}
        self.verify_tls = verify_tls
        self.timeout = timeout
        self.transport = transport

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            with httpx.Client(
                verify=self.verify_tls, timeout=self.timeout, trust_env=False, transport=self.transport
            ) as client:
                response = client.get(f"{self.base_url}{path}", headers=self.headers, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            label = f"HTTP {status}" if status else type(error).__name__
            raise LogpressoConnectionError(f"Logpresso API 호출 실패 ({label})") from error
        if not isinstance(payload, dict):
            raise LogpressoConnectionError("Logpresso API 응답 형식이 올바르지 않습니다.")
        return payload

    def _paged(self, path: str, key: str, fields: tuple[str, ...], *, limit: int = 500) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while len(rows) < 10_000:
            payload = self._get(path, {"offset": offset, "limit": limit})
            batch = payload.get(key, [])
            if not isinstance(batch, list):
                raise LogpressoConnectionError(f"{key} 응답 형식이 올바르지 않습니다.")
            rows.extend(self._allow_list(item, fields) for item in batch if isinstance(item, dict))
            total = int(payload.get("total_count", len(rows)) or 0)
            if not batch or len(rows) >= total or len(batch) < limit:
                break
            offset += len(batch)
        return rows

    def loggers(self) -> list[dict[str, Any]]:
        return self._paged("/api/sonar/loggers", "loggers", LOGGER_FIELDS)

    def log_schemas(self) -> list[dict[str, Any]]:
        return self._paged("/api/sonar/log-schemas", "schemas", SCHEMA_FIELDS)

    def parsers(self) -> list[dict[str, Any]]:
        return self._paged("/api/sonar/parsers", "parsers", PARSER_FIELDS)

    def tables(self) -> list[dict[str, Any]]:
        return self._paged("/api/sonar/tables", "tables", TABLE_FIELDS)

    def logger_models(self, loggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Load model metadata when the key has ADMIN permission; never retain model configs."""
        models = []
        for guid in sorted({str(item.get("model_guid")) for item in loggers if item.get("model_guid")}):
            payload = self._get(f"/api/sonar/logger-models/{guid}")
            model = payload.get("logger_model", payload)
            if isinstance(model, dict):
                models.append(self._allow_list(model, MODEL_FIELDS))
        return models

    @staticmethod
    def _allow_list(item: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
        # Deliberately excludes configs, credentials, stream queries and other opaque remote values.
        return {field: item.get(field) for field in fields if field in item}


class LogpressoEnvironmentStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def sync(self, client: LogpressoClient) -> dict[str, Any]:
        failures: dict[str, str] = {}
        resources: dict[str, list[dict[str, Any]]] = {}
        loaders = (
            ("loggers", client.loggers), ("schemas", client.log_schemas),
            ("parsers", client.parsers), ("tables", client.tables),
        )
        for name, loader in loaders:
            try:
                resources[name] = loader()
            except LogpressoConnectionError as error:
                resources[name] = []
                failures[name] = str(error)
        if failures.get("loggers"):
            raise LogpressoConnectionError(failures["loggers"])
        try:
            resources["logger_models"] = client.logger_models(resources["loggers"])
        except LogpressoConnectionError as error:
            resources["logger_models"] = []
            failures["logger_models"] = str(error)
        payload = {
            "version": 1,
            "synced_at": datetime.now(timezone.utc).isoformat(),
            **resources,
            "summary": self.summary(resources["loggers"]),
            "partial_failures": failures,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return payload

    @staticmethod
    def summary(loggers: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "total": len(loggers),
            "running": sum(item.get("status") == "running" for item in loggers),
            "stopped": sum(item.get("status") == "stopped" for item in loggers),
            "failed": sum(bool(item.get("failure")) for item in loggers),
            "enabled": sum(bool(item.get("enabled")) for item in loggers),
            "log_count": sum(int(item.get("log_count") or 0) for item in loggers),
            "log_volume": sum(int(item.get("log_volume") or 0) for item in loggers),
            "drop_count": sum(int(item.get("drop_count") or 0) for item in loggers),
            "drop_volume": sum(int(item.get("drop_volume") or 0) for item in loggers),
        }


def suggest_table_mappings(loggers: list[dict[str, Any]], products: list[dict[str, Any]]) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    for logger in loggers:
        table = str(logger.get("table_name") or "").strip()
        if not table:
            continue
        haystack = " ".join(str(logger.get(key) or "") for key in ("name", "description", "model_name", "table_name")).casefold()
        scored: list[tuple[int, str]] = []
        for product in products:
            name = str(product.get("name") or "")
            tokens = [token for token in re.findall(r"[a-z0-9]+", name.casefold()) if len(token) >= 3]
            score = sum(3 for token in tokens if token in haystack)
            if name.casefold() in haystack:
                score += 10
            if ("fw_" in haystack or "firewall" in haystack or "방화벽" in haystack) and any(
                token in name.casefold() for token in ("ngfw", "firewall", "방화벽", "(nf)")
            ):
                score += 2
            if score:
                scored.append((score, name))
        if scored:
            best = max(score for score, _ in scored)
            matches = [name for score, name in scored if score == best]
            if len(matches) == 1:
                suggestions.append({"product": matches[0], "table": table, "logger": str(logger.get("name") or "")})
    unique = {(item["product"], item["table"]): item for item in suggestions}
    counts: dict[str, int] = {}
    for product, _ in unique:
        counts[product] = counts.get(product, 0) + 1
    # Never auto-apply an arbitrary table when one product has multiple live collectors.
    safe = [item for (product, _), item in unique.items() if counts[product] == 1]
    return sorted(safe, key=lambda item: (item["product"], item["table"]))


def resolve_synced_table(snapshot: dict[str, Any], product: str | None) -> str | None:
    """Return a unique table inferred from the synchronized environment."""
    if not product:
        return None
    needle = product.casefold()
    tables = {
        str(item.get("table_name") or "").strip()
        for item in snapshot.get("loggers", [])
        if needle in " ".join(str(item.get(key) or "") for key in ("name", "description", "model_name")).casefold()
        and item.get("table_name")
    }
    return next(iter(tables)) if len(tables) == 1 else None
