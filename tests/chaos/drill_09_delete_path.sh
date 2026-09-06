#!/usr/bin/env bash
# Drill 09 — the delete path. Upload a memo, wait for `summarized`, then DELETE /v1/documents/{doc_id}
# through the gateway: S3 delete → EventBridge Object Deleted → the Lambda → DocumentDeleted → the embedder
# removes the points, the catalog row is gone, a docs question no longer cites it; a second DELETE is a no-op.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
KEY=$(key)
D=$(upload del1); stamp "memo ${D:0:8} uploaded"
wait_status "$D" summarized 300 && stamp "summarized; points=$(points "$D")"
stamp "DELETE /v1/documents/${D:0:8} through the gateway"
curl -s -o /dev/null -w '  first delete: HTTP %{http_code}\n' -X DELETE "$GW/v1/documents/$D" -H "authorization: Bearer $KEY"
n=0; until [ "$(status "$D")" = "-" ] || [ $n -ge 120 ]; do sleep 5; n=$((n+5)); done
stamp "catalog row after $n s: $(status "$D") (- means gone)"
n=0; until [ "$(points "$D")" = "0" ] || [ $n -ge 120 ]; do sleep 5; n=$((n+5)); done
stamp "points after $n s: $(points "$D")"
curl -s -o /dev/null -w '  second delete: HTTP %{http_code}\n' -X DELETE "$GW/v1/documents/$D" -H "authorization: Bearer $KEY"
stamp "events: $(events "$D")"
stamp "docs question mentions the memo? $(curl -s --max-time 60 "$GW/v1/chat/completions" -H "authorization: Bearer $KEY" -H 'content-type: application/json' -d '{"model":"docs","messages":[{"role":"user","content":"Where is the hub for del1?"}],"max_tokens":60}' | python3 -c 'import sys,json; d=json.load(sys.stdin); print(("drill-del1" in json.dumps(d).lower()) and "yes (fail)" or "no (pass): " + (d.get("choices") or [{}])[0].get("message",{}).get("content","")[:90])')"
echo "pass when the row is gone, points are 0, exactly one DocumentDeleted was produced, and the second delete is a no-op (404 or 204)."
