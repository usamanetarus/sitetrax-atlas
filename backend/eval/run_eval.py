#!/usr/bin/env python3
"""Simple evaluation runner for SiteTrax agent routing quality.

This intentionally measures tool routing, not full answer quality. Each case is
bounded so slow live SiteTrax endpoints or model calls cannot hang CI/local runs.
"""
from __future__ import annotations
import asyncio, json, os, sys
import contextlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(Path(__file__).parent.parent)
from dotenv import load_dotenv
load_dotenv(override=True)
# Routing eval is about model/tool selection. Use in-process ADK stores so it
# never blocks on Firestore startup probes or writes eval sessions to production.
os.environ["USE_FIRESTORE"] = "false"
from google.adk import Runner
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService
from google.genai import types
from app.agent import create_builder_agent

CASE_TIMEOUT_SECONDS = float(os.getenv("ROUTING_EVAL_CASE_TIMEOUT", "35"))
USER_ID = os.getenv("ROUTING_EVAL_USER_ID", "eval_user")


def create_eval_runner() -> Runner:
    """Use isolated in-memory ADK services so routing eval does not depend on Firestore."""
    return Runner(
        app_name="sitetrax_coordinator",
        agent=create_builder_agent(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
        artifact_service=InMemoryArtifactService(),
        auto_create_session=True,
    )

async def evaluate_case(case, runner):
    query = case["query"]
    expected = set(case["expected_tools"])
    session_id = "eval-" + str(hash(query) & 0xFFFFFFFF)
    user_content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
    invoked = set()
    error = None

    async def collect_tools():
        async for event in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=user_content):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call:
                        invoked.add(part.function_call.name)

    timed_out = False
    try:
        await asyncio.wait_for(collect_tools(), timeout=CASE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        timed_out = True
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    with contextlib.suppress(Exception):
        await runner.session_service.delete_session(
            app_name="sitetrax_coordinator",
            user_id=USER_ID,
            session_id=session_id,
        )

    matched = expected & invoked
    missed = expected - invoked
    extra = invoked - expected
    return {
        "query": query,
        "expected": list(expected),
        "invoked": list(invoked),
        "matched": list(matched),
        "missed": list(missed),
        "extra": list(extra),
        "timeout": timed_out,
        "error": error,
        "pass": len(missed) == 0 and error is None,
        "completed": not timed_out and error is None,
        "score": len(matched) / len(expected) if expected else 1.0,
    }

async def main():
    eval_path = Path(__file__).parent / "routing_eval.json"
    with open(eval_path) as f:
        cases = json.load(f)
    runner = create_eval_runner()
    print("Evaluating", len(cases), "routing cases with", CASE_TIMEOUT_SECONDS, "s timeout...\n", flush=True)
    results = []
    for case in cases:
        print("→", case["query"], flush=True)
        result = await evaluate_case(case, runner)
        results.append(result)
        status = "ERROR" if result["error"] else ("FAIL" if not result["pass"] else ("PASS_TIMEOUT" if result["timeout"] else "PASS"))
        print("[" + status + "]", result["query"])
        print("      Invoked:", result["invoked"])
        if result["error"]:
            print("      Error: ", result["error"])
        if result["missed"]:
            print("      Missed:", result["missed"])
        if result["extra"]:
            print("      Extra: ", result["extra"])
        print(flush=True)
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    avg_score = sum(r["score"] for r in results) / total if total else 0.0
    timeouts = sum(1 for r in results if r["timeout"])
    errors = sum(1 for r in results if r["error"])
    completed = sum(1 for r in results if r["completed"])
    print("\n" + "=" * 50, flush=True)
    print("Results:", passed, "/", total, "passed (", round(passed/total*100, 1), "%)", flush=True)
    print("Timeouts:", timeouts, flush=True)
    print("Errors:", errors, flush=True)
    print("Completed:", completed, "/", total, flush=True)
    print("Average score:", round(avg_score, 2), flush=True)
    print("=" * 50, flush=True)
    out_path = Path(__file__).parent / "routing_eval_results.json"
    with open(out_path, "w") as f:
        json.dump({"cases": results, "summary": {"total": total, "passed": passed, "avg_score": avg_score}}, f, indent=2)
    print("\nResults saved to", out_path)

if __name__ == "__main__":
    asyncio.run(main())
