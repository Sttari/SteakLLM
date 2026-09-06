# Drill 10 — restore the catalog from point-in-time recovery (Step 10.7)

**Claim:** A row is corrupted on purpose (named), the table is restored to a minute before into `steakllm-catalog-restored`, the rows are compared, the live row is repaired from the copy; a human removes the restored table afterwards.

**Script:** `tests/chaos/drill_10_restore_catalog.sh` (helpers in `tests/chaos/lib.sh`).

**Result (Sep 6 2026):** PASS — a row corrupted on purpose (named), restore-table-to-point-in-time to a minute before into steakllm-catalog-restored: ACTIVE after 210 s, the restored row read `summarized` where the live one read `corrupted`, 16 rows on both sides, the live row repaired from the copy. The restored table stays until a human removes it.
