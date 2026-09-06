# Drill 12 — Alertmanager dies during a firing alert (Step 11.8)

**Claim:** After the restart the firing alert is still shown and no duplicate notification leaves within the repeat interval.

**Script:** `tests/chaos/drill_12_alertmanager_kill.sh`.

**Result (Sep 6 2026):** Alertmanager removed through its operator resource (replicas 0 → 1, with root's and the monitoring app's self-heal paused), the pod gone in 5 s and back in 10 s, the same alerts shown after, one SNS publish in the window (a resolved notice for `CpuNodeRequestsSaturated`), no duplicate page; an earlier attempt without the self-heal pause never removed the pod.
