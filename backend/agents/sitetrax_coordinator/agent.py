"""ADK agent entry point for `adk web` and `adk deploy`.

Exposes `root_agent` — the variable the ADK CLI discovers when you run:
    adk web agents/sitetrax_coordinator
    adk deploy agent_engine agents/sitetrax_coordinator --project=... --region=...

For local dev, this imports `app.agent` from the parent `backend/` directory.
For Agent Engine deploy, the `scripts/sync_coordinator.sh` script copies `app/`
into this directory before running `adk deploy`.
"""

import sys
import os

_agent_dir = os.path.dirname(os.path.abspath(__file__))

# Local dev: add the parent directory (backend/) so `import app.agent` resolves
# to backend/app/agent.py instead of needing a duplicate copy here.
_backend_dir = os.path.dirname(_agent_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# If running inside Agent Engine (deployed), the parent dir may not exist,
# so fall back to importing from a local copy if present.
try:
    from app.agent import create_builder_agent  # noqa: E402
except ImportError:
    # Agent Engine deploy: app/ was copied here by sync_coordinator.sh
    if _agent_dir not in sys.path:
        sys.path.insert(0, _agent_dir)
    from app.agent import create_builder_agent  # noqa: E402

root_agent = create_builder_agent()
