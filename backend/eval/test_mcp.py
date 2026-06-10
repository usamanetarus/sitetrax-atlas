"""End-to-end test for the SiteTrax MCP server.

Starts the server as a real subprocess (same as ADK McpToolset does in production),
calls every tool, and verifies the response structure and data contract.

Run from the backend/ directory:
    python eval/test_mcp.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Make sure app.* imports resolve when run from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PYTHON = sys.executable
SERVER = str(Path(__file__).resolve().parents[1] / "app" / "mcp_server.py")
TIMEOUT = 20


def _ok(label: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{status}] {label}{suffix}")
    return passed


async def run_tests():
    print(f"\nStarting MCP server: {PYTHON} {SERVER}")
    params = StdioServerParameters(command=PYTHON, args=[SERVER])

    passed = failed = 0

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ── 1. list_tools ─────────────────────────────────────────────────
            print("\n── list_tools ──")
            result = await session.list_tools()
            names = {t.name for t in result.tools}
            expected = {
                "sitetrax_search_assets",
                "sitetrax_latest_scan",
                "sitetrax_asset_timeline",
                "sitetrax_facility_last_scan",
                "sitetrax_facility_metrics",
                "sitetrax_reference_lookup",
            }
            for name in sorted(expected):
                ok = _ok(f"tool present: {name}", name in names)
                passed += ok; failed += not ok

            # ── 2. sitetrax_reference_lookup ──────────────────────────────────
            print("\n── sitetrax_reference_lookup ──")
            r = await session.call_tool("sitetrax_reference_lookup", {"query": "status codes", "limit": 2})
            text = r.content[0].text if r.content else ""
            data = json.loads(text)
            ok = _ok("returns JSON with 'matches' list", isinstance(data.get("matches"), list))
            passed += ok; failed += not ok
            ok = _ok("query echoed back", data.get("query") == "status codes")
            passed += ok; failed += not ok
            ok = _ok("at least 1 match", len(data.get("matches", [])) >= 1)
            passed += ok; failed += not ok
            if data.get("matches"):
                m = data["matches"][0]
                ok = _ok("match has 'title'", "title" in m)
                passed += ok; failed += not ok
                ok = _ok("match has 'facts' list", isinstance(m.get("facts"), list))
                passed += ok; failed += not ok

            # ── 3. sitetrax_search_assets ─────────────────────────────────────
            print("\n── sitetrax_search_assets ──")
            r = await session.call_tool("sitetrax_search_assets", {"hours_back": 24})
            data = json.loads(r.content[0].text)
            if "error" in data:
                ok = _ok("search_assets (no auth — error is acceptable)", data.get("error") in ("auth_error", "query_failed"), data.get("detail", ""))
                passed += ok; failed += not ok
            else:
                ok = _ok("returns 'count' int", isinstance(data.get("count"), int))
                passed += ok; failed += not ok
                ok = _ok("returns 'assets' list", isinstance(data.get("assets"), list))
                passed += ok; failed += not ok
                ok = _ok("assets capped at 50", len(data.get("assets", [])) <= 50)
                passed += ok; failed += not ok

            # ── 4. sitetrax_latest_scan ───────────────────────────────────────
            print("\n── sitetrax_latest_scan ──")
            r = await session.call_tool("sitetrax_latest_scan", {"container_id": "TRDU1930583"})
            data = json.loads(r.content[0].text)
            if "error" in data:
                ok = _ok("latest_scan (no auth — error is acceptable)", data.get("error") in ("auth_error", "query_failed"), data.get("detail", ""))
                passed += ok; failed += not ok
            else:
                # Either a record or {"found": False}
                ok = _ok("returns dict (record or not-found)", isinstance(data, dict))
                passed += ok; failed += not ok

            # ── 5. sitetrax_asset_timeline ────────────────────────────────────
            print("\n── sitetrax_asset_timeline ──")
            r = await session.call_tool("sitetrax_asset_timeline", {"container_id": "TRDU1930583", "limit": 5})
            data = json.loads(r.content[0].text)
            if "error" in data:
                ok = _ok("asset_timeline (no auth — error is acceptable)", data.get("error") in ("auth_error", "query_failed"), data.get("detail", ""))
                passed += ok; failed += not ok
            else:
                ok = _ok("has 'container_id'", "container_id" in data)
                passed += ok; failed += not ok
                ok = _ok("has 'timeline' list", isinstance(data.get("timeline"), list))
                passed += ok; failed += not ok
                ok = _ok("timeline capped at limit=5", len(data.get("timeline", [])) <= 5)
                passed += ok; failed += not ok

            # ── 6. sitetrax_facility_last_scan ────────────────────────────────
            print("\n── sitetrax_facility_last_scan ──")
            r = await session.call_tool("sitetrax_facility_last_scan", {"facility": "Utah Intermodal Ramp"})
            data = json.loads(r.content[0].text)
            if "error" in data:
                ok = _ok("facility_last_scan (no auth — error is acceptable)", data.get("error") in ("auth_error", "query_failed"), data.get("detail", ""))
                passed += ok; failed += not ok
            else:
                ok = _ok("returns dict", isinstance(data, dict))
                passed += ok; failed += not ok

            # ── 7. sitetrax_facility_metrics ──────────────────────────────────
            print("\n── sitetrax_facility_metrics ──")
            r = await session.call_tool("sitetrax_facility_metrics", {"facility": "", "date_from": "", "date_to": ""})
            data = json.loads(r.content[0].text)
            if isinstance(data, dict) and "error" in data:
                ok = _ok("facility_metrics (no auth — error is acceptable)", data.get("error") in ("auth_error", "query_failed"), data.get("detail", ""))
                passed += ok; failed += not ok
            else:
                ok = _ok("returns list", isinstance(data, list))
                passed += ok; failed += not ok

    print(f"\n{'─'*40}")
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(asyncio.wait_for(run_tests(), timeout=TIMEOUT * 2))
    sys.exit(0 if success else 1)
