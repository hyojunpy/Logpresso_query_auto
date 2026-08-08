# Advanced Parser Roadmap

## Scope Boundary

The current product converts natural-language requests into reviewable Logpresso
query drafts. Its deterministic parser supports common table, filter,
aggregation, rename, and join patterns. It does not claim to parse every
Logpresso language feature.

The `advanced_parser` pytest marker isolates exploratory tests that cover a
larger future language surface. They are retained as a roadmap and are not
included in the default CI suite.

## Planned Increments

1. Define a grammar and AST for nested commands, quoted expressions, and
   command-specific options.
2. Add file source handling for CSV, JSON, TSV, EVTX, and ZIP only after a
   customer security review defines upload scanning and retention policies.
3. Add structured data extraction commands with fixture-driven syntax tests.
4. Extend field lineage across joins, aliases, and computed fields. Start by
   surfacing rename/eval provenance in validation output before treating it as
   a hard schema rule.
5. Add differential tests against a non-production Logpresso environment when
   customer access is available. This project must not connect to a customer
   server by default.

## Entry Criteria

Each increment needs documented syntax evidence, fixtures without customer log
content, validation behavior, diagnostics, and a dry-run-only acceptance test.
