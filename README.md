# SafeGuard 360

Local-first industrial safety monitoring system for Windows.

## Features

- **Smart Gate + Attendance** — Face recognition + PPE compliance check
- **PPE Detection** — Helmet, vest detection via YOLO11
- **Driver Monitoring** — Fatigue, distraction, seatbelt detection
- **Web Dashboard** — Real-time status, alerts, event logs

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

Server runs at: ENV_BACKEND_HTTP_ORIGIN

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Dashboard at: http://localhost:5173

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

Copy `.env.example` to `.env` and adjust settings:

```
DEBUG=true
CAMERA_SOURCE=webcam
```

## License

MIT
