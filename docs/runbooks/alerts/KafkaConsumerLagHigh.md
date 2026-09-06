# KafkaConsumerLagHigh

**Symptom:** A consumer group is falling behind.

**Look at:**
- which group (the label); its pod's log; is it crash-looping (`kubectl get pods`)?
- the broker: `kubectl -n kafka get kafka steakllm`; disk on the PVC

**Do:** restart the consumer; if the lag is a replay you started (drill 08), wait

**Escalate:** if the fix is not in this page, write the incident in docs/field-notes.md §3 and add what you learned here.
