"""Conditional data source — switches between real API and mock data."""

import os

if os.environ.get("USE_REAL_API", "false").lower() == "true":
    from .sitetrax_client import query_assets, get_latest_scan, get_asset_timeline  # noqa: F401
    DATA_SOURCE = "real_api"
else:
    from .mock_data import query_assets, get_latest_scan, get_asset_timeline  # noqa: F401
    DATA_SOURCE = "mock"
