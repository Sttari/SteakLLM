# CpuNodeRequestsSaturated

**Symptom:** CPU requests on the CPU node exceed 95% of allocatable: new pods cannot schedule (Incident 45b).

**Look at:**
- `kubectl describe node` → Allocated resources; who grew?

**Do:** trim requests in the offending chart or move to the next node size (11.7 decision)

**Escalate:** if the fix is not in this page, write the incident in docs/field-notes.md §3 and add what you learned here.
