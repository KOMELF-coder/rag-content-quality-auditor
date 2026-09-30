# Benchmark plan — pricing remains undecided

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

## Pricing decision inputs

Need measured cost distributions, support overhead, Store/platform fees, expected volume,
memory choice and acceptable margin. Source pagination uses batches of at most 50 rows;
measure API overhead and peak batch memory before increasing that size. Set a `page-audited` price only
after reviewing these data. No price or performance improvement is inferred here.
