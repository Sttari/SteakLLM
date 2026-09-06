# SteakLLMTargetDown

**Symptom:** A scrape target of ours is down.

**Look at:**
- `kubectl get pods -n <namespace>`; the ServiceMonitor's selector vs the Service's labels; NetworkPolicy from monitoring

**Do:** fix the pod or the policy; if the target was removed on purpose, remove its ServiceMonitor

**Escalate:** if the fix is not in this page, write the incident in docs/field-notes.md §3 and add what you learned here.
