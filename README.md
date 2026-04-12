# SafeGuard 360

Local-first industrial safety monitoring system for Windows.

## Features

- **Smart Gate + Attendance** — Face recognition + PPE compliance check
- **PPE Detection** — Helmet, vest detection via YOLO11
- **Driver Monitoring** — Fatigue, distraction, seatbelt detection
- **Web Dashboard** — Real-time status, alerts, event logs

## Current Build Notes

- Replace UI-only placeholder attendance profiles with a real test database of 2-3 workers for face-recognition attendance checks.
- Add a real PPE recognition/reference database so compliance decisions come from stored records instead of mocked frontend data.
- Keep manual override logging in scope so forced gate releases record worker, time, camera, and trigger details.

## Tech Stack

| Layer     | Technology                 |
| --------- | -------------------------- |
| Frontend  | React + Vite + Tailwind    |
| Backend   | FastAPI (Python)           |
| Database  | SQLite + SQLAlchemy        |
| AI Models | YOLO11, ArcFace, MediaPipe |
| Realtime  | WebSocket                  |

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Webcam (or test video file)

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
python main.py
```

The backend host, port, and database path come from the repo-root `.env`.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server uses the repo-root `.env` for backend HTTP and WebSocket targets.

## Project Structure

```
safeguard360/
├── backend/          # FastAPI backend
├── frontend/         # React dashboard
├── data/             # Runtime data (models, faces, snapshots)
├── scripts/          # Utility scripts
├── docs/             # Documentation
└── tests/            # Integration tests
```

## Modes

1. **Gate Mode** — Face + PPE verification for entry
2. **Driver Mode** — Fatigue + distraction monitoring
3. **Idle Mode** — System paused

## Configuration

Copy the repo-root `.env.example` to `.env` and adjust settings:

```
DEBUG=true
CAMERA_SOURCE=webcam
```

## License

MIT
