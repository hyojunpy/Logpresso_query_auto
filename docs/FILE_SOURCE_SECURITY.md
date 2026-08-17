# File source security gate

Direct file, archive, and upload query sources are not enabled. Implementation
may begin only after the repository owner approves all of the following:

- allowlisted file types and per-type size limits;
- malware scanning and archive-bomb/path-traversal defenses;
- storage location, encryption, retention period, and verified deletion;
- filename/path redaction and audit-log behavior;
- tenant isolation and authorization checks;
- fixtures containing no customer or production log data;
- dry-run tests proving that parsing never connects to a customer system.

Until then, roadmap tests for CSV, JSON, TSV, EVTX, ZIP, PCAP, XML, Prefetch,
WER, and text-file sources are reporting-only and must not be made to pass by
accepting a local path or upload.
