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
