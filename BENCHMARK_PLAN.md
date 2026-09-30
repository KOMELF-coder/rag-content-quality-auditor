# Benchmark plan and measured launch baseline

## Matrix

Measure 10, 50, 100 and 500 pages for documentation, blogs, SaaS content and ecommerce
content sections. Use public accessible targets that permit the audit and record the
exact input, source time, Actor build, concurrency, memory allocation and region.

Run website and dataset modes separately. For dataset mode, retain an immutable test
dataset ID and content version. Repeat each case at least three times; distinguish warm
and cold starts. Do not extrapolate the small Windows live check into Cloud costs.

## Record

| Metric | Evidence |
| --- | --- |
| Runtime | Actor run duration and application report runtime |
| Peak memory | Platform metrics, or sampled RSS with sampling interval recorded |
| HTTP requests | Report website transport attempts; separately count source/storage API calls |
| Platform cost | Actual Apify run usage and billing records |
| Dataset results | Output item count, reconciled with successful analyses |
| Successful billable events | SDK event count and platform charging ledger |
| Failures/skips | DIAGNOSTICS grouped by error code |
| Quality signals | Duplicates, recommendations, score distribution, estimated tokens |

## Procedure

1. Confirm permission/robots availability and constrain each source section using globs.
2. Begin at 10 pages. Inspect extraction and errors before expanding.
3. Keep page limits, retry behavior and scoring unchanged across comparable runs.
4. Test request failures, a mostly skipped corpus, duplicates and a budget-limited run.
5. Report median and range; retain raw run IDs/reports and document anomalies.
6. Calculate cost per successful audited document, including auxiliary requests, startup,
   storage, diagnostics and failures. Include the cost of entirely unsuccessful runs.

## Measured launch baseline — 2026-09-30

Apify Cloud website-mode validation used public Python documentation, 512 MB memory,
concurrency 4 and the same build/configuration family. Observed runs:

| Selected | Successful | Skipped | Engine runtime | Run cost |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 10 | 0 | 2.485 s | UI displayed $0.000 |
| 50 | 43 | 7 | 46.559 s | $0.001 |
| 100 | 92 | 8 | 112.513 s | $0.003 |
| 500 | 491 | 9 | 1005.311 s | $0.031 |

The 500-page run had 504 HTTP requests, 0 page-processing failures and 2,660,671
estimated analyzed tokens. A prior 500-page attempt hit the 300-second run timeout after
189 results; the clean run completed with a 1,200-second timeout.

These measurements are not universal guarantees. They justify the initial commercial
decision to launch at **$0.003 per successful `page-audited` event**, with platform usage
intended to be included. At that event price, 1,000 successful audits cost about $3 to
the user before any unrelated storage charges.

Future benchmarking should broaden targets (blogs, SaaS, ecommerce), repeat runs, capture
peak memory and verify the live PPE ledger/budget behavior after monetization is enabled.
