# Implementation plan

Follow the supplied eleven phases in order. Keep business logic independent of Apify.

1. Skeleton, dataclasses, strict input validation, input schema and offline test foundation.
2. Normalize URLs and reject unsafe addresses; enforce same host on every hop.
3. Bounded HTTPX transport, robots, sitemap parsing and deterministic discovery.
4. Main content extraction, structure, metadata and conservative JS-shell diagnosis.
5. Local token estimates and bounded SimHash candidate indexing.
6. Explainable six-component scoring, value/profile classification and chunk guidance.
7. Dataset row adapter with documented precedence and bounded pagination.
8. Reconciled aggregation, diagnostics, report and successful-analysis billing contract.
9. Apify adapter, output/storage schemas and Python 3.12 Docker image.
10. Buyer README, store metadata, architecture, validation and benchmark documents.
11. Offline tests, runtime checks, live small audit, three self-reviews, commit and push.

## Highest risks and decisions to verify

- Validate DNS and every redirect. Prevent DNS rebinding with a transport that connects to
  a validated address while preserving TLS SNI and Host. Test mixed DNS responses.
- Bound compressed and decoded bodies, sitemap trees, queue and duplicate candidates.
- Use deterministic ordering across concurrent fetches and retain compact fingerprints only.
- Separate successful analysis from ingestion recommendation and actual platform charging.
- Stop at platform budget limits and keep report totals equal to persisted page rows.
- Cloud permissions, actual billing and Docker must be reported only when exercised.
