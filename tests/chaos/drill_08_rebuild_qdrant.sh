#!/usr/bin/env bash
# Drill 08 — rebuild Qdrant from the log. The collection is dropped (named: curl -X DELETE through a
# port-forward), the embedder is scaled to 0, its consumer group is rewound to the earliest offset, and
# the embedder is scaled back: every DocumentUploaded in the log is re-embedded. Claim: the point count
# per document matches what the catalog says, and the time to rebuild is the number the README quotes.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
KEY=$(key)
kubectl -n qdrant port-forward svc/qdrant 16333:6333 >/dev/null 2>&1 & PF=$!; sleep 2
BEFORE=$(curl -s http://localhost:16333/collections/documents | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["points_count"])')
stamp "points before: $BEFORE · catalog rows indexed/summarized: $(aws dynamodb scan --table-name $TABLE --filter-expression '#s IN (:a, :b)' --expression-attribute-names '{"#s":"status"}' --expression-attribute-values '{":a":{"S":"indexed"},":b":{"S":"summarized"}}' --select COUNT --query Count --output text)"
stamp "dropping the collection (named)"; curl -s -X DELETE http://localhost:16333/collections/documents | cut -c1-80; kill $PF 2>/dev/null
kubectl -n $NS scale deploy embedder --replicas=0 >/dev/null; until [ -z "$(kubectl -n $NS get pods -l app.kubernetes.io/name=embedder --no-headers 2>/dev/null)" ]; do sleep 3; done; stamp "embedder at 0"
kubectl -n kafka exec steakllm-combined-0 -- sh -c '/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group steakllm-embedder --topic documents --reset-offsets --to-earliest --execute 2>/dev/null' | awk 'NR>1 {print "  "$0}' | cut -c1-120
T1=$(date +%s); kubectl -n $NS scale deploy embedder --replicas=1 >/dev/null; stamp "embedder back at 1; re-embedding from offset 0 (Argo's selfHeal would restore the replica count too)"
n=0; until [ "$(kubectl -n kafka exec steakllm-combined-0 -- sh -c '/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group steakllm-embedder --describe 2>/dev/null' | awk 'NR>1 && $2=="documents" {s+=$6} END {print s+0}')" = "0" ] || [ $n -ge 600 ]; do sleep 10; n=$((n+10)); done
stamp "lag 0 after $(( $(date +%s) - T1 )) s"
kubectl -n qdrant port-forward svc/qdrant 16333:6333 >/dev/null 2>&1 & PF=$!; sleep 2
AFTER=$(curl -s http://localhost:16333/collections/documents | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"]["points_count"])'); kill $PF 2>/dev/null
stamp "points after: $AFTER (before: $BEFORE)"
echo "pass when the rebuilt collection holds points for every non-deleted document (counts equal unless documents were deleted meanwhile)."
