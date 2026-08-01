# RC-1 Performance Signoff

Production probes returned frontend pages in 342–733 ms and backend public endpoints in 1,108–1,483 ms from this audit location. The database is healthy and 1,500 usage events reconcile exactly. Ingestion is atomic and idempotent; reporting paginates beyond the Data API 1,000-row default; counters avoid dashboard full-table aggregation; database clients are isolated per worker.

A bounded concurrent readiness probe completed 40/40 requests successfully: minimum 510 ms, mean 1,452.82 ms and maximum 5,933 ms. This proves availability under a small burst, not ingestion capacity.

This is acceptable for an RC-1 preview, not a capacity certification. Before paid public traffic, run the repository load harness from a representative region and set an explicit SLO. Recommended initial targets: API availability 99.9%, policy p95 under 500 ms, ingestion p95 under 1 second, dashboard p95 under 2 seconds, zero reconciliation drift. Alert on regression and investigate database round trips/region placement before adding caching that could weaken policy correctness.

RC-1 adds missing foreign-key indexes and optimizes two legacy RLS policies. Unused-index notices are not removal candidates without production observation history.
