"""Rewrite tests/golden/v1.json from the live schemas.

Run ONLY for an intentional, additive change, in its own reviewed commit:
    uv run python tests/golden/regenerate.py
If test_compat fails and you reach for this script, stop: you are about to erase a breaking change.
"""

import json
import pathlib

from steakllm_contracts.compat import fingerprints

out = pathlib.Path(__file__).with_name("v1.json")
out.write_text(json.dumps(fingerprints(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {out} ({len(fingerprints())} schemas)")
