# SteakLLMUploadToIndexedSLOBurn

**Symptom:** The embedder's group lag stays above zero: uploads are not becoming searchable.

**Look at:**
- `kubectl -n steakllm logs deploy/embedder --tail=50`: retries, Qdrant or Ollama errors
- Qdrant and Ollama pods Ready? their rooms' NetworkPolicies unchanged?
- consumer group state: `kafka-consumer-groups.sh --describe --group steakllm-embedder` in the broker

**Do:** restart the embedder (rollout restart) if it is wedged; if Qdrant lost its collection, drill 08 rebuilds it from the log

**Escalate:** if the fix is not in this page, write the incident in docs/field-notes.md §3 and add what you learned here.
