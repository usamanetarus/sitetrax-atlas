# SiteTrax Atlas Agent

**An autonomous AI agent for container-yard logistics**, built for **Track 1 (Build) of the
Google for Startups AI Agents Challenge**.

Ask it questions in plain English — *"when was container TCLU1234567 last seen?"*,
*"which facility was busiest this week?"* — and it answers from live SiteTrax.io
computer-vision asset data. Ask it to watch for something — *"alert me if anything dwells
at Newark over 48 hours"* — and it creates a **monitoring rule** that runs autonomously,
firing in-app and email alerts when the condition is met. No human in the loop.

**Built with:** Google ADK · Gemini 2.5 Flash (Vertex AI) · MCP · Cloud Run · Firestore ·
Cloud Scheduler · FastAPI · React

---

## Repository layout

| Folder | What it is | Docs |
|---|---|---|
| [`backend/`](backend/) | FastAPI service wrapping the ADK agent, MCP servers, rule evaluator, deploy scripts | [backend/README.md](backend/README.md) — architecture diagram, configuration, API reference, deployment |
| [`frontend/`](frontend/) | React + Vite + Tailwind chat UI with result cards and a demo bar | [frontend/README.md](frontend/README.md) |

---

## Why this fits Track 1

- **Net-new ADK agent** — built from scratch on the Agent Development Kit: function tools,
  session state, cross-session memory, artifacts, and callbacks, with Gemini 2.5 Flash on
  Vertex AI (ADC auth, no API keys anywhere).
- **MCP for secure tool access** — the agent reaches SiteTrax data *only* through an MCP
  server; a second MCP server (HTTP + OAuth) exposes the same tools to external clients
  like claude.ai and ChatGPT. Credentials live with the MCP servers, never with the model.
- **Acts, doesn't just respond** — conversational requests become standing monitoring
  rules, evaluated every 10 minutes by Cloud Scheduler with deduped alert dispatch.
- **Production-shaped** — stateless Cloud Run services, Firestore persistence, one-command
  deploy, evals + unit tests, deterministic guardrails for unsupported requests.

The full architecture diagram and design write-up are in [backend/README.md](backend/README.md).

---

## Run it in 5 minutes

Works out of the box on bundled **mock data** — no SiteTrax account needed. You need
Python 3.11+, Node 18+, and a GCP project with the Vertex AI API enabled.

```bash
# Terminal 1 — backend (http://localhost:8000)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
gcloud auth application-default login
cp .env.example .env        # set GOOGLE_CLOUD_PROJECT to your project ID
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (http://localhost:5173)
cd frontend
npm install
npm run dev
```

Then open **http://localhost:5173** and ask the agent something — or try the demo bar to
simulate a detection event and watch a rule fire.

Deployment to Google Cloud (Cloud Run + Scheduler + Firestore) is one script:
see [backend/README.md → Deploying](backend/README.md#deploying-to-google-cloud).

---

## License

[MIT](LICENSE)
