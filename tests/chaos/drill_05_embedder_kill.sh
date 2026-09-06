#!/usr/bin/env bash
# Drill 05 — the embedder dies mid-batch (Step 6's drill 01, on the cluster). Three uploads, then the
# embedder's process is killed while it works (kubectl exec … kill 1: the container restarts, the
# consumer group rebalances, the partition is re-read from the last commit). Claim: every document
# reaches `indexed` exactly once — one DocumentIndexed each, one set of points each.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
KEY=$(key)
stamp "uploading three memos"
D1=$(upload k1); D2=$(upload k2); D3=$(upload k3)
stamp "doc_ids ${D1:0:8} ${D2:0:8} ${D3:0:8}"
until [ "$(status "$D1")" != "-" ]; do sleep 2; done
stamp "first row exists → killing the embedder's process now (named: kubectl exec … kill 1)"
POD=$(kubectl -n $NS get pods -l app.kubernetes.io/name=embedder --no-headers | awk '{print $1}' | head -n 1)
kubectl -n $NS exec "$POD" -- sh -c "kill 1" && stamp "killed pid 1 in $POD (sh builtin kill: the slim image has no /bin/kill)"
wait_past_indexed() { local n=0; until [ "$(status "$1")" = "indexed" ] || [ "$(status "$1")" = "summarized" ] || [ $n -ge 240 ]; do sleep 3; n=$((n+3)); done; stamp "${1:0:8} $(status "$1") after $n s"; }
for d in $D1 $D2 $D3; do wait_past_indexed "$d"; done
stamp "embedder pod: $(kubectl -n $NS get pods -l app.kubernetes.io/name=embedder --no-headers | awk '{print $1, $3, "restarts="$4}')"
for d in $D1 $D2 $D3; do stamp "${d:0:8}: status=$(status "$d") points=$(points "$d") events=$(events "$d")"; done
echo "pass when every doc has exactly one DocumentUploaded, one DocumentIndexed, one SummaryReady and points > 0 (no doubles)."
