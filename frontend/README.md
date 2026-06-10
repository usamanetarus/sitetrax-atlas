# SiteTrax.io Atlas Agent — Frontend

Chat UI for the SiteTrax.io Atlas Agent. **React + Vite + Tailwind CSS.**

## Prerequisites

- **Node.js 18+** and npm
- The **backend running on port 8000** — the dev server proxies `/api` →
  `http://localhost:8000` (see `vite.config.js`)

## Setup

```bash
cd frontend
npm install
```

## Run (development)

```bash
npm run dev
```

Opens on **http://localhost:5173**. Requests to `/api/*` are proxied to the
backend at `http://localhost:8000` (the `/api` prefix is stripped), so **start
the backend first**.

## Build (production)

```bash
npm run build      # outputs static files to dist/
npm run preview    # serve the production build locally
```

## How it works

- `src/App.jsx` — the chat UI. Sends messages to `POST /api/chat`, renders the
  agent's reply plus result cards (**rule created**, **alert fired**,
  **opportunity logged**), and a demo bar to simulate detection events.
- `src/main.jsx` / `index.html` — app entry point.
- Styling via Tailwind (`tailwind.config.js`, `postcss.config.js`,
  `src/index.css`).
- Dev proxy in `vite.config.js` (`/api` → backend, strips the `/api` prefix).

## Configuration

| File | Purpose |
|---|---|
| `vite.config.js` | Dev server (port 5173) + `/api` proxy to the backend |
| `tailwind.config.js` | Tailwind content paths + theme |
| `postcss.config.js` | PostCSS (Tailwind + autoprefixer) |

> **Single deployed URL:** build the frontend and serve `dist/` from the backend
> (e.g. FastAPI `StaticFiles`) so one service hosts both the UI and the API.
