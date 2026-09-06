#!/usr/bin/env bash
# Drill 10 — restore the catalog from point-in-time recovery. A row is corrupted on purpose (named), the
# table is restored to a minute before into steakllm-catalog-restored, the rows are compared, the live row
# is repaired from the copy, and a human removes the restored table afterwards (removing tables is
# human-only here). Deletion protection is not touched: PITR restores into a new table.
set -euo pipefail
. "$(dirname "$0")/lib.sh"
DOC=$(aws dynamodb scan --table-name $TABLE --limit 1 --query 'Items[0].doc_id.S' --output text | head -n 1)
if [ -z "$DOC" ] || [ "$DOC" = "None" ]; then echo "no rows to corrupt; run a drill that uploads first"; exit 1; fi
GOOD=$(aws dynamodb get-item --table-name $TABLE --key "{\"doc_id\":{\"S\":\"$DOC\"}}" --query 'Item.status.S' --output text)
sleep 65; T=$(date -u -v-60S +%FT%TZ 2>/dev/null || date -u -d '60 seconds ago' +%FT%TZ)
stamp "corrupting ${DOC:0:8} (status $GOOD → corrupted) — named"
aws dynamodb update-item --table-name $TABLE --key "{\"doc_id\":{\"S\":\"$DOC\"}}" --update-expression 'SET #s = :c' --expression-attribute-names '{"#s":"status"}' --expression-attribute-values '{":c":{"S":"corrupted"}}'
stamp "restoring to $T into $TABLE-restored"
aws dynamodb restore-table-to-point-in-time --source-table-name $TABLE --target-table-name $TABLE-restored --restore-date-time "$T" --query 'TableDescription.TableStatus' --output text
n=0; until [ "$(aws dynamodb describe-table --table-name $TABLE-restored --query Table.TableStatus --output text)" = "ACTIVE" ] || [ $n -ge 1800 ]; do sleep 30; n=$((n+30)); done
stamp "restored table ACTIVE after $n s"
stamp "restored row status: $(aws dynamodb get-item --table-name $TABLE-restored --key "{\"doc_id\":{\"S\":\"$DOC\"}}" --query 'Item.status.S' --output text) (live: $(status "$DOC"))"
stamp "row counts live/restored: $(aws dynamodb scan --table-name $TABLE --select COUNT --query Count --output text)/$(aws dynamodb scan --table-name $TABLE-restored --select COUNT --query Count --output text)"
stamp "repairing the live row from the restored copy"
aws dynamodb update-item --table-name $TABLE --key "{\"doc_id\":{\"S\":\"$DOC\"}}" --update-expression 'SET #s = :g' --expression-attribute-names '{"#s":"status"}' --expression-attribute-values "{\":g\":{\"S\":\"$GOOD\"}}"
echo "pass when the restored row shows the pre-corruption status. Then a human removes the copy (the restored table is the only thing lost): see docs/chaos/10-restore.md"
