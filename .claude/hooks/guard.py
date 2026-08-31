#!/usr/bin/env python3
"""PreToolUse guard for Bash commands.

Belt-and-braces behind the permission deny list in .claude/settings.json: refuses the
irreversible or secret-leaking commands the CLAUDE.md safety rails name, whatever the
conversation says. Exit 2 blocks the command and feeds the message back to Claude;
exit 0 lets the normal permission flow decide.
"""

import json
import re
import sys

BLOCKED = [
    (
        r"\bterraform\s+destroy\b",
        "terraform destroy is only run by Thomas, by hand, after an explicit go-ahead.",
    ),
    (
        r"\bterraform\s+apply\b.*-destroy",
        "destroying via apply is the same as terraform destroy; human only.",
    ),
    (
        r"\bterraform\s+state\s+(rm|mv|push)\b",
        "state surgery is human-only; propose the command and stop.",
    ),
    (
        r"\brm\s+-[a-zA-Z]*[rR][a-zA-Z]*\s",
        "recursive rm is human-only; list what would be deleted instead.",
    ),
    (r"\bsudo\s+rm\b", "sudo rm is human-only."),
    (
        r"\bkubectl\s+delete\b",
        "kubectl delete is human-only except during a drill Thomas has named as such.",
    ),
    (
        r"\bhelm\s+uninstall\b",
        "helm uninstall is human-only; Argo CD owns the cluster.",
    ),
    (r"\bargocd\s+app\s+delete\b", "deleting an Argo application is human-only."),
    (
        r"\baws\s+\S+\s+(delete|terminate|remove)-",
        "destructive AWS calls are human-only; state what would be lost and stop.",
    ),
    (r"\baws\s+s3\s+(rb|rm)\b", "deleting S3 objects or buckets is human-only."),
    (r"\bgh\s+repo\s+delete\b", "deleting the repository is human-only."),
    (
        r"\bgh\s+secret\s+set\b",
        "no AWS secrets in GitHub: CI uses OIDC roles and repository variables (ADR-0001).",
    ),
    (r"\bgit\s+push\b.*(--force|-f\b)", "force-push is disallowed; open a PR instead."),
    (r"\bgit\s+reset\s+--hard\b", "hard reset discards work; ask Thomas first."),
    (r"\.aws/credentials|\bgh\s+auth\s+token\b", "never print credentials."),
    (
        r"\b(cat|less|more|head|tail|bat)\b.*\s\S*(\.env(\.\w+)?(?<!\.example)(\s|$)|terraform\.tfvars(\s|$))",
        "never print .env or terraform.tfvars; refer to .env.example / *.example.tfvars.",
    ),
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:  # json.JSONDecodeError is a ValueError; anything else is a real bug and should surface
        return 0
    command = (payload.get("tool_input") or {}).get("command", "") or ""
    for pattern, reason in BLOCKED:
        if re.search(pattern, command):
            print(
                f"BLOCKED by .claude/hooks/guard.py: {reason}\nCommand was: {command}",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
