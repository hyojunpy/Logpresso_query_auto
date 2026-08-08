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

## File-Based Catalog Exchange

When direct access to a customer Logpresso server is unavailable, accept a
reviewed JSON or CSV catalog file. The CSV header is:

```text
table_name,field_name,field_type,description
```

Review and publish a new catalog version through a catalog administrator.
