# Drill 11 — Prometheus dies mid-scrape (Step 11.8)

**Claim:** Its process is killed; the PVC keeps the data; targets, rules, the KEDA trigger and the dashboards come back whole.

**Script:** `tests/chaos/drill_11_prometheus_kill.sh`.

**Result (Sep 6 2026):** Prometheus asked to quit via `POST /-/quit` (its image has no shell), Ready again in 5 s (one restart), the same 24 targets, data from 30 min earlier still queryable (19 series), the ScaledObject Ready throughout.
