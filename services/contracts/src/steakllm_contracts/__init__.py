"""SteakLLM event contracts.

The envelope and the five event schemas live in ``schemas/`` as JSON Schema (draft 2020-12);
one valid example per event lives in ``examples/``. Both ship inside the package so any service
that installs it can validate against the same files.
"""

from importlib.resources import files

__version__ = "1.0.0"

SCHEMA_DIR = files(__package__) / "schemas"
EXAMPLE_DIR = files(__package__) / "examples"

EVENT_TYPES = (
    "DocumentUploaded",
    "DocumentIndexed",
    "SummaryReady",
    "DocumentDeleted",
    "ChatCompleted",
)
