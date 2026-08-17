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

## 0.1.2 Baseline

The exploratory suite currently reports 56 passing and 38 failing tests. Simple
rename/eval lineage is already surfaced as informational validation metadata.
The remaining failures cluster around file sources, structured parsers,
compound boolean expressions, source options, and UI wording. File-source
implementation remains deferred until the upload security entry criteria are
met; it must not be enabled merely to make roadmap tests pass.

## 0.1.3 Work Breakdown

- Product-track: compound boolean grouping, quoted fulltext expressions,
  command-specific parser options, offset/sort handling, and field lineage.
- Security-gated: every direct file source, archive member, upload, retention,
  and deletion behavior. These remain excluded until a written threat model,
  scanning policy, size/type limits, retention period, and audit behavior are
approved.
- Reporting-only: the exploratory suite runs in CI as a non-blocking job and
  publishes its result so regressions are visible without pretending the
  security-gated cases are supported.

The initial 0.1.3 implementation raises the roadmap baseline to 76 passing and
16 failing tests. The remaining failures are dominated by security-gated file
sources; the residual non-file cases are tracked separately from that gate.

## Entry Criteria

Each increment needs documented syntax evidence, fixtures without customer log
content, validation behavior, diagnostics, and a dry-run-only acceptance test.
