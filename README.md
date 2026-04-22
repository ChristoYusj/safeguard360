# SafeGuard 360

SafeGuard 360 is a local-first industrial safety system for Windows. The
backend, database, face recognition, PPE detection, and Fleet driver
monitoring all run on the host machine. The only network dependency is the
optional chatbot provider.

## Modules

- `Attendance / Smart Gate`: face recognition, PPE checking, operator review,
  check-in and check-out logging, and live gate status over WebSocket.
- `Fleet Monitoring`: MediaPipe-based driver monitoring for fatigue,
  distraction, and seatbelt checks.
- `Enrollment / Roster`: worker enrollment from photos or short video, roster
  import, and shift assignment.
- `Alerts / Logs`: event history and site-wide live alerts.
- `Safety Chatbot`: optional Groq-first assistant with OpenAI fallback.

## Current Runtime Model

- One shared camera manager owns capture and exposes frames to the active
  module.
- Gate recognition uses InsightFace for identity and YOLO PPE detection for
  helmet/vest checks.
- Fleet monitoring uses an in-process MediaPipe runtime wrapped by the driver
  runtime client.
- A single `/ws/events` stream carries live status, gate events, driver events,
  and preview frames.

More detail is in [docs/architecture.md](docs/architecture.md) and
[docs/attendance-gate.md](docs/attendance-gate.md).

## Repo Layout

```text
safeguard360/
|- backend/                  FastAPI app, DB models, inference, tests
|- frontend/                 Vite + React dashboard
|- data/                     Shared SQLite DB and model weights
|- docs/                     Architecture and operations docs
|- .env.example              Environment template
|- reset_admin_password.py   Admin recovery helper
`- roster-demo.csv           Sample import file
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- Windows host with webcam access
- Local model files in `data/models/`

## Setup

1. Create the root environment file.

```powershell
Copy-Item .env.example .env
```

2. Fill in the required auth and email settings in `.env`.
   The backend will refuse to start if required auth values are missing.
3. Add model weights under `data/models/`.

### Required model/data locations

- SQLite DB: `data/safeguard360.db` by default
- PPE model: `data/models/<your-model>.pt`
- InsightFace weights: `data/models/models/buffalo_l/`
- Runtime attendance snapshots: `backend/data/attendance/`
- Runtime enrollment media: `backend/data/faces/`

`MODELS_DIR` and `DATABASE_URL` are resolved from the repo root, so launching
from either the root or `backend/` is supported.

## Running Locally

### Backend

```powershell
cd backend
pip install -r requirements.txt
python main.py
```

Backend default origin: `http://127.0.0.1:8000`

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend default origin: `http://127.0.0.1:5173`

## Operator Guide

### Attendance / Gate

1. Start the camera feed from the Attendance page.
2. Enable recognition mode to run live face matching.
3. Use `Check-In` when workers are arriving.
4. The UI switches to `Check-Out` automatically when all registered workers
   for the selected shift are on site.
5. If nobody is on site, the UI switches back to `Check-In`.

### PPE states

- `Compliant`: required PPE was detected for the matched worker.
- `Flagged`: helmet and/or vest were not confirmed for the matched worker.
- `Review queue`: operator approval is required before entry is logged when the
  review band or PPE enforcement path is triggered.
- Resolved PPE findings stay attached to the worker card in the Workforce
  Roster. The PPE Command Center is reserved for live scan status and mode
  switching.

### Duplicate and checkout behavior

- If a worker already checked in appears again during `Check-In`, the live feed
  reports `already checked in`.
- Approved checkout writes a real exit attendance record and appears in the
  roster as `Check-Out`.

### Fleet Monitoring

- Select the Fleet camera source and enable MediaPipe from the dashboard.
- The rebuilt Fleet runtime initializes MediaPipe once and runs detection
  inside the dedicated driver runtime path, not in a separate subprocess.
- Driver status and events are pushed over the same live WebSocket channel.

## Environment Notes

Important variables from `.env.example`:

- `DATABASE_URL`
- `MODELS_DIR`
- `PPE_MODEL`
- `FACE_MODEL`
- `FPS_LIMIT`
- `GROQ_API_KEY` / `OPENAI_API_KEY`
- `JWT_ACCESS_SECRET`, `JWT_REFRESH_SECRET`, `JWT_APPROVAL_SECRET`
- `ADMIN_EMAIL`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `TOTP_ENCRYPTION_KEY`
- `VITE_API_BASE_URL`, `VITE_WS_BASE_URL`

## Useful Commands

```powershell
# Backend tests
cd backend
python -m pytest

# Frontend build
cd frontend
npm run build

# Frontend unit tests
cd frontend
npm test
```

## Notes

- `reset_admin_password.py` is the retained admin recovery utility.
- `roster-demo.csv` is a sample roster import file for local testing.
- Runtime outputs, local env files, logs, and build artifacts are git-ignored.
