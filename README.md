# SafeGuard 360

Local-first industrial safety monitoring system for Windows. Runs entirely on
the host machine — no external inference services required.

## Features

- **Smart Gate + Attendance** — Face recognition (ArcFace via InsightFace)
  combined with PPE compliance (YOLOv8) at the entry gate. Off-shift arrivals
  and low-quality frames are flagged for operator review.
- **Driver Monitoring** — Fatigue, distraction, and seatbelt checks from a
  live webcam feed.
- **Roster Management** — Enrollment flow (photos / short video) plus bulk
  CSV roster import with per-worker shift assignment.
- **Site-Wide Alerts** — Red-flash + audio toast notifications pushed over a
  single WebSocket subscription, visible on any page.
- **AI Safety Chatbot** — Groq-hosted Llama 3.3 70B (free tier) with an
  OpenAI fallback for operators who prefer that provider.

## Tech Stack

| Layer     | Technology                              |
| --------- | --------------------------------------- |
| Frontend  | React 18 + Vite + Tailwind + framer-motion |
| Backend   | FastAPI (Python 3.10+)                  |
| Database  | SQLite + SQLAlchemy                     |
| AI Models | YOLOv8, ArcFace (buffalo\_l), MediaPipe |
| Realtime  | WebSocket (`/ws/events`)                |
| LLM       | Groq (default) / OpenAI (fallback)      |

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Webcam (or a test video file)

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` to set your API keys (at minimum `GROQ_API_KEY` if you want the
chatbot). The key environment variables:

| Variable            | Purpose                                                    |
| ------------------- | ---------------------------------------------------------- |
| `DATABASE_URL`      | SQLite path (default: `sqlite:///./data/safeguard360.db`)  |
| `MODELS_DIR`        | Where PPE + ArcFace weights live (default: `./data/models`)|
| `PPE_MODEL`         | Filename of the YOLOv8 PPE weights in `MODELS_DIR`         |
| `FACE_MODEL`        | InsightFace pack name (default: `buffalo_l`)               |
| `GROQ_API_KEY`      | Groq API key for the safety chatbot                        |
| `GROQ_MODEL`        | Groq model id (default: `llama-3.3-70b-versatile`)         |
| `OPENAI_API_KEY`    | Fallback LLM provider                                      |
| `CAMERA_SOURCE`     | `webcam` or file path                                      |
| `FPS_LIMIT`         | Capture framerate cap                                      |

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
```

The backend reads the repo-root `.env`. Runtime data (DB, snapshots,
enrollment photos) is written under `backend/data/`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies API + WebSocket calls to the backend on
`http://127.0.0.1:8000`.

## Project Layout

```
safeguard360/
├── backend/             FastAPI app, DB models, inference pipelines
│   ├── app/
│   │   ├── api/         HTTP endpoints (auth, camera, persons, chatbot, …)
│   │   ├── camera/      Capture + gate/driver orchestration
│   │   ├── config/      Pydantic settings loader
│   │   ├── db/          SQLAlchemy models + session factory
│   │   ├── inference/   Face, PPE, and driver-event detectors
│   │   └── services/    Gate compliance, attendance, chatbot
│   ├── data/            Runtime snapshots, face thumbnails (git-ignored)
│   └── tests/           Pytest suite
├── frontend/            Vite + React dashboard
│   └── src/
│       ├── components/  Layout, shared UI, alert banner
│       ├── contexts/    Auth, alert feed, i18n
│       ├── pages/       Portal, Attendance, Dashboard, Enrollment, …
│       └── services/    API + WebSocket client
├── data/                Shared model weights + master SQLite DB
│   └── models/          PPE `.pt` file + `models/buffalo_l/` ArcFace pack
├── docs/                Architecture + feature notes
├── .env / .env.example  Shared config (backend + frontend read both)
└── reset_admin_password.py   Admin recovery helper
```

## Modes

1. **Gate Mode** — Face + PPE verification for site entry.
2. **Driver Mode** — Fatigue + distraction monitoring for a vehicle cam.
3. **Idle Mode** — Camera released, no inference running.

## License

MIT
