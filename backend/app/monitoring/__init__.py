"""Monitoring package — rules + opportunities store.

Selects the store implementation from the `USE_FIRESTORE` flag, mirroring the
`USE_REAL_API` switch in `app/data`. In-memory is the default (fast, zero-dependency);
Firestore is opt-in for durable, Cloud Run-safe persistence. When Firestore is
enabled, startup fails if Firestore is unavailable instead of silently using
non-durable local state.
"""

import os
import logging

from .rule_store import RuleStore, Rule, Opportunity  # noqa: F401

logger = logging.getLogger("sitetrax")

if os.environ.get("K_SERVICE") and "USE_FIRESTORE" not in os.environ:
    os.environ["USE_FIRESTORE"] = "true"

if os.environ.get("USE_FIRESTORE", "false").lower() == "true":
    try:
        from .firestore_store import FirestoreRuleStore
        store = FirestoreRuleStore()
    except Exception as e:
        raise RuntimeError(
            "USE_FIRESTORE=true but FirestoreRuleStore could not initialize. "
            "Fix Firestore/API/IAM configuration instead of falling back to non-durable memory. "
            f"Cause: {e}"
        ) from e
else:
    store = RuleStore()
