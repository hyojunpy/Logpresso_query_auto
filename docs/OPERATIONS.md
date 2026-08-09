# Operations And Access Design

## Safety Boundary

The application generates and validates Logpresso queries. It does not execute
queries, create schedules, or call a customer Logpresso server.

## Recommended Roles

- `viewer`: generate, validate, and download query drafts.
- `editor`: manage personal or team aliases and submit feedback.
- `catalog_admin`: import and publish catalog files.
- `platform_admin`: view feedback summaries and manage shared aliases.

## APIs Requiring Protection Before Shared Deployment

- `POST` and `DELETE /api/v1/aliases`
- Catalog import and update endpoints
- Feedback summary and improvement-candidate endpoints
- Development evaluation endpoints

Use the customer's existing identity provider or a reverse proxy. Do not add a
separate password store to this project. Apply role checks at the API boundary,
keep audit metadata, and restrict catalog exports when they contain sensitive
schema descriptions.

## Authentication And Audit Integration

The application does not authenticate users itself. A reverse proxy or customer
identity provider should enforce the roles above and may forward a non-sensitive
`X-Actor-ID` header. Management actions record only action type, resource,
actor identifier, small metadata such as table count, and timestamp in the
local `management_audit` SQLite table. Request text, generated queries, and log
content are intentionally excluded from this audit trail.

## Optional API Key Guard

For a small shared deployment without an upstream proxy, set
`MANAGEMENT_API_KEY` to a high-entropy secret. Catalog import/export/update,
catalog backup restore, aliases, feedback reports, audit records, and the
development Gold Set endpoint then require the matching
`X-Management-API-Key` header. Query generation, validation, feedback
submission, health checks, and catalog reads remain available. This is a
deployment guard, not a replacement for customer-managed role-based access.

## File-Based Catalog Exchange

When direct access to a customer Logpresso server is unavailable, accept a
reviewed JSON or CSV catalog file. The CSV header is:

```text
table_name,field_name,field_type,description
```

Review and publish a new catalog version through a catalog administrator.

## File-Based Alias Exchange

Business aliases can be exchanged as UTF-8 CSV with `phrase,target` headers.
Optional `kind` is `table` or `field`; optional `scope` limits an alias to a
product group. Import validates every row before writing, rejects duplicate
`phrase/kind/scope` keys, and applies no partial update on error. The API is
`POST /api/v1/aliases/import/csv` with `Content-Type: text/csv`.

## Future Non-Production Verification

`app.services.verification_adapter` defines a dry-run-only contract and ships
with no-op and fixture mock adapters. It has no network client and never calls
a Logpresso server. A customer-specific adapter may be implemented only after
the target environment, authorization boundary, query retention policy, and
acceptance tests are reviewed. Production query execution remains out of scope.

When `ENABLE_DEV_EVALUATION=true`, the protected development endpoint
`POST /api/v1/internal/verification/dry-run` demonstrates the contract using
the no-op adapter. It always returns `external_call_made: false` and does not
connect to Logpresso, even when a query is supplied.

## Privacy-Safe Operational Metrics

`GET /api/v1/internal/metrics` provides aggregate counts for HTTP response
statuses, query-generation outcomes, and LLM fallback events. It never stores
request text, generated queries, log contents, IP addresses, actor IDs, or
timestamps more precise than a UTC date. The endpoint is covered by the same
optional `MANAGEMENT_API_KEY` guard as other management APIs.

Counters are stored separately in `data/metrics.db` and are automatically
purged after 30 days. Set `METRICS_RETENTION_DAYS` to adjust the period; use a
positive integer only.

## Ollama Response Budget

The default Ollama request timeout is 45 seconds. A timeout is not retried;
the application returns the locally validated rule-based draft instead. Set
`OLLAMA_TIMEOUT_SECONDS` only when a larger local model requires more time.
