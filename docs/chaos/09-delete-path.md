# Drill 09 — the delete path (Step 10.7)

**Claim:** DELETE /v1/documents/{doc_id} through the gateway: S3 delete → EventBridge Object Deleted → the Lambda → DocumentDeleted → the embedder removes the points; the catalog row is gone; a docs question no longer cites it; a second DELETE is a no-op.

**Script:** `tests/chaos/drill_09_delete_path.sh` (helpers in `tests/chaos/lib.sh`).

**Result (Sep 6 2026):** PASS — upload → summarized in 15 s with 1 point; DELETE through the gateway 204; the catalog row gone at once, the points 0 within 6 s; the second DELETE 404; the log holds exactly one DocumentUploaded, DocumentIndexed, SummaryReady and DocumentDeleted; the docs model answers that no excerpt mentions the memo (the file name appears in no citation).
