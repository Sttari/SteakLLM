# VllmNotReadyWhileSummoned

**Symptom:** KEDA wants vLLM but no replica has become ready in 12 minutes.

**Look at:**
- `kubectl get nodeclaims` (capacity? Incident 41), the vLLM pod's events and logs (image pull, weights copy, CUDA)
- Karpenter's log for `InsufficientInstanceCapacity`

**Do:** if capacity: wait or widen the NodePool menu; if the pod is broken: Bedrock is answering meanwhile — fix the chart and let Argo roll it

**Escalate:** if the fix is not in this page, write the incident in docs/field-notes.md §3 and add what you learned here.
