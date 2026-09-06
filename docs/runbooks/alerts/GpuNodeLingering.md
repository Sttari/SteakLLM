# GpuNodeLingering

**Symptom:** A GPU node has existed for an hour while vLLM's replicas are zero.

**Look at:**
- `kubectl get nodeclaims`, Karpenter's log for disruption decisions; anything else scheduled on the node (`kubectl get pods -A --field-selector spec.nodeName=…`)?

**Do:** `make gpu-down` removes it now; the reaper would at 03:00 anyway

**Escalate:** if the fix is not in this page, write the incident in docs/field-notes.md §3 and add what you learned here.
