# shellcheck shell=bash
# Shared helpers for the Step 10 drills (05–10). Source me: `. tests/chaos/lib.sh`.
# The gateway key is read from Secrets Manager into a variable and never printed.
NS=steakllm
GW=${GW:-http://gateway:8000}
BUCKET=steakllm-documents-066591056087
TABLE=steakllm-catalog
T0=$(date +%s)
stamp() { printf '%5ds  %s\n' "$(( $(date +%s) - T0 ))" "$*" >&2; }
key() { aws secretsmanager get-secret-value --secret-id steakllm/gateway --query SecretString --output text | python3 -c 'import sys,json; print(json.load(sys.stdin)["api_key"])'; }
# upload <label>: presigned PUT of a small unique Markdown memo through the gateway; prints the doc_id
upload() {
  local body="# Drill memo $1\n\nThe hub for $1 is in Lyon; the steak is medium-rare. $(date -u +%FT%TZ)\n"
  printf "$body" > "/tmp/steakllm-drill-$1.md"
  local size; size=$(wc -c < "/tmp/steakllm-drill-$1.md" | tr -d ' ')
  local up; up=$(curl -s --max-time 20 "$GW/v1/uploads" -H "authorization: Bearer $KEY" -H 'content-type: application/json' -d "{\"filename\":\"drill-$1.md\",\"content_type\":\"text/markdown\",\"size_bytes\":$size}")
  python3 - "$up" "/tmp/steakllm-drill-$1.md" <<'PY'
import sys, json, subprocess
up = json.loads(sys.argv[1]); path = sys.argv[2]
hdrs = sum([["-H", f"{k}: {v}"] for k, v in up.get("headers", {}).items()], [])
subprocess.run(["curl", "-s", "-o", "/dev/null", "-X", up.get("method", "PUT"), up["url"], "--data-binary", f"@{path}", *hdrs], check=True)
PY
  shasum -a 256 "/tmp/steakllm-drill-$1.md" | awk '{print $1}'
}
# status <doc_id>: the catalog row's status (or "-")
status() { aws dynamodb get-item --table-name $TABLE --key "{\"doc_id\":{\"S\":\"$1\"}}" --query 'Item.status.S' --output text 2>/dev/null | sed 's/^None$/-/'; }
# wait_status <doc_id> <status> <seconds>
wait_status() { local n=0; until [ "$(status "$1")" = "$2" ] || [ $n -ge "$3" ]; do sleep 5; n=$((n+5)); done; [ "$(status "$1")" = "$2" ]; }
# points <doc_id>: Qdrant points carrying this doc_id (through a port-forward)
points() {
  kubectl -n qdrant port-forward svc/qdrant 16333:6333 >/dev/null 2>&1 & local pf=$!; sleep 2
  curl -s --max-time 10 -X POST http://localhost:16333/collections/documents/points/count -H 'content-type: application/json' -d "{\"filter\":{\"must\":[{\"key\":\"doc_id\",\"match\":{\"value\":\"$1\"}}]},\"exact\":true}" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("result",{}).get("count","?"))'
  kill $pf 2>/dev/null
}
# events <doc_id>: count of each event type for this doc on `documents` (console consumer, from earliest)
events() {
  kubectl -n kafka exec steakllm-combined-0 -- sh -c 'timeout 25 /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic documents --from-beginning --timeout-ms 20000 2>/dev/null' | python3 -c '
import sys, json, collections
doc = sys.argv[1]; c = collections.Counter()
for line in sys.stdin:
    try: d = json.loads(line)
    except Exception: continue
    if d.get("doc_id") == doc: c[d.get("type")] += 1
print(dict(c) or "{}")' "$1"
}
