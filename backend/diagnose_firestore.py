#!/usr/bin/env python3
"""Standalone diagnostic script for Firestore sessions."""
import os
import asyncio
import datetime

from dotenv import load_dotenv
load_dotenv(override=True)

from google.cloud import firestore


def main():
    db = firestore.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT") or None)
    sessions_col = db.collection("chat_sessions")
    docs = sessions_col.stream()

    sessions = []
    for doc in docs:
        data = doc.to_dict()
        events = list(doc.reference.collection("events").stream())
        sessions.append({
            "id": doc.id,
            "app_name": data.get("app_name"),
            "user_id": data.get("user_id"),
            "title": data.get("state", {}).get("title", ""),
            "last_update_time": data.get("last_update_time"),
            "event_count": len(events),
            "state_keys": list(data.get("state", {}).keys()),
        })

    print(f"Total sessions in Firestore: {len(sessions)}")
    for s in sessions:
        ts = s["last_update_time"]
        dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat() if ts else "N/A"
        print(f"  {s['id'][:8]} | app={s['app_name']} user={s['user_id']} | events={s['event_count']} | updated={dt} | title={s['title']}")

    # Check for sessions with events that might fail validation
    invalid_events = 0
    for doc in sessions_col.stream():
        for ev in doc.reference.collection("events").stream():
            ev_data = ev.to_dict()
            if not ev_data.get("author"):
                invalid_events += 1
                print(f"    WARNING: event {ev.id} in session {doc.id} has no author")

    if invalid_events:
        print(f"\nFound {invalid_events} potentially invalid events (missing author)")
    else:
        print("\nNo obviously invalid events found (all have author field)")


if __name__ == "__main__":
    main()
