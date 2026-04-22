# SafeGuard 360

SafeGuard 360 is a local-first industrial safety monitoring platform built for
an on-site Windows machine. It combines:

- gate attendance with face recognition
- PPE compliance scanning
- fleet driver monitoring
- operator review workflows
- live alerts and logs
- a safety assistant backed by Groq

This is not just a website. The browser dashboard is only one part of the
system. The product depends on a local runtime that owns the camera, runs the
vision models, stores the local database, and pushes live state to the UI.

## What The Product Does

### Attendance / Smart Gate

- recognizes enrolled workers at the gate
- checks helmet and vest compliance
- supports `Check-In` and `Check-Out`
- auto-switches gate direction based on who is currently on site
- creates operator reviews when confidence or PPE rules require approval
- stores attendance snapshots and audit state locally

### Fleet Monitoring

- runs MediaPipe-based live driver analysis
- monitors fatigue, distraction, and seatbelt-related signals
- overlays live driver status on the preview
- emits driver events over the realtime event channel

### Enrollment / Roster

- stores worker profiles and face embeddings
- supports photo and short-video enrollment
- supports shift assignment and roster import

### Operator Dashboard

- shows live gate/fleet feed
- displays review queue and workforce roster
- shows PPE state, attendance outcomes, and event history
- consumes a single backend websocket stream for frames and events

### Safety Assistant

- uses Groq only
- receives a live site snapshot each turn
- answers operational questions about attendance, PPE, alerts, and driver
  events

## System Shape

SafeGuard 360 has two major runtime sides.

### Hosted / Web UI Pieces

These are normal web-application pieces:

- `frontend/`
  React + Vite dashboard
- browser pages for:
  - Attendance
  - Dashboard / Fleet
  - Enrollment
  - Logs
  - Settings
  - AI Chatbot
- HTTP API calls to the backend
- websocket subscription for live frames and events

These pieces render operator state, controls, and history. They do not perform
the computer-vision inference themselves.

### Local Edge Runtime Pieces

These are the parts that make the product an on-site system:

- `backend/`
  FastAPI server and orchestration layer
- local camera ownership via the shared camera manager
- local inference:
  - InsightFace / ArcFace for face recognition
  - YOLO PPE model for helmet/vest checks
  - MediaPipe for Fleet Monitoring
- local SQLite database
- local attendance snapshots and enrollment media
- local model files under `data/models/`

This side is the core of the product. Without it, the UI would only be a shell.

## Core Runtime Responsibilities

### Shared Camera Manager

The backend uses one shared camera manager to:

- open the active source
- publish the latest raw frame
- run preview rendering without blocking capture
- feed gate recognition and driver monitoring workers
- prevent competing modules from fighting over the camera

### Gate Runtime

The gate runtime is responsible for:

- face quality checks
- enrolled-worker matching
- PPE evaluation
- review creation
- attendance logging
- entry/exit logic
- live gate overlay state

### Fleet Runtime

The Fleet runtime is responsible for:

- MediaPipe initialization
- face/landmark tracking
- fatigue and distraction state
- live overlay state
- driver event emission

## Realtime Data Flow

The backend emits:

- live JPEG preview frames
- camera status payloads
- gate state
- driver state
- gate events
- driver events

All of that is pushed through the websocket layer so the dashboard stays in
sync with the local runtime.

## Required Models, Data, And Hardware

### Hardware

- Windows machine
- webcam or compatible local camera source
- enough CPU/GPU headroom for local inference

### Required model files

- PPE model:
  `data/models/<your-ppe-model>.pt`
- InsightFace weights:
  `data/models/models/buffalo_l/`

Current local configuration points the PPE detector at:

- [data/models/ppe-hansung.pt](/C:/Users/chris/Documents/New%20project/safeguard360/data/models/ppe-hansung.pt)

### Local data stores

- SQLite database:
  `data/safeguard360.db`
- attendance snapshots:
  `backend/data/attendance/`
- enrollment face media:
  `backend/data/faces/`

These are intentionally local/runtime-oriented and are not treated as normal
source-controlled app assets.

## Repository Layout

```text
safeguard360/
|- backend/                  FastAPI app, inference, camera runtime, tests
|- frontend/                 React operator dashboard
|- data/                     SQLite DB and local model weights
|- docs/                     product, architecture, and operations docs
|- .env.example              environment template
|- reset_admin_password.py   admin recovery utility
`- roster-demo.csv           sample roster import file
```

## Documentation Map

- [docs/architecture.md](docs/architecture.md)
  System boundaries, ownership, deployment shape, and runtime responsibilities
- [docs/system-flow.md](docs/system-flow.md)
  End-to-end gate, fleet, websocket, and data flows
- [docs/attendance-gate.md](docs/attendance-gate.md)
  Attendance and PPE behavior from the operator workflow side

## Local Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Windows host with camera access
- local model files in `data/models/`

### Environment

Create the root `.env` from the template:

```powershell
Copy-Item .env.example .env
```

Important variables:

- `DATABASE_URL`
- `MODELS_DIR`
- `PPE_MODEL`
- `FACE_MODEL`
- `FPS_LIMIT`
- `GROQ_API_KEY`
- `JWT_ACCESS_SECRET`
- `JWT_REFRESH_SECRET`
- `JWT_APPROVAL_SECRET`
- `ADMIN_EMAIL`
- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL`
- `TOTP_ENCRYPTION_KEY`

### Run backend

```powershell
cd backend
pip install -r requirements.txt
python main.py
```

Backend default origin:

- `http://127.0.0.1:8000`

### Run frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend default origin:

- `http://127.0.0.1:5173`

## Operator Notes

### Attendance / Gate

1. Start the camera feed.
2. Enable recognition mode.
3. Use `Check-In` while workers are arriving.
4. When everyone registered for the selected shift is on site, the UI switches
   to `Check-Out`.
5. When nobody is on site, it switches back to `Check-In`.

### PPE handling

- `Compliant` means required items were confirmed.
- `Flagged` means PPE issues were recorded.
- unresolved gate reviews stay in the review queue
- resolved PPE findings move into the worker roster view

### Fleet Monitoring

- Fleet uses the local MediaPipe runtime
- detection and overlay are driven by the backend runtime, not the browser
- driver events flow through the same websocket event channel as the rest of
  the platform

## Useful Commands

```powershell
# Backend tests
cd backend
python -m pytest

# Frontend build
cd frontend
npm run build

# Frontend tests
cd frontend
npm test
```

## Notes

- `reset_admin_password.py` is kept as the admin recovery tool
- `roster-demo.csv` is the sample roster import file
- runtime outputs, caches, logs, models, and local env files are intentionally
  excluded from source control
